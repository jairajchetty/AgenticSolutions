# Planning

## What it is
The model breaks a goal into steps before acting, then carries the steps out. A planning phase produces the plan; an execution phase works through it, each step with the goal and earlier results as context; a final phase composes the answer from the results. The plan is written at run time for this particular request, and it can be shown, checked or edited before any work starts.

## When to use it
- The task needs several distinct steps, and which steps depends on the request.
- The plan should be visible: for a person to review, for progress display, or for debugging.
- A step-at-a-time loop tends to lose the goal over a long task.
- Not when the steps are the same for every request. Write them in code instead; a plan the model must rediscover each time only adds cost and variance.

## How it works
Roles:
- **Planner**: turns the goal into a plan.
- **Executor**: carries out one step at a time, using tools where a step needs them.
- **Tools**: the capabilities a step may call.
- **Synthesizer**: composes the final answer from the step results.

Flow:
1. The planner reads the goal and writes the plan.
2. The executor takes the next step, with the goal and the results so far as context.
3. If the step needs a tool, the call runs and its result returns to the executor.
4. When a step finishes, its result is recorded and the executor moves to the next step.
5. When every step is done, the synthesizer writes the answer.

## Design considerations
- **Plan shape:** an ordered list is simple to show and follow; a dependency graph lets independent steps run in parallel; a hierarchy of goals and sub-goals suits large tasks but is harder to keep consistent. Choose the simplest shape that fits the work.
- **When to replan:** a fixed plan is predictable and cheap; replanning after every step adapts to surprises at the cost of one model call per step; replanning only on failure or on an unexpected result sits between the two.
- **How each step runs:** a single model call is cheapest; a short reason-and-act loop per step handles steps that need several tool calls.
- **Plan length:** short plans are easier to get right. Long plans made in one shot accumulate errors in later steps.
- **Context per step:** passing every earlier result is simple but grows the prompt; passing only the results a step depends on keeps it lean.
- **Human checkpoint:** a plan is a natural point to pause for approval before any action is taken.

## Trade-offs
- An extra model call up front, and a bad plan sends every later step the wrong way.
- Less adaptive than a step-at-a-time loop unless replanning is added.
- Easier to inspect, display and resume than an open loop.

## Related patterns
- The dividing line with [[execution/workflow]]: in Planning the model writes the steps at run time. In Workflow the steps are fixed in code. If the steps can be written down before the request arrives, a workflow fits better.
- [[cognitive/react]] chooses one step at a time with no plan, and can serve as the executor for each step.
- [[cognitive/search]] generates several candidate paths and scores them, instead of committing to one plan.
- [[governance/approval]] can pause the run so a person signs off on the plan.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it. The Studio's planning choice is a flat list of two to five steps with no replanning.

- **Planner** → `planner`: would write `plan` from `goal`.
- **Executor** → `executor`: would work on `plan[current_step]`. Its router has three exits: `tools` for a tool call, back to `executor` when steps remain, and `synthesizer` when all are done. It is fixed to `synthesizer`.
- **Tools** → `tools`: would run the executor's calls, then return to `executor`.
- **Synthesizer** → `synthesizer`: would write the answer from `results`, then the run ends.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["tools", "executor", "synthesizer"]`, so all three exits appear in the diagram.
- **Structured output**: a live version would ask for the plan as a typed list of steps, not free text.
- **ToolNode**: a live version would use `langgraph.prebuilt.ToolNode` to run the executor's tool calls.
- **State**: holds the goal, the plan, a current-step index and the results.
- **Replanning**: a variation would add a node that revises the remaining steps; this demo has none.

### Key code
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

### Try this
- Write a plan for "compare two laptops and recommend one". Which steps would need `tools`, and which would not?
- A step fails halfway through. Where in this diagram would a replanning node go, and which edge would lead to it?
- Compare with [[execution/workflow]] (fixed steps) and [[cognitive/search]] (several candidate paths).
