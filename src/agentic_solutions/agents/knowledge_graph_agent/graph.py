"""Knowledge graph skeleton: extract entities, query the graph, answer, update it. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Knowledge-graph memory stores entities (people, products, places) and the
relations between them. `extract_entities` finds the entities in the question,
`query_graph` follows their relations, and after `answer`, `update_graph` writes
any new entities and relations back.

    START -> extract_entities -> query_graph -> answer -> update_graph -> END

There are no routers here: every edge is fixed.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    entities: list[str]
    relations: list[tuple[str, str, str]]  # (subject, relation, object)
    answer: str


def extract_entities(state: State) -> dict:
    """Placeholder: would find the entities named in the question."""
    return {}


def query_graph(state: State) -> dict:
    """Placeholder: would look up the entities' relations in the graph store."""
    return {}


def answer(state: State) -> dict:
    """Placeholder: would answer from the relations that were found."""
    return {}


def update_graph(state: State) -> dict:
    """Placeholder: would add newly learned entities and relations to the graph."""
    return {}


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("extract_entities", extract_entities)
    builder.add_node("query_graph", query_graph)
    builder.add_node("answer", answer)
    builder.add_node("update_graph", update_graph)

    builder.add_edge(START, "extract_entities")
    builder.add_edge("extract_entities", "query_graph")
    builder.add_edge("query_graph", "answer")
    builder.add_edge("answer", "update_graph")
    builder.add_edge("update_graph", END)

    return builder.compile()
