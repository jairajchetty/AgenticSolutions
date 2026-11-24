# Episodic

## What it is
Long-term memory of past interactions. The agent keeps records of what happened with a particular user, such as a preference they stated, a problem it solved or an approach that failed, in a store that lives outside any single conversation. When that user returns, the agent recalls the episodes relevant to the new request and uses them as context, so it can pick up where earlier conversations left off. The same idea applies to an agent's own experience: records of past runs that worked can be recalled as examples for similar tasks. Two traits set it apart: memories are partitioned by identity, and recall is selective, bringing back the few episodes that matter rather than whole transcripts.

## When to use it
- A returning user should not have to repeat their preferences, history or context.
- Past outcomes should shape future answers, for example "last time, this fix worked".
- The agent should reuse approaches that succeeded on earlier, similar tasks.
- Memories must outlive any single conversation or run.
- Not when everything the agent needs is in the current conversation. Conversation memory covers that and keeps no personal data beyond it.

## How it works
Roles:
- **Episode store**: durable storage outside any one conversation, partitioned by user or another identity.
- **Recall**: before the answer, selects the episodes relevant to this identity and this request.
- **Agent**: answers with the recalled episodes as extra context.
- **Writer**: after the interaction, decides what is worth keeping and saves it as a new episode.

Flow:
1. A request arrives together with the identity of who is asking.
2. Recall reads that identity's partition of the store and selects the relevant episodes.
3. The agent answers with those episodes in context.
4. The writer saves what is worth remembering. The new episode is available from the next interaction on, so an interaction never recalls itself.

## Design considerations
- **What an episode holds:** a raw transcript keeps every detail but is costly to store and recall; a model-written summary, or extracted facts such as preferences and outcomes, is compact but can lose or distort what was said.
- **How recall selects:** the most recent episodes are simple and predictable; similarity search over episode text finds relevant ones in long histories; filters by type or age cut noise. Systems often combine them.
- **When to write:** writing in the request path after each interaction is simple but adds latency; writing in the background after the conversation ends adds none, but memory lags and needs a separate job.
- **Partition key:** user, account, team or agent. The key decides who shares memory, and a wrong key leaks one user's memories into another's answers.
- **Updating and forgetting:** preferences change. Decide whether a new episode replaces, supersedes or sits beside an old one, and give users a way to see and delete what is kept.
- **Trust in recalled text:** recalled episodes re-enter the prompt, so a wrong fact or an injected instruction persists across conversations. Treat them as data, not instructions.
- **Retention and privacy:** this is personal data kept for a long time. Set retention, access rules and consent deliberately.

## Trade-offs
- Continuity and personalisation across conversations, at the cost of a read and a write on every interaction.
- Recalling the wrong episodes can mislead the answer, so retrieval quality matters.
- Stored memories go stale or are wrong from the start, and errors persist until corrected.
- Storage grows with every interaction and needs a retention policy.
- Keeping personal data brings privacy and compliance obligations.

## Related patterns
- The dividing line with [[memory/session]]: Session is one conversation, held in that conversation's checkpoints. Episodic carries memories across conversations. Start a new conversation and Session starts empty; Episodic still has what it stored about that user.
- [[memory/semantic]] looks up shared knowledge from documents, the same for every user; Episodic recalls this user's own history.
- [[memory/knowledge-graph]] can hold facts about a user as structured relations instead of episodes.
- [[governance/audit]] also keeps durable records of runs, but for people to inspect later, not for the agent to recall.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Request and identity** → the state keys `question` and `user_id`.
- **Recall** → `recall_episodes`: would read the episodes stored under `user_id` into `episodes`.
- **Agent** → `answer`: would answer `question` with `episodes` as context and set `answer`.
- **Writer** → `store_episode`: would save this interaction as a new episode under `user_id`.
- **Episode store** → not drawn; a live version would pass a store to the nodes. Every edge is fixed, so each step runs on every request.

### Framework concepts
- **Store**: the `langgraph.store.base.BaseStore` interface. A node receives it by declaring a `store: BaseStore` parameter; items live under a namespace such as `("episodes", user_id)`, read with `search` and written with `put`.
- **InMemoryStore**: `langgraph.store.memory.InMemoryStore` is the in-process store for experiments; a deployment would use a persistent one.
- **Compile with a store**: `builder.compile(store=...)` makes the store available to every node.
- **Checkpointer**: still holds the current conversation, as in [[memory/session]]. The store adds what checkpoints cannot: memory across threads.

### Key code
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

### Try this
- Which state field decides whose memories `recall_episodes` reads?
- A user states a preference in conversation 1, then opens a new conversation 2. Which node reads that preference back, and which node wrote it?
- Compare with [[memory/session]], the live pattern: what does it lose when a new thread starts?
