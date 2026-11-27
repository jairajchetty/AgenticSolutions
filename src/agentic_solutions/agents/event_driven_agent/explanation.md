# Event Driven

## What it is
An agent started by something that happened, not by a person typing a message: a message lands on a queue, a webhook fires, a record changes, a file arrives, or a schedule ticks. Typically each event starts one run, which handles that event and finishes; alternatively a long-lived agent waits and is woken by each event that concerns it. Either way, the result may itself be published as an event for another system. The trigger lives outside the agent. A queue consumer, webhook handler or scheduler receives the event and calls the agent with it as input. With no one waiting at a chat box, the concerns shift from conversation to delivery: events can arrive twice, late, out of order or in bursts, and failures must be noticed by monitoring rather than by a user.

## When to use it
- Work arrives from other systems at unpredictable times, and nobody is waiting for the reply.
- The agent should run on a schedule, such as a nightly summary, without a user present.
- Different kinds of event need different handling, and some should simply be ignored.
- Not when a person is waiting for an answer in a conversation. A direct request and reply is simpler and easier to debug.

## How it works
Roles:
- **Event source**: the system where something happens, such as a shop, a ticket system or a clock.
- **Trigger**: the code outside the agent that receives the event and starts a run with it.
- **Dispatcher**: reads the event, works out its kind, and picks a handler or drops it.
- **Handlers**: one per kind of event the agent deals with.
- **Publisher**: emits the outcome, for example to another queue, an API or a store.

Flow:
1. Something happens, and the event source emits an event.
2. The trigger receives it and starts one run with the event as input.
3. The dispatcher determines its kind. Kinds the agent does not handle are dropped, ideally with a log entry.
4. The matching handler processes the event.
5. The publisher emits the result, and the trigger acknowledges the event, where the source expects it, so it is not delivered again.

## Design considerations
- **Trigger mechanism:** a queue consumer buffers bursts and redelivers on failure, but needs a broker; a webhook is immediate and simple, but must answer quickly and follow the sender's retry rules, so it often just enqueues the event; a schedule suits periodic work, with latency up to one interval; polling or change capture fits sources that cannot push.
- **Duplicates and ordering:** many delivery systems deliver at least once. Make handlers safe to repeat, keyed by event id, and decide whether order matters per customer or per record.
- **When to acknowledge:** acknowledging after processing is safe but can cause redelivery; acknowledging on receipt avoids duplicates but can lose events on a crash.
- **Failure path:** retry with backoff, then park the event in a dead-letter queue for inspection, and alert someone who will read it.
- **Rate and cost:** bursts multiply model calls. Limit concurrency at the consumer, not inside the agent, and batch where the work allows.
- **Unknown events:** dropping silently hides a changed schema upstream. Log or park them.
- **One run per event or a long-lived agent:** a fresh run per event is simple and stateless; a long-lived agent, or related events correlated by a key, lets a later event resume an earlier run's state, at the cost of storing and expiring that state.

## Trade-offs
- Decouples the agent from its callers and lets it run without anyone present.
- Scales with the queue, but bursts can drive cost up quickly.
- Harder to debug: no one watches the run, so logging and alerting carry the load.
- The trigger, queue and retry machinery are extra infrastructure outside the agent.

## Related patterns
- [[execution/workflow]] is often what each event runs, with fixed steps per event type.
- [[execution/routing]] also dispatches by kind; here the kind usually comes from a typed field on the event rather than from classifying free text.
- [[execution/autonomous]] pursues a goal it was given and decides its own next steps; Event Driven is about what starts or wakes a run: an outside event, not a person. The two combine when events wake a long-running autonomous agent.
- [[governance/audit]] matters more here, because the record is often the only way to see what happened.
- [[collaboration/single-agent]], the live baseline, is started by a person asking a question.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Trigger** → not drawn, because it is not part of the graph: your consumer, handler or scheduler would call `invoke` with `event` as input. The graph does not listen for events by itself.
- **Dispatcher** → `receive_event`: would read `event` and set `event_type`. Its router `route_event` sends control to `handle_order`, `handle_refund` or `ignore`, and is fixed to `ignore`.
- **Handlers** → `handle_order` and `handle_refund`, which would each set `result`.
- **Unknown kinds** → `ignore`: would drop the event and end, without publishing.
- **Publisher** → `emit_result`: would publish `result`, for example to another queue, then end.

### Framework concepts
- **invoke**: the compiled graph's `invoke` method is what the trigger calls, with the event as input state.
- **Conditional edges**: the router is annotated `Literal["handle_order", "handle_refund", "ignore"]`, so every path appears in the diagram.
- **Checkpointer**: with one `thread_id` per event id in the config, a run can be inspected or resumed later.
- **State**: holds `event`, `event_type` and `result`.

### Key code
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

### Try this
- Which state field would the trigger fill when it calls `invoke`, and which field does `receive_event` fill so the router can choose?
- An event of an unknown kind arrives. Which node does it end at, and does it pass through `emit_result`?
- The same order event arrives twice. Which node would need to check the event id so the order is not processed twice?
- Compare with [[collaboration/single-agent]], the live baseline: who starts each run there, and who starts it here?
