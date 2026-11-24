# Routing

## What it is
Classify each incoming request and hand it to the one handler best suited to it. A handler can be a prompt, a model, a tool chain or a whole agent. The router does not solve the request; it decides who does, once, and the chosen handler then owns the request to the end. The same mechanism serves two purposes: specialisation, where each kind of request gets instructions and tools tuned to it, and cost control, where easy requests go to a cheaper model and hard ones to a stronger model.

## When to use it
- Requests fall into a few clear kinds, such as billing, technical and everything else, and each kind needs different instructions or tools.
- One prompt holding every instruction is getting long, and each specialist would be simpler on its own.
- Easy requests should go to a cheaper model and hard ones to a stronger one.
- Not when a request needs several specialists in turn, or the next step depends on what the first one found. A coordinator that keeps control across steps fits that.

## How it works
Roles:
- **Classifier**: reads the request and assigns one label from a fixed set, ideally with a confidence.
- **Specialists**: handlers, each for one label, with their own instructions, tools or model.
- **Fallback**: the handler for requests that fit no label, or whose label is uncertain.

Flow:
1. A request arrives.
2. The classifier labels it.
3. The request is dispatched to the matching specialist, or to the fallback when no label fits.
4. The specialist produces the reply, and the run ends there. Control does not return to the classifier.

## Design considerations
- **Kind of classifier:** rules or keywords are fast, free and explainable but brittle; similarity to example requests handles paraphrase but needs good examples; a small trained classifier is accurate and cheap once labelled data exists; a general model reading label descriptions is the most flexible, at the price of latency and cost per request. A typed label is safer to act on than free text.
- **Label set:** keep labels distinct and non-overlapping. Labels that overlap give inconsistent routes for similar requests.
- **Fallback and low confidence:** provide a catch-all route. A low-confidence label can go to the fallback, prompt a clarifying question, or reach a person.
- **Requests with several intents:** one label per request is simplest. Splitting the request, or picking a primary intent and accepting the miss, are the alternatives.
- **What the specialist receives:** the original request, and possibly the label and any fields the classifier extracted, so the specialist does not redo the work.
- **Measuring misroutes:** a wrong route fails silently. Log each label with its outcome and review samples.

## Trade-offs
- Each specialist stays small and focused, and is easier to test and change on its own.
- Adds one classification step before any real work, which costs latency.
- A wrong label sends the request to the wrong specialist, and nothing afterwards corrects it.
- Cheaper and simpler than keeping a coordinator in charge when one decision is enough.

## Related patterns
- The dividing line with [[collaboration/supervisor]]: Routing decides once and hands off for good. A supervisor keeps a coordinator in charge, calling workers in turn and deciding when the job is finished.
- [[collaboration/swarm]] lets specialists hand a request on to each other; in Routing only the classifier decides where a request goes.
- [[execution/workflow]] may contain a routing branch, but the rest of its path is fixed in code.
- [[governance/guardrails]] often sits before the router, so requests it blocks do not reach a specialist.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Classifier** → `classify`: would label `request` and store the label in `category`. Its router `route_classify` sends control to `billing`, `technical` or `general`, and is fixed to `general`.
- **Specialists** → `billing` for money questions and `technical` for faults and setup; each would set `reply`.
- **Fallback** → `general`, for anything else.
- Every specialist goes straight to `__end__`, with no edge back to `classify`. That missing edge is the line from Supervisor.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["billing", "technical", "general"]`, so all three routes appear in the diagram.
- **Structured output**: would ask the classifier model for a typed category instead of parsing free text.
- **Command**: a node can return `langgraph.types.Command` with `goto` to classify and jump in one step, instead of using a separate router.
- **State**: holds `request`, `category` and `reply`.

### Key code
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

### Try this
- A request reads "I was charged twice and now the app crashes". Which state field holds the label `classify` must choose, and what does the fixed router do with it?
- Which edges would you add to turn this into a supervisor, so the request can visit a second specialist? Name one by its two node names.
- Compare with [[collaboration/supervisor]]: what does a coordinator add, and what does it cost?
