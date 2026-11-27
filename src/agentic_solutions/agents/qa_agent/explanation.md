# Single LLM call

## What it is
The smallest useful LangGraph: one question goes in, one model call happens, one answer comes out. There is no loop, no memory between runs and no branching. It is the "hello world" that shows the building blocks every other pattern reuses.

## When to use it
- One-shot tasks: summarise this text, classify this ticket, rewrite this sentence.
- As a step inside a bigger system, where the surrounding code handles everything else.
- As a baseline. If one call solves your problem, do not add more machinery.

## How this graph works
The trace shows three stops: `__start__`, `answer`, `__end__`.

1. `__start__` hands your message to the graph.
2. `answer` sends a system prompt plus your message to the model and stores the reply.
3. `__end__` finishes the run.

Both edges are fixed. Nothing is decided at run time, so every run takes the same path.

## LangGraph concepts
- **State**: a `TypedDict` that holds the data flowing through the graph. Here it has a single key, `messages`.
- **Reducer**: `add_messages` tells LangGraph to append a node's returned messages to the list instead of replacing it.
- **Node**: a plain function that takes the state and returns a partial update.
- **Edge**: a fixed link from one node to the next (`START -> answer -> END`).
- **compile()**: turns the builder into a runnable graph.

## Trade-offs
- Fast, cheap and easy to debug: one model call per run.
- No memory. Ask a follow-up and the model has no idea what you said before.
- The model cannot check its work, use tools or ask you for clarification.
- No safety checks. Whatever you send goes straight to the model.

## Key code
```python
def answer(state: State) -> dict:
    """Node: call Claude with the conversation so far and return its reply."""
    llm = (llm_factory or get_llm)()
    reply = llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [reply]}

builder = StateGraph(State)
builder.add_node("answer", answer)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)
return builder.compile(checkpointer=checkpointer)
```

## Try this
- Ask any question, for example `What is a reducer in LangGraph?`, and watch the run go `__start__`, `answer`, `__end__`.
- Ask a follow-up such as `Explain that more simply`. Each run starts fresh, so the model will not know what "that" means. This is the gap the Chat loop pattern fills.
