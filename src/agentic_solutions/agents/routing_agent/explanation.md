# Routing

## What it is
Routing looks at each incoming request, decides which specialist should handle it, and sends it there. A classifier step labels the request, and one specialist then does the work. The classifier can be a model, a set of rules or a small trained classifier. It is the front desk of a system: it does not solve the request, it only decides who does.

The dividing line from Supervisor: **Routing decides once and does not loop back.** See [[collaboration/supervisor]] for the pattern that keeps a coordinator in charge across turns.

## When to use it
- Requests fall into a few clear kinds, such as billing, technical and everything else, and each kind needs different instructions or tools.
- One prompt with every instruction is getting long and the specialists would each be simpler on their own.
- You want to send easy requests to a cheaper model and hard ones to a stronger one.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The line from Supervisor is visible in the shape: [[collaboration/supervisor]] keeps a coordinator in charge across turns, while here the route is chosen once and every specialist goes straight to the end, with no edge back to `classify`.

- `classify` reads the request and picks a category. Its router sends control to `billing`, `technical` or `general`.
- `billing` handles money questions, then the run ends.
- `technical` handles faults and setup questions, then the run ends.
- `general` is the fallback for anything else, then the run ends.

The skeleton's router is fixed to `general`, so the diagram shows all three routes without running them.

## LangGraph concepts
A live version would use:
- **Conditional edges**: the router, annotated `Literal["billing", "technical", "general"]`, follows the label in state.
- **Structured output**: asks the classifier model for a typed category, which is safer than parsing free text.
- **Command**: a node can return `langgraph.types.Command` with `goto` to classify and jump in one step, instead of using a separate router.
- **State**: holds the request, the category and the reply.

## Trade-offs
- A wrong label sends the request to the wrong specialist, and nothing in the graph corrects it.
- The fallback route matters. Without a `general` branch, unusual requests have nowhere good to go.
- Adds one classification step before any real work, which costs latency.
- Cheaper and simpler than a supervisor when one decision is enough.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("classify", classify)
builder.add_node("billing", billing)
builder.add_node("technical", technical)
builder.add_node("general", general)

builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route_classify)
builder.add_edge("billing", END)
builder.add_edge("technical", END)
builder.add_edge("general", END)

return builder.compile()
```

## Try this
- A request reads "I was charged twice and now the app crashes". Which State field holds the label `classify` must choose, and what does the fixed router do with it?
- Which edges would you have to add to turn this into a supervisor, so the request can visit a second specialist? Name one edge by its two node names.
- Compare with [[collaboration/supervisor]]: what does a coordinator add, and what does it cost?
