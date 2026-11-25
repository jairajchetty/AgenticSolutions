"""The Approval pattern: the agent may only PROPOSE an order; someone else decides.

The model drafts a requisition on a mock ERP over MCP, then calls the local
tool `propose_order`. It never sees `submit_purchase_order`, the audit tool or
an approval token. A policy approves small orders; anything over the limit
pauses at `approval` for a person to approve, edit or reject. Only `submit_po`
calls the ERP's submit tool, with a token bound to the exact version and
content hash that was approved, and the ERP checks that token itself.

The graph
---------

    START -> ask -> agent <-> tools
                     |
                     +-(propose_order alone)-> policy -(<= limit)-> submit_po -> ask
                                                 |                     |
                                                 +-(> limit)-> approval ⏸  (refused) -> agent
                         approval -approve-> submit_po
                                  -edit / approve on expired quotes-> policy
                                  -reject-> agent

Rules that keep the guarantee
-----------------------------
* `propose_order` is answered by exactly one ToolMessage, written by whichever
  node ends the proposal (policy, approval or submit_po).
* On resume, `approval` re-runs from its first line, so before `interrupt()`
  it only reads, plus `approval_requested`, recorded once per version (checked
  against the ERP's audit trail, so a resume never records it twice).
* Expired quotes are re-quoted in `policy`, before the policy decides or the
  card is shown, and again in `approval` after an approve. A reject or edit is
  always honoured, even if the quotes expired while the card was open.
* The token is issued inside `submit_po`, at call time, so it never reaches
  the checkpoint. Its idempotency key `req_id:version` makes a re-run return
  the same PO instead of ordering twice.
"""

import json
import os
import time
from collections.abc import Callable
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from agentic_solutions.agents.chat_agent.graph import STOP_WORD
from agentic_solutions.agents.interrupt_chat_agent.graph import ask as ask_for_text
from agentic_solutions.common.errors import UserFacingError
from agentic_solutions.common.llm import LLMFactory, declined_or, get_llm
from agentic_solutions.mcp_servers.erp import policy as order_policy

from .erp import ErpClient, ErpToolError, ErpUnavailable, HttpErpClient, model_tools

MAX_TOOL_ROUNDS = 8
MAX_PROPOSALS = 3

# Anthropic's form; ChatAnthropic turns the bare string "none" into "force a tool named none".
NO_TOOLS = {"type": "none"}

SYSTEM_PROMPT = (
    "You are a procurement assistant for a fictional South African company, working on a "
    "mock ERP with prices in ZAR. To order something: search the catalogue, check the cost "
    "centre's budget, get a price quote for each item, draft a requisition, then call "
    "propose_order(req_id, summary) on its own. You cannot place orders yourself: a policy "
    "or a person approves each proposal, and you are told the outcome. Never assume missing "
    "details: if the request does not say exactly which item, how many, or which cost centre, "
    "or more than one catalogue item matches, ask the person before drafting anything. "
    "Otherwise answer in plain text."
)

PROPOSE_ALONE = "Error: call propose_order on its own, after the other tools."
EXPIRED = "This request has expired. Ask the agent to draft it again."
UNAVAILABLE = "The ERP system is unavailable. Try again shortly."
NO_APPROVER = "No approver identity for this run."
BAD_DECISION = "The decision must be approve, edit or reject."
STEP_LIMIT = "I've reached the step limit for this request."
BAD_EDITS = "Edits must name SKUs on this order, each with a quantity from 1 to 999."


class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    tool_rounds: int  # agent -> tools passes this user turn
    proposals: int  # propose_order calls routed to policy this user turn
    pending: dict | None  # the proposal: call_id, req_id, summary, requoted, req snapshot
    approval: dict | None  # who approved which version (never the token itself)
    audit: list  # the ERP's audit trail after the last placed order


@tool("propose_order")
def propose_order(req_id: str, summary: str) -> str:
    """Propose a drafted requisition for ordering. A policy or a person decides; you cannot
    place orders yourself. Call it on its own, after the other tools, as your last step."""
    # Only runs when the model mixes it with other calls: on its own, `agent`
    # routes to `policy` instead of executing it.
    return PROPOSE_ALONE


def _configurable(config: RunnableConfig) -> dict:
    return (config or {}).get("configurable") or {}


