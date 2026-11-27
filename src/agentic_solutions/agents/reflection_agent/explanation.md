# Reflection

## What it is
A generate, critique, revise loop run by one agent on its own output. The agent writes a draft, judges it against the task, and rewrites it using that feedback, repeating until the critique passes or a round limit is reached. It belongs to the family of ideas behind Reflexion and Self-Refine, and is often called an evaluator-optimizer loop. The critic is part of the same agent, so it shares the agent's knowledge and, to a degree, its blind spots.

## When to use it
- The output has a quality bar that can be stated: tone, correctness, format, completeness.
- A first draft is usually close, and a second look catches the gaps.
- Two or three extra model calls per answer are affordable.
- Not when the check must be independent of the author. A separate reviewer, or a person, is the right tool for that.

## How it works
Roles:
- **Generator**: writes the first draft from the task.
- **Critic**: judges the current draft against the task and stated criteria, and returns a verdict and written feedback.
- **Reviser**: rewrites the draft using the feedback.
- **Stop rule**: ends the loop when the verdict passes or the round budget is spent.

Flow:
1. The generator writes a draft.
2. The critic judges it and writes feedback.
3. If the verdict passes or the budget is spent, the latest draft is the result.
4. Otherwise the reviser rewrites the draft with the feedback, and the critic judges again, back at step 2.

## Design considerations
- **What the critic checks against:** the model's own judgement is cheap but can flatter the draft; an explicit rubric makes verdicts more consistent; external signals such as test results, a validator or tool lookups ground the critique in facts the model cannot invent. Grounded checks catch more, but need something to run.
- **Verdict shape:** a pass or fail with reasons is easier to act on than a numeric score. A model's score is a rough signal, so any threshold on it needs testing.
- **Feedback specificity:** feedback that names the exact problem and location produces better revisions than a general grade.
- **Round budget:** cap the rounds. Without a cap the loop may not converge, or may drift away from the task.
- **Keep or discard drafts:** keeping every draft and critique helps debugging and lets the loop return the best draft rather than the last one.
- **Separate prompts for author and critic:** the same model with a distinct critic prompt is still Reflection; a dedicated critic prompt can judge more strictly than asking the author to check itself in the same breath.

## Trade-offs
- At least two model calls per answer, and more for each revision.
- The critic can be wrong, or approve a draft too readily.
- Self-critique cannot catch what the model does not know; a fact check needs a tool or an outside reviewer.
- Revisions can over-correct, trading one flaw for another.

## Related patterns
- The dividing line with [[governance/review]]: Reflection is the same agent critiquing its own output. Review is a separate agent or a person checking it, which matters when the author's blind spots must not decide the outcome.
- [[cognitive/react]] loops on tool results, not on a critique of a draft.
- [[cognitive/search]] keeps several candidates and compares them, instead of improving one draft in place.
- [[governance/guardrails]] screens content for safety, not for quality.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Generator** → `generate`: would write the first draft from `task`.
- **Critic** → `critique`: would write `score` and `feedback` to state.
- **Stop rule** → `route_after_critique`: would end on a good score or after N rounds, counted in `iteration`; it is fixed to `__end__`, so the loop is drawn but never run.
- **Reviser** → `revise`: would rewrite `draft` from the feedback, then return to `critique`.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["revise", "__end__"]`, so both exits appear in the diagram.
- **Cycles**: graphs may loop, so a counter in state, here `iteration`, must bound them.
- **Structured output**: a live version would use `with_structured_output` to make the critique a typed object the router can read.
- **State**: holds the task, the latest draft, the score, the feedback and the round counter.

### Key code
```python
builder = StateGraph(State)
builder.add_node("generate", generate)
builder.add_node("critique", critique)
builder.add_node("revise", revise)

builder.add_edge(START, "generate")
builder.add_edge("generate", "critique")
builder.add_conditional_edges("critique", route_after_critique)
builder.add_edge("revise", "critique")

return builder.compile()
```

### Try this
- Which state fields must `critique` write so its router can decide, and what would it check to stop after three rounds?
- Name one task where a model grading itself would miss the error, and say what should check it instead.
- Compare with [[governance/review]], where a separate checker sits in the same shape.
