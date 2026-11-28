"""Edge labels and the fixed Approval layout (the conditions drawn on the graph)."""
from langgraph.checkpoint.memory import InMemorySaver

from agentic_solutions.agents.interrupt_chat_agent.graph import build_graph
from agentic_solutions.web.registry import PATTERNS, BuildContext, offline_factory, pattern_topology
from agentic_solutions.web.topology import graph_topology
from fakes import NoLibrary, UnreachableErp, make_guard, no_token

MAX_SHORT = 16  # characters: longer labels crowd the drawing


def ctx(pid, limit=5000):
    return BuildContext(llm_factory=offline_factory(pid, latency_scale=0), checkpointer=InMemorySaver(),
                        guard=make_guard(), erp=UnreachableErp(), issue_token=no_token, auto_limit_zar=limit,
                        library=NoLibrary())


def topology(pid, limit=5000):
    c = ctx(pid, limit)
    return pattern_topology(PATTERNS[pid], PATTERNS[pid].build(c), c.auto_limit_zar)


def by_edge(t):
    return {(e["source"], e["target"]): e for e in t["edges"]}


def test_graph_topology_attaches_short_label_and_detail():
    t = graph_topology(build_graph(), edge_labels={("ask", "__end__"): ("stop", "You typed stop.")})
    edge = by_edge(t)[("ask", "__end__")]
    assert (edge["label"], edge["detail"]) == ("stop", "You typed stop.")
    assert by_edge(t)[("ask", "answer")]["detail"] is None


def test_graph_topology_attaches_positions_and_bends():
    layout = {"positions": {"__start__": (0, 0), "ask": (0, 100), "answer": (0, 200), "__end__": (200, 100)},
              "bends": {("ask", "answer"): 30}}
    t = graph_topology(build_graph(), layout=layout)
    assert {n["id"]: n["position"] for n in t["nodes"]}["__end__"] == {"x": 200, "y": 100}
    assert by_edge(t)[("ask", "answer")]["bend"] == 30
    assert by_edge(t)[("answer", "ask")]["bend"] is None


def test_graph_topology_without_layout_leaves_positions_out():
    t = graph_topology(build_graph())
    assert all(n["position"] is None for n in t["nodes"])


def test_every_conditional_edge_of_every_runnable_pattern_is_labelled():
    for pid in PATTERNS:
        for e in topology(pid)["edges"]:
            if e["conditional"]:
                assert e["label"] and e["detail"], (pid, e["source"], e["target"])
                assert len(e["label"]) <= MAX_SHORT, (pid, e["label"])


def test_labels_name_only_real_edges():
    for pid, spec in PATTERNS.items():
        real = set(by_edge(topology(pid)))
        assert set(spec.edge_labels(5000)) <= real, pid
        layout = spec.layout
        if layout:
            assert set(layout["bends"]) <= real, pid


def test_approval_layout_places_every_node():
    nodes = topology("approval")["nodes"]
    assert all(n["position"] for n in nodes), [n["id"] for n in nodes if not n["position"]]


def test_fixed_layouts():
    # Approval and RAG are hand-placed: their labelled edges collide in the automatic layout.
    assert {pid for pid, s in PATTERNS.items() if s.layout} == {"approval", "rag"}


def test_rag_layout_places_every_node_and_bends_both_pairs():
    t = topology("rag")
    assert all(n["position"] for n in t["nodes"]), [n["id"] for n in t["nodes"] if not n["position"]]
    edges = by_edge(t)
    for pair in (("ask", "agent"), ("agent", "ask")):
        assert edges[pair]["bend"], pair  # the two directions curve apart, so their labels separate


def test_approval_threshold_labels_follow_the_configured_limit():
    edges = by_edge(topology("approval", limit=12000))
    assert edges[("policy", "submit_po")]["label"] == "≤ R12,000"
    assert edges[("policy", "approval")]["label"] == "> R12,000"
    assert "R12,000" in edges[("policy", "approval")]["detail"]


def test_api_serves_labels_and_positions(client):
    t = client.get("/api/patterns/approval").json()["topology"]
    assert by_edge(t)[("approval", "agent")]["label"] == "reject"
    assert all(n["position"] for n in t["nodes"])
    g = client.get("/api/patterns/guardrail").json()["topology"]
    assert by_edge(g)[("guard", "refuse")]["label"] == "flagged"
    assert all(n["position"] is None for n in g["nodes"])
