# Review

## What it is
A separate checker, another agent or a person, judges a result before it is accepted. The author produces a draft, the reviewer assesses it against stated criteria, and either accepts it or sends it back with comments for revision. Independence is the point: the reviewer brings different instructions, information, tools, authority or a different model, so it can catch what the author cannot see in its own work. Review is often called a critic or second-opinion pattern, and it is a natural place for a person's judgement on quality, as distinct from a person's permission to proceed.

## When to use it
- A mistake would be costly enough that a second opinion is worth the delay.
- The reviewer needs different information, rules or authority than the author.
- A person must vouch for the result, such as a lawyer reading a contract draft.
- Not when the author can check its own work well enough against a clear rubric. Self-critique costs less and needs no second party.

## How it works
Roles:
- **Author**: produces the draft, and revises it using the reviewer's comments.
- **Reviewer**: a separate agent or a person who judges the draft against criteria and returns a verdict with comments.
- **Acceptance**: records the accepted draft as the final result.
- **Round limit**: ends the back-and-forth when it does not converge.

Flow:
1. The author produces a draft.
2. The reviewer judges it and returns a verdict and comments.
3. If rejected, the author revises using the comments, back to step 2.
4. If accepted, the draft becomes the final result. If the round limit is reached first, the case escalates, for example to a person.

## Design considerations
- **Who reviews:** a different model, or the same model with its own role, instructions and context, is fast and scales but may share the author's blind spots; a reviewer agent with tools, such as tests or fact lookups, grounds its verdict in evidence; a person brings authority and judgement but is slow and costly; several reviewers, each on one aspect, cover more at more cost.
- **Criteria:** an explicit rubric, shared with the author, makes verdicts consistent and revisions targeted.
- **Verdict shape:** accept or reject with specific comments is easier to act on than a score; a score needs a tested threshold.
- **What the reviewer sees:** the draft alone gives fresh eyes; the task and sources let it check facts; hiding the author's reasoning reduces anchoring on it.
- **Round limit and escalation:** cap send-backs, and decide what happens at the cap: escalate to a person, or return the best draft with its open comments.
- **Review everything or sample:** full review is thorough and costly; reviewing a risk-based sample or a random share keeps cost down where errors are rare.
- **Waiting for a person:** a human review needs the run to pause durably and resume when they answer, with a timeout and a fallback.

## Trade-offs
- Catches errors the author misses, and puts a second party on record as having checked.
- Adds latency and cost for every review round.
- The reviewer can be wrong, too strict or too lenient.
- A model reviewer may share the author's blind spots; a person reviewer adds waiting time.

## Related patterns
- The dividing line with [[cognitive/reflection]]: Reflection is the same agent critiquing its own output. Review is a separate agent or a person checking it.
- [[governance/approval]] pauses for a person to permit an action; Review judges the quality of a result and can send it back for rework.
- [[governance/guardrails]] screens content automatically for safety; Review judges whether a result is good enough.
- [[collaboration/supervisor]] can route work to a reviewer as one of its workers.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Author** → `draft`: would write or rewrite `content` from `task`, using `comments` if present.
- **Reviewer** → `review`: would have a separate agent or a person set `comments` and `accepted`. Its router `route_review` sends control back to `draft` or on to `approve`, and is fixed to `approve`.
- **Acceptance** → `approve`: would copy the accepted `content` into `final`, then end.
- **Round limit** → not yet in state; a live version needs a counter that `route_review` reads.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["draft", "approve"]`, so the send-back path appears in the diagram.
- **Interrupt**: when the reviewer is a person, `review` can pause the run with `langgraph.types.interrupt` and resume when they answer; pausing and resuming needs a checkpointer (see [[governance/approval]]).
- **State**: holds `task`, `content`, `comments`, `accepted` and `final`.

### Key code
```python
builder = StateGraph(State)
builder.add_node("draft", draft)
builder.add_node("review", review)
builder.add_node("approve", approve)

builder.add_edge(START, "draft")
builder.add_edge("draft", "review")
builder.add_conditional_edges("review", route_review)
builder.add_edge("approve", END)

return builder.compile()
```

### Try this
- Which state field carries the reviewer's feedback back to `draft`, and which node sets it?
- `route_review` returns `"draft"` or `"approve"`. Which state field would a live version read to choose?
- To end an endless send-back cycle you would add a counter to state. Which function would read it: `draft` or `route_review`?
- Compare with [[cognitive/reflection]], the same loop shape with one agent in both roles. What does the separate reviewer change?
