from agentic_solutions.agents.interrupt_chat_agent.graph import build_graph
from agentic_solutions.web.topology import graph_topology


def edges(t):
    return {(e["source"], e["target"], e["conditional"]) for e in t["edges"]}


def test_interrupt_chat_topology():
    t = graph_topology(build_graph())
    assert {n["id"]: n["kind"] for n in t["nodes"]} == {
        "__start__": "start", "ask": "node", "answer": "node", "__end__": "end"}
    assert edges(t) == {("__start__", "ask", False), ("answer", "ask", False),
        ("ask", "__end__", True), ("ask", "answer", True), ("ask", "ask", True)}
