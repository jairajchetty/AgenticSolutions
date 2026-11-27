import json

import pytest

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agentic_solutions.web import app as app_module
from agentic_solutions.web.app import create_app
from agentic_solutions.web.config import Settings
from fakes import make_guard


def sse(resp):
    return [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]


def test_catalog_and_detail(client):
    assert [p["id"] for p in client.get("/api/patterns").json()] == ["qa", "chat_loop", "guardrail", "approval"]
    d = client.get("/api/patterns/guardrail").json()
    assert d["mode"] == "chat" and "## What it is" in d["explanation_md"] and d["topology"]["nodes"]
    assert client.get("/api/patterns/nope").status_code == 404


def test_chat_thread_is_primed_paused_and_runs_stream(client):
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    assert client.get(f"/api/threads/{tid}/state").json()["paused"]["node"] == "ask"
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "What is LangGraph?"}) as r:
        ev = sse(r)
    assert ev[0]["type"] == "run_started" and ev[-1]["status"] == "paused"


def test_state_rehydrates_messages_in_order(client):          # Review Focus 1
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "hello"}) as r:
        sse(r)
    msgs = client.get(f"/api/threads/{tid}/state").json()["values"]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[0]["content"] == "hello"


def test_other_session_cannot_see_thread(client, app):
    tid = client.post("/api/patterns/qa/threads").json()["thread_id"]
    with TestClient(app) as other:                               # fresh cookie jar
        assert other.get(f"/api/threads/{tid}/state").status_code == 404


def test_unknown_thread_is_404(client):
    assert client.get("/api/threads/00000000000000000000000000000000/state").status_code == 404


def test_after_stop_chat_is_ended(client):                    # Review Focus 3
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "stop"}) as r:
        assert sse(r)[-1]["status"] == "completed"
    r = client.post(f"/api/threads/{tid}/runs", json={"text": "hi"})
    assert r.status_code == 409 and r.json()["detail"] == "conversation ended"


def test_trigger_thread_runs_once(client):
    tid = client.post("/api/patterns/qa/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "What is LangGraph?"}) as r:
        assert sse(r)[-1]["output"]
    assert client.post(f"/api/threads/{tid}/runs", json={"text": "again"}).status_code == 409


def test_input_limits(client):                                 # Review Focus 4
    tid = client.post("/api/patterns/qa/threads").json()["thread_id"]
    assert client.post(f"/api/threads/{tid}/runs", json={"text": "x" * 2001}).status_code == 422
    assert client.post(f"/api/threads/{tid}/runs", json={"text": "   "}).status_code == 422


def test_disconnect_mid_stream_frees_the_session(client):     # Review Focus 2
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "hello"}) as r:
        next(r.iter_lines())                                   # read one line, then hang up
    tid2 = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid2}/runs", json={"text": "hello"}) as r:
        assert sse(r)[-1]["status"] == "paused"


def test_thread_disconnected_mid_run_is_closed(client):
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "hello"}) as r:
        next(r.iter_lines())                                   # hang up before run_finished
    r = client.post(f"/api/threads/{tid}/runs", json={"text": "hello again"})
    assert r.status_code == 409 and r.json() == {"detail": "conversation ended"}
    assert client.get(f"/api/threads/{tid}/state").json()["closed"] is True


def test_session_reports_offline(client):
    assert client.get("/api/session").json() == {
        "mode": "offline", "models": [{"id": "offline", "label": "Offline (scripted)"}], "max_input_chars": 2000}


def test_state_counts_checkpoints_and_the_count_grows(client):      # spec §4.6
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    before = client.get(f"/api/threads/{tid}/state").json()["checkpoints"]
    assert isinstance(before, int) and before > 0
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "What is a checkpointer?"}) as r:
        sse(r)
    assert client.get(f"/api/threads/{tid}/state").json()["checkpoints"] > before


def test_whitespace_on_chat_pauses_again_without_answer(client):     # Review Focus 4
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "   "}) as r:
        ev = sse(r)
    assert ev[-1]["status"] == "paused"
    assert not [e for e in ev if e["type"] == "node_started" and e["node"] == "answer"]


def test_other_session_cannot_run_thread(client, app):
    tid = client.post("/api/patterns/chat_loop/threads").json()["thread_id"]
    with TestClient(app) as other:
        assert other.post(f"/api/threads/{tid}/runs", json={"text": "hi"}).status_code == 404


def test_max_input_chars_setting_limits_runs():
    settings = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:", max_input_chars=5,
                        erp_db=":memory:")
    with TestClient(create_app(settings, checkpointer=InMemorySaver(), guard=make_guard())) as c:
        assert c.get("/api/session").json()["max_input_chars"] == 5
        tid = c.post("/api/patterns/qa/threads").json()["thread_id"]
        assert c.post(f"/api/threads/{tid}/runs", json={"text": "123456"}).status_code == 422


