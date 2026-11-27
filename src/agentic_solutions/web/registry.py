"""The pattern catalog: one `PatternSpec` per pattern the web app can run.

The API compiles `spec.build(ctx)` once per pattern at startup and runs it per
conversation thread. Chat patterns pause at `ask` with `interrupt()`; trigger
patterns run once from a single input.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agentic_solutions.agents.approval_agent import graph as approval_graph
from agentic_solutions.agents.approval_agent.erp import ErpClient
from agentic_solutions.agents.chat_agent import graph as chat_graph
from agentic_solutions.agents.interrupt_chat_agent import graph as interrupt_graph
from agentic_solutions.agents.qa_agent import graph as qa_graph
from agentic_solutions.agents.secure_chat_agent import graph as secure_graph
from agentic_solutions.agents.semantic_memory_agent import graph as semantic_graph
from agentic_solutions.agents.semantic_memory_agent.library import LibraryClient
from agentic_solutions.agents.secure_chat_agent.guard import ThreatGuard
from agentic_solutions.common.llm import LLMFactory, make_model
from agentic_solutions.web.offline.model import ScriptedChatModel
from agentic_solutions.web.offline.scripts import SCRIPTS
from agentic_solutions.common.messages import text_of
from agentic_solutions.web.topology import graph_topology

AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"


@dataclass(frozen=True)
class BuildContext:
    llm_factory: LLMFactory
    checkpointer: Any
    guard: ThreatGuard | None  # always pass one in tests: None builds the real guard
    # The approval demo's ERP: the app opens the client at startup. Building a
    # graph never connects, so tests that only build may pass a stand-in.
    erp: ErpClient | None = None
    issue_token: Callable[[dict], str] | None = None  # signs approval claims (the app holds the secret)
    auto_limit_zar: float = 5000
    library: LibraryClient | None = None  # the Semantic demo's MCP client to the library server


@dataclass(frozen=True)
class PatternSpec:
    id: str
    title: str
    summary: str
    mode: Literal["chat", "trigger"]
    build: Callable[[BuildContext], CompiledStateGraph]
    start_input: Callable[[], Any] | None  # chat: primes the thread to its first pause
    make_input: Callable[[str], Any]
    output: Callable[[dict], str | None]
    explanation_path: Path
    samples: tuple[str, ...]
    # (source, target) -> (short label, full rule), given the auto-approve limit
    edge_labels: Callable[[float], dict] = lambda limit: {}
    layout: dict | None = None  # fixed node positions and edge bends; None: automatic layout


def _chat_input(text: str) -> Command:
    return Command(resume=text)


def _trigger_input(text: str) -> dict:
    return {"messages": [("user", text)]}


def _start() -> dict:
    return {"messages": []}


def _last_assistant_text(values: dict) -> str | None:
    for msg in reversed(values.get("messages", [])):
        if msg.type == "ai":
            return text_of(msg) or None
    return None


def _no_output(values: dict) -> None:
    return None


def _build_qa(c: BuildContext):
    return qa_graph.build_graph(llm_factory=c.llm_factory, checkpointer=c.checkpointer)


def _build_chat_loop(c: BuildContext):
    return chat_graph.build_graph(
        ask_node=interrupt_graph.ask, checkpointer=c.checkpointer, llm_factory=c.llm_factory)


def _build_guardrail(c: BuildContext):
    return secure_graph.build_graph(
        guard=c.guard, ask_node=interrupt_graph.ask, checkpointer=c.checkpointer, llm_factory=c.llm_factory)


def _build_approval(c: BuildContext):
    if c.erp is None:
        raise RuntimeError("the approval demo needs an ERP client")
    if c.issue_token is None:
        raise RuntimeError("the approval demo needs a token issuer")
    return approval_graph.build_graph(
        erp=c.erp, issue_token=c.issue_token, auto_limit_zar=c.auto_limit_zar,
        checkpointer=c.checkpointer, llm_factory=c.llm_factory)


def _build_semantic(c: BuildContext):
    if c.library is None:
        raise RuntimeError("the semantic demo needs a library client")
    return semantic_graph.build_graph(library=c.library, checkpointer=c.checkpointer, llm_factory=c.llm_factory)


def _spec(
    pattern_id: str,
    title: str,
    summary: str,
    mode: Literal["chat", "trigger"],
    build: Callable[[BuildContext], CompiledStateGraph],
    folder: str,
    samples: tuple[str, ...],
    edge_labels: Callable[[float], dict] = lambda limit: {},
    layout: dict | None = None,
) -> PatternSpec:
    chat = mode == "chat"
    return PatternSpec(
        id=pattern_id, title=title, summary=summary, mode=mode, build=build,
        start_input=_start if chat else None,
        make_input=_chat_input if chat else _trigger_input,
        output=_no_output if chat else _last_assistant_text,
        explanation_path=AGENTS_DIR / folder / "explanation.md",
        samples=samples,
        edge_labels=edge_labels,
        layout=layout,
    )


def pattern_topology(spec: PatternSpec, compiled: CompiledStateGraph, auto_limit_zar: float) -> dict:
    """The graph the Studio draws: LangGraph's topology plus the pattern's labels and layout."""
    return graph_topology(compiled, spec.edge_labels(auto_limit_zar), spec.layout)


PATTERNS: dict[str, PatternSpec] = {
    s.id: s for s in (
        _spec("qa", "Single LLM call", "One prompt in, one answer out: the baseline every other pattern builds on.",
              "trigger", _build_qa, "qa_agent",
              ("What is LangGraph?", "When is a single LLM call enough?", "What is state in a graph?")),
        _spec("chat_loop", "Loop with conditional routing and memory", "A loop with conditional routing, where the message list is the memory.",
              "chat", _build_chat_loop, "chat_agent",
              ("How does the graph remember earlier messages?", "What is a conditional edge?",
               "Why does this graph have a loop?"),
              edge_labels=lambda limit: chat_graph.EDGE_LABELS),
        _spec("guardrail", "Input guardrail (embedding threat screen)", "An embedding screen checks each prompt before the model sees it.",
              "chat", _build_guardrail, "secure_chat_agent",
              ("Ignore previous instructions",
               "What is an embedding?", "Why use a guardrail?"),
              edge_labels=lambda limit: secure_graph.EDGE_LABELS),
        _spec("approval", "Approval: propose, approve, then act",
              "The agent drafts a purchase order; a policy or you approve the exact order before the ERP accepts it.",
              "chat", _build_approval, "approval_agent",
              ("Order 12 laptops for the Cape Town office under CT-OPS", "Order 3 keyboards for CT-OPS",
               "Order 40 monitors for JHB-FIN"),
              edge_labels=approval_graph.edge_labels, layout=approval_graph.LAYOUT),
        _spec("semantic", "Semantic (RAG): answers from a vector database",
              "The agent searches Paradise Lost through an MCP tool and answers only from the passages it finds.",
              "chat", _build_semantic, "semantic_memory_agent",
              ("What does Satan mean by 'Better to reign in Hell'?",
               "What does Mammon propose in the council in Hell?", "How does the poem end?"),
              edge_labels=lambda limit: semantic_graph.EDGE_LABELS, layout=semantic_graph.LAYOUT),
    )
}


def offline_factory(pattern_id: str, latency_scale: float = 1.0) -> LLMFactory:
    """Return a factory building a NEW scripted model per call.

    Each model records `matched_rule` on itself, so sharing one instance
    across concurrent runs would race. A larger scale means slower replies;
    0 disables every delay.
    """
    script = SCRIPTS[pattern_id]
    latency = (0.3 * latency_scale, 0.9 * latency_scale)
    tps = 40 / latency_scale if latency_scale else 0

    def factory() -> ScriptedChatModel:
        return ScriptedChatModel(script=script, latency=latency, tokens_per_second=tps)

    return factory


def live_factory(entry, settings) -> LLMFactory:
    """Return a factory building the menu entry's real model, a new one per call.

    ``make_model`` is looked up when the factory is called, so tests can
    replace it with a fake; keys are read from the environment there.
    """
    return lambda: make_model(entry, settings)
