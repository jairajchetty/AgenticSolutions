"""Review skeleton: a separate reviewer checks a draft before it is approved. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Review has a separate agent or a person check the result. `draft` produces the
work, `review` judges it, and the reviewer either sends it back to `draft` with
comments or lets it through to `approve`.

    START -> draft -> review --(changes needed)--> draft
                             --(accepted)--------> approve -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    task: str
    content: str
    comments: str
    accepted: bool
    final: str


def draft(state: State) -> dict:
    """Placeholder: would write or rewrite `content`, using `comments` if present."""
    return {}


def review(state: State) -> dict:
    """Placeholder: would have a reviewer set `comments` and `accepted`."""
    return {}


def approve(state: State) -> dict:
    """Placeholder: would copy the accepted `content` into `final`."""
    return {}


def route_review(state: State) -> Literal["draft", "approve"]:
    """Would follow `accepted`; fixed to `approve`."""
    return "approve"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("draft", draft)
    builder.add_node("review", review)
    builder.add_node("approve", approve)

    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_conditional_edges("review", route_review)
    builder.add_edge("approve", END)

    return builder.compile()
