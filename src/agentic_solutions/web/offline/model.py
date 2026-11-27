"""Scripted offline chat model.

Offline mode swaps Claude for this model so anonymous visitors (and every
test) can run each pattern for free. It picks a canned reply by matching the
latest human message against an ordered list of rules, then "types" it out
word by word so the browser still shows streaming tokens.

LangGraph nodes call ``llm.invoke(...)``; when the graph streams with
``stream_mode="messages"`` LangChain routes that call through ``_stream``,
which is why ``_stream`` yields word-sized chunks.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
import json
from uuid import uuid4
from typing import Any, Callable, Iterator, Literal, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


@dataclass(frozen=True)
class Rule:
    """A str ``match`` is a case-insensitive substring of the human message.

    ``reply`` is fixed text, an ``AIMessage`` (which may carry ``tool_calls``),
    or a function of the whole message list returning either. ``kind``
    restricts the rule to unbound ("text") or tool-bound ("tools") models;
    ``None`` matches both.
    """

    match: str | Callable[[str], bool]
    reply: Any  # str | AIMessage | Callable[[list[BaseMessage]], str | AIMessage]
    kind: Optional[Literal["text", "tools"]] = None


@dataclass(frozen=True)
class Script:
    rules: tuple[Rule, ...]
    fallback: Any  # same shapes as Rule.reply


def _words(text: str) -> int:
    return len(text.split())


def _text(content: Any) -> str:
    return content if isinstance(content, str) else str(content)


class ScriptedChatModel(BaseChatModel):
    script: Script
    latency: tuple[float, float] = (0.3, 0.9)  # seconds before the first token
    tokens_per_second: float = 40.0  # 0 = no pacing
    matched_rule: Optional[int] = None  # index of last rule used, None = fallback
    bound: bool = False  # True once bind_tools has been called
    bound_tool_names: tuple[str, ...] = ()
    tool_choice: Any = None

    @property
    def _llm_type(self) -> str:
        return "scripted-offline"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any) -> "ScriptedChatModel":
        """Return an independent copy that calls as kind "tools"."""
        names = []
        for t in tools:
            if isinstance(t, dict):
                names.append(t.get("name") or t.get("function", {}).get("name", ""))
            else:
                names.append(getattr(t, "name", None) or getattr(t, "__name__", str(t)))
        return self.model_copy(
            update={"bound": True, "bound_tool_names": tuple(names), "tool_choice": tool_choice}
        )

    def _resolve(self, reply: Any, messages: list[BaseMessage]) -> AIMessage:
        if callable(reply):
            reply = reply(messages)
        return reply if isinstance(reply, AIMessage) else AIMessage(content=_text(reply))

    def _pick(self, messages: list[BaseMessage]) -> tuple[AIMessage, str]:
        """Return (reply, latest human text) and record the matched rule."""
        human = ""
        for m in reversed(messages):
            if m.type == "human":
                human = _text(m.content)
                break
        lowered = human.lower()
        kind = "tools" if self.bound else "text"
        chosen: Any = None
        self.matched_rule = None
        for i, rule in enumerate(self.script.rules):
            if rule.kind is not None and rule.kind != kind:
                continue
            hit = rule.match(human) if callable(rule.match) else rule.match.lower() in lowered
            if hit:
                self.matched_rule = i
                chosen = rule.reply
                break
        if self.matched_rule is None:
            chosen = self.script.fallback
        msg = self._resolve(chosen, messages)
        if msg.tool_calls:
            if self.tool_choice == "none" or (
                isinstance(self.tool_choice, dict) and self.tool_choice.get("type") == "none"
            ):
                text = _text(msg.content)
                if not text:
                    text = _text(self._resolve(self.script.fallback, messages).content)
                msg = AIMessage(content=text)
            else:
                calls = [
                    {**c, "id": f"call_{uuid4().hex[:12]}", "type": "tool_call"}
                    for c in msg.tool_calls
                ]
                msg = AIMessage(content=msg.content, tool_calls=calls)
        return msg, human

    def _usage(self, prompt: str, reply: str) -> UsageMetadata:
        i, o = _words(prompt), _words(reply)
        return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}

    def _delay(self) -> None:
        if self.latency[1] > 0:
            time.sleep(random.uniform(*self.latency))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        picked, human = self._pick(messages)
        self._delay()
        text = _text(picked.content)
        msg = AIMessage(
            content=picked.content,
            tool_calls=picked.tool_calls,
            usage_metadata=self._usage(human, text),
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        picked, human = self._pick(messages)
        self._delay()
        reply = _text(picked.content)
        if picked.tool_calls:
            chunk = AIMessageChunk(
                content=picked.content,
                tool_call_chunks=[
                    {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                    for i, c in enumerate(picked.tool_calls)
                ],
                usage_metadata=self._usage(human, reply),
            )
            if run_manager:
                run_manager.on_llm_new_token(reply, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)
            return
        pieces = re.findall(r"\S+\s*", reply)  # words keep trailing whitespace
        for n, piece in enumerate(pieces):
            if self.tokens_per_second > 0:
                time.sleep(1 / self.tokens_per_second)
            last = n == len(pieces) - 1
            chunk = AIMessageChunk(
                content=piece,
                usage_metadata=self._usage(human, reply) if last else None,
            )
            if run_manager:
                run_manager.on_llm_new_token(piece, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)
