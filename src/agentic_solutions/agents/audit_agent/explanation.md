# Audit

## What it is
Durable, queryable records of what an agent system did: the inputs it received, each action and tool call it made, the decisions taken and who took them, the outputs, and when each happened. The records outlive the run that produced them, so people can come back later and ask what happened, in one run or across thousands: which runs touched a given customer, why an action was taken, where a class of failures began. It is the ledger of the system, kept for accountability, compliance, incident review and evaluation, not a display for watching a run as it happens. What makes a record useful for audit is that it is structured, tied to the run and actor that produced it, protected from later change, and retained for as long as policy requires.

## When to use it
- You need to answer questions after the fact, such as which runs touched a given customer or what the agent did last Tuesday.
- Compliance or traceability rules require a record of each action and who authorised it.
- You want to compare many runs, for example to find the ones that failed at the same step.
- Not when you only need to watch one run while it happens. A live trace view serves that without long-term storage or retention rules.

## How it works
Roles:
- **Agent**: performs the actions being recorded.
- **Recorder**: turns each action into a structured entry, with run id, step, actor, inputs and outputs or references to them, outcome and time.
- **Audit store**: durable, access-controlled storage that keeps entries beyond the run, append-only where possible.
- **Query and report**: searches entries across runs and summarises them for a person or a check.

Flow:
1. The agent performs an action.
2. The recorder writes an entry for it to the audit store.
3. Steps 1 and 2 repeat for each action in the run.
4. At the end of the run, or at any later time, entries are queried and summarised.

## Design considerations
- **What to record:** every step with full inputs and outputs makes a run reconstructible but is large and sensitive; decisions and outcomes alone are lean but may not explain a failure. Storing references or hashes for large payloads is a middle path.
- **Where entries come from:** steps can write them explicitly; tracing instrumentation around model and tool calls can emit them without touching agent code; the system's saved execution state can be copied out, though it exists to resume runs, so its format and retention rarely suit audit queries on their own.
- **Synchronous or buffered writes:** writing before the next step guarantees the record exists, which compliance may require, but adds latency; buffering is faster but can lose entries in a crash.
- **Integrity:** make the store append-only and access-controlled; hash-chaining entries makes tampering detectable.
- **Correlation keys:** record run, conversation, user and request ids, so entries can be joined and searched across runs.
- **Sensitive data:** redact or encrypt personal data, and decide who may read which entries.
- **Retention:** decide how long entries are kept. A deletion obligation can conflict with an append-only store, so plan for it up front.

## Trade-offs
- Accountability, debugging and evaluation across runs become possible.
- Every recorded action costs a write, and storage grows until retention trims it.
- The records themselves are sensitive and become a target worth protecting.
- A log nobody queries gives comfort but no oversight.

## Related patterns
- The dividing line with a live trace: a trace is a live view of one run while it happens. Audit means durable records that persist and can be searched across runs.
- [[governance/approval]] decisions are events an audit log should keep: who approved what, and when.
- [[governance/guardrails]] verdicts are worth recording, so blocked attempts can be studied later.
- [[memory/episodic]] also persists across runs, but for the agent to recall; audit records are for people and checks to inspect.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it. The Studio's trace panel is the live view from the dividing line; this graph shows what durable records would add.

- **Agent** → `act`: would perform the next action and append it to `actions`.
- **Recorder** → `record`: would write the action to a durable store and to `log_entries`. Its router `route_record` follows `more_work`, sending control back to `act` or on to `summarize`, and is fixed to `summarize`.
- **Query and report** → `summarize`: would read `log_entries` back and set `report`, then end.
- **Audit store** → not drawn; a live version would write to its own durable store.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["act", "summarize"]`, so the loop appears in the diagram.
- **Checkpointer history**: `aget_state_history` on a compiled graph with a checkpointer lists the saved snapshots of one thread. That is one per-thread source of records; querying across threads means copying entries into a store of your own.
- **State**: holds `task`, `actions`, `log_entries`, `more_work` and `report`.

### Key code
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

### Try this
- Which state field would `record` append to, and which node reads it back?
- `route_record` is fixed to `summarize`. Which state field would a live router read to return `"act"` instead?
- Is the edge from `record` back to `act` an `add_edge` edge or a router branch of `route_record`?
- Name one event from [[governance/approval]] and one from [[governance/guardrails]] that this log should keep.
