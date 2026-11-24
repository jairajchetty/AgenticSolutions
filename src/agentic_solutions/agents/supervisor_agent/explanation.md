# Supervisor

## What it is
One coordinator manages a set of specialist workers; this is often called the orchestrator-workers pattern. The coordinator reads the task and the progress so far, chooses which worker or workers act next, merges what comes back, and decides when the job is finished. Workers do not talk to each other: every handoff passes through the coordinator, which holds the only complete view of the run.

## When to use it
- The task splits into distinct roles, such as research then writing, and the order is not known in advance.
- One place should decide what happens next, so behaviour is easy to follow and to log.
- A single agent holding every tool is choosing poorly among too many options.
- Not when the order of roles is fixed. A fixed sequence in code does the same job without a coordinator step between them.

## How it works
Roles:
- **Coordinator**: reads the task and shared progress, then picks one or more workers for the next round, or declares the work done.
- **Workers**: specialists, each with its own instructions and tools, that perform one piece of work and report back.
- **Shared state**: the task, the workers' outputs and any notes the coordinator keeps.

Flow:
1. The coordinator reads the task and picks one or more workers, each with its sub-task.
2. Each chosen worker does its part and writes its result to the shared state.
3. Control returns to the coordinator, which reads and merges the results.
4. The coordinator picks the next workers, back at step 2, or finishes and returns the result.

## Design considerations
- **How the coordinator chooses:** a model choosing from worker descriptions handles open-ended tasks; rules or a classifier are cheaper and predictable where the choice is simple. A typed choice is safer to act on than parsing free text.
- **Sequential or parallel delegation:** one worker per round lets each choice use the previous result, but latency adds up; fanning independent sub-tasks out to several workers at once cuts latency, at the cost of splitting the task cleanly up front and merging, or reconciling, results that may overlap or conflict.
- **What workers see:** passing the full shared history is simple but costly and noisy; passing each worker only a task brief keeps it focused, but the coordinator must write good briefs.
- **Worker descriptions:** the coordinator can only choose well between roles it understands. Keep descriptions distinct and non-overlapping.
- **Round limit:** cap delegations per run, so a coordinator that keeps re-delegating cannot loop forever.
- **Finishing:** decide whether the coordinator writes the final answer itself or returns a worker's output as is.
- **Number of workers:** past a handful, the coordinator's choice gets harder; group workers into teams instead.

## Trade-offs
- Every round returns through the coordinator, adding a coordinator step and latency per hop.
- The coordinator is a single point of failure: a wrong choice sends the run the wrong way.
- Easier to trace and log than peers handing off directly.
- Does not scale to very many workers under one coordinator.

## Related patterns
- The dividing line across the three multi-agent patterns: Supervisor has exactly one coordinator. [[collaboration/hierarchy]] stacks supervisors of supervisors, and [[collaboration/swarm]] has no coordinator at all.
- [[collaboration/single-agent]] is the baseline: one agent, no delegation.
- [[execution/routing]] picks one specialist per request and hands off for good; a supervisor keeps control and may call several workers in turn.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Coordinator** → `supervisor`: would read progress and record its choice in `next_worker`, so it delegates to one worker at a time. Its router sends control to `researcher`, to `writer`, or to `__end__`; it is fixed to `__end__`.
- **Workers** → `researcher`, which would add facts to `notes`, and `writer`, which would turn the notes into `draft`. Both return to `supervisor`, and neither links to the other.
- **Shared state** → `task`, `notes` and `draft`.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["researcher", "writer", "__end__"]`, so every delegation appears in the diagram.
- **Command**: a live node could return `langgraph.types.Command` with `goto` to name the next node and update state in one step, instead of a separate router.
- **Structured output**: would ask the coordinator model for a typed worker choice.
- **State**: the shared keys every worker reads and writes.

### Key code
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

### Try this
- The task is "write a short report on tides". Which worker should `supervisor` pick first, and what in `notes` tells it to pick `writer` next?
- What would `supervisor` look at in state to decide the work is done?
- Compare with [[collaboration/single-agent]], the live baseline. What does a coordinator add, and what does it cost?
