# Knowledge Graph

## What it is
Memory stored as a map of things and how they connect, such as "Ada works at Acme" and "Acme makes Widget". To answer a question, the agent finds the things it mentions on the map and follows the connections, one step at a time. That lets it answer questions that need several links joined up, such as "who works at the company that makes Widget?", and the path it followed explains the answer.

## When to use it
- Questions are about how things connect, such as people, teams, products, systems and dependencies.
- Answers need several hops along relations rather than one matching passage.
- The answer should come with the chain of facts that supports it.
- The agent should build up structured knowledge as it works.
- Not when answers live in prose and a matching paragraph is enough. Building and maintaining a graph costs far more than indexing documents.

## How it works
Roles:
- **Graph store**: holds entities, relations and, ideally, where each fact came from.
- **Entity linker**: finds the entities named in the question and resolves them to entries in the graph.
- **Graph query**: follows relations from those entries and returns the connected facts.
- **Agent**: answers from the returned facts.
- **Graph writer** (optional): adds new entities and relations learned during the interaction.

Flow:
1. The entity linker extracts the entities in the question and resolves each to a graph entry.
2. The graph query follows their relations, one or more hops out, and returns the facts it reached.
3. The agent answers from those facts.
4. If the graph grows at run time, the writer adds what was learned, after checks.

## Design considerations
- **Where the graph comes from:** curated by people or loaded from existing structured data is accurate but slow to grow; extracted by a model from documents is broad but noisy; grown from conversations adapts over time but accumulates errors.
- **Schema:** a fixed set of entity and relation types keeps queries consistent; an open schema captures more but fragments, as "works at" and "employed by" become two relations.
- **Entity resolution:** "Acme" and "Acme Inc" must become one entry, and the question's mention must link to it. This is the usual weak point; missed links give empty or wrong lookups.
- **How to query:** a model writing a query in the graph's query language is flexible but can write wrong queries; fixed traversals, such as neighbours within two hops, are predictable but narrower. Bound the hops, because neighbourhoods grow fast.
- **Storage:** a dedicated graph database suits large graphs and deep traversals; triples in a general key-value or relational store suit small ones.
- **Writing back:** validate before writing, and record the source and time of each fact so a wrong one can be traced and removed.
- **Combine with passages:** linking facts to the passages they came from lets answers cite them and lets text search fill gaps the graph does not cover.

## Trade-offs
- Multi-hop and relationship questions become answerable, with an explainable path.
- Extraction and entity resolution limit quality; mistakes there give confident wrong answers.
- More effort to build and maintain than a document index.
- Wrong facts written into the graph persist and affect later answers.
- Nuance and context in prose are lost when text is reduced to triples.

## Related patterns
- The dividing line with [[memory/semantic]]: Knowledge Graph retrieves entities and the relations between them. Semantic retrieves passages of text that resemble the query, and cannot follow a chain of relations unless one passage happens to state it all.
- [[memory/episodic]] remembers what happened with a user; facts extracted from those episodes can feed a graph.
- [[cognitive/react]] fits when graph queries are one tool the agent calls in a loop, deciding how far to explore.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Entity linker** → `extract_entities`: would find the entities in `question` and put them in `entities`.
- **Graph query** → `query_graph`: would look up their relations and put them in `relations`, as (subject, relation, object) triples.
- **Agent** → `answer`: would answer from `relations` and set `answer`.
- **Graph writer** → `update_graph`: would add newly learned entities and relations, after the answer.
- **Graph store** → not drawn. Every edge is fixed, so the skeleton grows the graph on every request and does not model the number of hops.

### Framework concepts
- **State**: carries `entities` and `relations` from node to node.
- **Store**: `langgraph.store.base.BaseStore` is a key-value store passed to nodes. It could hold entities and edges under a namespace, but it is not a graph database, so traversal logic would live in the node.
- **Graph database as a tool**: a large graph would sit in a dedicated database, which a node calls like any other external service.
- **Structured output**: a way to make the model return entities and triples in a fixed shape.

### Key code
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

### Try this
- Which state field holds the facts that `query_graph` finds, and what shape does each fact have?
- Which node runs last, and why does it come after `answer` rather than before?
- Compare with [[memory/session]], the live pattern: it keeps the raw messages of one conversation. What does a graph keep instead?
