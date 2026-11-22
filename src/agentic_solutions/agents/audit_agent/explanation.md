# Audit

## What it is
Audit keeps persistent, queryable records of every run: what was done, in what order, and with what result. The records outlive the run that produced them, so someone can come back later and ask what happened. It is the ledger of a system, not a live display.

The dividing line from the Studio's trace panel: **the trace panel is a live view of one run. Audit means records that persist and can be searched across runs.**

## When to use it
- You need to answer questions after the fact, such as which runs touched a given customer or what the agent did last Tuesday.
- Compliance or traceability rules require a record of each action the agent took.
- You want to compare many runs, for example to find the ones that failed in the same step.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The line from the trace panel is about durability. A trace shows one run while you watch it; the entries `record` writes are meant to be kept and searched across runs. One source of such records is the checkpointer history, read with `aget_state_history` on a compiled graph that has a checkpointer. A real audit log usually also writes to its own durable store, because checkpoints exist to resume runs, not to answer audit queries.

Audit also relates to [[governance/approval]]: an approval is an event, and an audit log should record who approved what, and when.

- `act` performs the next action.
- `record` writes an entry for that action. Its router sends control back to `act` while there is more work, or on to `summarize`.
- `summarize` reads the entries back and produces a report, then the run ends.

The skeleton's router is fixed to `summarize`, so the diagram shows the loop without running it.

## LangGraph concepts
A live version would use:
- **Conditional edges**: the router, annotated `Literal["act", "summarize"]`, follows `more_work`.
- **Checkpointer**: saves state after each step. `aget_state_history` on a compiled graph with a checkpointer lists those saved snapshots, which makes them one source of records.
- **State**: holds the task, the actions, the log entries and the final report.

## Trade-offs
- Records can contain personal or sensitive data, so what you log and who may read it needs a decision.
- Writing an entry after every action adds a write to each step.
- Logs grow without limit unless you decide how long to keep them.
- Checkpoint history alone may not be enough: it is stored for resuming runs, so its format and retention may not suit audit queries.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("act", act)
builder.add_node("record", record)
builder.add_node("summarize", summarize)

builder.add_edge(START, "act")
builder.add_edge("act", "record")
builder.add_conditional_edges("record", route_record)
builder.add_edge("summarize", END)

return builder.compile()
```

## Try this
- Which State field would `record` append to, and which node reads it back? Name both.
- `route_record` is fixed to `summarize`. Which State field would a live router read to return `"act"` instead?
- To also log a person's sign-off, which node would you give the extra write: `act` or `record`? Compare with [[governance/approval]].
- Compare with [[governance/guardrails]]: when a guardrail blocks an action, should `record` still write an entry? Answer yes or no and say why.
