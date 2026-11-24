# Approval

## What it is
The agent can suggest an important action, such as placing an order or making a payment, but it cannot carry it out on its own. When the action is big enough to need a sign-off, the work stops and a person sees exactly what the agent wants to do. They approve it, change it or turn it down, and only what they approved goes ahead. The system that does the work checks for that approval itself, so even a confused or tricked agent cannot skip it.

## When to use it
- Actions that spend money, change records, contact people or are hard to undo: purchases, payments, emails, deletions.
- When accountability matters and a named person must own the decision.
- When the agent's judgement is useful but not yet trusted to act alone on high-risk cases.
- Pair it with [[governance/audit]] to record who approved what, and when.
- Not when every action is low-risk and reversible. A person in the loop then adds delay and approval fatigue without reducing real risk.

## How it works
Roles:
- **Agent**: plans and gathers information, and may only propose consequential actions.
- **Tools**: read-only or draft-only capabilities the agent may use freely.
- **Policy**: decides whether a proposal needs a person, using an amount threshold, a budget or a risk rating.
- **Approver**: a person who sees the exact proposal and decides.
- **Executor**: the only component able to perform the consequential action.
- **System of record**: holds the data, and independently refuses unapproved commits.
- **Audit log**: records every proposal and decision.

Flow:
1. The agent works with read-only and draft tools.
2. The agent proposes an action with exact parameters.
3. Policy either auto-approves a low-risk proposal or pauses the run with the proposal.
4. The approver approves, edits or rejects.
5. Edit changes the proposal and returns it to policy, so the edited proposal needs its own approval.
6. Reject returns to the agent with the reason.
7. Approve lets the executor perform exactly the approved proposal.
8. Every step is recorded in the audit log.

## Design considerations
- **Least privilege:** the agent never holds the commit capability. Only the executor does, and only after approval.
- **Bind approval to the exact proposal:** the approval covers these parameters and no others. Any change invalidates it.
- **Expiry:** approvals and quotes go stale. Give each an expiry and re-check it at execution time.
- **Re-validate at execution:** check budget, price and availability again just before acting.
- **Idempotent execution:** a retry or a resumed run must not perform the action twice.
- **Durable pause:** the run's state is saved while it waits. Approval may take minutes or days, and the process may restart in between.
- **Separation of duties:** the proposer cannot approve its own proposal.
- **Clear presentation:** show the approver what will happen, to whom, for how much and why.
- **Audit everything:** proposals, decisions, edits, rejections and executions, with who and when.
- **Defence in depth:** the system of record checks the approval too, so a bug upstream cannot commit on its own.

## Trade-offs
- Latency and human time: the run waits for a person.
- Approval fatigue: too many requests and approvers stop reading. Policy thresholds keep low-risk cases automatic.
- More states to manage: pending, expired, edited and rejected proposals all need handling.

## Related patterns
- The dividing line: Approval is a person signing off at a pause point before the run goes on. [[governance/review]] is a separate agent or person checking the finished result, who can send it back for rework.
- [[governance/guardrails]] blocks unsafe input or output automatically; Approval puts a person at the decision.
- [[governance/audit]] keeps the durable record of each proposal and decision.
- [[cognitive/react]] is the reason-and-act loop that typically produces the proposals.
- [[execution/tool-use]] supplies the read-only and draft tools the agent works with.

## How this Studio implements it

### Mapping
- **Agent** → `agent`: the model, bound to the read-only and draft ERP tools plus `propose_order`, which ends its turn.
- **Tools** → `tools`: runs the catalogue, budget, quote and draft calls on the mock ERP over MCP.
- **Policy** → `policy`: re-reads the requisition and auto-approves at or under R5,000; anything larger goes on to `approval`.
- **Approver** → you, at `approval`: the run pauses with the exact lines, total and budget, and resumes with approve, edit or reject.
- **Executor** → `submit_po`: the only node that calls `submit_purchase_order`, with a token bound to the approved version.
- **System of record and audit log** → the mock ERP server: it checks the token itself and records every step.
- **The person's next message** → `ask` waits for your next order between turns.

### Framework concepts
- **interrupt(value)**: `approval` pauses with the card's data; resuming with `Command(resume=decision)` returns the decision.
- **Re-run rule**: on resume `approval` restarts from its first line, so before the pause it only reads.
- **Command(goto=...)**: each node picks the next one, so the edges follow the decision.
- **MCP client**: the ERP is a separate server; the model sees only the read and draft tools, never the submit tool.

### Key code
```python
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
```

### Try this
- Send `Order 12 laptops for the Cape Town office under CT-OPS`. The total is over R5,000, so the run pauses at `approval`; approve it and `submit_po` places the order.
- Send `Order 3 keyboards for CT-OPS`. It is under the limit, so `policy` approves it and the order is placed with no pause.
- Send `Order 40 monitors for JHB-FIN` and approve it. The ERP refuses it as over budget, and the agent explains why nothing was ordered.
