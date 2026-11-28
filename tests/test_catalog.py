import pytest

from agentic_solutions.web import catalog as c
from agentic_solutions.web.registry import PATTERNS

EXPECTED = {
    "cognitive/react": ('ReAct', 'Reason and call tools in a loop', ('reason act', 'tool loop', 'agent loop')),
    "cognitive/reflection": ('Reflection', 'Critique and revise its own output', ('self-critique', 'evaluator-optimizer', 'self-refine')),
    "cognitive/planning": ('Planning', 'Break a goal into steps before acting', ('plan-and-execute', 'task decomposition')),
    "cognitive/search": ('Search', 'Explore several paths and keep the best', ('tree of thoughts', 'LATS', 'beam search', 'MCTS')),
    "collaboration/single-agent": ('Single Agent', 'One model handles the whole task', ('single LLM call', 'baseline', 'one-shot')),
    "collaboration/supervisor": ('Supervisor', 'A coordinator delegates to specialists', ('orchestrator-workers', 'manager', 'delegation')),
    "collaboration/swarm": ('Swarm', 'Peers hand work to each other directly', ('handoffs', 'peer-to-peer', 'network')),
    "collaboration/hierarchy": ('Hierarchy', 'Teams of agents led by supervisors', ('hierarchical teams', 'nested supervisors')),
    "memory/session": ('Session', 'Remember the current conversation', ('short-term memory', 'thread', 'conversation history', 'checkpointer')),
    "memory/episodic": ('Episodic', 'Recall past interactions with this user', ('long-term memory', 'user memory', 'experiences')),
    "memory/rag": ('Retrieval Augmented Generation (RAG)', 'Look up facts from a document store', ('RAG', 'retrieval', 'vector search', 'knowledge base')),
    "memory/knowledge-graph": ('Knowledge Graph', 'Reason over entities and relationships', ('graph RAG', 'entity memory', 'ontology')),
    "execution/tool-use": ('Tool Use', 'Call functions and APIs', ('function calling', 'tools', 'actions')),
    "execution/routing": ('Routing', 'Send each request to the right specialist', ('router', 'classifier', 'intent routing', 'dispatch')),
    "execution/workflow": ('Workflow', 'Run fixed steps defined in code', ('pipeline', 'prompt chaining', 'DAG')),
    "execution/event-driven": ('Event Driven', 'Start agents from events, queues or schedules', ('triggers', 'webhooks', 'background agents', 'cron')),
    "execution/autonomous": ('Autonomous', 'Work on its own for a long time until a goal is met', ('long-running', 'self-directed', 'background agent')),
    "governance/guardrails": ('Guardrails', 'Screen inputs and outputs for unsafe content', ('input filter', 'prompt injection', 'safety screen')),
    "governance/approval": ('Approval', 'Pause for a human to sign off', ('human-in-the-loop', 'HITL', 'interrupt', 'sign-off')),
    "governance/audit": ('Audit', 'Keep persistent, queryable records of every run', ('logging', 'traceability', 'run history', 'compliance')),
    "governance/review": ('Review', 'Have a separate agent or a person check the result', ('peer review', 'critic agent', 'second opinion')),
}


def test_categories_in_order_with_descriptions():
    assert [(k.id, k.name, k.description) for k in c.CATALOG] == [
        ("cognitive", "Cognitive", "How should the agent think?"),
        ("collaboration", "Collaboration", "How many agents, and who leads?"),
        ("memory", "Memory", "What must it remember?"),
        ("execution", "Execution", "How does it act and run?"),
        ("governance", "Governance", "How is it kept safe and accountable?")]


def test_twenty_one_patterns_in_spec_order():
    assert [p.route for k in c.CATALOG for p in k.patterns] == [
        "cognitive/react", "cognitive/reflection", "cognitive/planning", "cognitive/search",
        "collaboration/single-agent", "collaboration/supervisor", "collaboration/swarm", "collaboration/hierarchy",
        "memory/session", "memory/episodic", "memory/rag", "memory/knowledge-graph",
        "execution/tool-use", "execution/routing", "execution/workflow", "execution/event-driven", "execution/autonomous",
        "governance/guardrails", "governance/approval", "governance/audit", "governance/review"]


