"""The FastAPI app: pattern catalog, conversation threads and streamed runs (spec §3).

How a conversation flows:

1. ``POST /api/patterns/{id}/threads`` makes a thread owned by the caller's
   session. A chat pattern is *primed* straight away: its graph runs until it
   pauses at ``ask`` (``interrupt()``), so the first message is a resume.
2. ``POST /api/threads/{tid}/runs`` feeds one message in and streams the
   runner's trace events back as Server-Sent Events (``data: <json>\\n\\n``).
3. ``GET /api/threads/{tid}/state`` returns the checkpointed state (and how
   many checkpoints the thread has), so a page reload can rebuild the console.

A thread runs on the model it was created with (model picker spec §4): the
record's ``mode`` holds the menu id. Graphs are keyed by (pattern, model): the
offline graphs are compiled at startup, a live one on first use (``graph_for``).
All share one checkpointer, guard and ERP client; each thread id is its own
checkpoint thread. Choosing a real model, and every run on one, must pass
``may_choose_model``.

The catalog menu (Catalog spec §5.2) is read-only: ``GET /api/catalog`` lists
all 21 patterns, and ``GET /api/catalog/{category}/{pattern}`` returns one
page. Both are computed once at startup, so opening a page never runs a graph
or makes a thread.
"""
import asyncio
import hashlib
import json
import logging
import os
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
from agentic_solutions.common.llm import check_provider_available
from agentic_solutions.mcp_servers.erp.config import ErpSettings
from agentic_solutions.mcp_servers.erp.server import build_server
from agentic_solutions.mcp_servers.erp.store import ErpStore
from agentic_solutions.web import catalog
from agentic_solutions.web.config import Settings
from agentic_solutions.web.models import (
    MODEL_CHOICE_DENIED, OFFLINE, UNKNOWN_MODEL, credential_set, entry_for, listed_entries, load_entries,
    may_choose_model)
from agentic_solutions.web.registry import (
    AGENTS_DIR, PATTERNS, BuildContext, PatternSpec, live_factory, offline_factory, pattern_topology)
from agentic_solutions.web.runner import run_events
from agentic_solutions.web.serialize import to_jsonable
from agentic_solutions.web.threads import ThreadRecord, ThreadStore, once
from agentic_solutions.web.topology import graph_topology
from agentic_solutions.agents.semantic_memory_agent.library import InProcessLibraryClient, UnavailableLibrary
from agentic_solutions.mcp_servers.library.index import LibraryIndex
from agentic_solutions.mcp_servers.library.server import build_server as build_library_server

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MODE = "offline"  # the session default; a thread may run on a chosen model
PROVIDER_NAMES = {"anthropic": "Anthropic", "openrouter": "OpenRouter"}  # for the safe error copy
NOT_FOUND = "not found"  # same text for unknown and unowned, so ownership isn't leaked
NO_ERP_SECRET = "ERP_APPROVAL_SECRET must be set when ERP_MCP_URL is set"
NO_CLIENT_SECRET = "ERP_APPROVAL_SECRET must be set when an ERP client is passed in"
# The 409 rules for the two kinds of pause (Approval spec §5.3, §9.1).
FINISH_APPROVAL = "Finish the pending approval first"
NOTHING_WAITING = "Nothing is waiting for approval"
UNKNOWN_EDIT = "Unknown item in edits"
EDIT_NEEDS_EDITS = "Send changed quantities to edit the order"
EDITS_ONLY_WITH_EDIT = "Edits are only allowed with the edit decision"
DUPLICATE_EDIT = "Each item can be edited once"
OUT_OF_DATE = "This card is out of date. Showing the latest version."
APPROVAL_NODE = "approval"


class ThreadRequest(BaseModel):
    """The optional body of a new thread: which menu model it runs on."""
    model_config = ConfigDict(extra="forbid")
    model: str = Field(OFFLINE.id, min_length=1, max_length=64)


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=999)


class ResumeRequest(BaseModel):
    """A decision on the pending approval card.

    ``version`` and ``short_hash`` name the card the decision was made on, so
    a decision from a tab showing an older card is refused, never applied to
    whatever is pending now.
    """
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "edit", "reject"]
    version: int = Field(ge=1)
    short_hash: str = Field(min_length=1, max_length=64)
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


def _open_library_index(settings: Settings, stack: AsyncExitStack) -> LibraryIndex:
    """The Semantic demo's index, built first if the text, chunking or models changed.

    The first build downloads the embedding models and embeds the poem: about a minute.
    """
    from agentic_solutions.mcp_servers.library.config import LibrarySettings, open_index

    index = open_index(LibrarySettings(dir=Path(settings.library_dir)))
    stack.callback(index.close)
    return index


