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
from typing import Any, Callable, Iterator, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


@dataclass(frozen=True)
class Rule:
    """A str ``match`` is a case-insensitive substring of the human message.

    ``reply`` is fixed text, or a function of the whole message list for a
    reply that depends on the conversation (e.g. recalling an earlier turn).
    """

    match: str | Callable[[str], bool]
    reply: str | Callable[[list[BaseMessage]], str]


@dataclass(frozen=True)
class Script:
    rules: tuple[Rule, ...]
    fallback: str


def _words(text: str) -> int:
    return len(text.split())


def _text(content: Any) -> str:
    return content if isinstance(content, str) else str(content)


class ScriptedChatModel(BaseChatModel):
    script: Script
    latency: tuple[float, float] = (0.3, 0.9)  # seconds before the first token
    tokens_per_second: float = 40.0  # 0 = no pacing
    matched_rule: Optional[int] = None  # index of last rule used, None = fallback

    @property
    def _llm_type(self) -> str:
        return "scripted-offline"

    def _pick(self, messages: list[BaseMessage]) -> tuple[str, str]:
        """Return (reply, latest human text) and record the matched rule."""
        human = ""
        for m in reversed(messages):
            if m.type == "human":
                human = _text(m.content)
                break
        lowered = human.lower()
        for i, rule in enumerate(self.script.rules):
            hit = rule.match(human) if callable(rule.match) else rule.match.lower() in lowered
            if hit:
                self.matched_rule = i
                reply = rule.reply(messages) if callable(rule.reply) else rule.reply
                return reply, human
        self.matched_rule = None
        return self.script.fallback, human

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
        reply, human = self._pick(messages)
        self._delay()
        msg = AIMessage(content=reply, usage_metadata=self._usage(human, reply))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        reply, human = self._pick(messages)
        self._delay()
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
