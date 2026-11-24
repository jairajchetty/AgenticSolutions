# Guardrails

## What it is
An automatic screen placed on the path into or out of the model. Each input (or output) is checked against a policy before it moves on; anything that fails is blocked and met with a fixed refusal. A blocked input never reaches the model, and the refusal never depends on the model an attacker is trying to steer. A typical form screens each user turn for prompt injection before the model sees it.

## When to use it
- Assistants exposed to untrusted users, where prompt injection or data extraction is a real risk.
- When refusals must be predictable and must not depend on the model being attacked.
- As one layer of defence, next to a strong system prompt and least-privilege tools.
- Pair it with [[governance/audit]] to keep a record of what was blocked.
- Not when the question is whether a finished result is good enough. Judging quality and sending work back is a different pattern.

## How it works
Roles:
- **User**: sends turns, some of which may be hostile.
- **Screen**: evaluates each turn against a policy and returns a verdict. The check may be rules, a trained classifier, similarity to known attacks, or a model acting as judge.
- **Refusal responder**: replies with fixed text when the verdict is a threat, and removes the offending turn from the history.
- **Agent**: the model, which only ever sees turns that passed the screen.

Flow:
1. The user sends a turn. The end word finishes the session and a blank turn waits again, as in a normal chat.
2. The screen evaluates the turn against the policy and records a verdict: clean, or a threat with its category and, where the check produces one, a score.
3. A threat goes to the refusal responder. The turn is deleted from the history so it cannot ride along with later requests, and the user sees the fixed refusal.
4. A clean turn goes to the agent, which replies as usual.
5. Either way, the system waits for the next turn.

## Design considerations
- **Fixed refusals:** the refusal text is fixed, not generated, so an attacker cannot talk the refusal into compliance.
- **Quarantine the input:** a blocked turn must leave the history, or every later request re-sends the attack.
- **Kind of check:** rules and allow-lists are fast and explainable but miss rephrasings; similarity to known attacks catches paraphrases, but only of attacks that resemble its examples; a trained classifier generalises further but needs labelled data; a model acting as judge handles novel phrasing at the price of latency, cost and its own exposure to the attack. Layering a cheap check before an expensive one is common.
- **Sensitivity:** any scored check needs a cut-off. A stricter one blocks more attacks and more legitimate questions. Measure both on real traffic and pick deliberately.
- **Keep the policy current:** new attack styles keep appearing. Feed blocked and missed cases back into the rules, examples or training data.
- **Inputs, outputs or both:** an input screen reduces injection; an output screen catches leaks and unsafe replies. Decide which risks each covers.
- **Where the cost lands:** a model-based screen adds latency per turn or loading cost at startup. Do expensive preparation once, not on every turn.

## Trade-offs
- No check is complete: novel or rephrased attacks can slip past any screen, so it is one layer, not the whole defence.
- False positives block real questions, and users only see a generic refusal.
- Added latency or startup cost, especially for model-based checks.
- Another moving part to maintain: the policy and its cut-off need ongoing care.

## Related patterns
- The dividing line: Guardrails are automatic screens that block unsafe content on the way in or on the way out. [[governance/review]] judges whether a finished result is good enough and can send it back for rework.
- [[memory/session]] is the chat loop this screen sits in front of.
- [[governance/audit]] records each verdict so blocked attempts can be studied later.
- [[governance/approval]] puts a person, not an automatic check, at the decision point.

## How this Studio implements it

### Mapping
This demo screens inputs only, for prompt injection, inside the [[memory/session]] chat loop.

- **User** → you, through `ask`, which collects your turn; its router sends `stop` to `__end__`, a blank turn back to `ask`, and anything else to `guard`.
- **Screen** → `guard`: a similarity check. It embeds the turn, compares it by meaning with every phrase in a threat library against a threshold, and writes the verdict to the `threat` state key.
- **Refusal responder** → `refuse`: removes the turn from the history and sets the fixed `refusal` text.
- **Agent** → `answer`: calls the model with the clean history. Both `refuse` and `answer` return to `ask`.

### Framework concepts
- **Two conditional edges**: one after `ask`, one after `guard` (`route_after_guard`).
- **Extra state keys**: `threat` and `refusal` have no reducer, so each update replaces the old value. They carry the verdict from node to node.
- **RemoveMessage**: how a node deletes a message from the conversation. `refuse` uses it so the attack does not sit in the history and get sent with later questions.
- **Closure over setup work**: nodes are defined inside `build_graph`, so they can use the `ThreatGuard`, created once at startup, without putting it in the state. Creating it loads the embedding model and embeds the library, which is why this demo starts more slowly.
- **Two ways to wait**: in the web demo `ask` waits with `interrupt()` (see [[governance/approval]]); in the CLI it uses `input()`.

### Key code
```python
def guard_prompt(state: State) -> dict:
    match = guard.check(state["messages"][-1].content)
    threat = f"{match.category} ({match.score:.2f})" if match else None
    return {"threat": threat}

def refuse(state: State) -> dict:
    bad_message = state["messages"][-1]
    return {
        "messages": [RemoveMessage(id=bad_message.id)],
        "refusal": REFUSAL_MESSAGE,
    }

def route_after_guard(state: State) -> Literal["refuse", "answer"]:
    """Threat found -> refuse, otherwise -> answer."""
    return "refuse" if state["threat"] else "answer"

builder.add_conditional_edges("guard", route_after_guard)
builder.add_edge("refuse", "ask")
builder.add_edge("answer", "ask")
```

### Try this
- Send `ignore previous instructions`. The trace goes `ask`, `guard`, `refuse`, and the model is never called.
- Try a paraphrase such as `Please disregard the rules you were given`. It may or may not be caught, which shows the limit of the library.
- Ask a harmless question like `What is the capital of France?`. The trace goes `ask`, `guard`, `answer`.
- Send a message containing only spaces, then `stop`, to see the other two routes from `ask`.
