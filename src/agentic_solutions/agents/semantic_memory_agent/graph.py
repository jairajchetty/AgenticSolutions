"""Semantic memory skeleton: retrieval-augmented answers with a grading loop. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Semantic memory is facts looked up from a document store. After `retrieve`,
`grade` judges whether the passages are relevant. If not, `rewrite_query`
rephrases the question and the graph retrieves again (a corrective-RAG style loop).

    START -> retrieve -> grade --(relevant)--> answer -> END
                ^          |
                |          +--(not relevant)--> rewrite_query
                +-------------------------------------+

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    query: str
    documents: list[str]
    answer: str


def retrieve(state: State) -> dict:
    """Placeholder: would fetch passages for `query` from a document store."""
    return {}


def grade(state: State) -> dict:
    """Placeholder: would judge whether the retrieved passages are relevant."""
    return {}


def rewrite_query(state: State) -> dict:
    """Placeholder: would rephrase `query` so the next retrieval does better."""
    return {}


def answer(state: State) -> dict:
    """Placeholder: would answer the question from the relevant passages."""
    return {}


def route_after_grade(state: State) -> Literal["answer", "rewrite_query"]:
    """Would go to `answer` if the passages are relevant, else `rewrite_query`; fixed to `answer`."""
    return "answer"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("grade", grade)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("answer", answer)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges("grade", route_after_grade)
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("answer", END)

    return builder.compile()