def test_descriptions_and_aliases_match_spec():
    for k in c.CATALOG:
        for p in k.patterns:
            assert (p.name, p.description, p.aliases) == EXPECTED[p.route], p.route


def test_every_registered_demo_is_reachable_exactly_once():
    demos = [p.demo for k in c.CATALOG for p in k.patterns if p.demo and not p.crosslist_of]
    assert sorted(set(PATTERNS) & set(demos)) == sorted(PATTERNS) and len(demos) == len(set(demos))


def test_demo_folder_and_crosslist_values():
    got = {p.route: (p.demo, p.folder, p.crosslist_of) for k in c.CATALOG for p in k.patterns}
    assert got["cognitive/react"] == ("react", "react_agent", None)
    assert got["cognitive/planning"] == ("plan_execute", "plan_execute_agent", None)
    assert got["governance/approval"] == ("approval", "approval_agent", None)
    assert got["execution/tool-use"] == (None, None, "cognitive/react")
    assert got["governance/review"] == (None, "review_agent", None)
    assert sum(1 for v in got.values() if v[2]) == 1


def test_tool_use_crosslists_react_and_follows_its_status():
    tool = c.entry("execution/tool-use")
    assert c.target(tool).route == "cognitive/react"
    assert c.status(tool, live_ids={"qa"}) == "guide"
    assert c.status(tool, live_ids={"react"}) == "live"


def test_status_live_only_when_demo_registered():
    assert c.status(c.entry("governance/approval"), PATTERNS) == "live"
    assert c.status(c.entry("cognitive/reflection"), PATTERNS) == "guide"


def test_neighbours_wrap_within_category():
    assert c.neighbours("execution/tool-use") == ("execution/autonomous", "execution/routing")
    assert c.neighbours("governance/review") == ("governance/audit", "governance/guardrails")


def test_unknown_route_is_none():
    assert c.entry("memory/nope") is None and c.entry("nonsense") is None


def test_catalog_approval_points_at_approval_demo():
    approval = c.entry("governance/approval")
    assert (approval.demo, approval.folder) == ("approval", "approval_agent")
    assert approval.aliases == ('human-in-the-loop', 'HITL', 'interrupt', 'sign-off')
    assert c.status(approval, PATTERNS) == "live"
    assert "human_in_loop" not in PATTERNS


SIMPLE = {"cognitive/react", "collaboration/single-agent", "memory/session", "execution/tool-use",
          "execution/routing", "execution/workflow", "governance/audit"}


def test_composite_is_derived_from_builds_on():
    routes = {p.route: p for k in c.CATALOG for p in k.patterns}
    assert {r for r, p in routes.items() if not p.composite} == SIMPLE
    assert routes["governance/approval"].builds_on == (
        "memory/session", "cognitive/react", "execution/tool-use", "execution/routing", "governance/audit")
    assert routes["collaboration/hierarchy"].builds_on == ("collaboration/supervisor",)


# ---- the loader's startup checks, on small files ----------------------------

MINI = """\
categories:
  - id: gov
    name: Governance
    description: Kept safe?
    patterns:
      - id: log
        name: Log
        description: Keep records
        folder: log_agent
      - id: ok
        name: OK
        description: Approve things
        aliases: [sign-off]
        folder: ok_agent
        builds_on: [gov/log]
"""


def write(tmp_path, text):
    p = tmp_path / "catalog.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def fails(tmp_path, text, match):
    with pytest.raises(c.CatalogError, match=match):
        c.load_catalog(write(tmp_path, text))


def test_loads_minimal_file(tmp_path):
    (cat,) = c.load_catalog(write(tmp_path, MINI))
    assert cat.description == "Kept safe?"
    assert [p.composite for p in cat.patterns] == [False, True]
    assert cat.patterns[1].aliases == ("sign-off",) and cat.patterns[0].aliases == ()


def test_unknown_builds_on_route_fails(tmp_path):  # Review Focus 1
    fails(tmp_path, MINI.replace("builds_on: [gov/log]", "builds_on: [log]"), r"gov/ok.*log")


