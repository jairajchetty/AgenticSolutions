"""Swarm skeleton: peer agents hand control to each other. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

A swarm has no coordinator. Each agent either answers or hands the conversation
directly to a peer. Here `triage` is only the entry point, not a manager: once
it hands off, `billing` and `technical` can pass the work back and forth.

    START -> triage --(hand off)--> billing   <--> technical
                |                      |               |
                +--------(answer)------+---> END <-----+

Each router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    messages: list[str]
    active_agent: str


def triage(state: State) -> dict:
    """Placeholder: would answer simple questions or hand off to a specialist."""
    return {}


def billing(state: State) -> dict:
    """Placeholder: would handle invoices and refunds, or hand off to `technical`."""
    return {}


def technical(state: State) -> dict:
    """Placeholder: would handle faults and setup, or hand off to `billing`."""
    return {}


def route_triage(state: State) -> Literal["billing", "technical", "__end__"]:
    """Would follow `active_agent` after triage; fixed to `__end__`."""
    return END


def route_billing(state: State) -> Literal["technical", "__end__"]:
    """Would hand off to `technical` or finish; fixed to `__end__`."""
    return END


def route_technical(state: State) -> Literal["billing", "__end__"]:
    """Would hand off to `billing` or finish; fixed to `__end__`."""
    return END


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("triage", triage)
    builder.add_node("billing", billing)
    builder.add_node("technical", technical)

    builder.add_edge(START, "triage")
    builder.add_conditional_edges("triage", route_triage)
    builder.add_conditional_edges("billing", route_billing)
    builder.add_conditional_edges("technical", route_technical)

    return builder.compile()
