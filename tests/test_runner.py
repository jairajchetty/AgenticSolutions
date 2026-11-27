import pytest
from langgraph.checkpoint.memory import InMemorySaver
from agentic_solutions.web.registry import PATTERNS, BuildContext, offline_factory
from agentic_solutions.web.runner import run_events
from fakes import make_guard

async def collect(spec_id, graph_input_fn, resumed, cfg, graph=None):
    spec = PATTERNS[spec_id]
    graph = graph or spec.build(BuildContext(offline_factory(spec_id, 0), InMemorySaver(), make_guard()))
    return graph, [e async for e in run_events(graph, graph_input_fn(spec), cfg, thread_id="t",
                                               mode="offline", resumed=resumed, output=spec.output)]

def types(evts):
    return [e["type"] for e in evts if e["type"] != "token"]

@pytest.mark.anyio
async def test_trigger_run_event_sequence():
    _, ev = await collect("qa", lambda s: s.make_input(s.samples[0]), False, {"configurable": {"thread_id": "a"}})
    assert types(ev) == ["run_started", "edge", "node_started", "node_finished", "edge", "run_finished"]
    assert [(e["source"], e["target"]) for e in ev if e["type"] == "edge"] == [("__start__", "answer"), ("answer", "__end__")]
    assert ev[-1]["status"] == "completed" and ev[-1]["output"]
    assert any(e["type"] == "token" and e["node"] == "answer" for e in ev)

@pytest.mark.anyio
async def test_chat_prime_pauses_then_resume_marks_resumed_node():
    cfg = {"configurable": {"thread_id": "b"}}
    g, ev = await collect("chat_loop", lambda s: s.start_input(), False, cfg)
    assert ev[-1]["status"] == "paused" and any(e["type"] == "interrupt" for e in ev)
    spec = PATTERNS["chat_loop"]
    _, ev2 = await collect("chat_loop", lambda s: s.make_input(s.samples[0]), True, cfg, graph=g)
    first = next(e for e in ev2 if e["type"] == "node_started")
    assert first["node"] == "ask" and first["resumed"] is True
    assert [(e["source"], e["target"]) for e in ev2 if e["type"] == "edge"] == [("ask", "answer"), ("answer", "ask")]
    assert ev2[-1]["status"] == "paused"

@pytest.mark.anyio
async def test_node_failure_becomes_safe_error_event():
    class Boom:
        def invoke(self, *_a, **_k):
            raise RuntimeError("secret-detail")
    spec = PATTERNS["qa"]
    g = spec.build(BuildContext(lambda: Boom(), InMemorySaver(), None))
    ev = [e async for e in run_events(g, spec.make_input("hi"), {"configurable": {"thread_id": "c"}},
                                      thread_id="c", mode="offline", resumed=False)]
    assert ev[-2] == {"type": "error", "message": "The run failed."}
    assert ev[-1]["status"] == "error" and "secret-detail" not in str(ev)

@pytest.mark.anyio
async def test_timeout_becomes_error_event():
    spec = PATTERNS["qa"]
    g = spec.build(BuildContext(offline_factory("qa", 3), InMemorySaver(), None))    # 0.9-2.7 s before first token
    ev = [e async for e in run_events(g, spec.make_input(spec.samples[0]), {"configurable": {"thread_id": "d"}},
                                      thread_id="d", mode="offline", resumed=False, timeout_s=0.2)]
    assert {"type": "error", "message": "The run timed out."} in ev

@pytest.mark.anyio
async def test_node_failure_logs_original_exception_server_side(caplog):
    class Boom:
        def invoke(self, *_a, **_k):
            raise RuntimeError("secret-detail")
    spec = PATTERNS["qa"]
    g = spec.build(BuildContext(lambda: Boom(), InMemorySaver(), None))
    with caplog.at_level("ERROR"):
        ev = [e async for e in run_events(g, spec.make_input("hi"), {"configurable": {"thread_id": "e"}},
                                          thread_id="e", mode="offline", resumed=False)]
    assert "secret-detail" in caplog.text
    assert "secret-detail" not in str(ev)
    assert {"type": "error", "message": "The run failed."} in ev

