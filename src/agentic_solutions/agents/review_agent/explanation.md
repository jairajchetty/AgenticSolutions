# Review

## What it is
Review has a separate agent or a person check the result before it is accepted. One step produces a draft, a reviewer judges it, and the reviewer either sends it back with comments or lets it through. The checker has its own view of the work, so it can catch what the author missed.

The dividing line from Reflection: **unlike [[cognitive/reflection]], where the same agent critiques its own output, Review uses a separate reviewer.**

## When to use it
- A mistake would be costly enough that a second opinion is worth the delay.
- The reviewer needs different information, rules or authority than the author.
- A person must look at the result, such as a lawyer reading a contract draft.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

The line from Reflection is visible in the roles: in [[cognitive/reflection]] one agent writes and critiques, while here `review` stands for a different agent or a person, who can send the work back to `draft`.

- `draft` writes the content, or rewrites it using the reviewer's `comments`.
- `review` judges the draft and sets `comments` and `accepted`. Its router sends control back to `draft` for changes, or on to `approve`.
- `approve` records the accepted content as the final result, then the run ends.

The skeleton's router is fixed to `approve`, so the diagram shows the send-back path without running it.

## LangGraph concepts
A live version would use:
- **Conditional edges**: the router, annotated `Literal["draft", "approve"]`, follows `accepted`.
- **Interrupt**: when the reviewer is a person, `review` can pause the run with `langgraph.types.interrupt` and resume when they answer. Pausing and resuming needs a checkpointer.
- **State**: holds the task, the content, the comments, the accepted flag and the final result.

## Trade-offs
- A person in the loop adds waiting time, and a run can sit paused until they respond.
- Nothing in the graph stops an endless send-back cycle, so a live version needs a limit.
- A reviewer who is another model may share the author's blind spots.
- Reviewing costs another pass over the work on top of the drafting.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("draft", draft)
builder.add_node("review", review)
builder.add_node("approve", approve)

builder.add_edge(START, "draft")
builder.add_edge("draft", "review")
builder.add_conditional_edges("review", route_review)
builder.add_edge("approve", END)

return builder.compile()
```

## Try this
- Which State field carries the reviewer's feedback back to `draft`, and which node sets it?
- `route_review` is the function that returns `"draft"` or `"approve"`. Which State field would a live version read to choose between them?
- To stop an endless send-back cycle you would add a counter to State. Which function would read it: `draft` or `route_review`?
- Which of [[governance/approval]] and [[governance/guardrails]] pauses the run for a person?
