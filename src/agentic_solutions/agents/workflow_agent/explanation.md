# Workflow

## What it is
A workflow is a fixed pipeline: the steps and their order are written in code, and the program, not the model, decides what runs next. Models may do the work inside a step, such as extracting fields from text, but the path through the graph is known before the request arrives. The only branches are checks on data, such as "is this record valid?".

The dividing line from Planning: **in a workflow the steps are fixed in code.** In [[cognitive/planning]] the model writes the steps at run time.

## When to use it
- You can list the steps before the request arrives, as in an extract, validate, transform, load job.
- You need the same path every time, so results are predictable and easy to test.
- Failures should follow a known route, such as a quarantine step, instead of a model improvising.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The line from Planning is visible in the shape: [[cognitive/planning]] has a planner node that writes the steps, while here every step is a node wired in code and nothing writes a plan.

- `extract` reads the raw records.
- `validate` checks them. Its router sends control to `transform` when the data is fine, or to `handle_error` when it is not.
- `transform` reshapes the valid records, then `load` writes them out and the run ends.
- `handle_error` reports or quarantines the problem, then the run ends.

The skeleton's router is fixed to `transform`, so the diagram shows both branches without running them.

## LangGraph concepts
A live version would use:
- **Edges**: `add_edge` wires the fixed steps in order, which is what makes this a workflow and not an agent.
- **Conditional edges**: the router, annotated `Literal["transform", "handle_error"]`, branches on the validation result.
- **RetryPolicy**: `langgraph.types.RetryPolicy` can be set on a node so a flaky step is retried before the run fails.
- **State**: carries the records, the error list and the loaded count from step to step.

## Trade-offs
- Predictable and testable, but it only handles the cases its author thought of.
- A new kind of input means changing the code, because nothing re-plans.
- Cheap to run when steps are plain code, because only steps that need a model call one.
- Order matters. Moving `validate` after `load` would write bad data.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("extract", extract)
builder.add_node("validate", validate)
builder.add_node("transform", transform)
builder.add_node("load", load)
builder.add_node("handle_error", handle_error)

builder.add_edge(START, "extract")
builder.add_edge("extract", "validate")
builder.add_conditional_edges("validate", route_validate)
builder.add_edge("transform", "load")
builder.add_edge("load", END)
builder.add_edge("handle_error", END)

return builder.compile()
```

## Try this
- Which State field would `validate` fill so that the router can pick `handle_error`? Answer with its name from the skeleton.
- Suppose a new step, `deduplicate`, must run after `validate` and before `transform`. `validate` reaches `transform` through a router branch, not an `add_edge`. Which router branch do you change, and which new edge do you add? (Answer: the router's `transform` branch now returns `deduplicate`, and you add the edge `deduplicate` -> `transform`.)
- Compare with [[cognitive/planning]]: if the steps cannot be listed before the request arrives, which of the two patterns fits, Workflow or Planning?
