# Search

## What it is
Search treats reasoning as exploring a tree of possibilities. Instead of committing to one line of thought, the model proposes several candidate next steps, a scorer rates them, weak ones are pruned, and the best are expanded further. This is the idea behind Tree of Thoughts, which uses breadth-first or depth-first search over "thoughts", and LATS (Language Agent Tree Search), which brings in Monte Carlo tree search. Beam search is the simplest version: keep the top few candidates at each depth.

## When to use it
- Problems where a wrong early step is costly and hard to undo: puzzles, planning with constraints, code that must pass tests.
- You can judge a partial solution reasonably well, by a rule, a test or a model rating.
- You can pay for many model calls to get a better answer.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

- `propose` expands the current candidates into several possible next steps.
- `score` rates every candidate and keeps only the best few. Its router sends the search back to `propose` while it is promising and within budget, or on to `answer`.
- `answer` returns the best candidate found, and the graph ends.

The `propose` -> `score` -> `propose` cycle is one level of the tree per lap. The skeleton's router is fixed to `answer`, so the diagram shows the loop without running it. A live version would bound depth and total model calls.

## LangGraph concepts
A live version would use:
- **Send**: `langgraph.types.Send` fans out one task per candidate, so candidates are expanded in parallel.
- **Reducers**: a state channel with a reducer merges the results from the parallel branches.
- **Conditional edges**: the router, annotated `Literal["propose", "answer"]`, decides to go deeper or stop.
- **Checkpointing**: saves each level, so a long search can be inspected or resumed.

## Trade-offs
- The most expensive pattern here. Cost grows with breadth times depth.
- Only as good as the scorer. A model rating partial work can be noisy, so a test or rule is better when one exists.
- Diverse candidates are needed. If every proposal is a near copy, the search adds cost and no benefit.
- Latency stays acceptable only with parallel expansion and a firm budget.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("propose", propose)
builder.add_node("score", score)
builder.add_node("answer", answer)

builder.add_edge(START, "propose")
builder.add_edge("propose", "score")
builder.add_conditional_edges("score", route_after_score)
builder.add_edge("answer", END)

return builder.compile()
```

## Try this
- Suppose `propose` makes 3 candidates and `score` keeps 2. How many candidates exist after four laps, counting those pruned?
- What would you use to score a candidate for a coding task, and why is that better than asking a model?
- Compare with [[cognitive/reflection]], which improves one draft in place, and [[cognitive/planning]], which commits to a single plan.
