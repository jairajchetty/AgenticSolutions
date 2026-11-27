import importlib
import re

import pytest

from agentic_solutions.web import catalog
from guide_format import (
    AGENTS, ALL_FOLDERS, DENY_SUBSTRINGS, DENY_WORDS, SECTIONS, STUDIO_SUBSECTIONS,
    generic_text, sections, studio_section, subsections,
)
from test_skeletons import SKELETONS

GUIDES = sorted(AGENTS.glob("*/explanation.md"))
# Folders whose H1 must equal the taxonomy name: every catalog entry that has a folder.
H1_CHECK = {p.folder for c in catalog.CATALOG for p in c.patterns if p.folder}


def test_guides_are_found():
    # An empty glob would make every parametrized guide test vanish silently.
    assert len(GUIDES) >= 20, AGENTS


def ids(paths):
    return [p.parent.name for p in paths]


def guide(folder):
    return (AGENTS / folder / "explanation.md").read_text()


def first_fence_lines(text):
    m = re.search(r"```[^\n]*\n(.*?)```", text, re.S)
    assert m, "no fenced block under Key code"
    return len(m.group(1).splitlines())


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_new_format_sections_in_order(folder):
    secs = sections(guide(folder))
    assert [t for t, _ in secs] == SECTIONS
    assert [t for t, _ in subsections(secs[6][1])] == STUDIO_SUBSECTIONS


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_generic_sections_have_no_framework_vocabulary(folder):
    text = generic_text(guide(folder))
    assert "`" not in text
    for w in DENY_WORDS:
        assert not re.search(rf"\b{re.escape(w)}s?\b", text, re.I), w
    for sub in DENY_SUBSTRINGS:
        assert sub.lower() not in text.lower(), sub


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_studio_section_starts_with_mapping(folder):
    # guide.js drops any text before the first "###" of section 7 without a warning.
    assert studio_section(guide(folder)).lstrip().startswith("### Mapping")


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_when_to_use_has_a_not_when_bullet(folder):
    body = dict(sections(guide(folder)))["When to use it"]
    assert re.search(r"^\s*[-*]\s+(\*\*)?not when\b", body, re.I | re.M)


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_design_considerations_bullets_start_bold(folder):
    body = dict(sections(guide(folder)))["Design considerations"]
    bullets = re.findall(r"^[-*] (.*)$", body, re.M)
    assert bullets
    assert all(b.startswith("**") for b in bullets), bullets


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_mapping_names_every_node(folder):
    mapping = dict(subsections(studio_section(guide(folder))))["Mapping"]
    nodes = {n["id"] for n in node_topology(folder)["nodes"]} - {"__start__", "__end__"}
    assert nodes
    missing = {n for n in nodes if not re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", mapping)}
    assert not missing, missing


def node_topology(folder):
    from langgraph.checkpoint.memory import InMemorySaver

    from agentic_solutions.web.registry import PATTERNS, BuildContext, offline_factory
    from agentic_solutions.web.topology import graph_topology
    from fakes import make_guard

    if folder in SKELETONS:
        mod = importlib.import_module(f"agentic_solutions.agents.{folder}.graph")
        return graph_topology(mod.build_skeleton())
    for pid, spec in PATTERNS.items():
        if spec.explanation_path.parent.name == folder:
            ctx = BuildContext(offline_factory(pid, 0), InMemorySaver(), make_guard())
            return graph_topology(spec.build(ctx))
    raise AssertionError(f"no graph for {folder}")


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_key_code_at_most_25_lines(folder):
    sub = dict(subsections(studio_section(guide(folder))))["Key code"]
    assert first_fence_lines(sub) <= 25


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_skeleton_word_only_in_studio_section(folder):
    assert "skeleton" not in generic_text(guide(folder)).lower()


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_new_length_50_to_130_lines(folder):
    assert 50 <= len(guide(folder).splitlines()) <= 130


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


# folder -> routes that must appear as [[route]] markers inside "## Related patterns".
DIVIDING: dict[str, set[str]] = {
    "qa_agent": {"collaboration/supervisor", "collaboration/swarm", "collaboration/hierarchy"},
    "chat_agent": {"memory/episodic"},
    "interrupt_chat_agent": {"governance/review"},
    "secure_chat_agent": {"governance/review"},
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
def test_dividing_line_in_the_right_section(folder):
    text = dict(sections(guide(folder)))["Related patterns"]
    assert set(re.findall(r"\[\[([^\]]+)\]\]", text)) >= DIVIDING[folder]
