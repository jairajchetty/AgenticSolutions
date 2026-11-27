"""Audit skeleton: act, then write a durable record of each step. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Audit keeps persistent, queryable records of every run. After each action,
`record` writes an entry, then control either returns to `act` for the next
action or moves on to `summarize` when no work is left.

    START -> act -> record --(more work)--> act
                           --(done)-------> summarize -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    task: str
    actions: list[str]
    log_entries: list[str]
    more_work: bool
    report: str


def act(state: State) -> dict:
    """Placeholder: would perform the next action and append it to `actions`."""
    return {}


def record(state: State) -> dict:
    """Placeholder: would write the action to a durable store and `log_entries`."""
    return {}


def summarize(state: State) -> dict:
    """Placeholder: would read `log_entries` back and set `report`."""
    return {}


def route_record(state: State) -> Literal["act", "summarize"]:
    """Would follow `more_work`; fixed to `summarize`."""
    return "summarize"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("act", act)
    builder.add_node("record", record)
    builder.add_node("summarize", summarize)

    builder.add_edge(START, "act")
    builder.add_edge("act", "record")
    builder.add_conditional_edges("record", route_record)
    builder.add_edge("summarize", END)

    return builder.compile()
