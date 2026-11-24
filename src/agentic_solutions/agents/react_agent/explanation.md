# ReAct

## What it is
A loop in which the model alternates between reasoning and acting (Yao et al., "ReAct: Synergizing Reasoning and Acting"). It decides what it needs, requests a tool call, reads the result, and decides again. The loop ends when the model replies in plain text instead of requesting another call, or when a round limit is reached. Each round's decision rests on what the previous tools actually returned, not on a plan fixed in advance.

## When to use it
- The path to the answer depends on what the tools return, so the steps cannot be listed in advance.
- Questions that need a calculation, a lookup or a current value the model should not guess.
- A short, bounded task: one user request, a handful of tool calls.
- Not when the steps are known before the request arrives. Fixed steps in code are cheaper, faster and easier to test than a loop that rediscovers them each time.

## How it works
Roles:
- **User**: sends a request and receives the final reply.
- **Reasoner**: the model, given the conversation and a description of each available tool. Each turn it either requests one or more tool calls or writes the final answer.
- **Tool runner**: executes the requested calls and returns each result, or its error, to the conversation.

Flow:
1. The user sends a request.
2. The reasoner reads the conversation and decides: call tools, or answer.
3. If it requests calls, the tool runner executes them and appends the results.
4. The reasoner reads the results and decides again, back at step 2.
5. When the reasoner answers in plain text, or the round limit is hit, the reply goes to the user and the system waits for the next request.

## Design considerations
- **Round cap:** bound tool rounds per request, and decide what the user sees when the cap is hit: a partial answer, an apology or an escalation.
- **Tool descriptions:** the model chooses tools only from their names, descriptions and parameter schemas. Vague or overlapping descriptions lead to wrong calls.
- **Tool results are untrusted input:** text returned by a tool can try to steer the model. Treat it like user input, and keep consequential actions behind a separate check.
- **Errors as observations:** return a failed call's error to the model so it can retry or change course, rather than aborting the run.
- **Parallel calls:** letting the model request several independent calls in one round cuts latency; forcing one call per round is simpler to trace and order.
- **Context growth:** every round re-sends the growing history. Truncate or summarise long tool output before it goes back to the model.
- **Stop signal:** a plain-text reply is the usual end signal; an explicit final-answer tool makes the end unambiguous at the cost of one more convention.

## Trade-offs
- Flexible, but the number of model calls per request is not known up front, so cost and latency vary.
- Each round re-sends the growing history, so long loops grow more expensive per round.
- Over a long task the loop can lose sight of the goal, since nothing above it holds a plan.
- Quality depends heavily on tool design and descriptions.

## Related patterns
- The dividing line with [[execution/tool-use]]: they are the same page. Tool Use is the capability, calling functions and APIs; ReAct is the loop that uses it.
- The dividing line with [[execution/autonomous]]: ReAct answers one request in a short loop. Autonomous pursues an open goal over a long run and decides for itself when it is done.
- [[cognitive/planning]] writes the steps before acting, instead of choosing one step at a time.
- [[collaboration/single-agent]] makes one model call with no loop at all.
- [[governance/approval]] puts a person in front of the consequential calls this loop proposes.

## How this Studio implements it

### Mapping
This demo is a Guide-only skeleton: the nodes are placeholders that return `{}`, but the wiring is real and the diagram is drawn from it.

- **User** → `ask`: would collect the next message. Its router sends the turn to `agent`, back to `ask` on empty input, or to `__end__` on `stop`.
- **Reasoner** → `agent`: would call the model with tools bound. Its router goes to `tools` when the model requested calls, otherwise back to `ask` with the final text.
- **Tool runner** → `tools`: would run the requested calls, then return to `agent`.
- **Round cap** → the `tool_rounds` state key, which a live router would read.

### Framework concepts
- **Conditional edges**: each router is annotated with every target, such as `Literal["tools", "ask"]`, which is how the diagram shows branches the fixed placeholder never takes.
- **ToolNode**: a live version would use `langgraph.prebuilt.ToolNode` to run the tool calls on the last model message.
- **bind_tools**: tells the chat model which tools exist, so it can emit tool calls.
- **interrupt()**: would let `ask` pause for the next message without blocking a process.
- **recursion_limit**: a backstop that stops a runaway graph with an error, separate from the round cap.

### Key code
```python
builder = StateGraph(State)
builder.add_node("ask", ask)
builder.add_node("agent", agent)
builder.add_node("tools", tools)

builder.add_edge(START, "ask")
builder.add_conditional_edges("ask", route_after_ask)
builder.add_conditional_edges("agent", route_after_agent)
builder.add_edge("tools", "agent")

return builder.compile()
```

### Try this
- Trace "what is 17 times 23, in hex?" through the diagram. How many times would the `agent` → `tools` → `agent` cycle run if each tool does one operation?
- Which router would read `tool_rounds` to enforce the cap, and where should it send the run when the cap is hit?
- Compare with [[collaboration/single-agent]] (live), which makes one model call with no loop.
