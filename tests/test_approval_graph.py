"""The approval agent's graph: the model proposes, a policy or a person decides,
and only `submit_po` places an order (Approval spec §5.1, §9)."""

import json
import random
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_solutions.agents.approval_agent import graph as approval_graph
from agentic_solutions.agents.approval_agent.erp import ErpUnavailable, InProcessErpClient
from agentic_solutions.agents.approval_agent.graph import (
    MAX_PROPOSALS,
    MAX_TOOL_ROUNDS,
    build_graph,
)
from agentic_solutions.common.approval_tokens import issue
from agentic_solutions.common.errors import UserFacingError
from agentic_solutions.mcp_servers.erp.config import ErpSettings
from agentic_solutions.mcp_servers.erp.server import build_server
from agentic_solutions.mcp_servers.erp.store import MISMATCH, ErpError, ErpStore
from agentic_solutions.web.offline.model import Rule, Script, ScriptedChatModel
from agentic_solutions.web.topology import graph_topology

pytestmark = pytest.mark.anyio

SECRET = b"test-approval-graph-secret"
LIMIT = 5000.0
APPROVER = "visitor:0123456789ab"

LAPTOPS = "Order 12 laptops for the Cape Town office under CT-OPS"
KEYBOARDS = "Order 3 keyboards for CT-OPS"
MONITORS = "Order 40 monitors for JHB-FIN"
SAMPLES = (LAPTOPS, KEYBOARDS, MONITORS)


class Clock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


# ----------------------------------------------------------- scripted model

BINDS: list[tuple[tuple[str, ...], object]] = []


class RecordingModel(ScriptedChatModel):
    def bind_tools(self, tools, **kwargs):
        bound = super().bind_tools(tools, **kwargs)
        BINDS.append((bound.bound_tool_names, bound.tool_choice))
        return bound


class StubbornModel(RecordingModel):
    """Ignores tool_choice, like a misbehaving provider would."""

    def bind_tools(self, tools, **kwargs):
        return super().bind_tools(tools, **kwargs).model_copy(update={"tool_choice": None})


def call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "x"}])


def since_last_human(messages):
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i], messages[i + 1:]
    return None, []


ORDER = re.compile(r"order (\d+) (\w+?)s?\b.*?\b(CT-OPS|JHB-FIN|DBN-LOG|HQ-IT)", re.I)


def walk(messages, *, repropose=False):
    """search -> budget -> quote -> create -> propose_order, read off the history."""
    human, turn = since_last_human(messages)
    m = ORDER.search(human.content)
    if not m:
        return "Tell me what to order and for which cost centre."
    qty, item, cc = int(m.group(1)), m.group(2), m.group(3)
    tool_msgs = [t for t in turn if isinstance(t, ToolMessage)]
    if not tool_msgs:
        return call("search_catalogue", query=item)
    last = tool_msgs[-1]
    if last.name == "search_catalogue":
        return call("check_budget", cost_centre=cc)
    if last.name == "check_budget":
        search = next(t for t in tool_msgs if t.name == "search_catalogue")
        return call("get_price_quote", sku=json.loads(search.content)[0]["sku"], quantity=qty)
    if last.name == "get_price_quote":
        return call("create_requisition", cost_centre=cc,
                    lines=[{"quote_id": json.loads(last.content)["quote_id"]}],
                    justification=f"{qty} {item}s for {cc}.")
    if last.name == "create_requisition":
        req = json.loads(last.content)
        return call("propose_order", req_id=req["req_id"], summary=f"{qty} {item}s for {cc}")
    if last.name == "propose_order" and repropose and "rejected" in last.content:
        create = next(t for t in tool_msgs if t.name == "create_requisition")
        return call("propose_order", req_id=json.loads(create.content)["req_id"], summary="again")
    return f"Done: {last.content}"


def model_factory(reply=walk, model_cls=None):
    script = Script(rules=(Rule(lambda _t: True, reply, kind="tools"),),
                    fallback="I can only answer in text now.")
    cls = model_cls or RecordingModel
    return lambda: cls(script=script, latency=(0, 0), tokens_per_second=0)


