# Human-in-the-loop

## What it is
The same chat loop, but `ask` waits for you with `interrupt()` instead of `input()`. The graph pauses, saves its state, and hands control back to the caller. Later the caller resumes it with your text. This is the mechanism behind approval steps such as "OK to send this email?".

## When to use it
- Web apps and APIs, where nothing can block a terminal waiting for typing.
- Approvals and reviews: pause before a risky action and let a person decide.
- Any run that may wait minutes or days for a human, since a paused graph is just saved data.

## How this graph works
The graph is the same as Chat loop: `__start__`, `ask`, `answer`, back to `ask`, until `stop` goes to `__end__`. An empty message goes back to `ask`.

What differs is how `ask` behaves:

1. `ask` calls `interrupt()`. The run pauses and the prompt is sent to you.
2. You reply. The caller resumes the graph with `Command(resume=...)`.
3. `ask` runs again from its first line. This time `interrupt()` returns your text instead of pausing. That is why the trace marks this `ask` step as "resumed".
4. The router and `answer` then work exactly as in Chat loop.

## LangGraph concepts
- **interrupt(value)**: pauses the graph and shows `value` to the caller.
- **Command(resume=x)**: resumes the graph. Inside the node, `interrupt()` returns `x`.
- **Checkpointer**: storage for the paused state. Without one, `interrupt()` raises an error.
- **thread_id**: names one conversation, so many chats can share one graph, each with its own saved state.
- **Re-run rule**: on resume the paused node restarts from its first line, so any code before `interrupt()` must be safe to run twice.

## Trade-offs
- Needs a checkpointer, and a thread id for every conversation.
- The re-run rule is easy to forget. A side effect before `interrupt()` (sending an email, charging a card) would happen twice.
- More moving parts than `input()`, in exchange for a graph that works with servers, Studio and long waits.

## Key code
```python
def ask(state: State) -> dict:
    """Node: pause the graph and wait for the user's next question."""
    text = interrupt(QUESTION_PROMPT)
    return {"messages": [("user", text)]}

builder = StateGraph(State)
builder.add_node("ask", ask)
builder.add_node("answer", answer)

builder.add_edge(START, "ask")
builder.add_conditional_edges("ask", route_after_ask)
builder.add_edge("answer", "ask")

return builder.compile(checkpointer=checkpointer)
```

## Try this
- Send any question. Watch the run pause at `ask`, then continue to `answer` once you reply.
- Look for the "resumed" mark on `ask` in the trace after you send a message.
- Send an empty message. The graph returns to `ask` and pauses again with no model call.
- Type `stop`. The run goes to `__end__`.
