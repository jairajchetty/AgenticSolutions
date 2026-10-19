"""Shared LLM factory so every agent uses the same Claude configuration."""
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5-5"


def get_llm(model: str | None = None, **kwargs) -> ChatAnthropic:
    return ChatAnthropic(
        model=model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL),
        temperature=kwargs.pop("temperature", 0),
        **kwargs,
    )