# ----------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _clear_binds():
    BINDS.clear()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    s = ErpStore(str(tmp_path / "erp.sqlite"), secret=SECRET, auto_limit_zar=LIMIT,
                 tenant_ttl_hours=168.0, clock=clock)
    yield s
    s.close()


@pytest.fixture
async def erp(store):
    settings = ErpSettings(db=":memory:", secret=SECRET, auto_limit_zar=LIMIT)
    async with InProcessErpClient(build_server(store, settings)) as client:
        yield client


@pytest.fixture
def issued():
    return []


def make_graph(erp, clock, issued, reply=walk, model_cls=None):
    def issue_token(claims):
        issued.append(dict(claims))
        return issue(claims, SECRET, now=clock())

    return build_graph(erp=erp, issue_token=issue_token, auto_limit_zar=LIMIT,
                       checkpointer=InMemorySaver(), llm_factory=model_factory(reply, model_cls),
                       clock=clock)


def cfg(thread="t1", approver=APPROVER):
    return {"configurable": {"thread_id": thread, "approver": approver}, "recursion_limit": 100}


async def say(graph, text, config):
    """Start (or continue) a thread paused at ask, and send one message."""
    state = await graph.aget_state(config)
    if not state.next:
        await graph.ainvoke({"messages": []}, config)
    await graph.ainvoke(Command(resume=text), config)
    return await graph.aget_state(config)


async def decide(graph, config, **decision):
    await graph.ainvoke(Command(resume=decision), config)
    return await graph.aget_state(config)


def payload(state):
    return state.tasks[0].interrupts[0].value


def events(store, req_id="REQ-0001", tenant="t1"):
    return [e["event"] for e in store.get_audit_trail(tenant, req_id)]


def last_ai(state):
    return next(m for m in reversed(state.values["messages"]) if isinstance(m, AIMessage))


def tool_messages(state):
    return [m for m in state.values["messages"] if isinstance(m, ToolMessage)]


# -------------------------------------------------------------------- tests


def test_topology_edges():
    t = graph_topology(build_graph(erp=object(), issue_token=lambda c: "", auto_limit_zar=LIMIT))
    assert {n["id"] for n in t["nodes"]} == {
        "__start__", "__end__", "ask", "agent", "tools", "policy", "approval", "submit_po"}
    assert {(e["source"], e["target"]) for e in t["edges"]} == {
        ("__start__", "ask"),
        ("ask", "agent"), ("ask", "ask"), ("ask", "__end__"),
        ("agent", "tools"), ("agent", "policy"), ("agent", "ask"),
        ("tools", "agent"),
        ("policy", "submit_po"), ("policy", "approval"), ("policy", "agent"),
        ("approval", "submit_po"), ("approval", "policy"), ("approval", "agent"),
        ("submit_po", "ask"), ("submit_po", "agent"),
    }
    assert MAX_TOOL_ROUNDS == 8 and MAX_PROPOSALS == 3


def test_module_imports_without_env_and_builds_graph_lazily(monkeypatch):
    monkeypatch.delenv("ERP_MCP_URL", raising=False)
    assert "graph" not in vars(approval_graph)
    import agentic_solutions.agents.approval_agent.__main__ as cli  # noqa: F401  (import smoke)


