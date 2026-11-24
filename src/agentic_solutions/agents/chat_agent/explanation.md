# Session

## What it is
A conversation that keeps going. The system takes a turn from the user, replies, and waits for the next turn until the user ends the session. Every turn is kept in the session's message history, so the model sees the whole conversation each time it replies and follow-up questions make sense.

## When to use it
- Chat assistants and support bots, where follow-ups depend on what was said earlier.
- Any flow that repeats "take input, do work" until the user is done.
- When each turn needs a small decision about what happens next: reply, wait again, or finish.
- Not when memory must outlive the conversation. Recalling last week's chat in a new one is a different pattern.

## How it works
Roles:
- **User**: sends one turn at a time and decides when the session ends.
- **Turn controller**: inspects each incoming turn and picks the next step.
- **Agent**: a model that replies, given the full message history.
- **Session store**: holds the message history for this one conversation, keyed by a session id.

Flow:
1. The system waits for the user's turn and appends it to the history.
2. The turn controller checks the turn. An explicit end signal finishes the session. A blank turn goes straight back to waiting, with no model call. Anything else goes to the agent.
3. The agent replies using the whole history. The reply is appended.
4. The session store saves the history, and the system waits for the next turn.

## Design considerations
- **Where the history lives:** in process memory it dies with the process. A durable store keyed by session id survives restarts and lets several servers serve one conversation.
- **Session identity:** one id per conversation. Mixing ids leaks one user's history into another's.
- **Growth and the context limit:** history grows every turn. Decide early how to trim or summarise it, and what must never be dropped.
- **Cheap decisions before expensive ones:** the turn controller filters blank turns and an explicit end signal with plain code, so no model call is spent on them.
- **Explicit exits:** list every place a turn can go, including the end of the session, so the loop cannot run forever.
- **Input trust:** every turn reaches the model and stays in the history. Untrusted users need a screen in front.

## Trade-offs
- Natural to use, but cost and latency rise with every turn because the whole history is sent each time.
- Long sessions eventually hit the context limit and need trimming or summarising.
- A durable session store adds infrastructure; without one, the conversation is lost when the process stops.

## Related patterns
- The dividing line: Session is one conversation, held in that session's saved checkpoints. [[memory/episodic]] carries memories across separate conversations, so a new chat can recall an old one.
- [[collaboration/single-agent]] is the same model call without the loop or the history.
- [[governance/guardrails]] adds a screen before the agent sees each turn.
- [[governance/approval]] uses the same wait-for-a-person step to sign off risky actions.

## How this Studio implements it

### Mapping
- **User** → you, typing in the Studio chat.
- **Turn controller** → `ask` collects your turn; the router `route_after_ask` on its outgoing edge picks `answer`, `ask` again, or `__end__`.
- **Agent** → `answer`: sends the full history to the model, then returns to `ask`.
- **Session store** → the checkpointer, one `thread_id` per chat.

### Framework concepts
- **Cycle**: `answer` links back to `ask`, so the graph loops.
- **Conditional edge**: `add_conditional_edges` runs a router function that returns the name of the next node, or `END`.
- **Memory inside a run**: the `add_messages` reducer appends every question and reply, so history builds up.
- **Checkpointer + `thread_id`**: the web demo compiles the graph with a checkpointer; each `thread_id` is one session, and its messages are saved after every step.
- **Typed router**: the return type `Literal["answer", "ask", "__end__"]` lists every possible destination, which is how the graph diagram is drawn.
- **Two ways to wait**: in the web demo `ask` waits with `interrupt()` (see [[governance/approval]]); in the CLI it uses `input()`.

### Key code
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

### Try this
- Ask `My name is Sam.` then `What is my name?` to see memory working.
- Send a message containing only spaces. The trace goes `ask` to `ask` with no `answer` step and no model call.
- Type `stop`. The run goes to `__end__` and the chat is over.
