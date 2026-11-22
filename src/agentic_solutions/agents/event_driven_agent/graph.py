"""Event Driven skeleton: one event in, handled by kind, one result out. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

An event-driven agent runs when something happens, not when a person types.
The trigger (a queue consumer, a webhook or a cron job) lives OUTSIDE this graph
and calls `invoke` with the event as input. The graph only handles that event.

    START -> receive_event --(order)--> handle_order  -> emit_result -> END
                           --(refund)-> handle_refund -> emit_result -> END
                           --(other)--> ignore -> END

The router returns one fixed branch. It is annotated `Literal[...]` listing ALL
its targets, which is how LangGraph draws the conditional edges.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    event: dict
    event_type: str
    result: str


def receive_event(state: State) -> dict:
    """Placeholder: would read `event` and set `event_type`."""
    return {}


def handle_order(state: State) -> dict:
    """Placeholder: would process an order event and set `result`."""
    return {}


def handle_refund(state: State) -> dict:
    """Placeholder: would process a refund event and set `result`."""
    return {}


def ignore(state: State) -> dict:
    """Placeholder: would drop an event this agent does not handle."""
    return {}


def emit_result(state: State) -> dict:
    """Placeholder: would publish `result`, for example to another queue."""
    return {}


def route_event(state: State) -> Literal["handle_order", "handle_refund", "ignore"]:
    """Would follow `event_type`; fixed to `ignore`."""
    return "ignore"


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("receive_event", receive_event)
    builder.add_node("handle_order", handle_order)
    builder.add_node("handle_refund", handle_refund)
    builder.add_node("ignore", ignore)
    builder.add_node("emit_result", emit_result)

    builder.add_edge(START, "receive_event")
    builder.add_conditional_edges("receive_event", route_event)
    builder.add_edge("handle_order", "emit_result")
    builder.add_edge("handle_refund", "emit_result")
    builder.add_edge("ignore", END)
    builder.add_edge("emit_result", END)

    return builder.compile()