def _tenant(config: RunnableConfig) -> str:
    tenant = _configurable(config).get("thread_id")
    if not isinstance(tenant, str) or not tenant:
        raise UserFacingError("This run has no thread id.")
    return tenant


def _approver(config: RunnableConfig) -> str:
    approver = _configurable(config).get("approver")
    if not isinstance(approver, str) or not approver.strip():
        raise UserFacingError(NO_APPROVER)
    return approver


def _answer(pending: dict, text: str) -> dict:
    """The one ToolMessage that answers the propose_order call, and the end of the proposal."""
    reply = ToolMessage(text, tool_call_id=pending["call_id"], name="propose_order")
    return {"messages": [reply], "pending": None, "approval": None}


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _describe(lines: list[dict]) -> str:
    return "; ".join(f"{line['quantity']} x {line['name']}" for line in lines)


def _card(pending: dict, limit: float) -> dict:
    """The interrupt payload: everything the approval card shows, JSON only (§9.1)."""
    req = pending["req"]
    soonest = min(req["lines"], key=lambda line: line["quote_expires_at_ts"])
    return {
        "kind": "approval_request",
        "req_id": req["req_id"],
        "version": req["version"],
        "summary": pending.get("summary", ""),
        "cost_centre": req["cost_centre"],
        "justification": req["justification"],
        "lines": [{k: line[k] for k in ("sku", "name", "quantity", "unit_price_zar",
                                         "line_total_zar", "quote_id", "quote_expires_at")}
                  for line in req["lines"]],
        "total_zar": req["total_zar"],
        "budget_remaining": pending["budget_remaining"],
        "policy_reason": order_policy.reason(req["total_zar"], limit),
        "short_hash": req["content_hash"][:8],
        "quote_expires_at": soonest["quote_expires_at"],
        "requoted": bool(pending.get("requoted")),
    }