async def _open_library(settings: Settings, stack: AsyncExitStack, app: FastAPI):
    """The library MCP server, in-process over the in-memory transport, for the app's lifetime.

    If the library cannot open (no network for the first model download, or another
    process holding LIBRARY_DIR), the Studio still starts: the Semantic demo's tools
    say the library is unavailable, and every other demo works as before.
    """
    try:
        index = _open_library_index(settings, stack)
    except Exception:
        log.exception("The library could not open; the Semantic demo will report it as unavailable.")
        return UnavailableLibrary()
    app.state.library_index = index
    return await stack.enter_async_context(InProcessLibraryClient(build_library_server(index)))


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


async def _checked_input(spec: PatternSpec, graph, config: dict, body) -> object:
    """The graph input for this request, or HTTPException (409/422) if it does not fit the pause.

    Order: the kind of pause first (409), then whether the decision was made
    on the pending card (409), then the payload's content (422).
    """
    decision = body.resume
    if spec.mode != "chat":
        if decision is not None:  # a trigger never pauses
            raise HTTPException(409, NOTHING_WAITING)
        if not body.text.strip():
            raise HTTPException(422, "text must not be empty")
        return spec.make_input(body.text)
    paused = _paused(await graph.aget_state(config))
    at_approval = paused is not None and paused[0] == APPROVAL_NODE
    if at_approval and decision is None:
        raise HTTPException(409, FINISH_APPROVAL)
    if not at_approval and decision is not None:
        raise HTTPException(409, NOTHING_WAITING)
    if decision is None:
        return spec.make_input(body.text)
    card = paused[1] if isinstance(paused[1], dict) else {}
    if (decision.version, decision.short_hash) != (card.get("version"), card.get("short_hash")):
        raise HTTPException(409, OUT_OF_DATE)
    if decision.decision == "edit" and not decision.edits:
        raise HTTPException(422, EDIT_NEEDS_EDITS)
    if decision.decision != "edit" and decision.edits is not None:
        raise HTTPException(422, EDITS_ONLY_WITH_EDIT)
    if decision.edits:
        skus = {line.get("sku") for line in card.get("lines") or []}
        if any(e.sku not in skus for e in decision.edits):
            raise HTTPException(422, UNKNOWN_EDIT)
        if len({e.sku for e in decision.edits}) != len(decision.edits):
            raise HTTPException(422, DUPLICATE_EDIT)
    # The graph gets the decision alone: the card check is done.
    return Command(resume=decision.model_dump(exclude_none=True, exclude={"version", "short_hash"}))


def _entry(app: FastAPI, model_id: str):
    """The menu entry for a model id (Offline included), or None."""
    if model_id == OFFLINE.id:
        return OFFLINE
    return entry_for(app.state.model_entries, model_id)


def _model_kwargs(app: FastAPI, model_id: str) -> dict:
    """The run_events arguments that name the thread's model."""
    if model_id == OFFLINE.id:
        return {"mode": "offline", "model": OFFLINE.id}
    entry = _entry(app, model_id)
    return {"mode": "live", "model": model_id, "label": entry.label,
            "provider": PROVIDER_NAMES.get(entry.provider)}


