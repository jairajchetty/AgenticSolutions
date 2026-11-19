"""Offline tests for the pausing chat agent.

No keyboard is involved: the tests play the part of the caller, running the
graph until it pauses and then resuming it with `Command(resume=...)`.
"""
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_solutions.agents.interrupt_chat_agent import graph as chat


def make_graph(monkeypatch, replies):
    fake_llm = FakeListChatModel(responses=replies)  # one instance: replies advance
    monkeypatch.setattr(chat, "get_llm", lambda: fake_llm)
    return chat.build_graph(checkpointer=InMemorySaver())


def config(thread_id="t1"):
    return {"configurable": {"thread_id": thread_id}}


def contents(graph, cfg):
    return [m.content for m in graph.get_state(cfg).values["messages"]]


def test_graph_pauses_at_ask_instead_of_blocking(monkeypatch):
    graph = make_graph(monkeypatch, [])
    result = graph.invoke({"messages": []}, config())
    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value == chat.QUESTION_PROMPT
    assert graph.get_state(config()).next == ("ask",)


def test_resume_answers_then_pauses_again_until_stop(monkeypatch):
    graph = make_graph(monkeypatch, ["a1", "a2"])
    cfg = config()
    graph.invoke({"messages": []}, cfg)
    graph.invoke(Command(resume="hi"), cfg)
    assert graph.get_state(cfg).next == ("ask",)  # waiting for question 2
    graph.invoke(Command(resume="and again"), cfg)
    graph.invoke(Command(resume="STOP"), cfg)

    assert graph.get_state(cfg).next == ()  # finished
    assert contents(graph, cfg) == ["hi", "a1", "and again", "a2", "STOP"]


def test_empty_input_pauses_again_without_calling_the_llm(monkeypatch):
    graph = make_graph(monkeypatch, [])
    cfg = config()
    graph.invoke({"messages": []}, cfg)
    result = graph.invoke(Command(resume="   "), cfg)
    assert "__interrupt__" in result  # asked again
    assert graph.get_state(cfg).next == ("ask",)


def test_threads_are_independent_conversations(monkeypatch):
    graph = make_graph(monkeypatch, ["for-a", "for-b"])
    for thread in ("a", "b"):
        graph.invoke({"messages": []}, config(thread))
    graph.invoke(Command(resume="question a"), config("a"))
    graph.invoke(Command(resume="question b"), config("b"))

    assert contents(graph, config("a")) == ["question a", "for-a"]
    assert contents(graph, config("b")) == ["question b", "for-b"]


def test_long_chat_needs_no_recursion_limit(monkeypatch):
    graph = make_graph(monkeypatch, ["ok"] * 20)
    cfg = config()
    graph.invoke({"messages": []}, cfg)
    for i in range(20):  # 20 questions would exceed the default 25 steps in agent 2
        graph.invoke(Command(resume=f"q{i}"), cfg)
    graph.invoke(Command(resume="stop"), cfg)
    assert len(contents(graph, cfg)) == 41
