"""The FastAPI app: pattern catalog, conversation threads and streamed runs (spec §3).

How a conversation flows:

1. ``POST /api/patterns/{id}/threads`` makes a thread owned by the caller's
   session. A chat pattern is *primed* straight away: its graph runs until it
   pauses at ``ask`` (``interrupt()``), so the first message is a resume.
2. ``POST /api/threads/{tid}/runs`` feeds one message in and streams the
   runner's trace events back as Server-Sent Events (``data: <json>\\n\\n``).
3. ``GET /api/threads/{tid}/state`` returns the checkpointed state, so a page
   reload can rebuild the console.

Graphs are compiled once per pattern at startup and share one checkpointer;
each thread id is its own checkpoint thread.
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from agentic_solutions.web.config import Settings
from agentic_solutions.web.registry import PATTERNS, BuildContext, offline_factory
from agentic_solutions.web.runner import run_events
from agentic_solutions.web.serialize import to_jsonable
from agentic_solutions.web.threads import ThreadRecord, ThreadStore, once
from agentic_solutions.web.topology import graph_topology

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MODE = "offline"  # M1 has no Live mode yet
NOT_FOUND = "not found"  # same text for unknown and unowned, so ownership isn't leaked


class RunRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


async def _open_sqlite_saver(path: str):
    """Open the SQLite checkpointer on one shared aiosqlite connection (spec §9a)."""
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver, conn


def _build_guard():
    """Build the real ThreatGuard once. Torch is imported only here, because it is slow."""
    import torch

    from agentic_solutions.agents.secure_chat_agent.guard import ThreatGuard

    torch.set_num_threads(2)  # concurrent guard calls must not oversubscribe the CPUs
    return ThreatGuard()


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


class _RunResponse(StreamingResponse):
    """A streaming response that cleans up deterministically when the client hangs up.

    On a disconnect Starlette abandons the ``async for`` over the body while
    the generator is parked at a ``yield``, so its ``finally`` would only run
    whenever the garbage collector finalizes it. Closing it here (shielded
    from the cancellation that is tearing the request down) runs that
    ``finally`` now. ``on_close`` covers a generator that never started:
    closing one of those skips its ``finally`` entirely.
    """

    def __init__(self, content, on_close, **kwargs):
        super().__init__(content, **kwargs)
        self._on_close = on_close

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:  # stop the run first, then release
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()
            finally:
                self._on_close()


def create_app(settings: Settings | None = None, *, checkpointer=None, guard=None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = ThreadStore()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Sync graph nodes run in the loop's default executor: make it large (spec §9a).
        executor = ThreadPoolExecutor(max_workers=settings.worker_threads)
        asyncio.get_running_loop().set_default_executor(executor)
        conn = None
        saver = checkpointer
        if saver is None:
            saver, conn = await _open_sqlite_saver(settings.checkpoint_db)
        threat_guard = guard if guard is not None else _build_guard()
        graphs = {
            pid: spec.build(BuildContext(
                offline_factory(pid, settings.offline_latency_scale), saver, threat_guard))
            for pid, spec in PATTERNS.items()
        }
        app.state.graphs = graphs
        app.state.topologies = {pid: graph_topology(g) for pid, g in graphs.items()}
        try:
            yield
        finally:
            if conn is not None:
                await conn.close()
            executor.shutdown(wait=False)

    app = FastAPI(title="Agentic Patterns Studio", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       same_site="lax", https_only=False)  # M3 turns https_only on in production

    def session_id(request: Request) -> str:
        return request.session.setdefault("sid", uuid4().hex)

    def owned_thread(request: Request, thread_id: str) -> ThreadRecord:
        try:
            return store.get(thread_id, session_id(request))
        except KeyError:
            raise HTTPException(404, NOT_FOUND) from None

    def pattern(pattern_id: str):
        spec = PATTERNS.get(pattern_id)
        if spec is None:
            raise HTTPException(404, NOT_FOUND)
        return spec

    @app.get("/api/patterns")
    def list_patterns():
        return [{"id": s.id, "title": s.title, "summary": s.summary, "mode": s.mode}
                for s in PATTERNS.values()]

    @app.get("/api/patterns/{pattern_id}")
    def pattern_detail(pattern_id: str, request: Request):
        spec = pattern(pattern_id)
        return {
            "id": spec.id, "title": spec.title, "summary": spec.summary, "mode": spec.mode,
            "samples": list(spec.samples),
            "explanation_md": spec.explanation_path.read_text(encoding="utf-8"),
            "topology": request.app.state.topologies[spec.id],
        }

    @app.get("/api/session")
    def get_session(request: Request):
        session_id(request)
        return {"mode": MODE, "live_available": False}

    @app.post("/api/patterns/{pattern_id}/threads")
    async def create_thread(pattern_id: str, request: Request):
        spec = pattern(pattern_id)
        record = store.create(session_id(request), spec.id, MODE)
        if spec.mode == "chat":
            # Prime: run to the first pause at `ask`, so every message is a resume.
            graph = request.app.state.graphs[spec.id]
            last = None
            async for event in run_events(graph, spec.start_input(), _config(record.id),
                                          thread_id=record.id, mode=MODE, resumed=False):
                last = event
            if last is None or last.get("status") != "paused":
                record.closed = True
                log.error("priming thread %s (%s) ended %r", record.id, spec.id, last)
                raise HTTPException(500, "could not start the conversation")
        return {"thread_id": record.id, "mode": record.mode, "pattern_id": record.pattern_id}

    @app.post("/api/threads/{thread_id}/runs")
    async def run_thread(thread_id: str, body: RunRequest, request: Request):  # async: begin_run stays on the loop, atomic
        record = owned_thread(request, thread_id)
        if record.ended or record.closed:
            raise HTTPException(409, "conversation ended")
        spec = PATTERNS[record.pattern_id]
        chat = spec.mode == "chat"
        if not chat and not body.text.strip():
            raise HTTPException(422, "text must not be empty")
        sid = record.session_id
        if not store.begin_run(sid):
            raise HTTPException(409, "a run is already in progress")
        graph = request.app.state.graphs[spec.id]

        finished = False

        def finish() -> None:
            # No run_finished means the stream was cut mid-run (disconnect or
            # cancellation): the checkpoint may not be paused at `ask`, so
            # resuming is unsafe. Close the thread; the UI offers New chat.
            if not finished:
                record.closed = True
            store.end_run(sid)

        finish = once(finish)  # called from the generator AND the response: must run once

        async def stream():
            nonlocal finished
            events = run_events(
                graph, spec.make_input(body.text), _config(record.id),
                thread_id=record.id, mode=record.mode,
                resumed=chat,  # a chat thread was primed to a pause; a trigger starts fresh
                output=spec.output)
            try:
                async for event in events:
                    if event["type"] == "run_finished":
                        finished = True
                        if event["status"] == "error":
                            record.closed = True
                        elif event["status"] == "completed":  # chat `stop`, or a trigger's one run
                            record.ended = True
                    yield _sse(event)
            finally:  # runs on a client disconnect too
                try:
                    await events.aclose()  # stop the graph now, not whenever GC finalizes it
                finally:
                    finish()

        return _RunResponse(stream(), on_close=finish,
                            media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/threads/{thread_id}/state")
    async def thread_state(thread_id: str, request: Request):
        record = owned_thread(request, thread_id)
        state = await request.app.state.graphs[record.pattern_id].aget_state(_config(record.id))
        paused = None
        for task in state.tasks:
            if task.interrupts:
                paused = {"node": task.name, "payload": to_jsonable(task.interrupts[0].value)}
                break
        return {"values": to_jsonable(state.values), "next": list(state.next),
                "paused": paused, "ended": record.ended, "closed": record.closed}

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        if not page.is_file():
            raise HTTPException(404, NOT_FOUND)
        return FileResponse(page)

    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
    return app
