"""Small helpers for LangChain messages, shared by the CLI agents and the web app."""


def text_of(message) -> str:
    """Return a message's text (Claude may reply with a list of content blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))
