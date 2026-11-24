"""The FastAPI app: pattern catalog, conversation threads and streamed runs (spec §3).

How a conversation flows:

1. ``POST /api/patterns/{id}/threads`` makes a thread owned by the caller's
   session. A chat pattern is *primed* straight away: its graph runs until it
   pauses at ``ask`` (``interrupt()``), so the first message is a resume.
2. ``POST /api/threads/{tid}/runs`` feeds one message in and streams the
   runner's trace events back as Server-Sent Events (``data: <json>\\n\\n``).
3. ``GET /api/threads/{tid}/state`` returns the checkpointed state (and how
   many checkpoints the thread has), so a page reload can rebuild the console.

Graphs are compiled once per pattern at startup and share one checkpointer;
each thread id is its own checkpoint thread.

The catalog menu (Catalog spec §5.2) is read-only: ``GET /api/catalog`` lists
all 21 patterns, and ``GET /api/catalog/{category}/{pattern}`` returns one
page. Both are computed once at startup, so opening a page never runs a graph
or makes a thread.
"""
import asyncio
import hashlib
import json
import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import Literal
from uuid import uuid4

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.sessions import SessionMiddleware

from agentic_solutions.agents.approval_agent.erp import ErpClient, HttpErpClient, InProcessErpClient
from agentic_solutions.common import approval_tokens
from agentic_solutions.mcp_servers.erp.config import ErpSettings
from agentic_solutions.mcp_servers.erp.server import build_server
from agentic_solutions.mcp_servers.erp.store import ErpStore
from agentic_solutions.web import catalog
from agentic_solutions.web.config import Settings
from agentic_solutions.web.registry import AGENTS_DIR, PATTERNS, BuildContext, PatternSpec, offline_factory
from agentic_solutions.web.runner import run_events
from agentic_solutions.web.serialize import to_jsonable
from agentic_solutions.web.threads import ThreadRecord, ThreadStore, once
from agentic_solutions.web.topology import graph_topology

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MODE = "offline"  # M1 has no Live mode yet
NOT_FOUND = "not found"  # same text for unknown and unowned, so ownership isn't leaked
NO_ERP_SECRET = "ERP_APPROVAL_SECRET must be set when ERP_MCP_URL is set"
NO_CLIENT_SECRET = "ERP_APPROVAL_SECRET must be set when an ERP client is passed in"
# The 409 rules for the two kinds of pause (Approval spec §5.3, §9.1).
FINISH_APPROVAL = "Finish the pending approval first"
NOTHING_WAITING = "Nothing is waiting for approval"
UNKNOWN_EDIT = "Unknown item in edits"
EDIT_NEEDS_EDITS = "Send changed quantities to edit the order"
APPROVAL_NODE = "approval"


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=999)


class ResumeRequest(BaseModel):
    """A decision on the pending approval card."""
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "edit", "reject"]
    edits: list[Edit] | None = Field(None, max_length=20)
    reason: str | None = Field(None, max_length=500)


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


async def _open_erp(settings: Settings, stack: AsyncExitStack, app: FastAPI,
                    erp: ErpClient | None) -> tuple[ErpClient, bytes]:
    """The approval demo's ERP client and approval secret (plan ruling 3).

    With no URL, the ERP server runs in-process over MCP's in-memory transport,
    on its own SQLite store, for the app's lifetime; the secret is random per
    start unless one is set. With a URL, the server is another process, so the
    two must share ERP_APPROVAL_SECRET and startup fails without it.
    """
    secret = settings.erp_approval_secret.encode("utf-8") if settings.erp_approval_secret else None
    if erp is not None:  # a caller-supplied client (tests); create_app checked the secret
        return erp, secret
    if settings.erp_mcp_url:
        if secret is None:
            raise RuntimeError(NO_ERP_SECRET)
        return HttpErpClient(settings.erp_mcp_url), secret
    secret = secret or secrets.token_bytes(32)
    erp_settings = ErpSettings(db=settings.erp_db, secret=secret,
                               auto_limit_zar=settings.erp_auto_approve_limit_zar,
                               tenant_ttl_hours=settings.erp_tenant_ttl_hours)
    store = ErpStore(erp_settings.db, secret=secret, auto_limit_zar=erp_settings.auto_limit_zar,
                     tenant_ttl_hours=erp_settings.tenant_ttl_hours)
    stack.callback(store.close)  # runs after the client below has closed (LIFO)
    app.state.erp_store = store
    client = await stack.enter_async_context(InProcessErpClient(build_server(store, erp_settings)))
    return client, secret


