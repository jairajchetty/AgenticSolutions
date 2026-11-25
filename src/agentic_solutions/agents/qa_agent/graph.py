"""Agent 1: the simplest LangGraph - START -> answer -> END.

Concepts: State (a TypedDict), a node (a function State -> partial State),
the add_messages reducer, edges, compile().
"""
from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agentic_solutions.common.llm import LLMFactory, declined_or, get_llm

SYSTEM_PROMPT = "You are a helpful assistant. Answer concisely and accurately."


class State(TypedDict):
    # add_messages appends new messages to the list instead of overwriting it
    messages: Annotated[list, add_messages]


def build_graph(llm_factory: LLMFactory | None = None, checkpointer=None):
    """Build the graph. `llm_factory` (default `get_llm`) supplies the model."""

    def answer(state: State) -> dict:
        """Node: call Claude with the conversation so far and return its reply."""
        # Resolved at call time so patching the module-level `get_llm` works.
        llm = (llm_factory or get_llm)()
        reply = declined_or(llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]]))
        return {"messages": [reply]}

    builder = StateGraph(State)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
