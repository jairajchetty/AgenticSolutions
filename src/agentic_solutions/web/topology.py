"""Export a compiled LangGraph graph as plain JSON for the browser to draw.

The frontend (Cytoscape) needs only nodes and edges, so we flatten
``compiled.get_graph()`` into dicts. ``__start__`` and ``__end__`` are
LangGraph's virtual entry/exit nodes; they get their own ``kind`` so the UI
can style them differently.
"""
from __future__ import annotations

_KINDS = {"__start__": "start", "__end__": "end"}


def graph_topology(compiled) -> dict:
    """Return {"nodes": [...], "edges": [...]} for a compiled graph."""
    g = compiled.get_graph()
    nodes = [
        {"id": nid, "label": nid, "kind": _KINDS.get(nid, "node")}
        for nid in g.nodes
    ]
    edges = [
        {
            "source": e.source,
            "target": e.target,
            "conditional": bool(e.conditional),
            "label": e.data if isinstance(e.data, str) else None,
        }
        for e in g.edges
    ]
    return {"nodes": nodes, "edges": edges}
