# Event Driven

## What it is
An event-driven agent runs because something happened, not because a person typed a message. An order arrives on a queue, a webhook fires, or a schedule ticks. Each event starts one run of the graph, and the run handles that event and finishes. The agent can also publish a result, which may itself be the next event for another system.

The key point: **the graph is started by an external trigger, such as a queue consumer, a webhook or a cron job, calling `invoke`.** The trigger lives outside the graph. The `langgraph` library does not listen for events by itself.

## When to use it
- Work arrives from other systems at unpredictable times, and nobody is waiting at a chat box.
- Different kinds of event need different handling, and some events should simply be ignored.
- The agent should run on a schedule, such as a nightly summary, without a user present.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The trigger is not drawn because it is not part of the graph: a queue consumer, a webhook handler or a cron job, running in your own process or service, calls `invoke` with one event as the input. The graph starts at `receive_event` and handles that single event.

- `receive_event` reads the event and works out its kind. Its router sends control to `handle_order`, `handle_refund` or `ignore`.
- `handle_order` and `handle_refund` each process their kind of event, then both go to `emit_result`.
- `emit_result` publishes the outcome, for example to another queue, and the run ends.
- `ignore` drops events this agent does not handle, and the run ends.

The skeleton's router is fixed to `ignore`, so the diagram shows every path without running them.

## LangGraph concepts
A live version would use:
- **invoke**: the compiled graph's `invoke` method is what the trigger calls, with the event as input state.
- **Conditional edges**: the router, annotated `Literal["handle_order", "handle_refund", "ignore"]`, follows the event type.
- **Checkpointing**: with a checkpointer and a `thread_id` in the config, a run can be resumed or inspected later, for example one thread per event id.
- **State**: holds the event, its type and the result.

## Trade-offs
- Events can arrive twice or out of order, so handlers should be safe to repeat.
- No person is watching, so failures need logging and alerting that someone actually reads.
- Bursts of events can pile up model calls. The queue, not the graph, is where you control the rate.
- The trigger is extra code and infrastructure that this graph does not provide.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`. The trigger is not in this graph.
```python
builder = StateGraph(State)
builder.add_node("receive_event", receive_event)
builder.add_node("handle_order", handle_order)
builder.add_node("handle_refund", handle_refund)
builder.add_node("ignore", ignore)
builder.add_node("emit_result", emit_result)

builder.add_edge(START, "receive_event")
builder.add_conditional_edges("receive_event", route_event)
builder.add_edge("handle_order", "emit_result")
builder.add_edge("handle_refund", "emit_result")
builder.add_edge("ignore", END)
builder.add_edge("emit_result", END)

return builder.compile()
```

## Try this
- Which State field would the trigger fill when it calls `invoke`, and which field does `receive_event` fill so the router can choose a branch? Answer with both names from the skeleton.
- An event of an unknown kind arrives. Which node does it end at, and does it pass through `emit_result`?
- Compare with [[collaboration/single-agent]], the live baseline: who starts each run there, and who starts it here?
