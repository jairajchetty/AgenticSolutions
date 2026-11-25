"""Offline tests for the model adapters and refusal handling (no network)."""
import builtins

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from agentic_solutions.agents.chat_agent import graph as chat
from agentic_solutions.common import llm as llm_mod
from agentic_solutions.common.llm import check_provider_available, declined_or, make_model
from agentic_solutions.web.config import Settings
from agentic_solutions.web.models import ModelEntry

CLAUDE = ModelEntry("claude-haiku", "Claude Haiku 5.5", "anthropic", "claude-haiku-5-5")
ROUTER = ModelEntry("deepseek", "DeepSeek", "openrouter", "deepseek/deepseek-chat")


@tool
def ping() -> str:
    """Dummy tool."""
    return "pong"


def test_anthropic_entry_builds_with_max_tokens_and_no_temperature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    m = make_model(CLAUDE, Settings())
    assert m.model == "claude-haiku-5-5"
    assert m.max_tokens == 4096
    assert m.temperature is None


def test_openrouter_payload_has_base_url_routing_and_headers(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    s = Settings(openrouter_zdr=True, openrouter_site_url="https://example.org", openrouter_app_title="Studio")
    m = make_model(ROUTER, s)
    assert m.openai_api_base == "https://openrouter.ai/api/v1"
    assert m.default_headers == {"HTTP-Referer": "https://example.org", "X-Title": "Studio"}
    payload = m._get_request_payload([HumanMessage("hi")])
    assert payload["extra_body"]["provider"] == {
        "data_collection": "deny", "require_parameters": True, "zdr": True}
    assert (payload.get("max_tokens") or payload.get("max_completion_tokens")) == 4096
    assert "temperature" not in payload

    plain = make_model(ROUTER, Settings())
    assert plain._get_request_payload([HumanMessage("hi")])["extra_body"]["provider"] == {
        "data_collection": "deny", "require_parameters": True}
    assert not plain.default_headers or "X-Title" not in plain.default_headers


def test_openrouter_tool_choice_none_is_openai_form(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    m = make_model(ROUTER, Settings())
    for choice in ({"type": "none"}, "none"):
        bound = m.bind_tools([ping], tool_choice=choice)
        payload = m._get_request_payload([HumanMessage("hi")], **bound.kwargs)
        assert payload["tool_choice"] == "none"


def test_missing_provider_package_message(monkeypatch):
    monkeypatch.setattr(llm_mod, "_openrouter_cls", None)
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("langchain_openai"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(RuntimeError, match=r"Install the providers extra: pip install -e '\.\[providers\]'"):
        check_provider_available(ROUTER)
    with pytest.raises(RuntimeError, match="providers extra"):
        make_model(ROUTER, Settings())
    check_provider_available(CLAUDE)  # anthropic needs no extra


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        make_model(ModelEntry("x", "X", "nope", "m"), Settings())  # type: ignore[arg-type]


def test_declined_or_maps_refusal_and_passes_others():
    usage = {"input_tokens": 3, "output_tokens": 0, "total_tokens": 3}
    for meta in ({"stop_reason": "refusal"}, {"finish_reason": "content_filter"}):
        out = declined_or(AIMessage("secret", response_metadata=meta, usage_metadata=usage))
        assert out.content == "The model declined this request."
        assert not out.tool_calls
        assert out.usage_metadata == usage
    ok = AIMessage("fine", response_metadata={"stop_reason": "end_turn"})
    assert declined_or(ok) is ok
    assert declined_or(AIMessage("plain")).content == "plain"


class RefusingModel(FakeListChatModel):
    def _generate(self, *a, **k):
        r = super()._generate(*a, **k)
        r.generations[0].message.response_metadata = {"stop_reason": "refusal"}
        return r


def test_live_graph_uses_declined_text(monkeypatch):
    inputs = iter(["hello", "stop"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    fake = RefusingModel(responses=["I will not say"])
    out = chat.build_graph(llm_factory=lambda: fake).invoke({"messages": []}, {"recursion_limit": 25})
    assert [m.content for m in out["messages"] if m.type == "ai"] == ["The model declined this request."]
