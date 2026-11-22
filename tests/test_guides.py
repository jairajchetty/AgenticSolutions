import importlib
import re
from pathlib import Path

import pytest

from agentic_solutions.web import catalog
from test_skeletons import SKELETONS

AGENTS = Path("src/agentic_solutions/agents")
GUIDES = sorted(AGENTS.glob("*/explanation.md"))
# Folders whose H1 must equal the taxonomy name. Task 7 extends this to the live four.
H1_CHECK = set(SKELETONS)


def ids(paths):
    return [p.parent.name for p in paths]


@pytest.mark.parametrize("path", GUIDES, ids=ids(GUIDES))
def test_key_code_fence_at_most_25_lines(path):
    text = path.read_text()
    section = text.split("## Key code", 1)[1]
    m = re.search(r"```[^\n]*\n(.*?)```", section, re.S)
    assert m, "no fenced block under Key code"
    assert len(m.group(1).splitlines()) <= 25


@pytest.mark.parametrize("path", GUIDES, ids=ids(GUIDES))
def test_length_50_to_110_lines(path):
    assert 50 <= len(path.read_text().splitlines()) <= 110


@pytest.mark.parametrize("path", GUIDES, ids=ids(GUIDES))
def test_langgraph_names_import(path):
    for name in re.findall(r"`(langgraph(?:\.\w+)+)`", path.read_text()):
        mod, _, attr = name.rpartition(".")
        try:
            module = importlib.import_module(mod)
            ok = hasattr(module, attr)
        except ImportError:
            ok = False
        if not ok:  # the whole name may itself be a module
            importlib.import_module(name)


@pytest.mark.parametrize("path", GUIDES, ids=ids(GUIDES))
def test_crosslinks_name_catalog_routes(path):
    for route in re.findall(r"\[\[([^\]]+)\]\]", path.read_text()):
        assert catalog.entry(route) is not None, route


def test_guide_only_h1_is_taxonomy_name():
    seen = set()
    for p in (q for c in catalog.CATALOG for q in c.patterns):
        if p.folder in H1_CHECK:
            first = (AGENTS / p.folder / "explanation.md").read_text().splitlines()[0]
            assert first == f"# {p.name}", p.folder
            seen.add(p.folder)
    assert seen == H1_CHECK


# folder -> routes that must appear as [[route]] markers inside "## How this graph works".
DIVIDING: dict[str, set[str]] = {
    "react_agent": {"execution/tool-use", "execution/autonomous"},
    "reflection_agent": {"governance/review"},
    "plan_execute_agent": {"execution/workflow"},
    "supervisor_agent": {"collaboration/hierarchy", "collaboration/swarm"},
    "swarm_agent": {"collaboration/supervisor"},
    "hierarchy_agent": {"collaboration/supervisor"},
    "episodic_memory_agent": {"memory/session"},
    "semantic_memory_agent": {"memory/knowledge-graph"},
    "knowledge_graph_agent": {"memory/semantic"},
    "routing_agent": {"collaboration/supervisor"},
    "workflow_agent": {"cognitive/planning"},
    "autonomous_agent": {"cognitive/react"},
    "review_agent": {"cognitive/reflection"},
    "audit_agent": {"governance/approval"},
}


@pytest.mark.parametrize("folder", sorted(DIVIDING))
def test_dividing_line_in_how_this_graph_works(folder):
    text = (AGENTS / folder / "explanation.md").read_text()
    section = text.split("## How this graph works", 1)[1].split("\n## ", 1)[0]
    assert set(re.findall(r"\[\[([^\]]+)\]\]", section)) >= DIVIDING[folder]
