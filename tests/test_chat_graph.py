"""Offline tests for the looping chat agent (no API calls, no keyboard)."""
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from agentic_solutions.agents.chat_agent import graph as chat


def run_chat(monkeypatch, typed, replies, limit=25):
    """Run the graph, feeding `typed` as keyboard input and `replies` as Claude."""
    inputs = iter(typed)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    fake_llm = FakeListChatModel(responses=replies)  # one instance: replies advance
    monkeypatch.setattr(chat, "get_llm", lambda: fake_llm)
    return chat.build_graph().invoke({"messages": []}, {"recursion_limit": limit})


def test_answers_each_question_then_stops(monkeypatch):
    result = run_chat(monkeypatch, ["hi", "and again", "STOP"], ["a1", "a2"])
    contents = [m.content for m in result["messages"]]
    assert contents == ["hi", "a1", "and again", "a2", "STOP"]


def test_stop_immediately_never_calls_the_llm(monkeypatch):
    result = run_chat(monkeypatch, ["stop"], [])
    assert len(result["messages"]) == 1


def test_empty_input_asks_again(monkeypatch):
    result = run_chat(monkeypatch, ["", "   ", "hi", "stop"], ["a1"])
    contents = [m.content for m in result["messages"] if m.content.strip()]
    assert contents == ["hi", "a1", "stop"]


def test_conversation_can_outlast_default_recursion_limit(monkeypatch):
    questions = [f"q{i}" for i in range(20)]
    result = run_chat(monkeypatch, questions + ["stop"], ["ok"] * 20, limit=1000)
    assert len(result["messages"]) == 41
