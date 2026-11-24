# Approval

## What it is
A person signs off before an agent's consequential action takes effect. The agent may only propose such an action with exact parameters; when policy requires a person, the run pauses durably with the proposal, an approver approves, edits or rejects it, and only a separate executor can carry out exactly what was approved. Enforcement does not rest on the agent's good behaviour: the agent never holds the commit capability, and the system of record refuses anything unapproved.

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
This demo currently shows only the pause mechanism: the run pauses for your input and resumes when you reply. The full approval demo (a proposal, approve, edit or reject, and enforcement at the system of record) comes later.

- **The person the paused run waits for** → you: `ask` pauses and resumes with your reply.
- **Agent** → `answer` (replies to your turn, then returns to `ask`; no proposals yet).
- **Durable pause** → the checkpointer saves the paused run, one `thread_id` per chat.
- **Tools, policy, executor, system of record, audit log** → not in this demo yet.

### Framework concepts
- **interrupt(value)**: pauses the graph and shows `value` to the caller.
- **Command(resume=x)**: resumes the graph. Inside the node, `interrupt()` returns `x`.
- **Checkpointer**: storage for the paused state. Without one, `interrupt()` raises an error.
- **thread_id**: names one conversation, so many chats can share one graph, each with its own saved state.
- **Re-run rule**: on resume the paused node restarts from its first line, so any code before `interrupt()` must be safe to run twice. A side effect there (sending an email, charging a card) would happen twice.

### Key code
```python
def ask(state: State) -> dict:
    text = interrupt(QUESTION_PROMPT)
    return {"messages": [("user", text)]}

builder = StateGraph(State)
builder.add_node("ask", ask)
builder.add_node("answer", answer)

builder.add_edge(START, "ask")
builder.add_conditional_edges("ask", route_after_ask)
builder.add_edge("answer", "ask")

return builder.compile(checkpointer=checkpointer)
```

### Try this
- Send any question. Watch the run pause at `ask`, then continue to `answer` once you reply.
- Look for the "resumed" mark on `ask` in the trace after you send a message.
- Send a message containing only spaces. The graph returns to `ask` and pauses again with no model call.
- Type `stop`. The run goes to `__end__`.
