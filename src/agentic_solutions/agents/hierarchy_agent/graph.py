"""Hierarchy skeleton: a director over two team leads, each leading workers. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Hierarchy is supervisors of supervisors. The `director` delegates to team
leads; each lead is itself a supervisor for its own workers. A live version
would typically make each team a subgraph, drawn here as flat nodes so the
whole structure shows in one diagram.

    START -> director --> research_lead --> searcher / analyst --> research_lead
                |     --> writing_lead  --> drafter  / editor  --> writing_lead
                +--(work is done)--> END       (leads report back to director)

Each router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    goal: str
    findings: list[str]
    draft: str


def director(state: State) -> dict:
    """Placeholder: would assign work to a team lead, or finish."""
    return {}


def research_lead(state: State) -> dict:
    """Placeholder: would direct the research team and report to `director`."""
    return {}


def writing_lead(state: State) -> dict:
    """Placeholder: would direct the writing team and report to `director`."""
    return {}


def searcher(state: State) -> dict:
    """Placeholder: would find sources and add to `findings`."""
    return {}


def analyst(state: State) -> dict:
    """Placeholder: would analyse the `findings`."""
    return {}


def drafter(state: State) -> dict:
    """Placeholder: would write a first `draft`."""
    return {}


def editor(state: State) -> dict:
    """Placeholder: would polish the `draft`."""
    return {}


def route_director(state: State) -> Literal["research_lead", "writing_lead", "__end__"]:
    """Would choose a team or finish; fixed to `__end__`."""
    return END


def route_research_lead(state: State) -> Literal["searcher", "analyst", "director"]:
    """Would choose a worker or report back; fixed to `director`."""
    return "director"


def route_writing_lead(state: State) -> Literal["drafter", "editor", "director"]:
    """Would choose a worker or report back; fixed to `director`."""
    return "director"


def build_skeleton():
    builder = StateGraph(State)
    for name, fn in [("director", director), ("research_lead", research_lead),
                     ("writing_lead", writing_lead), ("searcher", searcher),
                     ("analyst", analyst), ("drafter", drafter), ("editor", editor)]:
        builder.add_node(name, fn)

    builder.add_edge(START, "director")
    builder.add_conditional_edges("director", route_director)
    builder.add_conditional_edges("research_lead", route_research_lead)
    builder.add_conditional_edges("writing_lead", route_writing_lead)
    for worker, lead in [("searcher", "research_lead"), ("analyst", "research_lead"),
                         ("drafter", "writing_lead"), ("editor", "writing_lead")]:
        builder.add_edge(worker, lead)

    return builder.compile()
