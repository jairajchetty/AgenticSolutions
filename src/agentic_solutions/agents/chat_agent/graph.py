"""Agent 2: a question-and-answer LOOP that ends when the user types "stop".

What's new compared with agent 1 (qa_agent)
-------------------------------------------
* A cycle. Agent 1 was a straight line; here the graph loops back on itself.
* A conditional edge. After each question a *router* function decides where
  to go next (answer it, ask again, or finish).
* Conversation memory inside one run. Because `messages` uses the
  `add_messages` reducer, every question and answer is appended to the state,
  so Claude sees the whole conversation each time it answers.

The graph
---------

            +--------------------------------------+
            v                                      |
    START -> ask --(router)--> answer -------------+
              |  \\
              |   +--(empty input)--> ask  (try again)
              |
              +--(user typed "stop")--> END

Nodes do the work, edges decide the order:

* `ask`    - waits for the user to type a question.
* `answer` - sends the conversation to Claude and stores the reply.
* `route_after_ask` - not a node; it is the function behind the conditional
  edge and returns the NAME of the next node (or END).
"""
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agentic_solutions.common.llm import LLMFactory, declined_or, get_llm

SYSTEM_PROMPT = "You are a helpful assistant. Answer concisely and accurately."

# The word (case-insensitive) that ends the conversation.
STOP_WORD = "stop"


class State(TypedDict):
    """The data that flows through the graph.

    `messages` holds the whole conversation. The `add_messages` reducer
    tells LangGraph to APPEND whatever a node returns for this key rather
    than replace the list, which is what gives the agent its memory.
    """

    messages: Annotated[list, add_messages]


# --------------------------------------------------------------------------
# Nodes: plain functions that take the State and return a PARTIAL State
# update. LangGraph merges the returned dict into the state for us.
# --------------------------------------------------------------------------
def ask(state: State) -> dict:
    """Node: wait for the user to type the next question.

    The user's text is stored as a "user" message so the router (and later
    Claude) can read it from the state like any other message.

    Note: `input()` blocks the terminal, so this agent is meant to be run
    from the command line. A later lesson replaces it with LangGraph's
    `interrupt()`, which pauses the graph properly (needed for human
    approvals and for LangGraph Studio).
    """
    try:
        text = input("\nYou: ")
    except EOFError:  # Ctrl+Z / Ctrl+D: treat like typing "stop"
        text = STOP_WORD
    return {"messages": [("user", text)]}


# --------------------------------------------------------------------------
# Router: the function behind the conditional edge.
# --------------------------------------------------------------------------
def route_after_ask(state: State) -> Literal["answer", "ask", "__end__"]:
    """Decide what happens after the user has typed something.

    Reads the latest message and returns the name of the next node:
    * "stop"        -> END (the graph finishes and `invoke` returns)
    * empty input   -> "ask" (loop back and ask again, no wasted API call)
    * anything else -> "answer"
    """
    text = state["messages"][-1].content.strip().lower()
    if text == STOP_WORD:
        return END
    if not text:
        return "ask"
    return "answer"


def build_graph(ask_node=ask, checkpointer=None, llm_factory: LLMFactory | None = None):
    """Wire the nodes and edges together and compile them into a runnable.

    `ask_node` swaps how the user is asked (e.g. the interrupt-based `ask`),
    `checkpointer` enables pause/resume, and `llm_factory` supplies the model.
    """

    def answer_node(state: State) -> dict:
        # Resolved at call time so patching the module-level `get_llm` works.
        llm = (llm_factory or get_llm)()
        reply = declined_or(llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]]))
        return {"messages": [reply]}

    builder = StateGraph(State)

    builder.add_node("ask", ask_node)
    builder.add_node("answer", answer_node)

    builder.add_edge(START, "ask")  # always begin by asking
    builder.add_conditional_edges("ask", route_after_ask)  # router picks next
    builder.add_edge("answer", "ask")  # after answering, loop back

    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