def _approver(session_id: str) -> str:
    """The visitor's approver identity: a short hash, so the session id never reaches the ERP."""
    return "visitor:" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


def _config(thread_id: str, session_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "approver": _approver(session_id)}}


def _paused(state) -> tuple[str, object] | None:
    """The paused node and its interrupt value: the first task with interrupts."""
    for task in state.tasks:
        if task.interrupts:
            return task.name, task.interrupts[0].value
    return None


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


def _skeleton_topology(folder: str) -> dict:
    """Compile a Guide-only folder's skeleton (no checkpointer) and flatten it."""
    try:
        build_skeleton = import_module(f"agentic_solutions.agents.{folder}.graph").build_skeleton
        return graph_topology(build_skeleton())
    except Exception as exc:  # fail startup loudly: never serve a half-built catalog
        raise RuntimeError(f"could not build the skeleton graph for {folder!r}") from exc


def _catalog_pages(registry: dict[str, PatternSpec], topologies: dict[str, dict]) -> dict[str, dict]:
    """Page data for every catalog route (Catalog spec §5.2), keyed by route.

    A cross-list (Tool Use) takes its content from its target (ReAct) but keeps
    its own route, category and neighbours, so the breadcrumb and arrows follow
    the category it was reached from.
    """
    pages = {}
    for category in catalog.CATALOG:
        for p in category.patterns:
            t = catalog.target(p)
            status = catalog.status(p, registry)
            demo = t.demo if status == "live" else None
            prev, next_ = catalog.neighbours(p.route)
            pages[p.route] = {
                "route": p.route, "target": t.route,
                "category": {"id": category.id, "name": category.name},
                "name": t.name, "status": status,
                "demo": demo, "demo_title": registry[demo].title if demo else None,
                "explanation_md": (AGENTS_DIR / t.folder / "explanation.md").read_text(encoding="utf-8"),
                "topology": topologies[demo] if demo else _skeleton_topology(t.folder),
                "prev": prev, "next": next_,
            }
    return pages


def _catalog_listing(registry: dict[str, PatternSpec]) -> dict:
    return {"categories": [
        {"id": k.id, "name": k.name, "question": k.question, "patterns": [
            {"id": p.id, "name": p.name, "hint": p.hint, "aliases": list(p.aliases),
             "status": catalog.status(p, registry), "route": p.route,
             "target": catalog.target(p).route}
            for p in k.patterns]}
        for k in catalog.CATALOG]}


