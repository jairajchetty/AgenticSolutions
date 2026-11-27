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
    "memory/semantic": ('Semantic', 'Look up facts from a document store', ('RAG', 'retrieval', 'vector search', 'knowledge base')),
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


def test_categories_in_order_with_questions():
    assert [(k.id, k.name, k.question) for k in c.CATALOG] == [
        ("cognitive", "Cognitive", "How should the agent think?"),
        ("collaboration", "Collaboration", "How many agents, and who leads?"),
        ("memory", "Memory", "What must it remember?"),
        ("execution", "Execution", "How does it act and run?"),
        ("governance", "Governance", "How is it kept safe and accountable?")]


def test_twenty_one_patterns_in_spec_order():
    assert [p.route for k in c.CATALOG for p in k.patterns] == [
        "cognitive/react", "cognitive/reflection", "cognitive/planning", "cognitive/search",
        "collaboration/single-agent", "collaboration/supervisor", "collaboration/swarm", "collaboration/hierarchy",
        "memory/session", "memory/episodic", "memory/semantic", "memory/knowledge-graph",
        "execution/tool-use", "execution/routing", "execution/workflow", "execution/event-driven", "execution/autonomous",
        "governance/guardrails", "governance/approval", "governance/audit", "governance/review"]


def test_hints_and_aliases_match_spec():
    for k in c.CATALOG:
        for p in k.patterns:
            assert (p.name, p.hint, p.aliases) == EXPECTED[p.route], p.route


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
