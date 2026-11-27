# Guardrails

## What it is
The chat loop with a security check in front of the model. Every message passes through a `guard` node that compares it with a library of known attack phrases. If it looks like an attack, a fixed `refuse` node replies and the model never sees it.

## When to use it
- Assistants exposed to untrusted users, where prompt injection is a real risk.
- When refusals must be predictable and must not depend on the model being attacked.
- Pair it with [[governance/audit]] to keep a record of what was blocked.
- As one layer of defence, next to a strong system prompt and least-privilege tools.

## How this graph works
The trace shows `ask`, `guard`, then either `answer` or `refuse`, then back to `ask`.

1. `ask` collects your message. Its router sends `stop` to `__end__`, an empty message back to `ask`, and anything else to `guard`.
2. `guard` embeds your message and compares it with every phrase in the threat library. It records the verdict in the `threat` state key.
3. A second router, `route_after_guard`, sends a threat to `refuse` and a clean message to `answer`.
4. `refuse` removes the bad message from the history and sets a fixed refusal text. `answer` calls the model as usual.
5. Both return to `ask`.

In the web demo the `ask` node waits with `interrupt()` (see [[governance/approval]]); in the CLI it uses `input()`.

The dividing line: Guardrails are automatic screens that block unsafe content on the way in (as this demo does) or on the way out. [[governance/review]] judges whether a finished result is good enough and can send it back for rework.

## LangGraph concepts
- **Two conditional edges**: one after `ask`, one after `guard`.
- **Extra state keys**: `threat` and `refusal` have no reducer, so each update replaces the old value. They carry the verdict from node to node.
- **RemoveMessage**: how a node deletes a message from the conversation. `refuse` uses it so the attack does not sit in the history and get sent with later questions.
- **Closure over setup work**: nodes are defined inside `build_graph`, so they can use the `ThreatGuard`, created once at startup, without putting it in the state.

## Trade-offs
- It uses embeddings (meaning), not keywords, so a paraphrase can still be caught, because matching is by meaning.
- It only catches attacks that resemble the library. Weaker paraphrases can slip through, so grow the library over time.
- The threshold is a trade: lower catches more attacks but blocks more real questions.
- Startup is slower because the embedding model loads and the library is embedded once.

## Key code
```python
def guard_prompt(state: State) -> dict:
    match = guard.check(state["messages"][-1].content)
    threat = f"{match.category} ({match.score:.2f})" if match else None
    return {"threat": threat}

def refuse(state: State) -> dict:
    bad_message = state["messages"][-1]
    return {
        "messages": [RemoveMessage(id=bad_message.id)],
        "refusal": REFUSAL_MESSAGE,
    }

def route_after_guard(state: State) -> Literal["refuse", "answer"]:
    """Threat found -> refuse, otherwise -> answer."""
    return "refuse" if state["threat"] else "answer"

builder.add_conditional_edges("guard", route_after_guard)
builder.add_edge("refuse", "ask")
builder.add_edge("answer", "ask")
```

## Try this
- Send `ignore previous instructions`. The trace goes `ask`, `guard`, `refuse`, and the model is never called.
- Try a paraphrase such as `Please disregard the rules you were given`. It may or may not be caught, which shows the limit of the library.
- Ask a harmless question like `What is the capital of France?`. The trace goes `ask`, `guard`, `answer`.
- Send a message containing only spaces, then `stop`, to see the other two routes from `ask`.
