"""Shared LLM factory so every agent uses the same Claude configuration."""
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5-5"


def get_llm(model: str | None = None, **kwargs) -> ChatAnthropic:
    """Build the Claude client.

    No temperature is set by default: newer Claude models reject non-default
    values. Pass `temperature=...` explicitly only for models that allow it.
    """
    return ChatAnthropic(
        model=model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL),
        **kwargs,
    )
