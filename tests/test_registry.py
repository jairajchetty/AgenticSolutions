from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from agentic_solutions.web.registry import PATTERNS, BuildContext, offline_factory
from agentic_solutions.web.offline.model import ScriptedChatModel
from agentic_solutions.web.offline.scripts import SCRIPTS
from agentic_solutions.web.topology import graph_topology
from fakes import NoLibrary, UnreachableErp, make_guard, no_token
import pytest
from guide_format import SECTIONS
from pathlib import Path
import re

AGENTS = Path("src/agentic_solutions/agents")

def test_every_explanation_has_required_sections():
    files = sorted(AGENTS.glob("*/explanation.md"))
    assert len(files) >= 4
    for f in files:
        assert re.findall(r"^## (.+)$", f.read_text(), re.M) == SECTIONS, f

EXPECTED_EDGES = {
    "qa": {("__start__", "answer"), ("answer", "__end__")},
    "chat_loop": {("__start__", "ask"), ("answer", "ask"), ("ask", "__end__"), ("ask", "answer"), ("ask", "ask")},
    "guardrail": {("__start__", "ask"), ("ask", "__end__"), ("ask", "ask"), ("ask", "guard"),
                  ("guard", "answer"), ("guard", "refuse"), ("answer", "ask"), ("refuse", "ask")},
    "approval": {
        ("__start__", "ask"),
        ("ask", "agent"), ("ask", "ask"), ("ask", "__end__"),
        ("agent", "tools"), ("agent", "policy"), ("agent", "ask"),
        ("tools", "agent"),
        ("policy", "submit_po"), ("policy", "approval"), ("policy", "agent"),
        ("approval", "submit_po"), ("approval", "policy"), ("approval", "agent"),
        ("submit_po", "ask"), ("submit_po", "agent"),
    },
    "rag": {("__start__", "ask"), ("ask", "agent"), ("ask", "ask"), ("ask", "__end__"),
                 ("agent", "tools"), ("agent", "ask"), ("tools", "grade"), ("grade", "agent"),
                 ("grade", "rewrite_query"), ("rewrite_query", "tools"), ("rewrite_query", "agent")},
}

APPROVAL_SAMPLES = ("Order 12 laptops for the Cape Town office under CT-OPS",
                    "Order 3 keyboards for CT-OPS", "Order 40 monitors for JHB-FIN")

def ctx(pid):
    return BuildContext(llm_factory=offline_factory(pid, latency_scale=0), checkpointer=InMemorySaver(),
                        guard=make_guard(), erp=UnreachableErp(), issue_token=no_token, library=NoLibrary())

def test_catalog_order_and_modes():
    assert [(p.id, p.mode) for p in PATTERNS.values()] == [
        ("qa", "trigger"), ("chat_loop", "chat"), ("guardrail", "chat"), ("approval", "chat"),
        ("rag", "chat")]

def test_topology_matches_expected_edges_for_every_pattern():
    for pid, spec in PATTERNS.items():
        t = graph_topology(spec.build(ctx(pid)))
        assert {(e["source"], e["target"]) for e in t["edges"]} == EXPECTED_EDGES[pid], pid

def test_every_sample_hits_a_specific_rule():
    for pid, spec in PATTERNS.items():
        script = SCRIPTS[pid]
        for sample in spec.samples:
            if pid == "guardrail" and "ignore previous instructions" in sample.lower():
                continue  # refused by the guard; the LLM is never called
            m = ScriptedChatModel(script=script, latency=(0, 0), tokens_per_second=0)
            if pid in ("approval", "rag"):
                m = m.bind_tools([])  # these agents always call a tool-bound model
            m.invoke([("user", sample)])
            assert m.matched_rule is not None, (pid, sample)

def test_chat_pattern_ignores_whitespace_without_calling_llm():
    spec = PATTERNS["chat_loop"]
    calls = []
    def counting_factory():
        calls.append(1)
        return offline_factory("chat_loop", 0)()
    g = spec.build(BuildContext(counting_factory, InMemorySaver(), None))
    cfg = {"configurable": {"thread_id": "w"}}
    g.invoke(spec.start_input(), cfg)
    g.invoke(spec.make_input("   "), cfg)
    assert g.get_state(cfg).next == ("ask",) and calls == []

def test_trigger_output_is_last_assistant_text():
    spec = PATTERNS["qa"]
    g = spec.build(ctx("qa"))
    values = g.invoke(spec.make_input(spec.samples[0]), {"configurable": {"thread_id": "q"}})
    assert spec.output(values)

def test_offline_factory_builds_a_new_model_each_call():
    f = offline_factory("qa", latency_scale=2)
    a, b = f(), f()
    assert a is not b and a.latency == (0.6, 1.8) and a.tokens_per_second == 20
    assert offline_factory("qa", 0)().tokens_per_second == 0

def test_guardrail_refuses_attack_sample_and_answers_harmless_ones():
    spec = PATTERNS["guardrail"]
    g = spec.build(ctx("guardrail"))
    cfg = {"configurable": {"thread_id": "g"}}
    g.invoke(spec.start_input(), cfg)
    for sample in spec.samples:
        v = g.invoke(spec.make_input(sample), cfg)
        attack = "ignore previous instructions" in sample.lower()
        assert bool(v["refusal"]) == attack, sample

def test_titles_match_spec():
    assert [p.title for p in PATTERNS.values()] == [
        "Single LLM call",
        "Loop with conditional routing and memory",
        "Input guardrail (embedding threat screen)",
        "Approval: propose, approve, then act",
        "RAG: answers from a vector database",
    ]


def test_approval_registered_and_human_in_loop_gone():
    assert "human_in_loop" not in PATTERNS and "human_in_loop" not in SCRIPTS
    spec = PATTERNS["approval"]
    assert spec.title == "Approval: propose, approve, then act"
    assert spec.summary == ("The agent drafts a purchase order; a policy or you approve the exact "
                            "order before the ERP accepts it.")
    assert spec.mode == "chat"
    assert spec.explanation_path == AGENTS.resolve() / "approval_agent" / "explanation.md"
    assert spec.samples == APPROVAL_SAMPLES
    assert "approval" in SCRIPTS


def test_approval_build_needs_an_erp():
    with pytest.raises(RuntimeError, match="^the approval demo needs an ERP client$"):
        PATTERNS["approval"].build(BuildContext(offline_factory("approval", 0), InMemorySaver(), None))


def test_build_context_erp_defaults():
    c = BuildContext(offline_factory("qa", 0), InMemorySaver(), None)
    assert (c.erp, c.issue_token, c.auto_limit_zar) == (None, None, 5000)


def test_approval_build_needs_a_token_issuer():
    with pytest.raises(RuntimeError, match="^the approval demo needs a token issuer$"):
        PATTERNS["approval"].build(BuildContext(offline_factory("approval", 0), InMemorySaver(), None,
                                                erp=UnreachableErp()))
