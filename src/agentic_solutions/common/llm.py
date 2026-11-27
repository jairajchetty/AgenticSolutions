"""Shared LLM factory so every agent uses the same Claude configuration."""
import os
from collections.abc import Callable

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

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
