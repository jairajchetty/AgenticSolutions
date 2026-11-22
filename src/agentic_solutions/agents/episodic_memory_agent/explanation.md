# Episodic

## What it is
Episodic memory is long-term memory of past interactions. The agent keeps records of what happened with a particular user, such as a preference they stated or a problem it solved for them, and brings the relevant ones back when that user returns. The memories are retrieved for the current user, so the agent can pick up where earlier conversations left off.

The dividing line from the live pattern: **[[memory/session]] is one conversation, held in the thread's checkpoints. Episodic carries memories across conversations.** Start a new thread and Session forgets everything. Episodic still has what it stored about that user.

## When to use it
- A returning user should not have to repeat their preferences, history or context.
- Past outcomes should shape future answers, for example "last time this fix worked".
- Memories must outlive any single thread or run.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real. There are no routers, and every step runs on every turn.

1. `recall_episodes` looks up earlier episodes stored for the current user and puts them in `episodes`.
2. `answer` responds to the question with those episodes as extra context.
3. `store_episode` saves this interaction as a new episode, so the next conversation can recall it.

Unlike [[memory/session]], which lives in one thread's checkpoints, `recall_episodes` and `store_episode` read and write a store keyed by `user_id`, so memory survives a new thread.

Reading happens before the answer and writing happens after it. That order means an interaction cannot recall itself, and a new episode becomes available from the next conversation on. State carries `user_id`, which is the key that separates one user's memories from another's.

## LangGraph concepts
A live version would use:
- **Store**: the `langgraph.store.base.BaseStore` interface. A node receives the store by declaring a `store: BaseStore` parameter, and items are keyed by a namespace such as the user id. Nodes read with `search` and write with `put`.
- **InMemoryStore**: `langgraph.store.memory.InMemoryStore` is the in-process implementation for experiments. A real deployment would use a persistent store.
- **Compile with a store**: `builder.compile(store=...)` makes the store available to every node.
- **Checkpointing**: still used for the current conversation, as in [[memory/session]]. The store adds what the checkpoints cannot: memory across threads.

## Trade-offs
- Recalling the wrong episodes can mislead the answer, so retrieval quality matters.
- Stored memories can go stale or be wrong, and need a way to be corrected or removed.
- Personal data is being kept. Decide what to store, for how long, and who can see it.
- Every turn adds a read and a write, which costs latency.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("recall_episodes", recall_episodes)
builder.add_node("answer", answer)
builder.add_node("store_episode", store_episode)

builder.add_edge(START, "recall_episodes")
builder.add_edge("recall_episodes", "answer")
builder.add_edge("answer", "store_episode")
builder.add_edge("store_episode", END)

return builder.compile()
```

## Try this
- Which State field decides whose memories `recall_episodes` reads? Answer with its name from the skeleton.
- A user states a preference in conversation 1, then opens a brand-new conversation 2. Which node, by name, reads that preference back?
- Compare with [[memory/session]], the live pattern: it remembers within one thread. What does it lose when a new thread starts?
