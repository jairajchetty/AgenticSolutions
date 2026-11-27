# Hierarchy

## What it is
A hierarchy is supervisors of supervisors. A top-level coordinator delegates to team leads, and each team lead is itself a supervisor that manages its own workers. Work flows down through the levels and results flow back up. It is the Supervisor pattern applied recursively, and it is often built by making each team a subgraph.

The dividing line from the other two multi-agent patterns: **Hierarchy stacks supervisors of supervisors.** [[collaboration/supervisor]] has one coordinator over workers, and [[collaboration/swarm]] has no coordinator at all.

## When to use it
- One supervisor would have too many workers or tools to choose between reliably.
- The work groups into teams, such as a research team and a writing team, each with its own skills.
- You want each team to be built, tested and changed on its own.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real. The teams are drawn as flat nodes so the whole structure fits in one diagram.

The line from [[collaboration/supervisor]] is the extra level: `director` never talks to a worker directly. It talks to leads, and the leads talk to workers.

- `director` is the top coordinator. Its router sends work to `research_lead`, to `writing_lead`, or to the end.
- `research_lead` supervises `searcher` and `analyst`, then reports back to `director`.
- `writing_lead` supervises `drafter` and `editor`, then reports back to `director`.
- Each worker returns to its own lead, never to the director.

The skeleton's routers are fixed, so the diagram shows the structure without running it.

## LangGraph concepts
A live version would use:
- **Subgraphs**: each team is its own compiled graph, added as a node of the parent graph. State can be shared or mapped between levels.
- **Conditional edges**: each lead has a router annotated with its worker targets and the way back up.
- **Command**: a node can return `langgraph.types.Command` with `goto` to move control, including up to a parent level where supported.
- **State**: a shared goal and findings, with each team free to keep private fields.

## Trade-offs
- More levels mean more coordinator calls, so latency and cost rise quickly.
- Each level can lose or distort detail passed through it.
- The structure adds design work. For a handful of workers a single supervisor is simpler.
- Teams are easier to test and reuse on their own than one large flat graph.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder.add_edge(START, "director")
builder.add_conditional_edges("director", route_director)
builder.add_conditional_edges("research_lead", route_research_lead)
builder.add_conditional_edges("writing_lead", route_writing_lead)

# Each worker reports back to its own lead.
for worker, lead in [("searcher", "research_lead"),
                     ("analyst", "research_lead"),
                     ("drafter", "writing_lead"),
                     ("editor", "writing_lead")]:
    builder.add_edge(worker, lead)

return builder.compile()
```

## Try this
- Count the hops from `director` to `editor` and back. Compare with a flat supervisor that manages all four workers directly.
- Which State fields would the research team need privately, and which must be shared with the writing team?
- Compare with [[collaboration/single-agent]], the live baseline. At what size of problem would you stop using one agent?
