# Reflection

## What it is
Reflection is a generate, critique, revise loop. The model writes a draft, judges that draft against the task, and rewrites it using its own feedback. It repeats until the critique is good enough or a round limit is hit. It belongs to the family of ideas behind Reflexion and Self-Refine, and is often called an evaluator-optimizer loop.

The dividing line from Review: **Reflection is the same agent critiquing its own output.** [[governance/review]] is a separate agent or a person checking it. The separation matters, because a model grading its own work tends to share its own blind spots.

## When to use it
- Output has a quality bar you can describe in words: tone, correctness, format, completeness.
- A first draft is usually close, and a second look catches the gaps.
- You can afford two or three extra model calls per answer.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

- `generate` writes the first draft from the task.
- `critique` reads the draft and returns a score and written feedback. Its router either ends the run, when the score is high enough or the round limit is reached, or sends the draft to `revise`.
- `revise` rewrites the draft using the feedback, then returns to `critique`.

The `critique` -> `revise` -> `critique` cycle is the reflection loop. The skeleton's router is fixed to end, so the diagram shows the loop without running it.

## LangGraph concepts
A live version would use:
- **Conditional edges**: a router annotated `Literal["revise", "__end__"]` stops or continues the loop.
- **Structured output**: `with_structured_output` makes the critique a typed object (score and feedback) that the router can read.
- **State**: keeps the task, the latest draft, the feedback and an iteration counter. A history list would show every draft.
- **Cycles**: LangGraph graphs may loop, so a counter in state must bound them.

## Trade-offs
- Costs at least two model calls per answer, and more for each revision.
- The critic can be wrong or flatter the draft. A numeric score from a model is a rough signal.
- Without a limit the loop may never converge, or may drift away from the task.
- Cannot catch what the model does not know. A fact-check needs a tool or an outside reviewer.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
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

## Try this
- Which two fields of state must `critique` write so its router can decide? What would you check to stop after three rounds?
- Name one task where a model grading itself would miss the error, and say who or what should check it instead.
- Compare with [[governance/review]], where a separate checker sits in the same shape, and with [[cognitive/react]], which loops on tool results rather than on a critique.
