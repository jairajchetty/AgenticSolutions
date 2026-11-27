"""Routing skeleton: classify a request once, send it to one specialist. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Routing sends each request to the right specialist. `classify` decides once,
one specialist handles the request, and the run ends. Nothing loops back.

    START -> classify --(billing)---> billing   -> END
                      --(technical)-> technical -> END
                      --(other)-----> general   -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    request: str
    category: str
    reply: str


def classify(state: State) -> dict:
    """Placeholder: would label `request` and store the label in `category`."""
    return {}


def billing(state: State) -> dict:
    """Placeholder: would answer money questions and set `reply`."""
    return {}


def technical(state: State) -> dict:
    """Placeholder: would answer faults and setup questions and set `reply`."""
    return {}


def general(state: State) -> dict:
    """Placeholder: would answer anything else and set `reply`."""
    return {}


def route_classify(state: State) -> Literal["billing", "technical", "general"]:
    """Would follow `category`; fixed to `general`."""
    return "general"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("classify", classify)
    builder.add_node("billing", billing)
    builder.add_node("technical", technical)
    builder.add_node("general", general)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route_classify)
    builder.add_edge("billing", END)
    builder.add_edge("technical", END)
    builder.add_edge("general", END)

    return builder.compile()
