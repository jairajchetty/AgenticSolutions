# Semantic

## What it is
Facts the agent looks up from an external knowledge source at answer time, rather than facts the model happened to absorb in training. This is retrieval-augmented generation: documents are split into passages and indexed ahead of time; at question time the question becomes a search, the best-matching passages are fetched, and the model answers from them. Because the knowledge sits outside the model, it can be updated without retraining, scoped to what the asker may see, and cited. A common extension, corrective retrieval, checks the passages before answering and searches again with a better query when they miss.

## When to use it
- Answers must come from your own documents, such as manuals, policies or articles.
- The knowledge is too large, or changes too often, to put in the prompt.
- Answers should point back to a source passage a reader can check.
- Not when the question is about how things connect across many facts, such as a chain of who reports to whom. Passage search finds text that resembles the question, not paths between entities.

## How it works
Roles:
- **Index**: the documents, split into passages and stored with whatever the search method needs.
- **Retriever**: turns the question into a query and returns the top passages.
- **Grader** (optional): judges whether the passages are relevant to the question.
- **Query rewriter** (optional): rephrases the query when the passages miss.
- **Agent**: answers from the passages, citing them where it can.

Flow:
1. Ahead of time, documents are split into passages and indexed.
2. The question becomes a query, and the retriever fetches the best-matching passages.
3. If a grader is used and the passages are poor, the query is rewritten and retrieval runs again, up to a retry limit.
4. The agent answers from the passages, and says so when they do not contain the answer.

## Design considerations
- **Retrieval method:** keyword search matches exact terms, names and codes; similarity search over embeddings matches meaning and paraphrase but can miss exact identifiers; hybrid search with a re-ranking step combines both at more cost.
- **Chunking:** small passages match precisely but lose surrounding context; large ones keep context but dilute the match and cost more tokens. Keep source and position with each passage so answers can cite it.
- **How many passages:** fetching more raises the chance the answer is there, and also the cost and the noise the model must ignore.
- **Check before answering:** a single retrieve-then-answer pass is cheapest; a grading step that rewrites the query and retries rescues poor first searches, at the cost of more model calls. Cap the retries.
- **Who decides to retrieve:** retrieving on every request is simple and predictable; giving the agent search as a tool lets it skip retrieval or search several times, but its choices are harder to predict.
- **Freshness:** re-index when sources change. A stale index gives confident, outdated answers.
- **Access control:** filter passages by what the asker may see before they reach the prompt, not after.

## Trade-offs
- Answers are grounded in sources and can be updated without retraining the model.
- Quality is bounded by retrieval: a passage that is not found cannot be used.
- Retrieval, and any grading or retries, add latency and cost to every question.
- The index needs building, re-indexing and monitoring.
- Retrieved text is untrusted input to the prompt and can carry injected instructions.

## Related patterns
- The dividing line with [[memory/knowledge-graph]]: Semantic retrieves passages of text that resemble the query. Knowledge Graph retrieves entities and the relations between them, so it can follow a chain of facts that no single passage states.
- [[memory/episodic]] recalls one user's own history; Semantic looks up shared knowledge that is the same for everyone.
- [[cognitive/reflection]] critiques a draft; the grading step here judges the evidence before any draft exists.
- [[cognitive/react]] is the loop to use when search is one tool among several that the agent calls as needed.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it. It draws the corrective variant, with the grading loop.

- **Retriever** → `retrieve`: would fetch passages for `query` into `documents`.
- **Grader** → `grade`: would judge the passages; its router `route_after_grade` sends control to `answer` or `rewrite_query`, and is fixed to `answer`.
- **Query rewriter** → `rewrite_query`: would rephrase `query`, then loop back to `retrieve`.
- **Agent** → `answer`: would answer `question` from `documents`, then go to `__end__`.
- **Index** → not drawn; a live version would search a document store. There is no retry counter in state yet, which a live version needs.

### Framework concepts
- **Conditional edges**: `route_after_grade` is annotated `Literal["answer", "rewrite_query"]`, so both branches appear in the diagram.
- **Cycle**: the edge from `rewrite_query` back to `retrieve` lets the graph retry.
- **State**: holds `question`, `query`, `documents` and `answer`; a counter field would let the router give up.
- **Store search**: `langgraph.store.base.BaseStore` supports similarity search when it is configured with an embedding index; a separate vector database is the other usual choice.

### Key code
```python
builder = StateGraph(State)
builder.add_node("retrieve", retrieve)
builder.add_node("grade", grade)
builder.add_node("rewrite_query", rewrite_query)
builder.add_node("answer", answer)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "grade")
builder.add_conditional_edges("grade", route_after_grade)
builder.add_edge("rewrite_query", "retrieve")
builder.add_edge("answer", END)

return builder.compile()
```

### Try this
- Which state field would `rewrite_query` change so that the next `retrieve` searches differently?
- Which node does `grade` send the run to when the passages are not relevant?
- Where would you add a retry limit: in a node, in `route_after_grade`, or both?
- Compare with [[memory/session]], the live pattern: it remembers what was said in this conversation. Where does Semantic's knowledge come from instead?
