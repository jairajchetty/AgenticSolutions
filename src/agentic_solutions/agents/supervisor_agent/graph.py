"""Supervisor skeleton: a coordinator picks a worker, the worker reports back. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Supervisor is the orchestrator-workers pattern: one coordinator model decides
which specialist runs next, reads what it produced, and decides when to finish.

    START -> supervisor --(delegate)--> researcher -> supervisor
                 |       --(delegate)--> writer     -> supervisor
                 +--(work is done)--> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    task: str
    notes: list[str]
    draft: str
    next_worker: str


def supervisor(state: State) -> dict:
    """Placeholder: would read progress and choose the next worker, or finish."""
    return {}


def researcher(state: State) -> dict:
    """Placeholder: would gather facts for the task and add them to `notes`."""
    return {}


def writer(state: State) -> dict:
    """Placeholder: would turn the notes into a `draft`."""
    return {}


def route_supervisor(state: State) -> Literal["researcher", "writer", "__end__"]:
    """Would follow the coordinator's choice in `next_worker`; fixed to `__end__`."""
    return END


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("supervisor", supervisor)
    builder.add_node("researcher", researcher)
    builder.add_node("writer", writer)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_supervisor)
    builder.add_edge("researcher", "supervisor")
    builder.add_edge("writer", "supervisor")

    return builder.compile()
