"""The catalog API (Catalog spec §5.2): the menu listing and one page per route."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

import agentic_solutions.web.app as app_module
from agentic_solutions.web.app import create_app
from agentic_solutions.web.config import Settings
from agentic_solutions.web.offline.scripts import SCRIPTS
from agentic_solutions.web.registry import PATTERNS
from fakes import make_guard

LIVE_ROUTES = {"collaboration/single-agent", "memory/session",
               "governance/guardrails", "governance/approval"}


def _settings() -> Settings:
    return Settings(session_secret="test-secret", offline_latency_scale=0, checkpoint_db=":memory:")


def test_catalog_listing_shape_and_order(client):
    body = client.get("/api/catalog").json()
    cats = body["categories"]
    assert [c["id"] for c in cats] == ["cognitive", "collaboration", "memory", "execution", "governance"]
    assert set(cats[0]) == {"id", "name", "question", "patterns"}
    rows = [p for c in cats for p in c["patterns"]]
    assert len(rows) == 21
    assert set(rows[0]) == {"id", "name", "hint", "aliases", "status", "route", "target"}
    statuses = {p["route"]: p["status"] for p in rows}
    assert {r for r, s in statuses.items() if s == "live"} == LIVE_ROUTES
    assert sum(s == "guide" for s in statuses.values()) == 17
    assert statuses["execution/tool-use"] == "guide"
    tool_use = next(p for p in rows if p["route"] == "execution/tool-use")
    assert tool_use["target"] == "cognitive/react"
    assert all(p["target"] == p["route"] for p in rows if p is not tool_use)


def test_page_for_live_pattern(client):
    page = client.get("/api/catalog/governance/approval").json()
    assert page["route"] == page["target"] == "governance/approval"
    assert page["category"] == {"id": "governance", "name": "Governance"}
    assert page["name"] == "Approval"
    assert page["status"] == "live"
    assert page["demo"] == "human_in_loop"
    assert page["demo_title"] == PATTERNS["human_in_loop"].title
    assert page["explanation_md"].startswith("# Approval")
    assert "ask" in {n["id"] for n in page["topology"]["nodes"]}
    assert (page["prev"], page["next"]) == ("governance/guardrails", "governance/audit")


def test_page_for_guide_only_pattern(client):
    page = client.get("/api/catalog/memory/episodic").json()
    assert page["status"] == "guide"
    assert page["demo"] is None
    assert page["demo_title"] is None
    nodes = {n["id"] for n in page["topology"]["nodes"]}
    assert nodes >= {"recall_episodes", "answer", "store_episode"}


def test_crosslist_page_uses_target_content_and_request_category(client):
    page = client.get("/api/catalog/execution/tool-use").json()
    react = client.get("/api/catalog/cognitive/react").json()
    assert page["route"] == "execution/tool-use"
    assert page["target"] == "cognitive/react"
    assert page["category"] == {"id": "execution", "name": "Execution"}
    assert page["explanation_md"].startswith("# ReAct")
    for key in ("name", "explanation_md", "topology", "demo", "demo_title", "status"):
        assert page[key] == react[key]
    assert page["prev"].startswith("execution/") and page["next"].startswith("execution/")
    assert (page["prev"], page["next"]) == ("execution/autonomous", "execution/routing")


def test_unknown_route_404(client):
    for path in ("/api/catalog/memory/nope", "/api/catalog/nope/nope"):
        r = client.get(path)
        assert r.status_code == 404
        assert r.json() == {"detail": "not found"}


def test_status_flips_when_demo_registered(monkeypatch):
    # A stand-in "reflection" demo: the qa graph under the id the catalog already names.
    monkeypatch.setitem(SCRIPTS, "reflection", SCRIPTS["qa"])
    registry = {**PATTERNS, "reflection": replace(PATTERNS["qa"], id="reflection", title="Fake reflection")}
    app = create_app(_settings(), checkpointer=InMemorySaver(), guard=make_guard(), registry=registry)
    with TestClient(app) as c:
        rows = {p["route"]: p for k in c.get("/api/catalog").json()["categories"] for p in k["patterns"]}
        assert rows["cognitive/reflection"]["status"] == "live"
        page = c.get("/api/catalog/cognitive/reflection").json()
    assert page["status"] == "live"
    assert page["demo"] == "reflection"
    assert page["demo_title"] == "Fake reflection"
    assert page["explanation_md"].startswith("# Reflection")


def test_opening_guide_page_creates_no_thread():
    saver = InMemorySaver()
    app = create_app(_settings(), checkpointer=saver, guard=make_guard())
    with TestClient(app) as c:
        assert c.get("/api/catalog/memory/episodic").status_code == 200
        assert app.state.store._threads == {}  # no ThreadRecord made (Review Focus 5)
    assert list(saver.list(None)) == []  # and nothing checkpointed


def test_broken_skeleton_fails_startup_naming_the_folder(monkeypatch):
    real = app_module.import_module

    def broken(name):
        if name == "agentic_solutions.agents.audit_agent.graph":
            raise ImportError("boom")
        return real(name)

    monkeypatch.setattr(app_module, "import_module", broken)
    app = create_app(_settings(), checkpointer=InMemorySaver(), guard=make_guard())
    with pytest.raises(RuntimeError, match="audit_agent"):
        with TestClient(app):
            pass
