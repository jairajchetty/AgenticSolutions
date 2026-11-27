"""Shared LLM factory so every agent uses the same Claude configuration."""
import os
from collections.abc import Callable

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5-5"

# A zero-argument callable that returns a chat model. Graphs accept one so a
# caller (e.g. a web layer or a test) can inject its own model.
LLMFactory = Callable[[], BaseChatModel]


def make_chat_model(model: str, **kwargs) -> BaseChatModel:
    """Build any provider's chat model from a "provider:model" string.

    A thin wrapper over LangChain's `init_chat_model`, e.g.
    `make_chat_model("anthropic:claude-haiku-5-5")`.
    """
    return init_chat_model(model, **kwargs)


def get_llm(model: str | None = None, **kwargs) -> ChatAnthropic:
    """Build the Claude client.

    No temperature is set by default: newer Claude models reject non-default
    values. Pass `temperature=...` explicitly only for models that allow it.
    """
    return ChatAnthropic(
        model=model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL),
        **kwargs,
    )


# ---- Model menu adapters (Task 2) -----------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1"
MAX_TOKENS = 4096
DECLINED = "The model declined this request."
PROVIDERS_HINT = "Install the providers extra: pip install -e '.[providers]'"

_openrouter_cls: type | None = None


def _openrouter_class() -> type:
    """Build the OpenRouterChat class on first use, so langchain_openai stays optional."""
    global _openrouter_cls
    if _openrouter_cls is None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise RuntimeError(PROVIDERS_HINT) from None

        class OpenRouterChat(ChatOpenAI):
            """ChatOpenAI pointed at OpenRouter; maps tool_choice none to the OpenAI form."""

            def bind_tools(self, tools, *, tool_choice=None, **kwargs):
                if tool_choice == {"type": "none"}:
                    tool_choice = "none"
                return super().bind_tools(tools, tool_choice=tool_choice, **kwargs)

        _openrouter_cls = OpenRouterChat
    return _openrouter_cls


def check_provider_available(entry) -> None:
    """Raise RuntimeError at startup when the entry's provider package is missing."""
    if entry.provider == "openrouter":
        _openrouter_class()


def make_model(entry, settings) -> BaseChatModel:
    """Build the chat model for a menu entry. Keys are read from the environment here."""
    if entry.provider == "anthropic":
        return ChatAnthropic(
            model=entry.model, max_tokens=MAX_TOKENS, api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
    if entry.provider == "openrouter":
        cls = _openrouter_class()
        provider = {"data_collection": "deny", "require_parameters": True}
        if settings.openrouter_zdr:
            provider["zdr"] = True
        headers = {}
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_title:
            headers["X-Title"] = settings.openrouter_app_title
        return cls(
            model=entry.model,
            base_url=OPENROUTER_URL,
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            max_tokens=MAX_TOKENS,  # sent as max_completion_tokens, OpenRouter's current field
            stream_usage=True,  # with a custom base_url it is off, and streamed runs report 0 tokens
            extra_body={"provider": provider},
            default_headers=headers or None,
        )
    raise ValueError(f"Unknown provider '{entry.provider}'")


def declined_or(msg: AIMessage) -> AIMessage:
    """Replace a refused reply (Anthropic or OpenAI format) with the plain declined copy."""
    meta = msg.response_metadata or {}
    if meta.get("stop_reason") == "refusal" or meta.get("finish_reason") == "content_filter":
        return AIMessage(DECLINED, usage_metadata=msg.usage_metadata)
    return msg
