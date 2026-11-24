"""The run API for the approval demo: text or a decision, and the 409 rules (Approval spec §5.3, §9.1)."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agentic_solutions.agents.approval_agent.erp import ErpUnavailable
from agentic_solutions.web.app import create_app
from agentic_solutions.web.config import Settings
from conftest import TEST_ERP_SECRET
from fakes import make_guard

LAPTOPS = "Order 12 laptops for the Cape Town office under CT-OPS"
APPROVE = {"resume": {"decision": "approve"}}
FINISH_FIRST = "Finish the pending approval first"
NOTHING_WAITING = "Nothing is waiting for approval"
IN_PROGRESS = "a run is already in progress"
ERP_DOWN = "The ERP system is unavailable. Try again shortly."


def sse(resp):
    return [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]


def run(client, tid, body):
    with client.stream("POST", f"/api/threads/{tid}/runs", json=body) as r:
        assert r.status_code == 200, r.read()
        return sse(r)


def state(client, tid):
    return client.get(f"/api/threads/{tid}/state").json()


def pending_thread(client):
    """An approval thread paused at `approval` with sample 1 (12 laptops, over the limit)."""
    tid = client.post("/api/patterns/approval/threads").json()["thread_id"]
    ev = run(client, tid, {"text": LAPTOPS})
    assert ev[-1]["status"] == "paused"
    return tid


def submitted(values):
    return [e for e in values.get("audit") or [] if e["event"] == "submitted"]


def erp_events(app, tid):
    """Every audit event the ERP holds for this thread (its tenant), straight from the store."""
    return [e["event"] for e in app.state.erp_store.get_audit_trail(tid, "REQ-0001")]


def test_full_approval_over_http_api(client, app):
    tid = pending_thread(client)
    paused = state(client, tid)["paused"]
    assert paused["node"] == "approval" and paused["payload"]["kind"] == "approval_request"

    ev = run(client, tid, APPROVE)
    assert ev[-1]["status"] == "paused"
    assert [e["node"] for e in ev if e["type"] == "interrupt"] == ["ask"]
    after = state(client, tid)
    assert after["paused"]["node"] == "ask"
    assert len(submitted(after["values"])) == 1
    # The approver is this visitor's hashed session id, never a default.
    sid = app.state.store._threads[tid].session_id
    approver = "visitor:" + hashlib.sha256(sid.encode("utf-8")).hexdigest()[:12]
    approved = [e for e in after["values"]["audit"] if e["event"] == "approved"]
    assert [e["actor"] for e in approved] == [approver]


def test_text_while_pending_is_409(client):
    tid = pending_thread(client)
    r = client.post(f"/api/threads/{tid}/runs", json={"text": "hello"})
    assert r.status_code == 409 and r.json() == {"detail": FINISH_FIRST}
    assert state(client, tid)["paused"]["node"] == "approval"      # still waiting, not closed
    assert state(client, tid)["closed"] is False


@pytest.mark.parametrize("pattern", ["approval", "chat_loop", "qa"])
def test_resume_when_nothing_pending_is_409(client, pattern):
    tid = client.post(f"/api/patterns/{pattern}/threads").json()["thread_id"]
    r = client.post(f"/api/threads/{tid}/runs", json=APPROVE)
    assert r.status_code == 409 and r.json() == {"detail": NOTHING_WAITING}
    if pattern != "qa":
        assert state(client, tid)["paused"]["node"] == "ask"


EDIT = {"decision": "edit"}
SCHEMA_CASES = {
    "bad decision": ({"resume": {"decision": "maybe"}}, None),
    "quantity 0": ({"resume": {**EDIT, "edits": [{"sku": "LAP-001", "quantity": 0}]}}, None),
    "quantity 1000": ({"resume": {**EDIT, "edits": [{"sku": "LAP-001", "quantity": 1000}]}}, None),
    "21 edits": ({"resume": {**EDIT, "edits": [{"sku": "LAP-001", "quantity": 1}] * 21}}, None),
    "reason 501": ({"resume": {"decision": "reject", "reason": "x" * 501}}, None),
    "text and resume": ({"text": "hi", **APPROVE}, None),
    "neither": ({}, None),
    "edit without edits": ({"resume": EDIT}, "Send changed quantities to edit the order"),
    "edit with empty edits": ({"resume": {**EDIT, "edits": []}}, "Send changed quantities to edit the order"),
    "edits with approve": ({"resume": {"decision": "approve", "edits": [{"sku": "LAP-001", "quantity": 2}]}},
                           "Edits are only allowed with the edit decision"),
    "edits with reject": ({"resume": {"decision": "reject", "edits": []}},
                          "Edits are only allowed with the edit decision"),
    "unknown sku": ({"resume": {**EDIT, "edits": [{"sku": "NOPE-999", "quantity": 2}]}},
                    "Unknown item in edits"),
}


@pytest.mark.parametrize("body,detail", SCHEMA_CASES.values(), ids=SCHEMA_CASES.keys())
def test_resume_schema_validation(client, body, detail):
    tid = pending_thread(client)
    r = client.post(f"/api/threads/{tid}/runs", json=body)
    assert r.status_code == 422
    if detail is not None:
        assert r.json() == {"detail": detail}
    after = state(client, tid)
    assert after["paused"]["node"] == "approval" and after["closed"] is False


def test_valid_edit_is_accepted(client):
    tid = pending_thread(client)
    ev = run(client, tid, {"resume": {**EDIT, "edits": [{"sku": "LAP-001", "quantity": 10}]}})
    assert ev[-1]["status"] == "paused"
    paused = state(client, tid)["paused"]
    assert paused["node"] == "approval"                             # still over the limit: a fresh card
    assert [(x["sku"], x["quantity"]) for x in paused["payload"]["lines"]] == [("LAP-001", 10)]


def test_double_resume_places_one_po(client, app):                  # Review Focus 5
    tid = pending_thread(client)
    store = app.state.store
    sid = store._threads[tid].session_id

    # Second click while the first is still streaming: the first run holds the
    # session's slot (claimed exactly as run_thread does), so this one is
    # refused before it reads the state or reaches the graph.
    assert store.begin_run(sid)
    r = client.post(f"/api/threads/{tid}/runs", json=APPROVE)
    assert r.status_code == 409 and r.json() == {"detail": IN_PROGRESS}
    store.end_run(sid)

    ev = run(client, tid, APPROVE)                                  # the first click's run
    assert ev[-1]["status"] == "paused"

    # Second click after the first finished: the thread now waits at `ask`.
    r = client.post(f"/api/threads/{tid}/runs", json=APPROVE)
    assert r.status_code == 409 and r.json() == {"detail": NOTHING_WAITING}

    after = state(client, tid)
    assert len(submitted(after["values"])) == 1
    assert erp_events(app, tid).count("submitted") == 1
    assert after["closed"] is False


def test_other_session_thread_404(client, app):                    # Review Focus 2
    tid = pending_thread(client)
    # A fresh cookie jar. Not a `with` block: that would run the app's lifespan
    # again and close the in-process ERP the first client is still using.
    other = TestClient(app)
    assert other.post(f"/api/threads/{tid}/runs", json=APPROVE).status_code == 404
    assert other.get(f"/api/threads/{tid}/state").status_code == 404
    assert state(client, tid)["paused"]["node"] == "approval"
    assert "submitted" not in erp_events(app, tid)


class DraftsThenDownErp:
    """Answers the drafting tools the scripted model calls, then is down for the nodes."""

    QUOTE = {"quote_id": "Q-1", "sku": "LAP-001", "quantity": 12}

    async def call(self, tool, args):
        canned = {
            "search_catalogue": [{"sku": "LAP-001", "name": "Laptop"}],
            "check_budget": {"cost_centre": "CT-OPS", "remaining": 100000},
            "get_price_quote": self.QUOTE,
            "create_requisition": {"req_id": "REQ-0001", "version": 1},
        }
        if tool in canned:
            return canned[tool]
        raise ErpUnavailable("connection refused")


def test_erp_down_event_message(tmp_path):
    settings = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:",
                        erp_db=str(tmp_path / "erp.sqlite"), erp_approval_secret=TEST_ERP_SECRET)
    app = create_app(settings, checkpointer=InMemorySaver(), guard=make_guard(), erp=DraftsThenDownErp())
    with TestClient(app) as c:
        tid = c.post("/api/patterns/approval/threads").json()["thread_id"]
        ev = run(c, tid, {"text": LAPTOPS})                        # `policy` reads the requisition: down
        assert {"type": "error", "message": ERP_DOWN} in ev
        assert ev[-1]["type"] == "run_finished" and ev[-1]["status"] == "error"
        assert "connection refused" not in json.dumps(ev)
        assert state(c, tid)["closed"] is True


def test_erp_client_without_secret_is_refused():
    settings = Settings(session_secret="s", offline_latency_scale=0, checkpoint_db=":memory:",
                        erp_db=":memory:", erp_approval_secret=None)
    with pytest.raises(RuntimeError, match="^ERP_APPROVAL_SECRET must be set when an ERP client is passed in$"):
        create_app(settings, checkpointer=InMemorySaver(), guard=make_guard(), erp=DraftsThenDownErp())


def test_pending_card_survives_state_reload(client):
    tid = pending_thread(client)
    payload = state(client, tid)["paused"]["payload"]
    assert payload["kind"] == "approval_request"
    assert [(x["sku"], x["quantity"]) for x in payload["lines"]] == [("LAP-001", 12)]
    assert payload["total_zar"] > 5000
    assert isinstance(payload["short_hash"], str) and len(payload["short_hash"]) == 8
    assert state(client, tid)["paused"] == {"node": "approval", "payload": payload}  # stable on reload


@pytest.mark.parametrize("body,status,detail", [
    ({"text": "hello"}, 409, FINISH_FIRST),
    ({"resume": {**EDIT, "edits": [{"sku": "NOPE-999", "quantity": 2}]}}, 422, "Unknown item in edits"),
], ids=["text while pending", "unknown sku"])
def test_refused_request_releases_the_slot_and_keeps_the_thread(client, app, body, status, detail):
    tid = pending_thread(client)
    r = client.post(f"/api/threads/{tid}/runs", json=body)
    assert r.status_code == status and r.json() == {"detail": detail}
    store, sid = app.state.store, app.state.store._threads[tid].session_id
    assert store.begin_run(sid)                                     # the refusal freed the slot
    store.end_run(sid)
    after = state(client, tid)
    assert after["closed"] is False and after["paused"]["node"] == "approval"
    assert run(client, tid, APPROVE)[-1]["status"] == "paused"     # the card still works
    assert len(submitted(state(client, tid)["values"])) == 1


def test_text_while_a_run_holds_the_slot_never_reaches_the_card(client, app):   # Review Focus 5
    tid = pending_thread(client)
    store, sid = app.state.store, app.state.store._threads[tid].session_id
    assert store.begin_run(sid)
    r = client.post(f"/api/threads/{tid}/runs", json={"text": "hello"})
    assert r.status_code == 409 and r.json() == {"detail": IN_PROGRESS}
    store.end_run(sid)
    after = state(client, tid)
    assert after["closed"] is False and after["paused"]["node"] == "approval"


@pytest.mark.parametrize("resume", [
    {"decision": "edit"},
    {"decision": "approve", "edits": [{"sku": "LAP-001", "quantity": 2}]},
    {"decision": "edit", "edits": [{"sku": "NOPE-999", "quantity": 2}]},
], ids=["edit without edits", "edits with approve", "unknown sku"])
def test_pause_kind_is_checked_before_the_payload(client, resume):
    tid = client.post("/api/patterns/approval/threads").json()["thread_id"]   # waiting at `ask`
    r = client.post(f"/api/threads/{tid}/runs", json={"resume": resume})
    assert r.status_code == 409 and r.json() == {"detail": NOTHING_WAITING}
