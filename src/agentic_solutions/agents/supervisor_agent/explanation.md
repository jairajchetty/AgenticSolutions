# Supervisor

## What it is
A supervisor is a coordinator model that manages specialist workers. This is the orchestrator-workers pattern: the coordinator reads the task and the progress so far, chooses which worker runs next, reads what came back, and decides when the job is finished. The workers do not talk to each other. Everything passes through the coordinator.

The dividing line from the other two multi-agent patterns: **Supervisor has exactly one coordinator.** [[collaboration/hierarchy]] adds supervisors of supervisors, and [[collaboration/swarm]] has no coordinator at all.

## When to use it
- The task splits into distinct roles, such as research then writing, and the order is not known in advance.
- You want one place that decides what happens next, so behaviour is easy to follow and to log.
- A single agent with every tool is getting confused by too many options.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The lines from [[collaboration/hierarchy]] and [[collaboration/swarm]] are visible in the shape: every edge runs through `supervisor`, the single coordinator, and no worker links to another worker.

- `supervisor` reads the state and picks the next step. Its router sends control to `researcher`, to `writer`, or to the end when the work is done.
- `researcher` gathers material and returns to `supervisor`.
- `writer` produces a draft and returns to `supervisor`.

The skeleton's router is fixed to the end, so the diagram shows the delegation loops without running them. A live version would bound the number of rounds.

## LangGraph concepts
A live version would use:
- **Conditional edges**: the router, annotated `Literal["researcher", "writer", "__end__"]`, follows the coordinator's choice.
- **Command**: a node can return `langgraph.types.Command` with `goto` to name the next node and update state in one step. That is an alternative to a separate router.
- **Structured output**: asks the coordinator model for a typed choice of worker, which is safer than parsing free text.
- **State**: holds the task, shared notes and the draft that the workers read and write.

## Trade-offs
- Every step goes back through the coordinator, which adds a model call and latency per hop.
- The coordinator is a single point of failure. A wrong choice sends the whole run the wrong way.
- Clear worker descriptions matter. The coordinator can only pick well between roles it understands.
- Simpler to reason about than a swarm, but it does not scale to very many workers in one prompt. That is where a hierarchy can help.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("supervisor", supervisor)
builder.add_node("researcher", researcher)
builder.add_node("writer", writer)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route_supervisor)
builder.add_edge("researcher", "supervisor")
builder.add_edge("writer", "supervisor")

return builder.compile()
```

## Try this
- Suppose the task is "write a short report on tides". Which worker should the supervisor pick first, and what in `notes` tells it to pick `writer` next?
- The state has `notes` and `draft`. What would the supervisor look at to decide the work is done?
- Compare with [[collaboration/single-agent]], the live baseline: one agent, no delegation. What does a coordinator add, and what does it cost?
