"""JSON-safe conversion of graph state and messages for trace events."""
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from agentic_solutions.common.messages import text_of  # noqa: F401  (re-exported)

ROLES = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}
ROLE_NAMES = set(ROLES.values())


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def message_to_dict(msg, limit: int = 4096) -> dict:
    if msg.type == "remove":
        return {"role": "remove", "id": msg.id}
    out = {"role": ROLES.get(msg.type, msg.type), "content": _cut(text_of(msg), limit)}
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = to_jsonable(
            [{"name": c["name"], "args": c["args"], "id": c["id"]} for c in tool_calls], limit
        )
    if msg.type == "tool" and msg.name:
        out["name"] = msg.name
    return out


def to_jsonable(value: Any, limit: int = 4096) -> Any:
    if isinstance(value, BaseMessage):
        return message_to_dict(value, limit)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _cut(value, limit)
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(), limit)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if (len(value) == 2 and isinstance(value[0], str) and value[0] in ROLE_NAMES
                and isinstance(value[1], str)):
            return {"role": value[0], "content": _cut(value[1], limit)}
        return [to_jsonable(v, limit) for v in value]
    return _cut(str(value), limit)
