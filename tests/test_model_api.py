"""The API with a chosen model (model picker spec §4, §5; Review Focus 1, 2, 3, 5).

No test calls a provider: ``make_model`` is replaced with a fake that returns
a scripted model, or one that raises an exception named like a provider's own.
"""
import asyncio
import dataclasses
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agentic_solutions.web import registry as registry_module
from agentic_solutions.web.app import create_app, graph_for
from agentic_solutions.web.config import Settings
from agentic_solutions.web.offline.model import Script, ScriptedChatModel
from agentic_solutions.web.offline.scripts import SCRIPTS
from agentic_solutions.web.registry import PATTERNS
from conftest import TEST_ERP_SECRET
from fakes import make_guard

SENTINEL = "sk-secret"
LOOPBACK = {"base_url": "http://127.0.0.1:8000", "client": ("127.0.0.1", 50000)}
LIVE_REPLY = "Live reply from the fake model."
LIVE_SCRIPT = Script(rules=(), fallback=LIVE_REPLY)
DENIED = {"detail": "model choice is not available"}
UNKNOWN = {"detail": "unknown model"}
OFFLINE_ONLY = [{"id": "offline", "label": "Offline (scripted)"}]
ALL_MODELS = OFFLINE_ONLY + [{"id": "claude-haiku", "label": "Claude Haiku 5.5"},
                             {"id": "deepseek", "label": "DeepSeek (via OpenRouter)"}]
LAPTOPS = "Order 12 laptops for the Cape Town office under CT-OPS"


def sse(resp):
    return [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]


def run(client, tid, body, **kw):
    with client.stream("POST", f"/api/threads/{tid}/runs", json=body, **kw) as r:
        assert r.status_code == 200, r.read()
        return sse(r)


def make_app(tmp_path, **settings):
    s = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:",
                 erp_db=str(tmp_path / "erp.sqlite"), erp_approval_secret=TEST_ERP_SECRET, **settings)
    return create_app(s, checkpointer=InMemorySaver(), guard=make_guard())


