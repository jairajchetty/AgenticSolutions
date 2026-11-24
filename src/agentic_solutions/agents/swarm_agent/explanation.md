# Swarm

## What it is
A group of peer agents that hand control to each other directly. Each agent either answers or passes the conversation to a better-suited peer, which carries on from there. No manager chooses who goes next: the active agent decides, typically by calling a handoff tool or returning a handoff. The system usually remembers which agent is active, so the next user turn goes straight to it.

## When to use it
- Distinct specialists should own the conversation in turn, such as refunds and then troubleshooting.
- Who acts next is best decided by the agent doing the work, not by a central planner.
- Fewer hops matter: there is no coordinator call between agents.
- Not when one place must decide and account for every step. Without a coordinator, the overall flow is harder to predict, constrain and audit.

## How it works
Roles:
- **Entry agent**: receives the first turn and answers it or hands it off. It is a peer, not a manager.
- **Specialist peers**: each with its own instructions and tools, and a list of peers it may hand off to.
- **Active-agent record**: notes who currently holds the conversation.

Flow:
1. The entry agent reads the request and answers it, or hands off to a peer.
2. A handoff updates the active-agent record and passes the conversation on.
3. The active peer works on the request, then answers or hands off to another peer.
4. The next user turn goes to whichever agent is active.

## Design considerations
- **Handoff targets:** letting any agent reach any other is flexible; listing each agent's allowed targets keeps the flow predictable and easier to test.
- **What moves with a handoff:** passing the full conversation keeps context; passing a summary keeps the receiver focused but can drop detail.
- **Handoff limit:** peers can bounce a request back and forth. Cap handoffs per turn, or detect repeats.
- **Peer descriptions:** each agent decides on its own when and to whom to hand off, so it needs a clear picture of what each peer handles.
- **Persisting the active agent:** save it with the conversation, or the next turn starts over at the entry agent.
- **Observability:** with no central view, log each handoff with its reason so the run can be followed afterwards.

## Trade-offs
- No central view: following who did what, and why, is harder than with a coordinator.
- Handoffs can loop between peers without a limit.
- Avoids a coordinator hop, so a simple handoff can be quicker and cheaper.
- Adding a peer means updating the handoff knowledge of every agent that should reach it.

## Related patterns
- The dividing line across the three multi-agent patterns: Swarm has no coordinator at all. [[collaboration/supervisor]] has one coordinator that routes every step, and [[collaboration/hierarchy]] stacks supervisors of supervisors.
- [[execution/routing]] makes one up-front choice of specialist; in a swarm the specialists keep choosing as the conversation goes on.
- [[collaboration/single-agent]] is the baseline: one agent, no handoffs.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Entry agent** → `triage`: would answer simple questions or hand off. Its router goes to `billing`, `technical` or `__end__`.
- **Specialist peers** → `billing`, which would handle invoices and refunds, and `technical`, which would handle faults and setup. Each can hand off to the other or finish.
- **Active-agent record** → the `active_agent` state key.
- All three routers are fixed to `__end__`, so the handoffs are drawn but never run.

### Framework concepts
- **Command**: a live node would return `langgraph.types.Command` with `goto` set to a peer's name, plus a state update, to hand off in one step.
- **Conditional edges**: each router is annotated with its `Literal` targets, which is how the diagram draws the possible handoffs.
- **Checkpointing**: would save `active_agent` between turns of the same conversation.

### Key code
```python
builder = StateGraph(State)
builder.add_node("triage", triage)
builder.add_node("billing", billing)
builder.add_node("technical", technical)

builder.add_edge(START, "triage")
builder.add_conditional_edges("triage", route_triage)
builder.add_conditional_edges("billing", route_billing)
builder.add_conditional_edges("technical", route_technical)

return builder.compile()
```

### Try this
- A customer asks about a failed payment caused by an app bug. Using only the edges in the diagram, trace which agents handle it and which handoffs happen.
- What goes wrong on the next turn if `active_agent` is not saved?
- Compare with [[collaboration/supervisor]], where every handoff would pass through one coordinator.
