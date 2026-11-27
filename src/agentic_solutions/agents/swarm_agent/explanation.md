# Swarm

## What it is
A swarm is a group of peer agents that hand control to each other directly. Each agent either answers the user or passes the conversation to a better-suited peer, and the receiving agent carries on from there. There is no manager choosing who goes next. The agents themselves decide, usually by calling a handoff tool or returning a handoff.

The dividing line from the other two multi-agent patterns: **Swarm has no coordinator at all.** [[collaboration/supervisor]] has one coordinator that routes every step, and [[collaboration/hierarchy]] stacks supervisors of supervisors.

## When to use it
- Distinct specialists should own the conversation in turn, such as billing then technical support.
- Control is naturally decided by whoever is working, not by a central planner.
- You want fewer hops than a supervisor, because there is no coordinator call between agents.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The line from [[collaboration/supervisor]] is visible in the shape: no node coordinates, and `billing` and `technical` hand off to each other directly.

`triage` is only the entry point. It is not a manager. After it hands off, control moves between peers.

- `triage` answers simple questions or hands off. Its router goes to `billing`, `technical`, or the end.
- `billing` handles money questions. It can hand off to `technical` or finish.
- `technical` handles faults and setup. It can hand off to `billing` or finish.

The `billing` and `technical` edges to each other are the swarm: peers pass work sideways, with no node in the middle. The skeleton's routers are fixed to the end, so the diagram shows the handoffs without running them. A live version would track which agent is active.

## LangGraph concepts
A live version would use:
- **Command**: a node returns `langgraph.types.Command` with `goto` set to a peer's name, plus a state update, to hand off in one step.
- **State**: records the active agent, so a later turn resumes with the right peer.
- **Checkpointing**: saves the active agent between turns in the same conversation.
- **Conditional edges**: the routers, annotated with `Literal` targets, draw the possible handoffs in the diagram.

## Trade-offs
- No central view. Following who did what, and why, is harder than with a supervisor.
- Handoffs can ping-pong between peers. A live version needs a limit.
- Each agent must know when to hand off and to whom, so peer descriptions need care.
- It avoids the coordinator hop, so simple handoffs can be quicker and cheaper.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
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

## Try this
- A customer asks about a failed payment caused by an app bug. Trace which agents handle it, and which handoffs happen, using only the edges in the diagram.
- Which State field says who is active? What goes wrong if it is not saved between turns?
- Compare with [[collaboration/single-agent]], the live baseline: one agent holds every tool. When would splitting into peers help?