@pytest.mark.anyio
async def test_only_ai_messages_become_tokens():
    from typing import Annotated, TypedDict
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langgraph.graph import START, END, StateGraph
    from langgraph.graph.message import add_messages

    class S(TypedDict):
        messages: Annotated[list, add_messages]

    def node(state):
        return {"messages": [HumanMessage("human-text", id="h"),
                             ToolMessage("tool-text", tool_call_id="1", id="t"),
                             AIMessage([{"type": "text", "text": "ai-"}, {"type": "text", "text": "blocks"}], id="a")]}

    b = StateGraph(S)
    b.add_node("n", node)
    b.add_edge(START, "n")
    b.add_edge("n", END)
    g = b.compile(checkpointer=InMemorySaver())
    ev = [e async for e in run_events(g, {"messages": []}, {"configurable": {"thread_id": "f"}},
                                      thread_id="f", mode="offline", resumed=False)]
    tokens = [e["text"] for e in ev if e["type"] == "token"]
    assert "human-text" not in tokens and "tool-text" not in tokens
    assert tokens == ["ai-blocks"]


def _graph_raising(exc):
    from typing import TypedDict
    from langgraph.graph import START, END, StateGraph

    class S(TypedDict, total=False):
        x: int

    def node(state):
        raise exc

    b = StateGraph(S)
    b.add_node("n", node)
    b.add_edge(START, "n")
    b.add_edge("n", END)
    return b.compile(checkpointer=InMemorySaver())


@pytest.mark.anyio
async def test_user_facing_error_message_reaches_the_stream():
    from agentic_solutions.common.errors import UserFacingError
    g = _graph_raising(UserFacingError("The ERP system is unavailable. Try again shortly."))
    ev = [e async for e in run_events(g, {}, {"configurable": {"thread_id": "u"}},
                                      thread_id="u", mode="offline", resumed=False)]
    assert ev[-2] == {"type": "error", "message": "The ERP system is unavailable. Try again shortly."}
    assert ev[-1]["type"] == "run_finished" and ev[-1]["status"] == "error"


@pytest.mark.anyio
async def test_other_errors_stay_generic():
    g = _graph_raising(ValueError("secret-detail"))
    ev = [e async for e in run_events(g, {}, {"configurable": {"thread_id": "v"}},
                                      thread_id="v", mode="offline", resumed=False)]
    assert ev[-2] == {"type": "error", "message": "The run failed."}
    assert "secret-detail" not in str(ev)


@pytest.mark.anyio
async def test_refusal_after_streamed_text_finishes_with_the_declined_reply():
    """A model that streams some text and then refuses (finding 5).

    The tokens carry both the partial text and the declined copy, so the
    console must take the reply from ``node_finished``: it holds only the
    declined copy, never the partial text.
    """
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk
    from agentic_solutions.common.llm import DECLINED

    class StreamThenRefuse(FakeListChatModel):
        def _stream(self, *a, **k):
            yield ChatGenerationChunk(message=AIMessageChunk("partial secret "))
            yield ChatGenerationChunk(message=AIMessageChunk("", response_metadata={"stop_reason": "refusal"}))

    spec = PATTERNS["chat_loop"]
    g = spec.build(BuildContext(lambda: StreamThenRefuse(responses=["x"]), InMemorySaver(), None))
    cfg = {"configurable": {"thread_id": "refusal"}}
    async for _ in run_events(g, spec.start_input(), cfg, thread_id="refusal", mode="live", resumed=False):
        pass
    ev = [e async for e in run_events(g, spec.make_input("hi"), cfg, thread_id="refusal", mode="live",
                                      resumed=True)]
    streamed = "".join(e["text"] for e in ev if e["type"] == "token" and e["node"] == "answer")
    assert streamed.startswith("partial secret ")                     # what the bubble showed while streaming
    finished = next(e for e in ev if e["type"] == "node_finished" and e["node"] == "answer")
    assert [m["content"] for m in finished["update"]["messages"]] == [DECLINED]
