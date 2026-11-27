# Knowledge Graph

## What it is
Knowledge-graph memory stores what the agent knows as entities and the relations between them, for example "Ada works at Acme" or "Acme makes Widget". To answer, the agent extracts the entities in the question, queries the graph for what is connected to them, and answers from those relations. After answering, it adds anything new it learned back into the graph.

How it differs from [[memory/semantic]]: **Knowledge Graph retrieves entities and the relations between them. Semantic retrieves passages of text that resemble the query.** A graph can follow a chain of relations, such as who works at the company that makes a product. Passage search cannot do that unless one passage happens to say it all.

## When to use it
- Questions are about how things connect, such as people, teams, products and dependencies.
- Answers need several hops along relations rather than one matching passage.
- The agent should accumulate structured knowledge as it talks.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real. There are no routers, and every step runs on every turn.

1. `extract_entities` finds the entities named in the question and puts them in `entities`.
2. `query_graph` looks up the relations around those entities and puts them in `relations`.
3. `answer` responds from the relations that were found.
4. `update_graph` writes newly learned entities and relations back, so the graph grows.

Unlike [[memory/semantic]], `query_graph` follows relations between entities rather than matching passages of text.

Writing comes last, after the answer. The relations are stored as (subject, relation, object) triples in the State.

## LangGraph concepts
A live version would use:
- **State**: carries the `entities` and `relations` between nodes.
- **Store**: `langgraph.store.base.BaseStore` is a key-value store passed to nodes, which could hold nodes and edges under a namespace. It is not a graph database, so graph queries would be written by the node.
- **Graph database**: a dedicated graph database is the usual home for a large graph. A node would call it as an ordinary tool.
- **Structured output**: a way to make the model return entities and relations in a fixed shape.

## Trade-offs
- Extraction is the weak point. Missed or wrong entities give a wrong or empty lookup.
- Duplicates are common, such as "Acme" and "Acme Inc", so merging entities needs thought.
- Building and maintaining the graph costs more effort than indexing documents.
- Wrong facts written by `update_graph` persist and affect later answers.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("extract_entities", extract_entities)
builder.add_node("query_graph", query_graph)
builder.add_node("answer", answer)
builder.add_node("update_graph", update_graph)

builder.add_edge(START, "extract_entities")
builder.add_edge("extract_entities", "query_graph")
builder.add_edge("query_graph", "answer")
builder.add_edge("answer", "update_graph")
builder.add_edge("update_graph", END)

return builder.compile()
```

## Try this
- Which State field holds the facts that `query_graph` finds? Answer with its name from the skeleton.
- Which node runs last? Answer with its name from the diagram.
- Compare with [[memory/session]], the live pattern. It keeps the raw messages of one conversation. What does a graph keep instead?
