# Approval

## What it is
The Approval pattern requires a person to approve an action before it can be executed.

The agent can analyse information and prepare a recommendation, but it cannot perform the action. The workflow pauses until an authorised person approves, modifies, or rejects the proposal.

Only approved actions can be executed. Approval is enforced by the platform, ensuring that people remain accountable for important decisions.

## When to use it
- Actions that spend money, change records, contact people or are hard to undo, such as purchases, payments, emails and deletions.
- Decisions that a named person must be accountable for.
- Work where the agent's analysis is useful, but it is not yet trusted to act alone on high-risk cases.
- Combine it with [[governance/audit]] to record who approved what, and when.
- Not when every action is low-risk and easy to reverse. A person in the loop then adds delay and approval fatigue without reducing risk.

## How it works
Roles:
- **Agent**: gathers information and prepares proposals. It cannot perform the action.
- **Tools**: read-only or draft-only functions that the agent may use freely.
- **Policy**: decides whether a proposal needs a person, using rules such as an amount limit, a budget or a risk rating.
- **Approver**: an authorised person who sees the exact proposal and decides.
- **Executor**: the only component that can perform the action.
- **System of record**: holds the business data and refuses any action that was not approved.
- **Audit log**: records every proposal and decision.

Flow:
1. The agent uses read-only and draft tools to prepare its work.
2. The agent proposes an action with exact details.
3. Policy approves a low-risk proposal automatically, or pauses the workflow for a person.
4. The approver approves, modifies or rejects the proposal.
5. A modified proposal goes back to policy and needs its own decision.
6. A rejected proposal goes back to the agent with the reason.
7. An approved proposal lets the executor perform exactly what was approved.
8. The audit log records each step.

## Design considerations
- **Least privilege:** the agent never holds the ability to perform the action. Only the executor does, and only after approval.
- **Bind approval to the exact proposal:** an approval covers these details and no others. Any change needs a new approval.
- **Expiry:** approvals and prices go out of date. Give each an expiry and check it again before acting.
- **Re-check before acting:** confirm budget, price and availability just before the action runs.
- **Act only once:** a retry or a resumed workflow must not perform the action twice.
- **Durable pause:** save the workflow's state while it waits. Approval can take minutes or days, and systems may restart in between.
- **Separation of duties:** whoever proposes an action cannot approve it.
- **Clear presentation:** show the approver what will happen, to whom, for how much, and why.
- **Audit everything:** record proposals, decisions, changes, rejections and actions, with who and when.
- **Defence in depth:** the system of record checks the approval too, so a fault elsewhere cannot bypass it.

## Trade-offs
- Delay: the workflow waits for a person, which can take minutes or days.
- Approval fatigue: when too many requests need a person, approvers stop reading them. Policy limits keep low-risk cases automatic.
- More states to manage: pending, expired, modified and rejected proposals all need handling.

## Related patterns
- The dividing line: Approval is a person signing off at a pause, before the action runs. [[governance/review]] is a separate agent or person checking a finished result, who can send it back for rework.
- [[governance/guardrails]] blocks unsafe input or output automatically. Approval puts a person at the decision.
- [[governance/audit]] keeps the lasting record of each proposal and decision.
- [[cognitive/react]] is the reason-and-act loop that usually produces the proposals.
- [[execution/tool-use]] provides the read-only and draft tools the agent uses.

## How this Studio implements it

### Mapping
- **Agent** → `agent`: the model. It may use the ERP's read and draft tools, plus `propose_order`, which ends its turn.
- **Tools** → `tools`: runs the catalogue, budget, quote and requisition calls on the mock ERP over MCP.
- **Policy** → `policy`: re-reads the requisition and approves it automatically at R5,000 or less. Larger orders go to `approval`.
- **Approver** → you, at `approval`: the run pauses on a card with the exact lines, total and remaining budget. You approve, edit or reject.
- **Executor** → `submit_po`: the only node that calls `submit_purchase_order`. It sends a token bound to the approved version.
- **System of record** → the mock ERP MCP server. It checks the token itself and refuses anything that was not approved.
- **Audit log** → the ERP's audit trail, shown in the state view after an order is placed. `approval_requested` is recorded once per version, so a re-proposal of the same version after a reject is not recorded again.
- **Between requests** → `ask`: waits for your next message.
- **Limitation:** you both ask for the order and approve it, so this demo has no real separation of duties. A real deployment takes the approver's identity from an identity provider.

### Framework concepts
- **`interrupt()` and `Command(resume=...)`:** `approval` calls `interrupt()` with the card's data, and the run pauses. The Studio resumes it with `Command(resume={"decision": ...})`, and `interrupt()` returns that decision.
- **Re-run on resume:** LangGraph runs `approval` again from its first line. So before the pause the node only reads, apart from recording `approval_requested` once per version. Every other write happens after the decision.
- **Checkpointer as a durable pause:** the paused run is saved in the SQLite checkpointer, not held in memory. A page reload rebuilds the card from the saved state.
- **Prebuilt tool node:** `tools` is LangGraph's `ToolNode`. It runs the model's tool calls and returns each result as a message.
- **`Command(goto=...)` routing:** each node returns a `Command` that names the next node, so the route follows the decision.
- **MCP client:** the ERP is a separate MCP server, in-process by default or over HTTP. The model's tools omit the `tenant` argument; the wrapper fills it from the thread id. The model never sees `submit_purchase_order`, `record_approval_event` or a token.
- **Quote expiry:** quotes last 30 minutes. `policy` re-quotes expired lines before it decides or shows the card. An approve that arrives after a quote expired is re-quoted and sent back to `policy`. The ERP checks expiry again at submit.

### Key code
How `approval` handles the decision that `interrupt()` returned:
```python
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
```

### Try this
- Send `Order 12 laptops for the Cape Town office under CT-OPS`. The total is over R5,000, so the run pauses at `approval`. Approve it, and `submit_po` places the order.
- Send `Order 3 keyboards for CT-OPS`. The total is under the limit, so `policy` approves it and the order is placed with no pause.
- Send `Order 40 monitors for JHB-FIN` and approve it. The ERP refuses it as over budget, and the agent explains that nothing was ordered.
- Send the monitors order again. On the card, choose Edit and set the quantity to 1. The new total of R2,900 is under the limit, so `policy` approves the edited version and the order is placed.