def create_app(settings: Settings | None = None, *, checkpointer=None, guard=None,
               registry: dict[str, PatternSpec] | None = None, erp: ErpClient | None = None) -> FastAPI:
    """Build the app. ``registry`` (default ``PATTERNS``) is the set of runnable
    demos; tests pass a larger one to see a catalog entry turn live. ``erp``
    (default: from settings, see ``_open_erp``) is the approval demo's ERP client."""
    settings = settings or Settings.from_env()
    if erp is not None and not settings.erp_approval_secret:
        # A random secret here would sign tokens the caller's ERP can never verify.
        raise RuntimeError(NO_CLIENT_SECRET)
    registry = PATTERNS if registry is None else registry
    store = ThreadStore()

    class RunRequest(BaseModel):
        """Exactly one of a message (``text``) or a decision on the approval card (``resume``)."""
        text: str | None = Field(None, min_length=1, max_length=settings.max_input_chars)
        resume: ResumeRequest | None = None

        @model_validator(mode="after")
        def _exactly_one(self):
            if (self.text is None) == (self.resume is None):
                raise ValueError("send exactly one of text or resume")
            return self

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Sync graph nodes run in the loop's default executor: make it large (spec §9a).
        executor = ThreadPoolExecutor(max_workers=settings.worker_threads)
        asyncio.get_running_loop().set_default_executor(executor)
        async with AsyncExitStack() as stack:  # unwinds in reverse, on a failed start too
            stack.callback(executor.shutdown, wait=False)
            saver = checkpointer
            if saver is None:
                saver, conn = await _open_sqlite_saver(settings.checkpoint_db)
                stack.push_async_callback(conn.close)
            erp_client, erp_secret = await _open_erp(settings, stack, app, erp)
            threat_guard = guard if guard is not None else _build_guard()
            graphs = {
                pid: spec.build(BuildContext(
                    offline_factory(pid, settings.offline_latency_scale), saver, threat_guard,
                    erp=erp_client,
                    issue_token=lambda claims: approval_tokens.issue(claims, erp_secret),
                    auto_limit_zar=settings.erp_auto_approve_limit_zar))
                for pid, spec in registry.items()
            }
            app.state.graphs = graphs
            app.state.topologies = {pid: graph_topology(g) for pid, g in graphs.items()}
            app.state.catalog_pages = _catalog_pages(registry, app.state.topologies)
            app.state.catalog_listing = _catalog_listing(registry)
            yield

    app = FastAPI(title="Agentic Patterns Studio", lifespan=lifespan)
    app.state.store = store
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
        spec = registry.get(pattern_id)
        if spec is None:
            raise HTTPException(404, NOT_FOUND)
        return spec

    @app.get("/api/patterns")
    def list_patterns():
        return [{"id": s.id, "title": s.title, "summary": s.summary, "mode": s.mode}
                for s in registry.values()]

    @app.get("/api/patterns/{pattern_id}")
    def pattern_detail(pattern_id: str, request: Request):
        spec = pattern(pattern_id)
        return {
            "id": spec.id, "title": spec.title, "summary": spec.summary, "mode": spec.mode,
            "samples": list(spec.samples),
            "explanation_md": spec.explanation_path.read_text(encoding="utf-8"),
            "topology": request.app.state.topologies[spec.id],
        }

    @app.get("/api/catalog")
    def catalog_listing(request: Request):
        return request.app.state.catalog_listing

    @app.get("/api/catalog/{category}/{pattern}")
    def catalog_page(category: str, pattern: str, request: Request):
        page = request.app.state.catalog_pages.get(f"{category}/{pattern}")
        if page is None:
            raise HTTPException(404, NOT_FOUND)
        return page

    @app.get("/api/session")
    def get_session(request: Request):
        session_id(request)
        # The UI sets its textarea's maxlength from this, so the two never drift.
        return {"mode": MODE, "live_available": False, "max_input_chars": settings.max_input_chars}

    @app.post("/api/patterns/{pattern_id}/threads")
    async def create_thread(pattern_id: str, request: Request):
        spec = pattern(pattern_id)
        record = store.create(session_id(request), spec.id, MODE)
        if spec.mode == "chat":
            # Prime: run to the first pause at `ask`, so every message is a resume.
            graph = request.app.state.graphs[spec.id]
            last = None
            async for event in run_events(graph, spec.start_input(), _config(record.id, record.session_id),
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
        spec = registry[record.pattern_id]
        chat = spec.mode == "chat"
        graph = request.app.state.graphs[spec.id]
        config = _config(record.id, record.session_id)
        decision = body.resume
        if decision is not None and decision.decision == "edit" and not decision.edits:
            raise HTTPException(422, EDIT_NEEDS_EDITS)
        if not chat:
            if decision is not None:  # a trigger never pauses
                raise HTTPException(409, NOTHING_WAITING)
            if not body.text.strip():
                raise HTTPException(422, "text must not be empty")
        else:
            # Which pause is this? Checked before claiming the run slot. Two
            # resumes racing past this check are still serialised by begin_run;
            # the loser's retry then finds the thread back at `ask`.
            paused = _paused(await graph.aget_state(config))
            at_approval = paused is not None and paused[0] == APPROVAL_NODE
            if at_approval and decision is None:
                raise HTTPException(409, FINISH_APPROVAL)
            if not at_approval and decision is not None:
                raise HTTPException(409, NOTHING_WAITING)
            if at_approval and decision.edits:
                card = paused[1] if isinstance(paused[1], dict) else {}
                skus = {line.get("sku") for line in card.get("lines") or []}
                if any(e.sku not in skus for e in decision.edits):
                    raise HTTPException(422, UNKNOWN_EDIT)
        graph_input = (spec.make_input(body.text) if decision is None
                       else Command(resume=decision.model_dump(exclude_none=True)))
        sid = record.session_id
        if not store.begin_run(sid):
            raise HTTPException(409, "a run is already in progress")

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
                graph, graph_input, config,
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
        graph = request.app.state.graphs[record.pattern_id]
        config = _config(record.id, record.session_id)
        state = await graph.aget_state(config)
        # One checkpoint per saved step (spec §4.6): the trace shows this count.
        checkpoints = 0
        async for _ in graph.aget_state_history(config):
            checkpoints += 1
        found = _paused(state)
        paused = None if found is None else {"node": found[0], "payload": to_jsonable(found[1])}
        return {"values": to_jsonable(state.values), "next": list(state.next),
                "paused": paused, "ended": record.ended, "closed": record.closed,
                "checkpoints": checkpoints}

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        if not page.is_file():
            raise HTTPException(404, NOT_FOUND)
        return FileResponse(page)

    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
    return app