def test_duplicate_builds_on_fails(tmp_path):  # Review Focus 2
    fails(tmp_path, MINI.replace("builds_on: [gov/log]", "builds_on: [gov/log, gov/log]"), r"gov/ok.*gov/log")


def test_builds_on_and_aliases_must_be_lists(tmp_path):  # Review Focus 3
    fails(tmp_path, MINI.replace("builds_on: [gov/log]", "builds_on: gov/log"), "builds_on")
    fails(tmp_path, MINI.replace("aliases: [sign-off]", "aliases: a, b"), "aliases")


def test_self_and_cycle_fail(tmp_path):
    fails(tmp_path, MINI.replace("builds_on: [gov/log]", "builds_on: [gov/ok]"), "cycle")
    looped = MINI.replace("        folder: log_agent\n", "        folder: log_agent\n        builds_on: [gov/ok]\n")
    fails(tmp_path, looped, "cycle")


def test_duplicate_route_fails(tmp_path):
    fails(tmp_path, MINI.replace("- id: ok", "- id: log"), "gov/log")


def test_missing_or_empty_required_field_fails(tmp_path):
    fails(tmp_path, MINI.replace("description: Approve things", "description: ''"), "description")
    fails(tmp_path, MINI.replace("        name: OK\n", ""), "name")


def test_folder_xor_crosslist(tmp_path):
    fails(tmp_path, MINI.replace("folder: ok_agent", "folder: ok_agent\n        crosslist_of: gov/log"), "gov/ok")
    fails(tmp_path, MINI.replace("        folder: ok_agent\n", ""), "gov/ok")


def test_unknown_crosslist_target_fails(tmp_path):
    fails(tmp_path, MINI.replace("folder: log_agent", "crosslist_of: gov/nope"), "gov/nope")


def test_category_without_composite_fails(tmp_path):
    fails(tmp_path, MINI.replace("        builds_on: [gov/log]\n", ""), "gov")


def test_invalid_yaml_fails_with_file_name(tmp_path):
    fails(tmp_path, MINI.replace("      - id: log", "\t- id: log"), "catalog.yaml")


def test_unknown_keys_fail(tmp_path):  # review: a misspelt builds_on would turn a composite simple
    fails(tmp_path, MINI.replace("builds_on: [gov/log]", "buildson: [gov/log]"), r"gov/ok.*buildson")
    fails(tmp_path, MINI.replace("    description: Kept safe?", "    descrption: x\n    description: Kept safe?"), r"gov.*descrption")
    fails(tmp_path, "colours: []\n" + MINI, "colours")


def test_crosslist_must_point_at_a_page(tmp_path):  # review: chains crashed startup without naming the entry
    chained = MINI.replace("      - id: ok", """      - id: x
        name: X
        description: Cross-list
        crosslist_of: gov/y
      - id: y
        name: Y
        description: Cross-list
        crosslist_of: gov/log
      - id: ok""")
    fails(tmp_path, chained, r"gov/x.*gov/y")
    fails(tmp_path, MINI.replace("folder: log_agent", "crosslist_of: gov/log"), "gov/log")


def test_use_case_is_optional_and_keeps_paragraphs(tmp_path):
    text = MINI.replace("        aliases: [sign-off]\n",
                        "        aliases: [sign-off]\n        use_case: |\n          First paragraph.\n\n          Second paragraph.\n")
    (cat,) = c.load_catalog(write(tmp_path, text))
    assert cat.patterns[1].use_case == "First paragraph.\n\nSecond paragraph."
    assert cat.patterns[0].use_case is None


def test_empty_use_case_fails(tmp_path):
    fails(tmp_path, MINI.replace("        aliases: [sign-off]\n", "        aliases: [sign-off]\n        use_case: ''\n"),
          "use_case")


def test_rag_name_matches_everywhere_it_is_written():
    from pathlib import Path

    assert c.entry("memory/rag").name == "Retrieval Augmented Generation (RAG)"
    guide = Path("src/agentic_solutions/agents/rag_agent/explanation.md").read_text()
    assert guide.startswith("# Retrieval Augmented Generation (RAG)\n")
    assert "The Retrieval Augmented Generation (RAG) pattern" in guide
