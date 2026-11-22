# Autonomous

## What it is
An autonomous agent is long-running and self-directed until the goal is met. It is given a goal rather than a single question, makes its own plan, acts, looks at what happened, and keeps going round that loop. It decides for itself when to stop, by checking progress against the goal. This guide uses the narrow meaning: not every agent is autonomous, only one that runs this way over a long task.

The dividing line from ReAct: **ReAct answers one request in a short loop.** [[cognitive/react]] ends when the model can answer, while Autonomous keeps pursuing the goal across many rounds.

## When to use it
- The goal is open-ended, such as "keep this dataset clean" or "work through this backlog", and no fixed list of steps fits.
- The task takes long enough that progress must be checked and recorded along the way.
- You can state what "done" means in a form the agent can check.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

Autonomous here means long-running and self-directed until the goal is met. The line from ReAct is visible in the shape: [[cognitive/react]] answers one request in a short loop and stops, while here the loop closes through a goal check, and only `check_goal` can end the run.

- `set_goal` turns the request into a goal the agent can check.
- `plan` writes the next steps toward the goal.
- `act` carries out a step, and `observe` records what came back.
- `check_goal` compares the observations with the goal. Its router sends control back to `plan` when the goal is not met, or to `report` when it is.
- `report` summarises what was done, and the run ends.

The skeleton's router is fixed to `report`, so the diagram shows the loop without running it.

## LangGraph concepts
A live version would use:
- **Conditional edges**: the router, annotated `Literal["plan", "report"]`, closes the loop or leaves it.
- **recursion_limit**: a config setting that stops a graph after a set number of steps with `langgraph.errors.GraphRecursionError`. A long-running agent needs this backstop.
- **Checkpointing**: saves state after each step, so a long run can survive a restart.
- **interrupt()**: `langgraph.types.interrupt` can pause for a person when the agent is unsure or about to do something risky.

## Trade-offs
- Cost and time are open-ended unless you set limits on rounds, spend and wall-clock time.
- If the goal check is weak, the agent may stop too early or never stop.
- Errors compound. A wrong early observation can steer every later plan.
- Needs more oversight than a short loop, such as logs and a way to stop it.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
```python
builder = StateGraph(State)
builder.add_node("set_goal", set_goal)
builder.add_node("plan", plan)
builder.add_node("act", act)
builder.add_node("observe", observe)
builder.add_node("check_goal", check_goal)
builder.add_node("report", report)

builder.add_edge(START, "set_goal")
builder.add_edge("set_goal", "plan")
builder.add_edge("plan", "act")
builder.add_edge("act", "observe")
builder.add_edge("observe", "check_goal")
builder.add_conditional_edges("check_goal", route_check_goal)
builder.add_edge("report", END)

return builder.compile()
```

## Try this
- Which State field does `check_goal` set so the router can leave the loop? Answer with its name from the skeleton.
- Trace one full round by node names, starting at `plan` and ending at the node that decides whether to go round again.
- Compare with [[cognitive/react]]: which node name in this graph decides when the run is over?
