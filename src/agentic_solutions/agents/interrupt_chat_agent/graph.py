"""Agent 4: the chat loop again, but waiting for input with `interrupt()`.

The graph is IDENTICAL to agent 2 (chat_agent): ask -> answer -> ask ... until
"stop". Only HOW the `ask` node waits for the user changes.

agent 2:  input()      blocks the whole Python process until someone types.
agent 4:  interrupt()  PAUSES the graph, saves its state, and hands control
                       back to whoever called it. Later the caller RESUMES it
                       with the user's text.

What's new
----------
* `interrupt(value)`      - pause here. `value` is shown to the caller
                            (e.g. the prompt to display).
* `Command(resume=x)`     - how the caller resumes. Inside the node,
                            `interrupt(...)` then RETURNS `x`.
* A checkpointer          - storage where the paused state is saved. Without
                            one there is nothing to resume from, so
                            `interrupt()` raises an error.
* `thread_id`             - names one conversation. Each thread has its own
                            saved state, so many chats can share one graph.

Why bother?
-----------
A paused graph is just saved data. It doesn't hold a terminal, so a web
server, LangGraph Studio, or another program can supply the answer, even much
later. The same mechanism powers human approvals ("OK to send this email?").

Two rules to remember
---------------------
1. On resume, the node that paused RE-RUNS FROM ITS FIRST LINE. `interrupt()`
   then returns the resume value instead of pausing again. So anything before
   the `interrupt()` call must be safe to run twice.
2. State is only saved at the end of each step, so the resume value is
   delivered to the paused node, not to some later one.

The graph
---------

            +-----------------------------+
            v                             |
    START -> ask --(router)--> answer ----+
              |  \\
              |   +--(empty input)--> ask
              +--(user typed "stop")--> END
"""
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from agentic_solutions.common.llm import get_llm

SYSTEM_PROMPT = "You are a helpful assistant. Answer concisely and accurately."

STOP_WORD = "stop"

# What the caller shows the user when the graph pauses.
QUESTION_PROMPT = 'Your question (or "stop" to quit):'


class State(TypedDict):
    """The data that flows through the graph (same as agent 2)."""

    messages: Annotated[list, add_messages]


def ask(state: State) -> dict:
    """Node: pause the graph and wait for the user's next question.

    `interrupt()` stops the graph right here. Whatever is passed to it comes
    back to the caller as the pause's payload. When the caller resumes with
    `Command(resume="some text")`, this function runs again from the top and
    `interrupt()` returns "some text" instead of pausing.
    """
    text = interrupt(QUESTION_PROMPT)
    return {"messages": [("user", text)]}


def answer(state: State) -> dict:
    """Node: call Claude with the conversation so far and store its reply."""
    llm = get_llm()
    reply = llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [reply]}


def route_after_ask(state: State) -> Literal["answer", "ask", "__end__"]:
    """Same router as agent 2: stop -> END, empty -> ask again, else answer."""
    text = state["messages"][-1].content.strip().lower()
    if text == STOP_WORD:
        return END
    if not text:
        return "ask"
    return "answer"


def build_graph(checkpointer=None):
    """Wire the graph. Pass a checkpointer to make `interrupt()` usable.

    The checkpointer is a parameter because different callers need different
    ones: the command-line app passes an in-memory saver, while LangGraph
    Studio / `langgraph dev` supplies its own persistence and REJECTS a graph
    that brings its own. So the module-level `graph` below has none.
    """
    builder = StateGraph(State)
    builder.add_node("ask", ask)
    builder.add_node("answer", answer)

    builder.add_edge(START, "ask")
    builder.add_conditional_edges("ask", route_after_ask)
    builder.add_edge("answer", "ask")

    return builder.compile(checkpointer=checkpointer)


# Exported for LangGraph Studio (see langgraph.json).
graph = build_graph()
