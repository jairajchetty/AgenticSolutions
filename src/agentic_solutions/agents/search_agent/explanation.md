# Search

## What it is
Instead of following one line of thought, the agent explores several. It comes up with a few possible next steps, rates them, drops the weak ones and develops the promising ones further, much as a chess player looks a few moves ahead. It stops when one option is good enough or its budget runs out; Tree of Thoughts and LATS are well-known examples.

## When to use it
- Problems where a wrong early step is costly and hard to undo: puzzles, constrained planning, code that must pass tests.
- A partial solution can be judged reasonably well, by a rule, a test or a model rating.
- A better answer is worth many more model calls.
- Not when one good attempt is usually enough. Search multiplies cost and latency, and adds little when the first answer is already right or candidates cannot be told apart.

## How it works
Roles:
- **Proposer**: expands a candidate into several possible next steps.
- **Evaluator**: rates each candidate, by a test, a rule or a model judgement.
- **Selector**: decides which candidates to keep and which to expand next.
- **Budget**: limits depth, breadth or total calls.

Flow:
1. Start from the problem as the only candidate.
2. The proposer expands the selected candidates into new ones.
3. The evaluator rates the new candidates.
4. The selector keeps the promising ones and drops the rest.
5. If a candidate is good enough or the budget is spent, return the best one; otherwise go back to step 2.

## Design considerations
- **Search strategy:** keeping the top few at each level (beam search) is simple and bounded; breadth-first or depth-first search is systematic but explores many weak branches; best-first expands the highest-rated candidate anywhere in the tree; Monte Carlo tree search balances exploring new branches against exploiting good ones, and copes with noisy ratings, at the price of more bookkeeping and calls.
- **Evaluator kind:** a test, rule or checker is reliable and cheap where one exists; a model rating works for open-ended tasks but is noisy and can be fooled by confident wording.
- **Breadth and depth:** cost grows roughly with breadth times depth. Set both, or a total call budget, before the run.
- **Candidate diversity:** near-identical proposals waste the budget. Vary prompts or sampling, or deduplicate.
- **Parallel expansion:** expanding candidates in parallel keeps latency manageable, but parallel results must be merged before selection.
- **Backtracking:** keeping dropped candidates lets the search return to them when every kept branch fails, at the cost of memory.

## Trade-offs
- Expensive: many model calls per answer, growing with breadth and depth.
- Only as good as the evaluator; a weak one prunes the right path early.
- Higher latency than a single pass, even with parallel expansion.
- More state to keep and inspect than a linear loop.

## Related patterns
- [[cognitive/reflection]] improves one draft in place; Search keeps several candidates and compares them.
- [[cognitive/planning]] commits to a single plan; Search explores alternatives before committing.
- [[cognitive/react]] takes one step at a time along a single path.
- [[governance/review]] can act as the evaluator when a separate checker is needed.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it. The Studio sketches a beam search: keep the best few candidates at each level.

- **Proposer** → `propose`: would expand each candidate in `frontier` into several next steps.
- **Evaluator and selector** → `score`: would rate candidates into `scores` and keep the best few. Its router loops back to `propose` while promising and within budget, or goes on to `answer`; it is fixed to `answer`.
- **Budget** → the `depth` state key, which a live router would read.
- **Result** → `answer`: would return the best candidate found, then the run ends.

### Framework concepts
- **Send**: a live version would use `langgraph.types.Send` to fan out one task per candidate, so candidates expand in parallel.
- **Reducers**: a state channel with a reducer would merge the parallel results.
- **Conditional edges**: the router is annotated `Literal["propose", "answer"]`, so both exits appear in the diagram.
- **Checkpointing**: would save each level, so a long search can be inspected or resumed.

### Key code
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

### Try this
- The first lap starts from the task alone, `propose` makes 3 candidates per kept candidate, and `score` keeps the best 2 each lap. How many candidates exist after four laps, counting those dropped? (Answer: 3 + 6 + 6 + 6 = 21.)
- What would you use to score a candidate for a coding task, and why is that better than asking a model?
- Compare with [[cognitive/reflection]], which improves one draft in place.