@pytest.fixture
def fake_models(monkeypatch):
    """Both credentials set (to a sentinel), and ``make_model`` returning a fake.

    Call the fixture's value with a script or a zero-argument model builder
    to change what the fake returns. ``built`` lists the entry ids built.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    monkeypatch.setenv("OPENROUTER_API_KEY", SENTINEL)
    state = {"make": lambda: ScriptedChatModel(script=LIVE_SCRIPT, latency=(0, 0), tokens_per_second=0),
             "built": []}

    def fake_make_model(entry, settings):
        state["built"].append(entry.id)
        return state["make"]()

    def use(script_or_make):
        if isinstance(script_or_make, Script):
            state["make"] = lambda: ScriptedChatModel(script=script_or_make, latency=(0, 0), tokens_per_second=0)
        else:
            state["make"] = script_or_make

    use.built = state["built"]
    monkeypatch.setattr(registry_module, "make_model", fake_make_model)
    return use


@pytest.fixture
def live(tmp_path, fake_models):
    with TestClient(make_app(tmp_path), **LOOPBACK) as c:
        yield c


def new_thread(client, pattern="chat_loop", model=None, **kw):
    body = None if model is None else {"model": model}
    return client.post(f"/api/patterns/{pattern}/threads", json=body, **kw)


# ---- /api/session --------------------------------------------------------


def test_session_lists_only_offline_without_check(tmp_path, fake_models):
    with TestClient(make_app(tmp_path)) as c:                     # client host "testclient"
        assert c.get("/api/session").json() == {"mode": "offline", "models": OFFLINE_ONLY,
                                                "max_input_chars": 2000}


def test_session_lists_models_on_loopback_with_keys(live, monkeypatch):
    assert live.get("/api/session").json() == {"mode": "offline", "models": ALL_MODELS,
                                               "max_input_chars": 2000}
    monkeypatch.delenv("OPENROUTER_API_KEY")                        # an entry without its key is not listed
    assert live.get("/api/session").json()["models"] == ALL_MODELS[:2]


# ---- creating a thread ---------------------------------------------------


def test_create_live_thread_runs_full_turn_and_state_reports_model(live, fake_models):
    r = new_thread(live, model="claude-haiku")
    assert r.status_code == 200 and r.json()["mode"] == "claude-haiku"
    tid = r.json()["thread_id"]
    ev = run(live, tid, {"text": "hello"})
    assert ev[0]["type"] == "run_started"
    assert (ev[0]["mode"], ev[0]["model"]) == ("live", "claude-haiku")
    assert "".join(e["text"] for e in ev if e["type"] == "token").strip() == LIVE_REPLY
    assert ev[-1]["status"] == "paused"
    st = live.get(f"/api/threads/{tid}/state").json()
    assert st["model"] == {"id": "claude-haiku", "label": "Claude Haiku 5.5"}
    assert [m["content"] for m in st["values"]["messages"]] == ["hello", LIVE_REPLY]
    assert set(fake_models.built) == {"claude-haiku"}              # the model came from the menu entry


def test_offline_thread_is_unchanged(live, fake_models):
    for body in (None, {"model": "offline"}):
        r = live.post("/api/patterns/chat_loop/threads", json=body)
        assert r.status_code == 200 and r.json()["mode"] == "offline"
        tid = r.json()["thread_id"]
        ev = run(live, tid, {"text": "hello"})
        assert (ev[0]["mode"], ev[0]["model"]) == ("offline", "offline")
        assert live.get(f"/api/threads/{tid}/state").json()["model"] == OFFLINE_ONLY[0]
    assert fake_models.built == []


def test_unknown_model_422(live):
    r = new_thread(live, model="gpt-nope")
    assert r.status_code == 422 and r.json() == UNKNOWN
    assert new_thread(live, model="").status_code == 422
    assert new_thread(live, model="x" * 65).status_code == 422
    assert live.post("/api/patterns/chat_loop/threads", json={"model": "offline", "x": 1}).status_code == 422


@pytest.mark.parametrize("how", ["peer", "host", "origin", "credential"])
def test_denied_model_403(tmp_path, fake_models, monkeypatch, how):       # Review Focus 1
    kw, headers, model = dict(LOOPBACK), {}, "claude-haiku"
    if how == "peer":
        kw["client"] = ("10.0.0.5", 50000)
    elif how == "host":
        kw["base_url"] = "http://rebound.example:8000"             # DNS rebinding: a foreign name on 127.0.0.1
    elif how == "origin":
        headers["Origin"] = "http://other-site.example"
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY")
        model = "deepseek"
    with TestClient(make_app(tmp_path), **kw) as c:
        r = new_thread(c, model=model, headers=headers)
        assert r.status_code == 403 and r.json() == DENIED
        assert new_thread(c, headers=headers).status_code == 200      # Offline still works
        if how != "origin":                                             # Origin is checked on POSTs only
            assert "deepseek" not in str(c.get("/api/session").json()["models"])
    assert fake_models.built == []


def test_non_loopback_bind_denies(tmp_path, fake_models):
    with TestClient(make_app(tmp_path, host="0.0.0.0"), **LOOPBACK) as c:
        assert c.get("/api/session").json()["models"] == OFFLINE_ONLY
        assert new_thread(c, model="claude-haiku").json() == DENIED


# ---- running a thread ----------------------------------------------------


def test_run_rechecks_and_does_not_close(live, fake_models):             # Review Focus 2
    tid = new_thread(live, model="claude-haiku").json()["thread_id"]
    offline_tid = new_thread(live).json()["thread_id"]
    for headers in ({"host": "rebound.example:8000"}, {"origin": "http://other-site.example"}):
        r = live.post(f"/api/threads/{tid}/runs", json={"text": "hello"}, headers=headers)
        assert r.status_code == 403 and r.json() == DENIED
        st = live.get(f"/api/threads/{tid}/state").json()
        assert st["closed"] is False and st["paused"]["node"] == "ask"
        # Offline threads are unaffected by the check.
        assert run(live, offline_tid, {"text": "hello"}, headers=headers)[-1]["status"] == "paused"
    # The slot was never taken, and the thread still runs once the check holds.
    ev = run(live, tid, {"text": "hello"})
    assert ev[-1]["status"] == "paused" and ev[0]["model"] == "claude-haiku"


def test_open_thread_keeps_model_after_menu_change(live, fake_models, monkeypatch):   # Review Focus 3
    tid = new_thread(live, model="claude-haiku").json()["thread_id"]
    monkeypatch.delenv("ANTHROPIC_API_KEY")                        # Claude leaves the menu
    assert live.get("/api/session").json()["models"] == ALL_MODELS[::2]
    ev = run(live, tid, {"text": "hello"})                          # the open thread keeps its model
    assert ev[0]["model"] == "claude-haiku" and ev[-1]["status"] == "paused"
    assert live.get(f"/api/threads/{tid}/state").json()["model"] == {"id": "claude-haiku",
                                                                    "label": "Claude Haiku 5.5"}
    # A new thread on it is refused; a new Offline thread is fine.
    assert new_thread(live, model="claude-haiku").json() == DENIED
    assert new_thread(live).json()["mode"] == "offline"


# ---- provider errors -----------------------------------------------------


def _err(module, name, base=Exception, message="provider-detail", **attrs):
    cls = type(name, (base,), {"__module__": module})
    exc = cls(message)
    for k, v in attrs.items():
        setattr(exc, k, v)
    return exc


_OPENAI_STATUS = type("APIStatusError", (Exception,), {"__module__": "openai._exceptions"})


def _wrapped(exc):
    try:
        raise exc
    except Exception as inner:
        try:
            raise RuntimeError("wrapped by the framework") from inner
        except RuntimeError as outer:
            return outer


BUSY_CLAUDE = "Claude Haiku 5.5 is busy or unavailable. Try again in a moment."
BUSY_DEEPSEEK = "DeepSeek (via OpenRouter) is busy or unavailable. Try again in a moment."


@pytest.mark.parametrize("model, exc, message", [
    ("claude-haiku", _err("anthropic", "AuthenticationError"), "The Anthropic API key was rejected."),
    ("deepseek", _err("openai", "AuthenticationError"), "The OpenRouter API key was rejected."),
    ("claude-haiku", _err("anthropic._exceptions", "RateLimitError"), BUSY_CLAUDE),
    ("deepseek", _err("openai._exceptions", "NotFoundError", _OPENAI_STATUS, status_code=404,
                      message="No allowed providers are available for the selected model."), BUSY_DEEPSEEK),
    ("deepseek", _err("openai._exceptions", "InternalServerError", _OPENAI_STATUS, status_code=503,
                      message="No provider could serve this request."), BUSY_DEEPSEEK),
    ("claude-haiku", _err("anthropic", "APIConnectionError"), "Couldn't reach Claude Haiku 5.5."),
    ("deepseek", _err("openai", "APITimeoutError"), "Couldn't reach DeepSeek (via OpenRouter)."),
    ("deepseek", _err("openai._exceptions", "BadRequestError", _OPENAI_STATUS, status_code=400), "The run failed."),
    ("claude-haiku", _err("somewhere.else", "AuthenticationError"), "The run failed."),
    ("claude-haiku", _wrapped(_err("anthropic", "AuthenticationError")), "The Anthropic API key was rejected."),
], ids=["auth-anthropic", "auth-openrouter", "rate-limit", "no-provider-404", "no-provider-503",
        "connection", "timeout", "other-status", "not-a-provider", "wrapped"])
def test_provider_errors_map_to_safe_copy(live, fake_models, caplog, model, exc, message):   # Review Focus 5
    class Raising:
        def bind_tools(self, *_a, **_k):
            return self

        def invoke(self, *_a, **_k):
            raise exc

    fake_models(Raising)
    caplog.set_level(logging.DEBUG)
    tid = new_thread(live, model=model).json()["thread_id"]
    ev = run(live, tid, {"text": "hello"})
    errors = [e for e in ev if e["type"] == "error"]
    assert errors == [{"type": "error", "message": message}]
    assert ev[-1]["status"] == "error"
    assert live.get(f"/api/threads/{tid}/state").json()["closed"] is True
    r = live.post(f"/api/threads/{tid}/runs", json={"text": "again"})
    assert r.status_code == 409
    text = json.dumps(ev)
    assert SENTINEL not in text and "provider-detail" not in text
    assert SENTINEL not in caplog.text
    assert "run failed" in caplog.text                              # the real exception is logged server-side


# ---- approval with a tool-calling live model -----------------------------


def test_approval_with_fake_tool_calling_live_model(live, fake_models):
    fake_models(SCRIPTS["approval"])                               # tool calls, like a real model's
    tid = new_thread(live, "approval", "claude-haiku").json()["thread_id"]
    ev = run(live, tid, {"text": LAPTOPS})
    assert ev[0]["model"] == "claude-haiku" and ev[-1]["status"] == "paused"
    assert {e["name"] for e in ev if e["type"] == "tool_call"} >= {"propose_order"}
    card = live.get(f"/api/threads/{tid}/state").json()["paused"]
    assert card["node"] == "approval"
    decision = {"decision": "approve", "version": card["payload"]["version"],
                "short_hash": card["payload"]["short_hash"]}
    ev = run(live, tid, {"resume": decision})
    assert ev[-1]["status"] == "paused"
    after = live.get(f"/api/threads/{tid}/state").json()
    assert after["paused"]["node"] == "ask"
    assert [e["event"] for e in after["values"]["audit"]].count("submitted") == 1
    assert "submitted" in [e["event"] for e in live.app.state.erp_store.get_audit_trail(tid, "REQ-0001")]
    assert set(fake_models.built) == {"claude-haiku"}


# ---- lazy graphs ---------------------------------------------------------


def test_live_graph_built_once_under_concurrency(tmp_path, fake_models, monkeypatch):
    calls = []

    def slow_build(ctx):
        calls.append(ctx)
        time.sleep(0.05)                                            # long enough for the second caller to arrive
        return PATTERNS["qa"].build(ctx)

    registry = {**PATTERNS, "qa": dataclasses.replace(PATTERNS["qa"], build=slow_build)}
    s = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:",
                 erp_db=str(tmp_path / "erp.sqlite"), erp_approval_secret=TEST_ERP_SECRET)
    app = create_app(s, checkpointer=InMemorySaver(), guard=make_guard(), registry=registry)
    with TestClient(app, **LOOPBACK) as c:
        assert len(calls) == 1                                      # the offline graph, at startup

        async def both():
            return await asyncio.gather(*(graph_for(app, "qa", "claude-haiku") for _ in range(5)))

        graphs = c.portal.call(both)
        assert len(calls) == 2 and all(g is graphs[0] for g in graphs)
        assert graphs[0] is not app.state.graphs[("qa", "offline")]
        # The live graph shares the startup checkpointer, guard and ERP client.
        offline_ctx, live_ctx = calls
        assert live_ctx.checkpointer is offline_ctx.checkpointer
        assert live_ctx.guard is offline_ctx.guard and live_ctx.erp is offline_ctx.erp
        assert live_ctx.issue_token is offline_ctx.issue_token
        assert c.portal.call(graph_for, app, "qa", "claude-haiku") is graphs[0]
        # The live graph's model comes from the menu entry.
        assert isinstance(live_ctx.llm_factory(), ScriptedChatModel)
        assert fake_models.built == ["claude-haiku"]
