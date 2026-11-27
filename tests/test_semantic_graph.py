"""The Semantic agent: ReAct over the library, with the first search of each question forced."""
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_solutions.agents.semantic_memory_agent.graph import EDGE_LABELS, MAX_TOOL_ROUNDS, NO_TOOLS, build_graph
from agentic_solutions.web.topology import graph_topology

pytestmark = pytest.mark.anyio


class FakeLibrary:
    def __init__(self):
        self.calls = []

    async def call(self, tool, args):
        self.calls.append((tool, args))
        return [{"book": "I", "start_line": 1, "end_line": 3, "text": "Of Man's first disobedience", "score": 0.5}]


class RecordingModel:
    """Returns queued replies and records the tool_choice each call was bound with."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.choices = []
        self._choice = None

    def bind_tools(self, tools, tool_choice=None, **_):
        bound = RecordingModel.__new__(RecordingModel)
        bound.__dict__ = self.__dict__.copy()
        bound._parent = self
        bound._choice = tool_choice
        return bound

    async def ainvoke(self, messages, config=None):
        parent = getattr(self, "_parent", self)
        parent.choices.append(self._choice)
        return parent.replies.pop(0)


def search_call(query="q", id_="c1"):
    return AIMessage("", tool_calls=[{"name": "search_book", "args": {"query": query}, "id": id_}])


async def start(model, library=None):
    library = library or FakeLibrary()
    g = build_graph(library=library, checkpointer=InMemorySaver(), llm_factory=lambda: model)
    cfg = {"configurable": {"thread_id": "t"}}
    await g.ainvoke({"messages": []}, cfg)
    return g, cfg, library


async def test_first_call_of_each_question_forces_search_book():
    model = RecordingModel([search_call(), AIMessage("Answer one (Book I, 1–3)."),
                            search_call(id_="c2"), AIMessage("Answer two (Book I, 1–3).")])
    g, cfg, library = await start(model)
    await g.ainvoke(Command(resume="Who tempts Eve?"), cfg)
    await g.ainvoke(Command(resume="What is the fruit?"), cfg)
    assert model.choices == ["search_book", None, "search_book", None]
    assert [t for t, _ in library.calls] == ["search_book", "search_book"]


async def test_model_ignoring_forced_choice_still_searches():  # Review Focus 4
    model = RecordingModel([AIMessage("I know this already."), AIMessage("From the passage (Book I, 1–3).")])
    g, cfg, library = await start(model)
    await g.ainvoke(Command(resume="How does the poem begin?"), cfg)
    assert [(t, a["query"]) for t, a in library.calls] == [("search_book", "How does the poem begin?")]
    assert len(model.choices) == 2
    messages = (await g.aget_state(cfg)).values["messages"]
    assert not any(m.type == "ai" and m.content == "I know this already." for m in messages)


async def test_round_cap_forces_text():
    replies = [search_call(id_=f"c{i}") for i in range(MAX_TOOL_ROUNDS)] + [AIMessage("Done (Book I, 1–3).")]
    model = RecordingModel(replies)
    g, cfg, _ = await start(model)
    await g.ainvoke(Command(resume="Tell me everything"), cfg)
    assert model.choices[0] == "search_book" and model.choices[-1] == NO_TOOLS
    assert len(model.choices) == MAX_TOOL_ROUNDS + 1


async def test_stop_and_empty_routing():
    g, cfg, _ = await start(RecordingModel([]))
    await g.ainvoke(Command(resume="   "), cfg)
    assert (await g.aget_state(cfg)).next == ("ask",)
    await g.ainvoke(Command(resume="stop"), cfg)
    assert (await g.aget_state(cfg)).next == ()


def test_edge_labels_cover_conditional_edges():
    t = graph_topology(build_graph(library=FakeLibrary()))
    conditional = {(e["source"], e["target"]) for e in t["edges"] if e["conditional"]}
    assert conditional == set(EDGE_LABELS)


async def test_round_zero_read_passage_is_replaced_by_the_search():  # review: forced search bypass
    read_first = AIMessage("", tool_calls=[{"name": "read_passage", "args": {"book": "I", "start_line": 1,
                                                                            "end_line": 5}, "id": "r1"}])
    model = RecordingModel([read_first, AIMessage("From the passage (Book I, 1–3).")])
    g, cfg, library = await start(model)
    await g.ainvoke(Command(resume="How does the poem begin?"), cfg)
    assert [t for t, _ in library.calls] == ["search_book"]


async def test_forced_search_ids_are_unique_per_question():  # review: repeated tool-call id
    model = RecordingModel([AIMessage("no"), AIMessage("Answer one."), AIMessage("no"), AIMessage("Answer two.")])
    g, cfg, _ = await start(model)
    await g.ainvoke(Command(resume="First question?"), cfg)
    await g.ainvoke(Command(resume="Second question?"), cfg)
    ids = [c["id"] for m in (await g.aget_state(cfg)).values["messages"] if m.type == "ai" for c in m.tool_calls]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_prompt_asks_for_a_short_answer_then_sources():
    from agentic_solutions.agents.semantic_memory_agent.graph import SYSTEM_PROMPT

    assert "simply and concisely" in SYSTEM_PROMPT
    assert "Sources:" in SYSTEM_PROMPT
    assert "at the end" in SYSTEM_PROMPT
    assert "two or three" in SYSTEM_PROMPT
    # Models miscount lines inside a passage: they must copy the tool's own range.
    assert "exactly as the tool returned" in SYSTEM_PROMPT and "count lines" in SYSTEM_PROMPT
