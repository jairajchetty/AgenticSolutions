# ReAct

## What it is
ReAct (Yao et al., "ReAct: Synergizing Reasoning and Acting") is a loop where the model alternates between reasoning and acting. It thinks about what it needs, calls a tool, reads the result, and thinks again. It stops when it can answer in plain text. This is the loop most people mean by "an agent that uses tools".

Dividing lines:
- **ReAct vs Tool Use:** the same page. Tool Use is the capability (calling functions and APIs). ReAct is the loop that uses it, which is why [[execution/tool-use]] opens this guide.
- **ReAct vs Autonomous:** ReAct answers one request in a short loop. [[execution/autonomous]] pursues an open goal over a long run and decides for itself when it is done.

## When to use it
- The path to the answer depends on what the tools return, so you cannot list the steps in advance.
- Questions that need a calculation, a lookup or a current value that the model should not guess.
- A short, bounded task: one user request, a handful of tool calls.

## How this graph works
This is a skeleton: the nodes below are placeholders, but the wiring is real.

- `ask` takes the next user message. Its router sends the turn to `agent`, back to `ask` on empty input, or to `__end__` when the user stops.
- `agent` is the reasoning step. A live version would call the model with tools bound. Its router goes to `tools` when the model asked for any, otherwise back to `ask` with the final text.
- `tools` runs the requested calls, then returns to `agent` so the model can read the results.

The `agent` -> `tools` -> `agent` cycle is the ReAct loop. A live version would cap the number of rounds per user turn so the loop cannot spin forever.

## LangGraph concepts
A live version would use:
- **Conditional edges**: a router annotated `Literal["tools", "ask"]` chooses the next node from state.
- **ToolNode**: `langgraph.prebuilt.ToolNode` runs the tool calls found on the last model message.
- **bind_tools**: tells the chat model which tools exist, so it can emit tool calls.
- **interrupt()**: lets `ask` pause for the next message without blocking a process.
- **recursion_limit**: a backstop that stops a runaway graph with an error.

## Trade-offs
- Flexible, but the number of model calls is not known up front, so cost and latency vary.
- Each round re-sends the growing message history.
- Tool results are untrusted input. A tool that returns text can try to steer the model.
- Needs a round cap and good tool descriptions. Vague tools lead to wrong calls.

## Key code
These are the wiring lines from `build_skeleton()`. The node bodies are placeholders that return `{}`.
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

## Try this
- Trace the question "what is 17 times 23, in hex?" through the diagram. How many times would the `agent` -> `tools` -> `agent` cycle run?
- What would you put in state to cap the loop at a fixed number of rounds, and which router would read it?
- Compare with [[collaboration/single-agent]] (live), which makes one model call with no loop, and with [[cognitive/planning]], which writes the steps before acting.
