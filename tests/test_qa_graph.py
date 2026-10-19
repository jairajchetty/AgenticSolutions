from langchain_core.language_models.fake_chat_models import FakeListChatModel

from agentic_solutions.agents.qa_agent import graph as qa


def test_graph_returns_llm_reply(monkeypatch):
    monkeypatch.setattr(qa, "get_llm", lambda: FakeListChatModel(responses=["42"]))
    result = qa.build_graph().invoke({"messages": [("user", "meaning of life?")]})
    assert result["messages"][-1].content == "42"
    assert len(result["messages"]) == 2
