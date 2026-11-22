# Semantic

## What it is
Semantic memory is facts the agent looks up from a document store, rather than facts the model happens to remember. This is retrieval-augmented generation (RAG): the question is turned into a search, the best-matching passages are fetched, and the model answers from them. This version adds a quality check. A grading step judges whether the retrieved passages are relevant, and if not, the query is rewritten and retrieval is tried again. That is the corrective or self-reflective RAG style.

How it differs from [[memory/knowledge-graph]]: **Semantic retrieves passages of text that resemble the query. Knowledge Graph retrieves entities and the relations between them.** Passages suit prose answers, and a graph suits questions about how things connect.

## When to use it
- Answers must come from your own documents, such as manuals, policies or articles.
- The knowledge is too large, or changes too often, to put in the prompt.
- You want answers that can point back to a source passage.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

1. `retrieve` fetches passages for the current `query` from a document store.
2. `grade` judges whether those passages are relevant to the question.
3. The router, `route_after_grade`, picks the next step:
   - Relevant passages go to `answer`.
   - Poor passages go to `rewrite_query`.
4. `rewrite_query` rephrases the query and loops back to `retrieve`.
5. `answer` responds from the passages and goes to `__end__`.

The loop from `rewrite_query` back to `retrieve` is the point of the pattern. The skeleton's router is fixed to `answer`, so the diagram shows the loop without running it. A live version needs a cap on rewrites.

## LangGraph concepts
A live version would use:
- **Conditional edges**: `route_after_grade`, annotated with `Literal` targets, draws both branches in the diagram.
- **Cycle**: `rewrite_query` links back to `retrieve`, so the graph can retry.
- **State**: holds the `query`, the `documents` and the `answer`. A counter field would let the router stop retrying.
- **Store**: `langgraph.store.base.BaseStore` supports similarity search over stored items when an embedding index is configured. A separate vector database is the other common choice.

## Trade-offs
- Grading and rewriting add model calls, so latency and cost go up on every retry.
- The grader can be wrong. It may reject good passages or accept bad ones.
- Answer quality depends on how documents are split and indexed.
- Without a retry limit, an unanswerable question can loop forever.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
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

## Try this
- Name the State field that `rewrite_query` would change so that the next `retrieve` searches differently.
- Which node does `grade` send the run to when the passages are not relevant? Answer with the node name.
- Compare with [[memory/session]], the live pattern. It remembers what was said in this conversation. Where does Semantic's knowledge come from instead?