def build_graph(
    *,
    erp: ErpClient,
    issue_token: Callable[[dict], str],
    auto_limit_zar: float,
    checkpointer=None,
    llm_factory: LLMFactory | None = None,
    clock: Callable[[], float] = time.time,
):
    """Wire the approval graph.

    `erp` is the MCP client, `issue_token(claims)` signs an approval (the graph
    never sees the secret), and `clock` must match the ERP's clock, because
    quote expiry is checked here as well as in the server.
    """
    tools = [*model_tools(erp), propose_order]

    async def call(tool_name: str, tenant: str, **args) -> Any:
        try:
            return await erp.call(tool_name, {"tenant": tenant, **args})
        except ErpUnavailable as err:
            raise UserFacingError(UNAVAILABLE) from err

    async def record(tenant: str, req: dict, event: str, actor: str, reason: str | None = None):
        await call("record_approval_event", tenant, req_id=req["req_id"], version=req["version"],
                   event=event, actor=actor, reason=reason)

    def expired(req: dict) -> bool:
        now = clock()
        return any(now >= line["quote_expires_at_ts"] for line in req["lines"])

    async def requote(tenant: str, req: dict, quantities: dict[str, int], *, all_lines: bool) -> bool:
        """Re-quote changed (or every) line and write a new version. True if prices were re-quoted."""
        now, lines, requoted = clock(), [], False
        for line in req["lines"]:
            quantity = quantities.get(line["sku"], line["quantity"])
            stale = now >= line["quote_expires_at_ts"]
            if all_lines or stale or quantity != line["quantity"]:
                quote = await call("get_price_quote", tenant, sku=line["sku"], quantity=quantity)
                lines.append({"quote_id": quote["quote_id"]})
                requoted = requoted or quantity == line["quantity"]
            else:
                lines.append({"quote_id": line["quote_id"]})
        await call("update_requisition", tenant, req_id=req["req_id"], lines=lines)
        return requoted

    async def rebuild(tenant: str, pending: dict, quantities: dict[str, int], *, all_lines: bool):
        """Write a new version and send it back to policy for a fresh decision."""
        requoted = await requote(tenant, pending["req"], quantities, all_lines=all_lines)
        return Command(goto="policy", update={"pending": {**pending, "requoted": requoted}})

    async def explain_tool_error(tenant: str, pending: dict, err: ErpToolError) -> Command:
        try:
            await call("get_requisition", tenant, req_id=pending["req_id"])
        except ErpToolError:
            return Command(goto="agent", update=_answer(pending, EXPIRED))
        return Command(goto="agent", update=_answer(pending, f"Error: {err}"))

    # ---------------------------------------------------------------- nodes

    def ask(state: State) -> Command[Literal["agent", "ask", "__end__"]]:
        """Wait for the visitor's next message (the reused interrupt `ask`)."""
        update = ask_for_text(state)
        text = str(update["messages"][0][1]).strip()
        if not text:
            return Command(goto="ask")
        reset = {"tool_rounds": 0, "proposals": 0}
        if text.lower() == STOP_WORD:
            return Command(goto=END, update={**update, **reset})
        return Command(goto="agent", update={**update, **reset})

    async def agent(state: State, config: RunnableConfig) -> Command[Literal["tools", "policy", "ask"]]:
        rounds = state.get("tool_rounds", 0)
        proposals = state.get("proposals", 0)
        llm = (llm_factory or get_llm)()
        # Up to MAX_TOOL_ROUNDS tools passes; the call after the last one must answer in text.
        capped = rounds >= MAX_TOOL_ROUNDS or proposals >= MAX_PROPOSALS
        llm = llm.bind_tools(tools, tool_choice=NO_TOOLS) if capped else llm.bind_tools(tools)
        reply = declined_or(await llm.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]], config))
        calls = reply.tool_calls
        if capped and calls:
            # Defence in depth: a model that ignores tool_choice still cannot pass the caps.
            reply = AIMessage(reply.text.strip() or STEP_LIMIT)
            calls = []
        if not calls:
            return Command(goto="ask", update={"messages": [reply]})
        if len(calls) == 1 and calls[0]["name"] == "propose_order":
            args = calls[0]["args"]
            pending = {"call_id": calls[0]["id"], "req_id": args.get("req_id"),
                       "summary": str(args.get("summary") or ""), "requoted": False}
            return Command(goto="policy", update={"messages": [reply], "pending": pending,
                                                  "approval": None, "proposals": proposals + 1})
        return Command(goto="tools", update={"messages": [reply], "tool_rounds": rounds + 1})

    async def policy(state: State, config: RunnableConfig) -> Command[Literal["submit_po", "approval", "agent"]]:
        tenant, pending = _tenant(config), state["pending"]
        try:
            req = await call("get_requisition", tenant, req_id=pending["req_id"])
        except ErpToolError:
            return Command(goto="agent", update=_answer(pending, EXPIRED))
        if req["status"] != "draft":
            return Command(goto="agent", update=_answer(
                pending, f"{req['req_id']} was already ordered as {req.get('po_number')}."))
        try:
            # Card time (and auto-approval time): expired quotes are re-quoted
            # here, so the version a person or the policy decides on is fresh.
            if expired(req):
                await requote(tenant, req, {}, all_lines=True)
                req = await call("get_requisition", tenant, req_id=pending["req_id"])
                pending = {**pending, "requoted": True}
        except ErpToolError as err:
            return await explain_tool_error(tenant, pending, err)
        pending = {**pending, "req": req}
        try:
            if not order_policy.needs_person(req["total_zar"], auto_limit_zar):
                await record(tenant, req, "auto_approved", "policy",
                             order_policy.reason(req["total_zar"], auto_limit_zar))
                approval = {"approver": "policy", "reason": "under limit", "req_id": req["req_id"],
                            "version": req["version"], "content_hash": req["content_hash"]}
                return Command(goto="submit_po", update={"pending": pending, "approval": approval})
            budget = await call("check_budget", tenant, cost_centre=req["cost_centre"])
        except ErpToolError as err:
            return await explain_tool_error(tenant, pending, err)
        pending["budget_remaining"] = budget["remaining"]
        return Command(goto="approval", update={"pending": pending})

    async def approval(state: State, config: RunnableConfig) -> Command[Literal["submit_po", "policy", "agent"]]:
        tenant, pending = _tenant(config), state["pending"]
        req = pending["req"]
        try:
            # Everything up to interrupt() re-runs on resume, so it only reads
            # (plus approval_requested, once per version). Quotes were checked
            # in policy; a decision sent after they expire is still honoured.
            trail = await call("get_audit_trail", tenant, req_id=req["req_id"])
            if not any(e["event"] == "approval_requested" and e["version"] == req["version"]
                       for e in trail):
                await record(tenant, req, "approval_requested", "agent",
                             order_policy.reason(req["total_zar"], auto_limit_zar))

            decision = interrupt(_card(pending, auto_limit_zar))

            kind = decision.get("decision") if isinstance(decision, dict) else None
            if kind == "edit":
                skus = {line["sku"] for line in req["lines"]}
                edits = decision.get("edits") or []
                quantities = {e.get("sku"): e.get("quantity") for e in edits if isinstance(e, dict)}
                if not quantities or any(
                        sku not in skus or isinstance(q, bool) or not isinstance(q, int)
                        or not 1 <= q <= 999 for sku, q in quantities.items()):
                    raise UserFacingError(BAD_EDITS)
                return await rebuild(tenant, pending, quantities, all_lines=False)
            if kind == "reject":
                approver = _approver(config)
                reason = str(decision.get("reason") or "").strip()
                await record(tenant, req, "rejected", approver, reason or None)
                return Command(goto="agent", update=_answer(
                    pending, f"The approver rejected this order. Reason: {reason or 'none given'}."))
            if kind == "approve":
                approver = _approver(config)
                if expired(req):
                    return await rebuild(tenant, pending, {}, all_lines=True)
                await record(tenant, req, "approved", approver, "approved")
                return Command(goto="submit_po", update={"approval": {
                    "approver": approver, "reason": "approved", "req_id": req["req_id"],
                    "version": req["version"], "content_hash": req["content_hash"]}})
            raise UserFacingError(BAD_DECISION)
        except ErpToolError as err:
            return await explain_tool_error(tenant, pending, err)

    async def submit_po(state: State, config: RunnableConfig) -> Command[Literal["ask", "agent"]]:
        tenant, pending, ok = _tenant(config), state["pending"], state["approval"]
        token = issue_token({
            "req_id": ok["req_id"], "version": ok["version"], "content_hash": ok["content_hash"],
            "tenant": tenant, "approver": ok["approver"], "requested_by": "agent",
            "reason": ok["reason"]})
        try:
            po = await call("submit_purchase_order", tenant, req_id=ok["req_id"],
                            version=ok["version"], approval_token=token,
                            idempotency_key=f"{ok['req_id']}:{ok['version']}")
        except ErpToolError as err:
            return Command(goto="agent", update=_answer(pending, f"The ERP refused the order: {err}"))
        try:
            trail = await call("get_audit_trail", tenant, req_id=ok["req_id"])
        except ErpToolError:
            trail = []
        update = _answer(pending, _compact(po))
        update["messages"].append(AIMessage(
            f"Purchase order {po['po_number']} placed: {_describe(pending['req']['lines'])} for "
            f"{order_policy.format_zar(po['total_zar'])} on {po['cost_centre']}."))
        update["audit"] = trail
        return Command(goto="ask", update=update)

    builder = StateGraph(State)
    builder.add_node("ask", ask)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("policy", policy)
    builder.add_node("approval", approval)
    builder.add_node("submit_po", submit_po)
    builder.add_edge(START, "ask")
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


def make_graph():
    """The graph for `langgraph dev`, against a separate ERP server over HTTP."""
    from agentic_solutions.common.approval_tokens import issue
    from agentic_solutions.mcp_servers.erp.config import ErpSettings

    url = os.environ.get("ERP_MCP_URL")
    secret = os.environ.get("ERP_APPROVAL_SECRET")
    if not url or not secret:
        raise RuntimeError(
            "The approval agent needs ERP_MCP_URL (e.g. http://127.0.0.1:8765/mcp) and the "
            "ERP_APPROVAL_SECRET the ERP server was started with.")
    key = secret.encode("utf-8")
    return build_graph(erp=HttpErpClient(url), issue_token=lambda claims: issue(claims, key),
                       auto_limit_zar=ErpSettings.from_env().auto_limit_zar)


def __getattr__(name: str):
    # Built on first access (langgraph.json reads `graph`), so importing this
    # module never needs the ERP or its settings. Building does not connect.
    if name == "graph":
        globals()["graph"] = built = make_graph()
        return built
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
