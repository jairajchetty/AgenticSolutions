"""Offline scripts: canned, teaching-oriented replies for each pattern.

Each script is an ordered list of rules. A rule matches when its keyword is a
case-insensitive substring of the latest human message, and the first match
wins. Every sample input offered in the UI, and every input a Guide's "Try
this" section suggests, has its own rule; anything else falls through to the
pattern's fallback reply.
"""

import re

from langchain_core.messages import BaseMessage

from agentic_solutions.web.offline.model import Rule, Script

OFFLINE_NOTE = "(Offline demo: scripted response. Unlock Live mode for real answers.)"


def _fallback(lead: str) -> str:
    return f"{lead} {OFFLINE_NOTE}"


_NAME = re.compile(r"\bmy name is\s+([A-Za-z][\w'-]*)", re.IGNORECASE)


def _given_name(messages: list[BaseMessage]) -> str | None:
    """The latest name the user gave with "My name is ..." in this thread."""
    for m in reversed(messages):
        if m.type == "human" and isinstance(m.content, str):
            found = _NAME.search(m.content)
            if found:
                return found.group(1)
    return None


def _greet(messages: list[BaseMessage]) -> str:
    name = _given_name(messages) or "there"
    return (f"Nice to meet you, {name}. Your message is now in the messages list, which "
            "the checkpointer saves for this thread. Ask 'What is my name?' next to see the "
            "graph remember it.")


def _recall(messages: list[BaseMessage]) -> str:
    name = _given_name(messages[:-1])
    if name is None:
        return ("You haven't told me your name in this chat yet. Say 'My name is Sam.' first, "
                "then ask again.")
    return (f"You told me your name is {name}. This reply is scripted, but the name is real: "
            "it was read from the earlier message in this thread, because every turn sends "
            "the whole message list back to the model.")


QA = Script(
    rules=(
        Rule("reducer",
             "A reducer decides how a node's update merges into one state key. Without one the "
             "new value replaces the old; with Annotated[list, add_messages] LangGraph "
             "appends the new messages instead. That is how chat graphs keep their history."),
        Rule("langgraph",
             "LangGraph models an agent as a graph: nodes are Python functions that read and "
             "update a shared state, and edges decide which node runs next. Because the flow is "
             "explicit, you can loop, branch, pause and inspect every step."),
        Rule("single llm call",
             "A single LLM call sends one prompt and gets one answer, with no loop, tools or "
             "memory. It is the simplest pattern and often the right one: start here, and add "
             "structure only when the task proves it needs it."),
        Rule("explain that",
             "I can't tell what \"that\" refers to: this graph makes one fresh call per run "
             "and keeps no memory, so your earlier question is not in my input. The Chat loop "
             "pattern fills this gap by keeping the message list between turns."),
        Rule("state",
             "State is the data that flows through a graph, usually a TypedDict. Each node "
             "returns a partial update, and a reducer such as add_messages decides how that "
             "update merges in, for example by appending to the message list."),
    ),
    fallback=_fallback("This pattern makes one model call: your question goes in and one answer "
                       "comes out, with nothing remembered afterwards."),
)

CHAT_LOOP = Script(
    rules=(
        Rule("what is my name", _recall),
        Rule("my name is", _greet),
        Rule("remember",
             "The graph remembers through its state: the add_messages reducer appends every "
             "question and answer to the message list, and a checkpointer saves that list per "
             "thread. Each new turn sends the whole history back to the model."),
        Rule("conditional edge",
             "A conditional edge is a router function that looks at the state and returns the "
             "name of the next node. Here it sends 'stop' to the end, empty input back to ask, "
             "and everything else to answer."),
        Rule("loop",
             "Graphs can contain cycles: after answer, an edge leads back to ask, so the "
             "conversation continues until the router sends you to END. Loops are what turn a "
             "single call into a chat."),
    ),
    fallback=_fallback("In this loop the graph asks for your message, routes it to the model, "
                       "appends the reply to its memory, then asks again."),
)

GUARDRAIL = Script(
    rules=(
        Rule("capital of france",
             "The capital of France is Paris. Your question passed the guard, so it reached "
             "the model: the trace went ask, guard, answer."),
        Rule("embedding",
             "An embedding turns text into a vector so similar meanings land close together. "
             "The guard embeds your prompt and compares it with a library of known attack "
             "phrases, so reworded attacks can still be caught."),
        Rule("guardrail",
             "A guardrail is a check placed around the model. This one screens the prompt "
             "before the model sees it, so a risky request is refused by fixed code instead of "
             "relying on the model to resist it."),
        Rule("prompt injection",
             "Prompt injection hides instructions in the input to hijack the model, such as "
             "'ignore previous instructions'. Screening input before it reaches the model, as "
             "this graph does, is one layer of defense, not a complete one."),
    ),
    fallback=_fallback("Your message passed the guard, so it reached the model. Had it matched "
                       "a known attack, the refuse node would have answered instead."),
)

HUMAN_IN_LOOP = Script(
    rules=(
        Rule("interrupt",
             "interrupt() pauses a running graph and hands a payload to the caller. The "
             "graph's state is saved by the checkpointer, and nothing runs until someone "
             "resumes it, so waiting costs no compute."),
        Rule("checkpointer",
             "A checkpointer saves the graph's state after every step, keyed by thread id. "
             "That is what lets a paused graph survive a page reload or a server restart and "
             "continue exactly where it stopped."),
        Rule("resume",
             "To resume, you call the graph again on the same thread with Command(resume=value). "
             "The paused interrupt() call returns that value, and the node carries on from "
             "that point."),
    ),
    fallback=_fallback("The graph is paused at the ask node, waiting for a human. Your message "
                       "resumed it, the model replied, and it paused again."),
)

SCRIPTS: dict[str, Script] = {
    "qa": QA,
    "chat_loop": CHAT_LOOP,
    "guardrail": GUARDRAIL,
    "human_in_loop": HUMAN_IN_LOOP,
}