async def graph_for(app: FastAPI, pattern_id: str, model_id: str):
    """The compiled graph for a (pattern, model) pair.

    Offline graphs exist from startup. A live graph is compiled on first use,
    with the startup checkpointer, guard, ERP client and token issuer, and
    cached. The lock makes concurrent first requests build it once; the
    compile runs in a worker thread so the loop stays free meanwhile.
    """
    key = (pattern_id, model_id)
    graph = app.state.graphs.get(key)
    if graph is not None:
        return graph
    async with app.state.graph_lock:
        graph = app.state.graphs.get(key)
        if graph is None:
            entry = entry_for(app.state.model_entries, model_id)
            if entry is None:
                raise KeyError(model_id)
            ctx = app.state.build_context(live_factory(entry, app.state.settings))
            graph = await asyncio.to_thread(app.state.registry[pattern_id].build, ctx)
            app.state.graphs[key] = graph
    return graph


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
    """The main page's data. `builds_on` is resolved here, so the browser needs no lookups."""
    category_names = {k.id: k.name for k in catalog.CATALOG}

    def block(route: str) -> dict:
        b = catalog.entry(route)
        return {"route": b.route, "target": catalog.target(b).route, "name": b.name,
                "category": category_names[b.category], "description": b.description,
                "aliases": list(b.aliases), "composite": b.composite}

    return {"categories": [
        {"id": k.id, "name": k.name, "description": k.description, "patterns": [
            {"id": p.id, "name": p.name, "description": p.description, "aliases": list(p.aliases),
             "status": catalog.status(p, registry), "route": p.route,
             "target": catalog.target(p).route, "composite": p.composite,
             "builds_on": [block(r) for r in p.builds_on]}
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
            library_client = await _open_library(settings, stack, app)
            threat_guard = guard if guard is not None else _build_guard()
            entries = load_entries(settings.studio_models)  # a bad STUDIO_MODELS fails startup here
            for entry in listed_entries(entries, os.environ):
                if entry is not OFFLINE:
                    check_provider_available(entry)  # a missing provider package fails startup too

            def issue_token(claims):
                return approval_tokens.issue(claims, erp_secret)

            def build_context(llm_factory) -> BuildContext:
                # Every graph, offline or live, shares these.
                return BuildContext(llm_factory, saver, threat_guard, erp=erp_client, issue_token=issue_token,
                                    auto_limit_zar=settings.erp_auto_approve_limit_zar, library=library_client)

            graphs = {
                (pid, OFFLINE.id): spec.build(build_context(offline_factory(pid, settings.offline_latency_scale)))
                for pid, spec in registry.items()
            }
            app.state.model_entries = entries
            app.state.build_context = build_context
            app.state.graph_lock = asyncio.Lock()
            app.state.graphs = graphs
            app.state.topologies = {
                pid: pattern_topology(spec, graphs[(pid, OFFLINE.id)], settings.erp_auto_approve_limit_zar)
                for pid, spec in registry.items()}
            app.state.catalog_pages = _catalog_pages(registry, app.state.topologies)
            app.state.catalog_listing = _catalog_listing(registry)
            yield

    app = FastAPI(title="Agentic Patterns Studio", lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings
    app.state.registry = registry
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

    def models_for(request: Request) -> tuple:
        """The menu this request may choose from: Offline, plus keyed models when the check holds."""
        entries = request.app.state.model_entries if may_choose_model(request, settings) else ()
        return listed_entries(entries, os.environ)

    @app.get("/api/session")
    def get_session(request: Request):
        session_id(request)
        # The UI sets its textarea's maxlength from this, so the two never drift.
        return {"mode": MODE, "models": [{"id": e.id, "label": e.label} for e in models_for(request)],
                "max_input_chars": settings.max_input_chars}

    @app.post("/api/patterns/{pattern_id}/threads")
    async def create_thread(pattern_id: str, request: Request, body: ThreadRequest | None = None):
        spec = pattern(pattern_id)
        model_id = body.model if body is not None else OFFLINE.id
        if model_id != OFFLINE.id:
            entry = entry_for(request.app.state.model_entries, model_id)
            if entry is None:
                raise HTTPException(422, UNKNOWN_MODEL)
            if not may_choose_model(request, settings) or not credential_set(entry, os.environ):
                raise HTTPException(403, MODEL_CHOICE_DENIED)
        graph = await graph_for(request.app, spec.id, model_id)
        record = store.create(session_id(request), spec.id, model_id)
        if spec.mode == "chat":
            # Prime: run to the first pause at `ask`, so every message is a resume.
            last = None
            async for event in run_events(graph, spec.start_input(), _config(record.id, record.session_id),
                                          thread_id=record.id, resumed=False,
                                          **_model_kwargs(request.app, model_id)):
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
        # Every run on a real model repeats the check, before the slot is taken:
        # a refusal leaves the thread open and the slot free.
        if record.mode != OFFLINE.id and not may_choose_model(request, settings):
            raise HTTPException(403, MODEL_CHOICE_DENIED)
        spec = registry[record.pattern_id]
        chat = spec.mode == "chat"
        graph = await graph_for(request.app, spec.id, record.mode)
        config = _config(record.id, record.session_id)
        sid = record.session_id
        # Claim the run slot first, then check which pause the thread is in.
        # The slot is per session and a thread belongs to one session, so the
        # state read below cannot go stale: a second click or tab gets 409
        # here, or (after the first run) a 409 for the pause it now finds.
        if not store.begin_run(sid):
            raise HTTPException(409, "a run is already in progress")
        try:
            graph_input = await _checked_input(spec, graph, config, body)
        except BaseException:
            # Refused (or cancelled) before any run started: free the slot, but
            # never close the thread, which is exactly as it was.
            store.end_run(sid)
            raise

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
                thread_id=record.id,
                resumed=chat,  # a chat thread was primed to a pause; a trigger starts fresh
                output=spec.output, **_model_kwargs(request.app, record.mode))
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
        graph = await graph_for(request.app, record.pattern_id, record.mode)
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
                "checkpoints": checkpoints,
                "model": {"id": record.mode, "label": _entry(request.app, record.mode).label}}

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        if not page.is_file():
            raise HTTPException(404, NOT_FOUND)
        return FileResponse(page)

    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
    return app
