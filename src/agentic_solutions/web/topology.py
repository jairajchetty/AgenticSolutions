"""Export a compiled LangGraph graph as plain JSON for the browser to draw.

The frontend (Cytoscape) needs only nodes and edges, so we flatten
``compiled.get_graph()`` into dicts. ``__start__`` and ``__end__`` are
LangGraph's virtual entry/exit nodes; they get their own ``kind`` so the UI
can style them differently.

Two optional extras come from the pattern, not from LangGraph:

* ``edge_labels`` maps ``(source, target)`` to ``(short, detail)``: the short
  label is drawn on the edge, the detail is the full condition shown on hover.
* ``layout`` fixes the drawing: ``positions`` maps each node to ``(x, y)`` and
  ``bends`` maps an edge to how far its curve bows (0 or absent: straight).
  Without it the browser lays the graph out automatically.
"""
from __future__ import annotations

_KINDS = {"__start__": "start", "__end__": "end"}


def graph_topology(compiled, edge_labels: dict | None = None, layout: dict | None = None) -> dict:
    """Return {"nodes": [...], "edges": [...]} for a compiled graph."""
    g = compiled.get_graph()
    labels = edge_labels or {}
    positions = (layout or {}).get("positions", {})
    bends = (layout or {}).get("bends", {})

    def position(nid):
        return {"x": positions[nid][0], "y": positions[nid][1]} if nid in positions else None

    nodes = [
        {"id": nid, "label": nid, "kind": _KINDS.get(nid, "node"), "position": position(nid)}
        for nid in g.nodes
    ]
    edges = []
    for e in g.edges:
        short, detail = labels.get((e.source, e.target), (None, None))
        edges.append({
            "source": e.source,
            "target": e.target,
            "conditional": bool(e.conditional),
            "label": short or (e.data if isinstance(e.data, str) else None),
            "detail": detail,
            "bend": bends.get((e.source, e.target)),
        })
    return {"nodes": nodes, "edges": edges}
