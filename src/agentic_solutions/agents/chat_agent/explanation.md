# Session

## What it is
A conversation that keeps going. The graph asks for a message, answers it, then loops back to ask again, until you type `stop`. Because every message is kept in the state, the model sees the whole conversation each time it answers.

## When to use it
- Chat assistants and support bots where follow-up questions matter.
- Any flow that repeats "get input, do work" until the user is done.
- When you need the graph to choose between several next steps (answer, ask again, finish).

## How this graph works
The trace shows `__start__`, then `ask` and `answer` taking turns.

1. `__start__` goes to `ask`, which collects your message.
2. A router, `route_after_ask`, reads your message and picks the next step:
   - `stop` (any case) goes to `__end__`.
   - An empty message goes back to `ask`, with no model call.
   - Anything else goes to `answer`.
3. `answer` sends the full history to the model, stores the reply, and returns to `ask`.

In the web demo the `ask` node waits with `interrupt()` (see [[governance/approval]]); in the CLI it uses `input()`.

The dividing line: Session is one conversation, remembered through one thread's checkpoints. [[memory/episodic]] keeps memories across separate conversations, so a new chat can recall an old one.

## LangGraph concepts
- **Cycle**: `answer` links back to `ask`, so the graph loops.
- **Conditional edge**: `add_conditional_edges` runs a router function that returns the name of the next node, or `END`.
- **Memory inside a run**: the `add_messages` reducer appends every question and reply, so history builds up.
- **Typed router**: the return type `Literal["answer", "ask", "__end__"]` lists every possible destination, which is how the graph diagram is drawn.

## Trade-offs
- Natural to use, but the history grows with every turn. Cost and latency rise, and long chats eventually hit the context limit.
- Memory lasts only for one run. Closing the chat loses it unless you add a checkpointer.
- Anything you type reaches the model unchecked. See [[governance/guardrails]] for a fix, and [[governance/approval]] for a version that pauses for a person.

## Key code
```python
def route_after_ask(state: State) -> Literal["answer", "ask", "__end__"]:
    text = state["messages"][-1].content.strip().lower()
    if text == STOP_WORD:
        return END
    if not text:
        return "ask"
    return "answer"

builder = StateGraph(State)
builder.add_node("ask", ask_node)
builder.add_node("answer", answer_node)

builder.add_edge(START, "ask")  # always begin by asking
builder.add_conditional_edges("ask", route_after_ask)  # router picks next
builder.add_edge("answer", "ask")  # after answering, loop back
```

## Try this
- Ask `My name is Sam.` then `What is my name?` to see memory working.
- Send a message containing only spaces. The trace goes `ask` to `ask` with no `answer` step and no model call.
- Type `stop`. The run goes to `__end__` and the chat is over.
