# Autonomous

## What it is
You give the agent a goal, not a single question, and it keeps working on its own until it decides the goal is met. Round after round it plans, acts, checks its progress and chooses the next step, sometimes over hours. Because nobody watches every step, its limits are set up front: how much it may spend, what it may touch, and when it must check with a person.

## When to use it
- The goal is open-ended, such as "work through this backlog" or "keep this dataset clean", and no fixed list of steps fits.
- The task takes long enough that progress must be recorded and checked along the way.
- You can state what "done" means in a form the agent can check.
- Not when the request can be answered in a handful of tool calls. A short reason-and-act loop is cheaper and easier to oversee.

## How it works
Roles:
- **Goal**: what to achieve, with criteria the agent can check.
- **Planner**: decides the next steps toward the goal, given progress so far.
- **Executor**: carries out a step, usually through tools.
- **Progress record**: what was done and what came back, kept outside the model's context when it grows long.
- **Goal check**: compares progress with the goal and the budget.
- **Reporter**: summarises the outcome when the run ends.

Flow:
1. The request is turned into a goal with checkable criteria.
2. The planner chooses the next steps.
3. The executor acts, and the result is recorded as progress.
4. The goal check decides: the goal is met, so report; the budget is spent, so report what was achieved; otherwise, back to step 2.

## Design considerations
- **Defining done:** checkable criteria, such as tests passing or a queue emptying, are reliable; a model judging its own progress is flexible but may declare success early or never. A weak check is a common cause of runaway runs.
- **Budgets:** cap rounds, spend and wall-clock time, enforced outside the model so the agent cannot argue past them.
- **Re-plan every round or follow a plan:** re-planning each round adapts to surprises but costs more and can drift from the goal; planning once and revising on failure is cheaper and steadier.
- **Progress memory:** history soon exceeds the context window. Summarise it, keep a task list or scratchpad, or store it externally and recall what is relevant.
- **Durability:** save state after each step so a crash or deploy resumes the run instead of restarting it, and make steps safe to repeat.
- **Oversight points:** decide where a person is consulted, such as before irreversible actions, on low confidence or at milestones, and provide a way to stop the run at any time.
- **Permissions:** grant the least access the goal needs and sandbox risky tools; autonomy multiplies the effect of one bad action.

## Trade-offs
- Handles open goals that no fixed sequence or single request can cover.
- Cost and duration are open-ended unless budgets bound them.
- Errors compound: a wrong early observation can steer every later plan.
- Harder to test and evaluate, because runs are long and paths vary.
- Needs monitoring, logs and a reliable way to stop it.

## Related patterns
- The dividing line with [[cognitive/react]]: ReAct answers one request in a short loop and ends when it can answer. Autonomous pursues an open goal over a long run, deciding for itself when it is done.
- [[cognitive/planning]] supplies the planning step; an autonomous agent plans repeatedly as it learns.
- [[governance/approval]] is how a person is consulted at the chosen oversight points.
- [[governance/audit]] keeps the durable record a long unattended run needs.
- [[execution/event-driven]] can start an autonomous run, or wake one that is waiting.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **Goal** → `set_goal`: would turn the request into a checkable `goal`.
- **Planner** → `plan`: would write the next `steps` toward `goal`.
- **Executor** → `act`: would carry out the next step in `steps`.
- **Progress record** → `observe`: would append what the action produced to `observations`.
- **Goal check** → `check_goal`: would judge `observations` and set `goal_met`. Its router `route_check_goal` sends control back to `plan` or on to `report`, and is fixed to `report`.
- **Reporter** → `report`: would summarise the run in `summary`, then end.
- The budget is not modelled in state; a live version would rely on the framework's step limit, below, and its own counters.

### Framework concepts
- **Conditional edges**: the router is annotated `Literal["plan", "report"]`, so the loop appears in the diagram.
- **recursion_limit**: a config setting that ends a run after a set number of steps by raising `langgraph.errors.GraphRecursionError`; a long-running graph needs this backstop.
- **Checkpointer**: saves state after each step, so a long run can survive a restart.
- **interrupt()**: `langgraph.types.interrupt` can pause for a person before a risky step (see [[governance/approval]]).

### Key code
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

### Try this
- Which state field does `check_goal` set so the router can leave the loop?
- Trace one full round by node names, starting at `plan` and ending at the node that decides whether to go round again.
- Where would you add a spend budget: a new state field read by `route_check_goal`, or only the step limit? What does each catch?
- Compare with [[cognitive/react]]: which node in this graph decides when the run is over?
