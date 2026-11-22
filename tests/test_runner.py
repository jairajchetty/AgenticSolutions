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
    g, ev = await collect("human_in_loop", lambda s: s.start_input(), False, cfg)
    assert ev[-1]["status"] == "paused" and any(e["type"] == "interrupt" for e in ev)
    spec = PATTERNS["human_in_loop"]
    _, ev2 = await collect("human_in_loop", lambda s: s.make_input(s.samples[0]), True, cfg, graph=g)
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
