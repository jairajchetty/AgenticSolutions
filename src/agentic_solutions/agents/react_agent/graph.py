"""ReAct skeleton: the wiring of the reason-and-act loop, with empty nodes.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. It exists so the catalog can draw the
pattern's real topology from a compiled graph. Live demo: milestone 3.

ReAct (Yao et al., "ReAct: Synergizing Reasoning and Acting") interleaves
reasoning with tool calls: think, call a tool, read the result, think again.

    START -> ask -> agent --(tool calls?)--> tools -> agent
              ^  \\             \\
              |   \\             +--(no)--> ask
              |    +--(empty input)--> ask
              |    +--(user typed "stop")--> END
              +---------------------------------+

The routers return one fixed branch, so the diagram is complete without any
model. Each is annotated `Literal[...]` listing ALL its targets: LangGraph reads
that annotation to draw the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import START, StateGraph


class State(TypedDict):
    messages: list
    tool_rounds: int


def ask(state: State) -> dict:
    """Placeholder: would wait for the user's next message."""
    return {}


def agent(state: State) -> dict:
    """Placeholder: would call the model with tools bound."""
    return {}


def tools(state: State) -> dict:
    """Placeholder: would run the tool calls the model asked for."""
    return {}


def route_after_ask(state: State) -> Literal["agent", "ask", "__end__"]:
    """Would end on "stop", re-ask on empty input; fixed to `agent`."""
    return "agent"


def route_after_agent(state: State) -> Literal["tools", "ask"]:
    """Would go to `tools` if the model requested any; fixed to `ask`."""
    return "ask"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("ask", ask)
    builder.add_node("agent", agent)
    builder.add_node("tools", tools)

    builder.add_edge(START, "ask")
    builder.add_conditional_edges("ask", route_after_ask)
    builder.add_conditional_edges("agent", route_after_agent)
    builder.add_edge("tools", "agent")

    return builder.compile()
