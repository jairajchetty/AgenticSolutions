"""The pattern catalog: the single source of truth for the Studio's taxonomy.

Five categories hold 21 patterns. Each entry is plain data; whether a pattern is
"live" or "guide" is never stored. It is derived from the web registry, so when a
later milestone registers a demo id this module already names, the entry turns
live with no edit here.

`execution/tool-use` is a cross-list: it has no page of its own and borrows
`cognitive/react` (its `crosslist_of`), including its status.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CatalogPattern:
    id: str
    category: str
    name: str
    hint: str
    aliases: tuple[str, ...]
    demo: str | None  # registry PatternSpec id (possibly not yet registered), else None
    crosslist_of: str | None  # route of the canonical page for cross-lists, else None
    folder: str | None  # agent folder holding explanation.md (+ skeleton); None for cross-lists

    @property
    def route(self) -> str:
        return f"{self.category}/{self.id}"


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    question: str
    patterns: tuple[CatalogPattern, ...]


def _p(category, id, name, hint, aliases, demo, folder, crosslist_of=None):
    return CatalogPattern(id, category, name, hint, tuple(aliases), demo, crosslist_of, folder)


CATALOG: tuple[Category, ...] = (
    Category(
        'cognitive',
        'Cognitive',
        'How should the agent think?',
        (
            _p('cognitive', 'react', 'ReAct', 'Reason and call tools in a loop',
               ('reason act', 'tool loop', 'agent loop'), 'react', 'react_agent'),
            _p('cognitive', 'reflection', 'Reflection', 'Critique and revise its own output',
               ('self-critique', 'evaluator-optimizer', 'self-refine'), 'reflection', 'reflection_agent'),
            _p('cognitive', 'planning', 'Planning', 'Break a goal into steps before acting',
               ('plan-and-execute', 'task decomposition'), 'plan_execute', 'plan_execute_agent'),
            _p('cognitive', 'search', 'Search', 'Explore several paths and keep the best',
               ('tree of thoughts', 'LATS', 'beam search', 'MCTS'), None, 'search_agent'),
        ),
    ),
    Category(
        'collaboration',
        'Collaboration',
        'How many agents, and who leads?',
        (
            _p('collaboration', 'single-agent', 'Single Agent', 'One model handles the whole task',
               ('single LLM call', 'baseline', 'one-shot'), 'qa', 'qa_agent'),
            _p('collaboration', 'supervisor', 'Supervisor', 'A coordinator delegates to specialists',
               ('orchestrator-workers', 'manager', 'delegation'), None, 'supervisor_agent'),
            _p('collaboration', 'swarm', 'Swarm', 'Peers hand work to each other directly',
               ('handoffs', 'peer-to-peer', 'network'), None, 'swarm_agent'),
            _p('collaboration', 'hierarchy', 'Hierarchy', 'Teams of agents led by supervisors',
               ('hierarchical teams', 'nested supervisors'), None, 'hierarchy_agent'),
        ),
    ),
    Category(
        'memory',
        'Memory',
        'What must it remember?',
        (
            _p('memory', 'session', 'Session', 'Remember the current conversation',
               ('short-term memory', 'thread', 'conversation history', 'checkpointer'), 'chat_loop', 'chat_agent'),
            _p('memory', 'episodic', 'Episodic', 'Recall past interactions with this user',
               ('long-term memory', 'user memory', 'experiences'), None, 'episodic_memory_agent'),
            _p('memory', 'semantic', 'Semantic', 'Look up facts from a document store',
               ('RAG', 'retrieval', 'vector search', 'knowledge base'), None, 'semantic_memory_agent'),
            _p('memory', 'knowledge-graph', 'Knowledge Graph', 'Reason over entities and relationships',
               ('graph RAG', 'entity memory', 'ontology'), None, 'knowledge_graph_agent'),
        ),
    ),
    Category(
        'execution',
        'Execution',
        'How does it act and run?',
        (
            _p('execution', 'tool-use', 'Tool Use', 'Call functions and APIs',
               ('function calling', 'tools', 'actions'), None, None, crosslist_of="cognitive/react"),
            _p('execution', 'routing', 'Routing', 'Send each request to the right specialist',
               ('router', 'classifier', 'intent routing', 'dispatch'), None, 'routing_agent'),
            _p('execution', 'workflow', 'Workflow', 'Run fixed steps defined in code',
               ('pipeline', 'prompt chaining', 'DAG'), None, 'workflow_agent'),
            _p('execution', 'event-driven', 'Event Driven', 'Start agents from events, queues or schedules',
               ('triggers', 'webhooks', 'background agents', 'cron'), None, 'event_driven_agent'),
            _p('execution', 'autonomous', 'Autonomous', 'Work on its own for a long time until a goal is met',
               ('long-running', 'self-directed', 'background agent'), None, 'autonomous_agent'),
        ),
    ),
    Category(
        'governance',
        'Governance',
        'How is it kept safe and accountable?',
        (
            _p('governance', 'guardrails', 'Guardrails', 'Screen inputs and outputs for unsafe content',
               ('input filter', 'prompt injection', 'safety screen'), 'guardrail', 'secure_chat_agent'),
            _p('governance', 'approval', 'Approval', 'Pause for a human to sign off',
               ('human-in-the-loop', 'HITL', 'interrupt', 'sign-off'), 'human_in_loop', 'interrupt_chat_agent'),
            _p('governance', 'audit', 'Audit', 'Keep persistent, queryable records of every run',
               ('logging', 'traceability', 'run history', 'compliance'), None, 'audit_agent'),
            _p('governance', 'review', 'Review', 'Have a separate agent or a person check the result',
               ('peer review', 'critic agent', 'second opinion'), None, 'review_agent'),
        ),
    ),
)

_BY_ROUTE = {p.route: p for k in CATALOG for p in k.patterns}


def entry(route: str) -> CatalogPattern | None:
    return _BY_ROUTE.get(route)


def target(p: CatalogPattern) -> CatalogPattern:
    """The canonical page for `p`: itself, or (one hop) the pattern it cross-lists."""
    return _BY_ROUTE[p.crosslist_of] if p.crosslist_of else p


def status(p: CatalogPattern, live_ids: Collection[str]) -> Literal["live", "guide"]:
    demo = target(p).demo
    return "live" if demo is not None and demo in live_ids else "guide"


def neighbours(route: str) -> tuple[str, str]:
    """Previous and next routes within the route's own category, wrapping around."""
    category, _, _ = route.partition("/")
    routes = [p.route for k in CATALOG if k.id == category for p in k.patterns]
    i = routes.index(route)
    return routes[i - 1], routes[(i + 1) % len(routes)]