def test_max_input_chars_reads_env(monkeypatch):
    monkeypatch.setenv("MAX_INPUT_CHARS", "123")
    assert Settings.from_env().max_input_chars == 123


def test_error_run_closes_the_thread(monkeypatch):
    class Boom:
        def invoke(self, *_a, **_k):
            raise RuntimeError("secret-detail")

    monkeypatch.setattr(app_module, "offline_factory", lambda *_a, **_k: (lambda: Boom()))
    settings = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:", erp_db=":memory:")
    with TestClient(create_app(settings, checkpointer=InMemorySaver(), guard=make_guard())) as c:
        tid = c.post("/api/patterns/chat_loop/threads").json()["thread_id"]
        with c.stream("POST", f"/api/threads/{tid}/runs", json={"text": "hello"}) as r:
            ev = sse(r)
        assert ev[-1]["status"] == "error" and "secret-detail" not in str(ev)
        r = c.post(f"/api/threads/{tid}/runs", json={"text": "hello again"})
        assert r.status_code == 409 and r.json() == {"detail": "conversation ended"}
        assert c.get(f"/api/threads/{tid}/state").json()["closed"] is True


def test_priming_failure_is_a_safe_500(client, app):
    class BrokenGraph:
        def astream(self, *_a, **_k):
            async def gen():
                raise RuntimeError("secret-detail")
                yield  # pragma: no cover  (makes this an async generator)
            return gen()

    app.state.graphs[("chat_loop", "offline")] = BrokenGraph()
    r = client.post("/api/patterns/chat_loop/threads")
    assert r.status_code == 500
    assert r.json() == {"detail": "could not start the conversation"}
    assert "secret-detail" not in r.text


def test_url_without_secret_fails_startup():
    settings = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:",
                        erp_mcp_url="http://127.0.0.1:8765/mcp", erp_approval_secret=None)
    app = create_app(settings, checkpointer=InMemorySaver(), guard=make_guard())
    with pytest.raises(RuntimeError, match="^ERP_APPROVAL_SECRET must be set when ERP_MCP_URL is set$"):
        with TestClient(app):
            pass


def test_erp_settings_read_env(monkeypatch):
    monkeypatch.setenv("ERP_MCP_URL", "http://erp.test/mcp")
    monkeypatch.setenv("ERP_APPROVAL_SECRET", "shh")
    monkeypatch.setenv("ERP_AUTO_APPROVE_LIMIT_ZAR", "7500")
    monkeypatch.setenv("ERP_DB", "/tmp/somewhere/erp.sqlite")
    monkeypatch.setenv("ERP_TENANT_TTL_HOURS", "24")
    s = Settings.from_env()
    assert (s.erp_mcp_url, s.erp_approval_secret, s.erp_auto_approve_limit_zar, s.erp_db,
            s.erp_tenant_ttl_hours) == ("http://erp.test/mcp", "shh", 7500.0, "/tmp/somewhere/erp.sqlite", 24.0)


def test_erp_settings_defaults(monkeypatch):
    for name in ("ERP_MCP_URL", "ERP_APPROVAL_SECRET", "ERP_AUTO_APPROVE_LIMIT_ZAR", "ERP_DB",
                 "ERP_TENANT_TTL_HOURS"):
        monkeypatch.delenv(name, raising=False)
    s = Settings.from_env()
    assert (s.erp_mcp_url, s.erp_approval_secret, s.erp_auto_approve_limit_zar, s.erp_db,
            s.erp_tenant_ttl_hours) == (None, None, 5000, "./data/erp.sqlite", 168)


def test_approval_thread_primes_at_ask_on_the_in_process_erp(client):
    tid = client.post("/api/patterns/approval/threads").json()["thread_id"]
    state = client.get(f"/api/threads/{tid}/state").json()
    assert state["paused"]["node"] == "ask"
    with client.stream("POST", f"/api/threads/{tid}/runs", json={"text": "Order 3 keyboards for CT-OPS"}) as r:
        ev = sse(r)
    assert ev[-1]["status"] == "paused"
    msgs = client.get(f"/api/threads/{tid}/state").json()["values"]["messages"]
    assert msgs[-1]["content"].startswith("Purchase order PO-0001 placed: 3 x Wired Keyboard")


def test_app_closes_the_in_process_erp_on_shutdown(tmp_path):
    settings = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:",
                        erp_db=str(tmp_path / "erp.sqlite"))
    app = create_app(settings, checkpointer=InMemorySaver(), guard=make_guard())
    with TestClient(app):
        erp_store = app.state.erp_store
        assert erp_store._conn is not None
    assert erp_store._conn is None
