# Single Agent

## What it is
One model handles the whole task in a single pass: a request goes in, one model call runs with a fixed instruction, and one reply comes out. There is no loop, no memory between requests and no branching. It is the baseline every other pattern adds to, and the yardstick for whether that extra machinery earns its cost. In multi-agent comparisons, "single agent" often means one agent looping over all the tools; that is [[cognitive/react]], and this Guide takes the narrow one-call baseline.

## When to use it
- One-shot tasks with a clear input and output: summarise a text, classify a ticket, rewrite a sentence, extract fields.
- As one step inside a larger system, where the surrounding code owns retries, state and side effects.
- As a baseline before reaching for a multi-step design. If one call solves the problem, stop here.
- Not when the task needs follow-up turns, external data or actions, or a check on its own output. Each of those is a different pattern.

## How it works
Roles:
- **Caller**: the application or person that sends the request and receives the reply.
- **Agent**: a model plus a fixed system instruction. It sees only what this request carries.

Flow:
1. The caller sends a request.
2. The agent combines its instruction with the request and makes one model call.
3. The reply goes back to the caller, and the run ends.

Every run takes the same path. Nothing is decided at run time, so behaviour is easy to predict and to test.

## Design considerations
- **Prompt as the whole contract:** with no loop to recover, the instruction and the input format carry all the quality. Version the instruction and test it like code.
- **Stateless by design:** nothing survives between requests. If the caller needs context, it must send that context with every request.
- **Output shape:** decide whether the caller needs free text or a structured result, and validate structured output before it is used.
- **Failure handling:** a timeout or a malformed reply is handled by the caller, not the agent. Keep retries outside and make them safe to repeat.
- **Input trust:** whatever arrives goes straight to the model. Screen untrusted input before this step if it matters.
- **Cost and latency:** one call per request gives the lowest and most predictable cost of any pattern.

## Trade-offs
- Fast, cheap and easy to debug: one call, one path.
- No memory: a follow-up question has no idea what came before.
- No self-check, no tools and no way to ask for clarification.
- No safety layer of its own: input reaches the model unchecked.

## Related patterns
- The dividing line: Single Agent is one model handling everything itself. [[collaboration/supervisor]], [[collaboration/swarm]] and [[collaboration/hierarchy]] split the work across several agents that hand work to each other.
- [[memory/session]] adds a loop and keeps the conversation, so follow-ups work.
- [[execution/workflow]] chains several fixed calls when one is not enough.
- [[governance/guardrails]] screens input before it reaches the model.

## How this Studio implements it

### Mapping
- **Caller** → the Studio sends your message as the run's input (`__start__`) and shows the reply when the run reaches `__end__`.
- **Agent** → `answer`: one model call with a system prompt plus your message.

### Framework concepts
- **State**: a `TypedDict` that holds the data flowing through the graph. Here it has a single key, `messages`.
- **Reducer**: `add_messages` tells LangGraph to append a node's returned messages to the list instead of replacing it.
- **Node**: a plain function that takes the state and returns a partial update.
- **Edge**: a fixed link from one node to the next (`START -> answer -> END`).
- **compile()**: turns the builder into a runnable graph.

### Key code
```python
def answer(state: State) -> dict:
    """Node: call Claude with the conversation so far and return its reply."""
    llm = (llm_factory or get_llm)()
    reply = llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [reply]}

builder = StateGraph(State)
builder.add_node("answer", answer)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)
return builder.compile(checkpointer=checkpointer)
```

### Try this
- Ask any question, for example `What is a reducer in LangGraph?`, and watch the run go `__start__`, `answer`, `__end__`.
- Ask a follow-up such as `Explain that more simply`. Each run starts fresh, so the model will not know what "that" means. This is the gap the [[memory/session]] pattern fills.
