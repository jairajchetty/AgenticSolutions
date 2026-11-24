# Hierarchy

## What it is
Supervisors of supervisors. A top-level coordinator delegates to team leads, and each lead is itself a supervisor over its own workers. Work flows down through the levels and results flow back up. It is the Supervisor pattern applied recursively, with each team typically packaged as a self-contained unit that can be built and tested on its own.

## When to use it
- One coordinator would have too many workers or tools to choose between reliably.
- The work groups into teams, such as research and writing, each with its own skills.
- Each team should be built, tested and changed independently.
- Not when a handful of workers would do. Every extra level adds coordinator calls, latency and a place where detail can be lost.

## How it works
Roles:
- **Top coordinator**: splits the goal across teams and decides when the whole job is done. It talks only to team leads.
- **Team leads**: each supervises its own workers, then reports a result upward.
- **Workers**: specialists that do one piece of work and report to their own lead.
- **Shared state and team-private state**: what every level sees, and what stays inside a team.

Flow:
1. The top coordinator reads the goal and assigns work to a team lead.
2. The lead picks one of its workers, reads the result, and repeats until the team's part is done.
3. The lead reports back to the top coordinator.
4. The top coordinator assigns the next team, back at step 1, or finishes.

## Design considerations
- **Number of levels:** each level reduces the choices any one coordinator faces, but adds calls and latency. Add a level only when a coordinator's choices have become unreliable.
- **What crosses a level:** a lead can pass up raw results or a summary. Summaries keep upper levels focused but can drop the detail a later team needs.
- **Team boundaries:** group workers by the skills and context they share, so that most work stays inside one team.
- **Private versus shared state:** keep a team's working notes private, and agree a small shared contract for what teams hand each other.
- **Mixing patterns per team:** a team does not have to be a supervisor inside; a lead can run a fixed sequence or a peer group where that fits better.
- **Limits per level:** cap rounds at every level, since a loop low in the tree multiplies cost above it.

## Trade-offs
- More levels mean more coordinator calls, so cost and latency rise quickly.
- Each level can lose or distort detail passed through it.
- Teams are easier to test and reuse than one large flat group.
- More design work up front than a single supervisor.

## Related patterns
- The dividing line across the three multi-agent patterns: Hierarchy stacks supervisors of supervisors. [[collaboration/supervisor]] has one coordinator over workers, and [[collaboration/swarm]] has no coordinator at all.
- [[collaboration/single-agent]] is the baseline: one agent, no teams.
- [[cognitive/planning]] can drive the top coordinator, turning the goal into team assignments.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it. The teams are drawn as flat nodes, so the whole structure fits in one diagram.

- **Top coordinator** → `director`: its router sends work to `research_lead`, to `writing_lead`, or to `__end__`. It never links to a worker.
- **Team leads** → `research_lead`, which supervises `searcher` and `analyst`, and `writing_lead`, which supervises `drafter` and `editor`. Each lead's router picks a worker or reports back to `director`.
- **Workers** → `searcher` and `analyst` would build `findings`; `drafter` and `editor` would write and polish `draft`. Each returns to its own lead.
- **Shared state** → `goal`, `findings` and `draft`. The routers are fixed, so the structure is drawn but never run.

### Framework concepts
- **Subgraphs**: a live version would make each team its own compiled graph, added as a node of the parent, with state shared or mapped between levels.
- **Conditional edges**: each lead's router is annotated with its worker targets and the way back up.
- **Command**: a node could return `langgraph.types.Command` with `goto` to move control, including up to a parent graph.

### Key code
```python
builder = StateGraph(State)
for name, fn in [("director", director), ("research_lead", research_lead),
                 ("writing_lead", writing_lead), ("searcher", searcher),
                 ("analyst", analyst), ("drafter", drafter), ("editor", editor)]:
    builder.add_node(name, fn)

builder.add_edge(START, "director")
builder.add_conditional_edges("director", route_director)
builder.add_conditional_edges("research_lead", route_research_lead)
builder.add_conditional_edges("writing_lead", route_writing_lead)
for worker, lead in [("searcher", "research_lead"), ("analyst", "research_lead"),
                     ("drafter", "writing_lead"), ("editor", "writing_lead")]:
    builder.add_edge(worker, lead)

return builder.compile()
```

### Try this
- Count the hops from `director` to `editor` and back. Compare with a flat supervisor that manages all four workers directly.
- Which state fields would the research team keep privately, and which must it share with the writing team?
- Compare with [[collaboration/supervisor]], one level of the same structure.
