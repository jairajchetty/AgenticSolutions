# Workflow

## What it is
A fixed procedure, like a recipe, written in advance by a developer. Models may do the work inside individual steps, such as pulling details out of an email or summarising a record, and each step's output feeds the next. The path can branch or run steps side by side, but every possible path is decided before the request arrives, which makes a workflow predictable and easy to test but limited to the cases its author foresaw.

## When to use it
- You can list the steps before the request arrives, as in an extract, validate, transform, load job.
- The same input should take the same path every time, so results are predictable and easy to test.
- Failures should follow a known route, such as a quarantine step, instead of a model improvising.
- Not when the steps depend on the request in ways you cannot list in advance. Then the model has to write the plan at run time.

## How it works
Roles:
- **Steps**: units of work, each plain code or a model call, with a defined input and output.
- **Gates**: checks between steps that pick which of the branches written in advance runs next.
- **Error path**: where data that fails a gate goes, for reporting or quarantine.
- **Shared state**: the data each step reads and writes as the run moves on.

Flow:
1. The input arrives and the first step runs.
2. Each step reads earlier results from the shared state and writes its own.
3. At a gate, the code checks the data and picks the next step, or the error path.
4. Steps that do not depend on each other may run in parallel, joining before the next step that needs both.
5. The last step produces the output, or the error path records what went wrong.

## Design considerations
- **Step size:** one model call per step is easy to test, cache and swap; fewer, larger steps cut latency and cost but blur where a failure happened.
- **Sequential, parallel or branching:** a straight sequence is simplest; fanning independent steps out and joining them cuts latency; branches handle known variants. All three are declared in code.
- **Kind of gate:** code checks, such as schema validation or thresholds, are cheap and deterministic; a model judging fuzzy criteria is more flexible but makes the path less predictable.
- **Failure handling:** retry transient failures with backoff, send bad data to an error step, and decide whether partial results are kept or rolled back.
- **Resumability:** saving state after each step lets a failed run resume from the last good step. Steps with side effects must then be safe to repeat.
- **Where model judgement is allowed:** inside steps, and at gates choosing among branches written in advance. Once the model invents the steps or their order, the system is Planning or a free-running agent, and it loses the predictability that justified a workflow.

## Trade-offs
- Predictable, testable and cheap to run, because only the steps that need a model call one.
- Handles only the cases its author anticipated.
- A new kind of input means changing the code, because nothing re-plans.
- Order is a correctness property: validating after loading would write bad data.

## Related patterns
- The dividing line with [[cognitive/planning]]: in Workflow the steps are fixed in code. In Planning the model writes the steps at run time.
- [[execution/routing]] is a single branch at the start; a workflow may begin with one and then follow fixed steps.
- [[execution/event-driven]] describes what starts a run; a workflow is often what each event runs.
- [[cognitive/react]] lets the model choose every next action, the opposite end from a workflow.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it. It is a sequential pipeline with one gate and no parallel steps.

- **Steps** → `extract` would read raw `records` from `source`; `transform` would reshape them; `load` would write them out and set `loaded`.
- **Gate** → `validate`: would check each record and note problems in `errors`. Its router `route_validate` sends control to `transform` or `handle_error`, and is fixed to `transform`.
- **Error path** → `handle_error`: would report or quarantine what is in `errors`, then end.
- **Shared state** → `source`, `records`, `errors` and `loaded`.

### Framework concepts
- **Edges**: `add_edge` wires the fixed steps in order; that is what makes this a workflow and not an agent.
- **Conditional edges**: the router is annotated `Literal["transform", "handle_error"]`, so both branches appear in the diagram.
- **Parallel steps**: two edges out of one node run both targets in the same step, and an edge from each into a third node joins them. This skeleton has none.
- **RetryPolicy**: `langgraph.types.RetryPolicy` set on a node retries a flaky step before the run fails.

### Key code
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

### Try this
- Which state field would `validate` fill so that the router can pick `handle_error`?
- A new step, `deduplicate`, must run after `validate` and before `transform`. Since `validate` reaches `transform` through a router branch, which branch do you change, and which edge do you add? (Answer: the router's `transform` branch now returns `deduplicate`, and you add the edge `deduplicate` -> `transform`.)
- Compare with [[cognitive/planning]]: if the steps cannot be listed before the request arrives, which pattern fits?
