"""Workflow skeleton: fixed steps in code, with one validation branch. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

A workflow is a pipeline whose steps are written in code, not chosen by a model.
The only decision is a check on the data: valid records continue, invalid ones
go to an error handler.

    START -> extract -> validate --(valid)---> transform -> load -> END
                                 --(invalid)-> handle_error -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    source: str
    records: list[dict]
    errors: list[str]
    loaded: int


def extract(state: State) -> dict:
    """Placeholder: would read raw records from `source`."""
    return {}


def validate(state: State) -> dict:
    """Placeholder: would check each record and note problems in `errors`."""
    return {}


def transform(state: State) -> dict:
    """Placeholder: would reshape the valid `records`."""
    return {}


def load(state: State) -> dict:
    """Placeholder: would write the records out and set `loaded`."""
    return {}


def handle_error(state: State) -> dict:
    """Placeholder: would report or quarantine what is in `errors`."""
    return {}


def route_validate(state: State) -> Literal["transform", "handle_error"]:
    """Would send to `handle_error` when `errors` is non-empty; fixed to `transform`."""
    return "transform"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
    builder.add_node("transform", transform)
    builder.add_node("load", load)
    builder.add_node("handle_error", handle_error)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "validate")
    builder.add_conditional_edges("validate", route_validate)
    builder.add_edge("transform", "load")
    builder.add_edge("load", END)
    builder.add_edge("handle_error", END)

    return builder.compile()
