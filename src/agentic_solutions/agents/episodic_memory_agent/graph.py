"""Episodic memory skeleton: recall past interactions, answer, then remember. All empty.

This module is a SKELETON. Its nodes do nothing, so there is no `graph` export,
no `__main__` and no Studio entry. No milestone has been planned to make it live.

Episodic memory is long-term memory of earlier interactions with the same user.
It lives outside any one conversation: `recall_episodes` reads it before the
answer, and `store_episode` writes the new interaction back afterwards.

    START -> recall_episodes -> answer -> store_episode -> END

There are no routers here: every edge is fixed.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    user_id: str
    episodes: list[str]
    answer: str


def recall_episodes(state: State) -> dict:
    """Placeholder: would look up past episodes stored for `user_id`."""
    return {}


def answer(state: State) -> dict:
    """Placeholder: would answer the question using the recalled episodes."""
    return {}


def store_episode(state: State) -> dict:
    """Placeholder: would save this interaction as a new episode for `user_id`."""
    return {}


def build_skeleton():
    builder = StateGraph(State)
    builder.add_node("recall_episodes", recall_episodes)
    builder.add_node("answer", answer)
    builder.add_node("store_episode", store_episode)

    builder.add_edge(START, "recall_episodes")
    builder.add_edge("recall_episodes", "answer")
    builder.add_edge("answer", "store_episode")
    builder.add_edge("store_episode", END)

    return builder.compile()