async def test_over_limit_pauses_with_snapshot_then_approve_places_one_po(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    state = await say(g, LAPTOPS, c)
    assert state.next == ("approval",)
    p = payload(state)
    json.dumps(p)  # the card is rebuilt from this alone, so it must serialise
    req = store.get_requisition("t1", "REQ-0001")
    assert p["kind"] == "approval_request"
    assert p["req_id"] == "REQ-0001" and p["version"] == 1
    assert p["total_zar"] == req["total_zar"] == 12 * 11780
    assert p["cost_centre"] == "CT-OPS"
    assert p["budget_remaining"] == 245000
    assert p["policy_reason"] == "Over R5,000 needs approval"
    assert p["short_hash"] == req["content_hash"][:8]
    assert p["quote_expires_at"] == req["lines"][0]["quote_expires_at"]
    assert p["requoted"] is False
    assert [(x["sku"], x["quantity"]) for x in p["lines"]] == [("LAP-001", 12)]
    assert events(store) == ["created", "approval_requested"]

    state = await decide(g, c, decision="approve")
    assert state.next == ("ask",)
    assert events(store) == ["created", "approval_requested", "approved", "submitted"]
    assert store.get_requisition("t1", "REQ-0001")["po_number"] == "PO-0001"
    assert last_ai(state).content == (
        "Purchase order PO-0001 placed: 12 x 14-inch Business Laptop, 16 GB for R141,360 on CT-OPS.")
    assert [e["event"] for e in state.values["audit"]][-1] == "submitted"
    assert state.values["pending"] is None and state.values["approval"] is None
    assert issued == [{"req_id": "REQ-0001", "version": 1, "content_hash": req["content_hash"],
                       "tenant": "t1", "approver": APPROVER, "requested_by": "agent",
                       "reason": "approved"}]
    # Exactly one ToolMessage answers the propose_order call.
    propose = [m for m in state.values["messages"] if isinstance(m, AIMessage)
               and m.tool_calls and m.tool_calls[0]["name"] == "propose_order"]
    answers = [m for m in tool_messages(state) if m.tool_call_id == propose[0].tool_calls[0]["id"]]
    assert len(answers) == 1 and "PO-0001" in answers[0].content


async def test_under_limit_auto_approves_without_pause(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    state = await say(g, KEYBOARDS, c)
    assert state.next == ("ask",)
    assert events(store) == ["created", "auto_approved", "submitted"]
    assert issued[0]["approver"] == "policy" and issued[0]["reason"] == "under limit"
    assert last_ai(state).content.startswith("Purchase order PO-0001 placed: 3 x Wired Keyboard")


async def test_approved_but_over_budget_is_refused_and_returns_to_agent(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    state = await say(g, MONITORS, c)
    assert state.next == ("approval",)
    state = await decide(g, c, decision="approve")
    assert state.next == ("ask",)
    assert events(store) == ["created", "approval_requested", "approved", "refused"]
    refusal = tool_messages(state)[-1]
    assert refusal.content.startswith("The ERP refused the order: Over budget")
    assert last_ai(state).content.startswith("Done: The ERP refused the order")
    assert "po_number" not in store.get_requisition("t1", "REQ-0001")


async def test_edit_requires_fresh_decision_and_old_token_refused(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    state = await say(g, LAPTOPS, c)
    v1 = store.get_requisition("t1", "REQ-0001")
    state = await decide(g, c, decision="edit", edits=[{"sku": "LAP-001", "quantity": 10}])
    assert state.next == ("approval",)
    p = payload(state)
    assert p["version"] == 2 and p["lines"][0]["quantity"] == 10
    assert p["lines"][0]["quote_id"] != v1["lines"][0]["quote_id"]
    old = issue({"req_id": "REQ-0001", "version": 1, "content_hash": v1["content_hash"],
                 "tenant": "t1", "approver": APPROVER, "requested_by": "agent",
                 "reason": "approved"}, SECRET, now=clock())
    with pytest.raises(ErpError) as err:
        store.submit_purchase_order("t1", "REQ-0001", 1, old, "REQ-0001:1")
    assert str(err.value) == MISMATCH
    state = await decide(g, c, decision="approve")
    assert state.next == ("ask",)
    assert events(store) == ["created", "approval_requested", "updated", "approval_requested",
                             "refused", "approved", "submitted"]
    assert issued[-1]["version"] == 2


async def test_edit_to_under_limit_goes_through_policy(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    await say(g, MONITORS, c)
    # One monitor is R2,900: under the limit, so the policy approves version 2.
    state = await decide(g, c, decision="edit", edits=[{"sku": "MON-001", "quantity": 1}])
    assert state.next == ("ask",)
    assert events(store) == ["created", "approval_requested", "updated", "auto_approved",
                             "submitted"]
    assert issued[-1]["approver"] == "policy" and issued[-1]["version"] == 2


async def test_reject_returns_reason_to_agent(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    await say(g, LAPTOPS, c)
    state = await decide(g, c, decision="reject", reason="Too many laptops")
    assert state.next == ("ask",)
    assert events(store) == ["created", "approval_requested", "rejected"]
    assert tool_messages(state)[-1].content == (
        "The approver rejected this order. Reason: Too many laptops.")
    assert last_ai(state).content.startswith("Done: The approver rejected")
    assert issued == []

    await say(g, LAPTOPS, cfg(thread="t2"))
    state = await decide(g, cfg(thread="t2"), decision="reject")
    assert tool_messages(state)[-1].content == (
        "The approver rejected this order. Reason: none given.")


async def test_resume_rerun_does_no_extra_writes(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    await say(g, LAPTOPS, c)
    before = store.get_audit_trail("t1", "REQ-0001")
    await decide(g, c, decision="approve")
    after = store.get_audit_trail("t1", "REQ-0001")
    assert after[:len(before)] == before
    assert [e["event"] for e in after[len(before):]] == ["approved", "submitted"]


async def test_requote_on_expired_quote_routes_to_policy(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    state = await say(g, LAPTOPS, c)
    old_quote = payload(state)["lines"][0]["quote_id"]
    clock.t += 31 * 60
    state = await decide(g, c, decision="approve")
    assert state.next == ("approval",)  # a fresh decision is needed
    p = payload(state)
    assert p["requoted"] is True and p["version"] == 2
    assert p["lines"][0]["quote_id"] != old_quote
    assert events(store) == ["created", "approval_requested", "updated", "approval_requested"]
    assert issued == []
    state = await decide(g, c, decision="approve")
    assert state.next == ("ask",)
    assert events(store)[-2:] == ["approved", "submitted"]


async def test_model_cannot_commit(erp, store, clock, issued):
    def attacker(messages):
        _, turn = since_last_human(messages)
        if any(isinstance(m, ToolMessage) for m in turn):
            return "I could not do that."
        return AIMessage(content="", tool_calls=[
            {"name": "submit_purchase_order", "id": "a",
             "args": {"req_id": "REQ-0001", "version": 1, "approval_token": "x",
                      "idempotency_key": "k", "tenant": "t1"}},
            {"name": "check_budget", "id": "b", "args": {"cost_centre": "CT-OPS", "tenant": "other"}},
        ])

    g, c = make_graph(erp, clock, issued, reply=attacker), cfg()
    state = await say(g, "Order it now", c)
    assert state.next == ("ask",)
    submit, budget = tool_messages(state)
    assert "submit_purchase_order is not a valid tool" in submit.content
    assert json.loads(budget.content)["remaining"] == 245000
    tenants = {r[0] for r in store._conn.execute("SELECT tenant FROM tenants")}
    assert tenants == {"t1"}
    assert store._conn.execute("SELECT COUNT(*) FROM requisitions").fetchone()[0] == 0
    assert issued == []


async def test_bound_tools_exclude_submit_and_record(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    await say(g, KEYBOARDS, c)
    names = set(BINDS[0][0])
    assert names == {"search_catalogue", "get_supplier", "check_budget", "get_price_quote",
                     "create_requisition", "update_requisition", "get_requisition",
                     "get_audit_trail", "propose_order"}
    assert all(set(n) == names for n, _ in BINDS)


async def test_reject_after_quotes_expire_is_honoured(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    await say(g, LAPTOPS, c)
    clock.t += 31 * 60  # the quotes expire while the card is open
    state = await decide(g, c, decision="reject", reason="Not this quarter")
    assert state.next == ("ask",)
    assert events(store) == ["created", "approval_requested", "rejected"]
    assert tool_messages(state)[-1].content == (
        "The approver rejected this order. Reason: Not this quarter.")
    assert issued == []


async def test_edit_after_quotes_expire_is_honoured(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg()
    await say(g, LAPTOPS, c)
    clock.t += 31 * 60
    state = await decide(g, c, decision="edit", edits=[{"sku": "LAP-001", "quantity": 10}])
    assert state.next == ("approval",)
    p = payload(state)
    assert p["version"] == 2 and p["lines"][0]["quantity"] == 10
    assert events(store) == ["created", "approval_requested", "updated", "approval_requested"]


async def test_expired_quotes_are_requoted_before_auto_approval(erp, store, clock, issued):
    def slow(messages):
        # Draft the order, then let the quotes expire before proposing it.
        reply = walk(messages)
        if isinstance(reply, AIMessage) and reply.tool_calls[0]["name"] == "propose_order":
            clock.t += 31 * 60
        return reply

    g, c = make_graph(erp, clock, issued, reply=slow), cfg()
    state = await say(g, KEYBOARDS, c)
    assert state.next == ("ask",)
    assert events(store) == ["created", "updated", "auto_approved", "submitted"]
    assert issued[-1]["version"] == 2


async def test_tool_round_cap_ends_turn_with_text(erp, store, clock, issued):
    g = make_graph(erp, clock, issued, reply=lambda _m: call("check_budget", cost_centre="HQ-IT"))
    c = cfg()
    state = await say(g, "How much budget is left?", c)
    assert state.next == ("ask",)
    final = state.values["messages"][-1]
    assert isinstance(final, AIMessage) and not final.tool_calls
    assert final.content == "I can only answer in text now."
    # 8 tools passes ran; the 9th model call is bound with tool_choice none.
    assert len(BINDS) == MAX_TOOL_ROUNDS + 1
    assert [choice for _, choice in BINDS] == [None] * 8 + [{"type": "none"}]
    assert len(tool_messages(state)) == MAX_TOOL_ROUNDS
    # The next turn starts with a fresh allowance.
    BINDS.clear()
    await say(g, "And now?", c)
    assert BINDS[0][1] is None


async def test_proposal_cap(erp, store, clock, issued):
    g = make_graph(erp, clock, issued, reply=lambda m: walk(m, repropose=True))
    c = cfg()
    state = await say(g, LAPTOPS, c)
    pauses = 0
    while state.next == ("approval",):
        pauses += 1
        state = await decide(g, c, decision="reject", reason="no")
    assert pauses == MAX_PROPOSALS
    assert state.next == ("ask",)
    assert BINDS[-1][1] == {"type": "none"}
    assert all(choice is None for _, choice in BINDS[:-1])
    assert state.values["messages"][-1].content == "I can only answer in text now."


async def test_caps_hold_when_the_model_ignores_tool_choice(erp, store, clock, issued):
    g = make_graph(erp, clock, issued, model_cls=StubbornModel,
                   reply=lambda _m: call("check_budget", cost_centre="HQ-IT"))
    state = await say(g, "How much budget is left?", cfg())
    assert state.next == ("ask",)
    final = state.values["messages"][-1]
    assert isinstance(final, AIMessage) and not final.tool_calls
    assert final.content == "I've reached the step limit for this request."
    assert len(tool_messages(state)) == MAX_TOOL_ROUNDS

    BINDS.clear()
    g = make_graph(erp, clock, issued, model_cls=StubbornModel,
                   reply=lambda m: walk(m, repropose=True))
    c = cfg(thread="t2")
    state = await say(g, LAPTOPS, c)
    pauses = 0
    while state.next == ("approval",):
        pauses += 1
        state = await decide(g, c, decision="reject", reason="no")
    assert pauses == MAX_PROPOSALS
    assert state.next == ("ask",)
    assert state.values["messages"][-1].content == "I've reached the step limit for this request."


class Flaky:
    """Delegates to the real ERP until one of `fail_on` is called while `down`."""

    def __init__(self, erp, fail_on=None):
        self.erp, self.fail_on, self.down = erp, fail_on, False

    async def call(self, tool, args):
        if self.down and (self.fail_on is None or tool in self.fail_on):
            raise ErpUnavailable("The ERP system is unavailable.")
        return await self.erp.call(tool, args)


DOWN = "The ERP system is unavailable. Try again shortly."


async def test_erp_down_raises_user_facing_error(erp, store, clock, issued):
    flaky = Flaky(erp)
    g, c = make_graph(flaky, clock, issued), cfg()
    state = await say(g, LAPTOPS, c)
    assert state.next == ("approval",)
    flaky.down = True
    with pytest.raises(UserFacingError, match=DOWN):
        await decide(g, c, decision="approve")
    assert issued == []


async def test_erp_down_in_policy_raises_user_facing_error(erp, store, clock, issued):
    flaky = Flaky(erp, fail_on={"get_requisition"})
    flaky.down = True
    g, c = make_graph(flaky, clock, issued), cfg()
    with pytest.raises(UserFacingError, match=DOWN):
        await say(g, KEYBOARDS, c)
    assert (await g.aget_state(c)).next == ("policy",)
    assert issued == []


async def test_erp_down_in_submit_po_raises_user_facing_error(erp, store, clock, issued):
    flaky = Flaky(erp, fail_on={"submit_purchase_order"})
    flaky.down = True
    g, c = make_graph(flaky, clock, issued), cfg()
    with pytest.raises(UserFacingError, match=DOWN):
        await say(g, KEYBOARDS, c)
    assert (await g.aget_state(c)).next == ("submit_po",)
    assert events(store) == ["created", "auto_approved"]


async def test_missing_approver_is_an_error_not_a_default(erp, store, clock, issued):
    g, c = make_graph(erp, clock, issued), cfg(approver=None)
    await say(g, LAPTOPS, c)
    with pytest.raises(UserFacingError, match="No approver identity for this run."):
        await decide(g, c, decision="approve")
    assert issued == []


async def test_expired_requisition_goes_back_to_agent(erp, store, clock, issued):
    def ghost(messages):
        _, turn = since_last_human(messages)
        if any(isinstance(m, ToolMessage) for m in turn):
            return f"Done: {turn[-1].content}"
        return call("propose_order", req_id="REQ-9999", summary="ghost")

    g, c = make_graph(erp, clock, issued, reply=ghost), cfg()
    state = await say(g, "Propose it", c)
    assert state.next == ("ask",)
    assert tool_messages(state)[-1].content == (
        "This request has expired. Ask the agent to draft it again.")


async def test_propose_mixed_with_other_calls_is_refused(erp, store, clock, issued):
    def mixed(messages):
        _, turn = since_last_human(messages)
        if any(isinstance(m, ToolMessage) for m in turn):
            return "ok"
        return AIMessage(content="", tool_calls=[
            {"name": "check_budget", "id": "a", "args": {"cost_centre": "CT-OPS"}},
            {"name": "propose_order", "id": "b", "args": {"req_id": "REQ-0001", "summary": "s"}},
        ])

    g, c = make_graph(erp, clock, issued, reply=mixed), cfg()
    state = await say(g, "Do both", c)
    assert state.next == ("ask",)
    assert tool_messages(state)[-1].content == (
        "Error: call propose_order on its own, after the other tools.")


@pytest.mark.parametrize("sample", SAMPLES)
async def test_guarantee_fuzz(erp, store, clock, issued, sample):
    g = make_graph(erp, clock, issued)
    placed = 0
    for seed in range(30):
        rnd = random.Random(seed)
        tenant = f"fuzz-{seed}"
        c = cfg(thread=tenant)
        state = await say(g, sample, c)
        for _ in range(4):
            if state.next != ("approval",):
                break
            if rnd.random() < 0.2:
                clock.t += 31 * 60  # let the quotes expire while the card is open
            roll = rnd.random()
            if roll < 0.4:
                state = await decide(g, c, decision="approve")
            elif roll < 0.8:
                edits = [{"sku": line["sku"], "quantity": rnd.randint(1, 60)}
                         for line in payload(state)["lines"]]
                state = await decide(g, c, decision="edit", edits=edits)
            else:
                state = await decide(g, c, decision="reject", reason="fuzz")

        rows = store._conn.execute(
            "SELECT req_id, version, content_hash FROM requisitions WHERE tenant = ?", (tenant,))
        for req_id, version, content_hash in rows.fetchall():
            trail = store.get_audit_trail(tenant, req_id)
            for i, e in enumerate(trail):
                if e["event"] != "submitted":
                    continue
                assert e["version"] == version
                prior = [p for p in trail[:i] if p["version"] == e["version"]
                         and p["event"] in ("approved", "auto_approved")]
                assert prior, (sample, seed, trail)
                tokens = [t for t in issued if t["tenant"] == tenant and t["req_id"] == req_id
                          and t["version"] == version]
                assert tokens and tokens[-1]["content_hash"] == content_hash
                assert tokens[-1]["approver"] in {p["actor"] for p in prior}
                placed += 1
    # The sequences reach both outcomes (keyboards never need a person).
    assert placed >= 1
    if sample != KEYBOARDS:
        assert placed < 30
