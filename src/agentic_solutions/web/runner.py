"""Turn LangGraph ``astream`` output into the trace events the browser animates (spec §5).

``stream_mode=["tasks", "messages"]`` yields ``(mode, payload)`` tuples:

* ``tasks`` with ``input``  -> a node started
* ``tasks`` with ``result`` -> a node finished (``interrupts`` lists any pause)
* ``messages``              -> ``(message, metadata)``; an AI chunk is one LLM token

The runner never raises: a failure or timeout becomes a safe ``error`` event
followed by ``run_finished{status: "error"}``. Details go to the server log only,
except for a ``UserFacingError``, whose message is written to be shown as is,
and a provider error on a live run, which becomes a fixed safe message
(model picker spec §5).
"""
import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator, Callable, Literal

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage

from agentic_solutions.common.errors import UserFacingError
from agentic_solutions.common.messages import text_of
from agentic_solutions.web.serialize import to_jsonable

log = logging.getLogger(__name__)

RunStatus = Literal["completed", "paused", "error"]  # M3 adds "budget_exhausted"
_HIDDEN_NODES = {"__start__", "__end__"}
_PROVIDER_MODULES = ("anthropic", "openai")  # matched by name, so neither SDK is imported here
RUN_FAILED = "The run failed."


def _provider_class_names(exc: BaseException) -> set[str]:
    """Class names in the exception's MRO that come from a provider SDK."""
    return {c.__name__ for c in type(exc).__mro__
            if (c.__module__ or "").split(".")[0] in _PROVIDER_MODULES}


def _chain(exc: BaseException):
    """The exception and those it wraps (``__cause__``, then ``__context__``), without loops."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def provider_error_message(exc: BaseException, label: str | None, provider: str | None) -> str:
    """The safe copy for a provider error on a live run; "The run failed." for anything else.

    Only the exception's class and status are read: its text, request and
    headers never reach the browser.
    """
    if label is None or provider is None:
        return RUN_FAILED
    for err in _chain(exc):
        names = _provider_class_names(err)
        if "AuthenticationError" in names:
            return f"The {provider} API key was rejected."
        # Anthropic's overload is HTTP 529: OverloadedError, or a bare status error in older SDKs.
        if "RateLimitError" in names or "OverloadedError" in names or (
                "APIStatusError" in names and getattr(err, "status_code", None) == 529):
            return f"{label} is busy or unavailable. Try again in a moment."
        if names & {"APIConnectionError", "APITimeoutError"}:
            return f"Couldn't reach {label}."
        if "APIStatusError" in names and getattr(err, "status_code", None) in (404, 503):
            text = str(err).lower()
            if "provider" in text or "endpoint" in text:  # OpenRouter: no compliant provider
                return f"{label} is busy or unavailable. Try again in a moment."
    return RUN_FAILED


def _messages_in(value: Any) -> list[BaseMessage]:
    """Collect every message nested in a node's result (dicts, lists, tuples)."""
    if isinstance(value, BaseMessage):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return [m for v in value for m in _messages_in(v)]
    return []


async def run_events(
    graph,
    graph_input,
    config: dict,
    *,
    thread_id: str,
    mode: str,
    resumed: bool,
    timeout_s: float = 90.0,
    output: Callable[[dict], str | None] | None = None,
    model: str = "offline",
    label: str | None = None,
    provider: str | None = None,
) -> AsyncIterator[dict]:
    """``mode`` is "offline" or "live"; ``model`` is the menu id. ``label`` and
    ``provider`` (e.g. "Anthropic") name a live model in the safe error copy."""
    yield {"type": "run_started", "run_id": uuid.uuid4().hex, "thread_id": thread_id, "mode": mode,
           "model": model}

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    started: dict[str, tuple[int, float]] = {}  # task id -> (step, monotonic start)
    step = 0
    last_node: str | None = None
    first_node = True
    interrupted = False
    status: RunStatus = "completed"
    deadline = asyncio.get_running_loop().time() + timeout_s
    stream = graph.astream(graph_input, config, stream_mode=["tasks", "messages"]).__aiter__()

    try:
        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    item = await stream.__anext__()
            except StopAsyncIteration:
                break
            kind, payload = item

            if kind == "messages":
                chunk, meta = payload
                # Only model output is a token. A node that returns a user or
                # tool message shows up here too, and must not be "typed out".
                if not isinstance(chunk, (AIMessageChunk, AIMessage)):
                    continue
                text = text_of(chunk)
                if text:
                    yield {"type": "token", "node": meta.get("langgraph_node"), "text": text}
                continue
            if kind != "tasks" or payload.get("name") in _HIDDEN_NODES:
                continue

            node = payload["name"]
            if "input" in payload:
                step += 1
                started[payload["id"]] = (step, time.monotonic())
                if first_node and not resumed:
                    yield {"type": "edge", "source": "__start__", "target": node, "step": step}
                elif not first_node:
                    yield {"type": "edge", "source": last_node, "target": node, "step": step}
                yield {"type": "node_started", "step": step, "node": node, "ts": time.time(),
                       "resumed": resumed and first_node}
                first_node = False
            elif "result" in payload or "error" in payload:
                if payload.get("error"):
                    err = payload["error"]  # LangGraph hands us the real exception: log it, never send it
                    raise err if isinstance(err, BaseException) else RuntimeError(f"node {node} failed")
                n, t0 = started.pop(payload["id"], (step, time.monotonic()))
                result = payload["result"]
                for msg in _messages_in(result):
                    if isinstance(msg, AIMessage):
                        for call in msg.tool_calls:
                            yield {"type": "tool_call", "node": node, "name": call["name"],
                                   "args": to_jsonable(call["args"]), "id": call["id"]}
                        for key, val in (msg.usage_metadata or {}).items():
                            if key in usage:
                                usage[key] += int(val)
                    elif isinstance(msg, ToolMessage):
                        yield {"type": "tool_result", "name": msg.name,
                               "content": to_jsonable(text_of(msg)), "id": msg.tool_call_id}
                yield {"type": "node_finished", "step": n, "node": node, "ts": time.time(),
                       "duration_ms": int((time.monotonic() - t0) * 1000),
                       "update": to_jsonable(result)}
                last_node = node
                for it in payload.get("interrupts") or []:
                    interrupted = True
                    yield {"type": "interrupt", "node": node, "payload": to_jsonable(it["value"])}

        if interrupted:
            status = "paused"
        elif last_node is not None:
            yield {"type": "edge", "source": last_node, "target": "__end__", "step": step}
        out = None
        if status == "completed" and output is not None:
            out = output((await graph.aget_state(config)).values)
        yield {"type": "run_finished", "status": status, "output": out, "usage": usage}
    except TimeoutError:
        log.exception("run timed out (thread %s)", thread_id)
        yield {"type": "error", "message": "The run timed out."}
        yield {"type": "run_finished", "status": "error", "output": None, "usage": usage}
    except UserFacingError as err:  # written to be shown: plain, specific, no internals
        log.warning("run stopped (thread %s): %s", thread_id, err, exc_info=True)  # cause stays here
        yield {"type": "error", "message": str(err)}
        yield {"type": "run_finished", "status": "error", "output": None, "usage": usage}
    except Exception as exc:
        # The event never carries the exception's text, only the fixed safe copy.
        # The log has the traceback (class and message) but not the exception's
        # request, response, headers or body, nor any frame's locals.
        log.exception("run failed (thread %s, model %s)", thread_id, model)
        yield {"type": "error", "message": provider_error_message(exc, label, provider)}
        yield {"type": "run_finished", "status": "error", "output": None, "usage": usage}
    finally:
        await stream.aclose()
