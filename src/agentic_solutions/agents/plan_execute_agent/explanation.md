# Planning

## What it is
Planning, in its plan-and-execute form, splits a task into two phases. First the model writes a short plan: a list of steps. Then the steps are carried out one at a time, each with the goal and the earlier results as context. A last step turns the results into the final answer. Planning first keeps a long task on track and lets you show the plan to a person before any work starts.

The dividing line from Workflow: **in Planning the model writes the steps at run time.** In [[execution/workflow]] the steps are fixed in code. If you can write the steps down before the request arrives, you want a workflow.

## When to use it
- The task needs several distinct steps, and the steps depend on the request.
- You want the plan visible: for review, for progress display, or for debugging.
- A step-by-step loop like [[cognitive/react]] tends to lose the goal over a long task.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The line from Workflow: here the model writes the steps at run time, in `planner`. In [[execution/workflow]] the steps are fixed in code.

- `planner` turns the goal into a short list of steps.
- `executor` works on the current step. Its router has three exits: `tools` if the step needs a tool call, back to `executor` when a step finished and more remain, and `synthesizer` when all steps are done.
- `tools` runs the requested calls and returns to `executor`.
- `synthesizer` writes the final answer from the step results, then the graph ends.

The skeleton's router is fixed to `synthesizer`, so the diagram shows every path without running them. A live version would also let `executor` see the plan and the results so far.

## LangGraph concepts
A live version would use:
- **Conditional edges**: a router annotated `Literal["tools", "executor", "synthesizer"]` picks among the three exits.
- **Structured output**: the plan comes back as a typed list of steps, not free text.
- **ToolNode**: `langgraph.prebuilt.ToolNode` runs the executor's tool calls.
- **State**: holds the plan, a current-step index and a list of results.
- **Replanning**: a variation where a node revises the remaining steps after a surprise. The skeleton has no such node.

## Trade-offs
- An extra model call up front, and a bad plan sends every later step the wrong way.
- Less adaptive than a pure reasoning loop, because the plan is fixed unless you add replanning.
- Plans of two to five steps work best. Very long plans are often wrong.
- Easier to inspect and cheaper to resume than an open loop.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("planner", planner)
builder.add_node("executor", executor)
builder.add_node("tools", tools)
builder.add_node("synthesizer", synthesizer)

builder.add_edge(START, "planner")
builder.add_edge("planner", "executor")
builder.add_conditional_edges("executor", route_after_executor)
builder.add_edge("tools", "executor")
builder.add_edge("synthesizer", END)

return builder.compile()
```

## Try this
- Write a plan for "compare two laptops and recommend one". Which step would need `tools`, and which would not?
- A step fails halfway through. Where in this diagram would a replanning node go?
- Compare with [[execution/workflow]] (fixed steps) and [[cognitive/search]] (several candidate plans scored against each other).
