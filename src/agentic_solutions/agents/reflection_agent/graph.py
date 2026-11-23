"""Reflection skeleton: generate, critique, revise, with empty nodes.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. It exists so the catalog can draw the
pattern's real topology from a compiled graph. Live demo: milestone 3.

Reflection is the generate -> critique -> revise loop of the Reflexion and
Self-Refine family: the SAME model drafts, judges its own draft, and rewrites it.

    START -> generate -> critique --(good enough or out of rounds)--> END
                            |  ^
                            v  |
                            revise

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    task: str
    draft: str
    score: float
    feedback: str
    iteration: int


def generate(state: State) -> dict:
    """Placeholder: would write the first draft."""
    return {}


def critique(state: State) -> dict:
    """Placeholder: would score the draft and say what is wrong with it."""
    return {}


def revise(state: State) -> dict:
    """Placeholder: would rewrite the draft using the critique."""
    return {}


def route_after_critique(state: State) -> Literal["revise", "__end__"]:
    """Would stop on a good score or after N rounds; fixed to `__end__`."""
    return END


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("generate", generate)
    builder.add_node("critique", critique)
    builder.add_node("revise", revise)

    builder.add_edge(START, "generate")
    builder.add_edge("generate", "critique")
    builder.add_conditional_edges("critique", route_after_critique)
    builder.add_edge("revise", "critique")

    return builder.compile()
