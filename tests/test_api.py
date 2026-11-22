import json

from fastapi.testclient import TestClient


def sse(resp):
    return [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]


def test_catalog_and_detail(client):
    assert [p["id"] for p in client.get("/api/patterns").json()] == ["qa", "chat_loop", "guardrail", "human_in_loop"]
    d = client.get("/api/patterns/guardrail").json()
    assert d["mode"] == "chat" and "## What it is" in d["explanation_md"] and d["topology"]["nodes"]
    assert client.get("/api/patterns/nope").status_code == 404


def test_chat_thread_is_primed_paused_and_runs_stream(client):
    tid = client.post("/api/patterns/human_in_loop/threads").json()["thread_id"]
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


def test_session_reports_offline(client):
    assert client.get("/api/session").json() == {"mode": "offline", "live_available": False}
