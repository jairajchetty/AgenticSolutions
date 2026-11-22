"""Plan-and-Execute skeleton: planner, executor, tools, synthesizer, all empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. It exists so the catalog can draw the
pattern's real topology from a compiled graph. Live demo: milestone 3.

The model writes a short plan at run time, a worker carries out one step at a
time (calling tools when needed), and a final node composes the answer.

    START -> planner -> executor --(tool calls?)--> tools -> executor
                          |  ^
                          |  +--(step done, steps left)
                          +--(all steps done)--> synthesizer -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    goal: str
    plan: list[str]
    current_step: int
    results: list[str]


def planner(state: State) -> dict:
    """Placeholder: would turn the goal into 2-5 steps."""
    return {}


def executor(state: State) -> dict:
    """Placeholder: would work on the current step."""
    return {}


def tools(state: State) -> dict:
    """Placeholder: would run the tool calls the executor asked for."""
    return {}


def synthesizer(state: State) -> dict:
    """Placeholder: would write the final answer from the step results."""
    return {}


def route_after_executor(state: State) -> Literal["tools", "executor", "synthesizer"]:
    """Would pick tools / next step / finish; fixed to `synthesizer`."""
    return "synthesizer"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("planner", planner)
    builder.add_node("executor", executor)
    builder.add_node("tools", tools)
    builder.add_node("synthesizer", synthesizer)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_conditional_edges("executor", route_after_executor)
    builder.add_edge("tools", "executor")
    builder.add_edge("synthesizer", END)

    return builder.compile()
