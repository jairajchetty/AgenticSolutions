"""Search skeleton: propose candidates, score them, repeat, answer. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Search treats reasoning as exploring a tree (Tree of Thoughts; LATS adds
tree-search ideas such as Monte Carlo selection): expand several candidate next
steps, score them, keep the promising ones, drop the rest, and go deeper.

    START -> propose -> score --(keep exploring)--> propose
                          |
                          +--(good enough or budget spent)--> answer -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    problem: str
    frontier: list[str]
    scores: list[float]
    depth: int


def propose(state: State) -> dict:
    """Placeholder: would expand each kept candidate into several next steps."""
    return {}


def score(state: State) -> dict:
    """Placeholder: would rate candidates and prune all but the best few."""
    return {}


def answer(state: State) -> dict:
    """Placeholder: would return the best candidate found."""
    return {}


def route_after_score(state: State) -> Literal["propose", "answer"]:
    """Would loop while promising and within budget; fixed to `answer`."""
    return "answer"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("propose", propose)
    builder.add_node("score", score)
    builder.add_node("answer", answer)

    builder.add_edge(START, "propose")
    builder.add_edge("propose", "score")
    builder.add_conditional_edges("score", route_after_score)
    builder.add_edge("answer", END)

    return builder.compile()
