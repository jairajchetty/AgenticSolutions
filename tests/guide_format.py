"""Shared helpers for the Guide tests.

Every Guide has seven sections: six generic ones, then "How this Studio implements it".
"""
import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[1] / "src" / "agentic_solutions" / "agents"

SECTIONS = ["What it is", "When to use it", "How it works", "Design considerations",
            "Trade-offs", "Related patterns", "How this Studio implements it"]
STUDIO_SUBSECTIONS = ["Mapping", "Framework concepts", "Key code", "Try this"]

ALL_FOLDERS = sorted(p.parent.name for p in AGENTS.glob("*/explanation.md"))

# Guides spec section 9.3 (case-insensitive, whole words, optional plural "s").
DENY_WORDS = ["LangGraph", "LangChain", "MCP", "Model Context Protocol", "StateGraph", "ToolNode",
              "add_messages", "reducer", "checkpointer", "thread_id", "RemoveMessage", "get_graph",
              "build_graph", "build_skeleton", "Claude", "Anthropic", "OpenAI", "GPT"]
DENY_SUBSTRINGS = ["interrupt(", "Command(", "Send(", "langgraph.", "langchain"]


def _split(md: str, prefix: str) -> list[tuple[str, str]]:
    """Split on lines starting with `prefix` (e.g. "## "), ignoring fenced code.
    Returns (title, body) pairs; text before the first heading is dropped."""
    out: list[tuple[str, list[str]]] = []
    in_fence = False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith(prefix):
            out.append((line[len(prefix):].strip(), []))
        elif out:
            out[-1][1].append(line)
    return [(t, "\n".join(b)) for t, b in out]


def sections(md: str) -> list[tuple[str, str]]:
    return _split(md, "## ")


def subsections(body: str) -> list[tuple[str, str]]:
    return _split(body, "### ")


def generic_text(md: str) -> str:
    """The H1 line plus sections 1-6 (headings included)."""
    h1 = next((ln for ln in md.splitlines() if ln.startswith("# ")), "")
    parts = [h1] + [f"## {t}\n{b}" for t, b in sections(md)[:6]]
    return "\n".join(parts)


def studio_section(md: str) -> str:
    return dict(sections(md)).get("How this Studio implements it", "")


def try_this_text(md: str) -> str:
    return dict(subsections(studio_section(md)))["Try this"]
