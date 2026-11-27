"""The Semantic agent: ReAct over the library, with the first search of each question forced."""
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import json

from agentic_solutions.agents.semantic_memory_agent.graph import (
    EDGE_LABELS, MAX_REWRITES, MAX_TOOL_ROUNDS, NO_TOOLS, build_graph)
from agentic_solutions.web.topology import graph_topology

pytestmark = pytest.mark.anyio


P = [{"book": "I", "start_line": n, "end_line": n + 2, "text": f"passage {n}", "score": 0.5} for n in (1, 4, 7)]


class FakeLibrary:
    def __init__(self, passages=None):
        self.calls = []
        self.passages = passages or [P[0]]

    async def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == "read_passage":
            return {"book": "I", "start_line": 1, "end_line": 3, "text": "Of Man's first disobedience"}
        return list(self.passages)


class RecordingModel:
    """Agent calls return queued `replies` and record their tool_choice in `choices`.

    Grader and rewriter calls (bound with tool_choice "grade_passages" or
    "rewrite_search") draw from their own queues and record in `helper_choices`.
    With no queued grade, every passage is graded relevant.
    """

    def __init__(self, replies, grades=(), rewrites=()):
        self.replies = list(replies)
        self.grades = list(grades)
        self.rewrites = list(rewrites)
        self.choices = []
        self.helper_choices = []
        self.grader_inputs = []
        self._choice = None

    def bind_tools(self, tools, tool_choice=None, **_):
        bound = RecordingModel.__new__(RecordingModel)
        bound.__dict__ = self.__dict__.copy()
        bound._parent = self
        bound._choice = tool_choice
        return bound

    async def ainvoke(self, messages, config=None):
        parent = getattr(self, "_parent", self)
        if self._choice == "grade_passages":
            parent.helper_choices.append(self._choice)
            parent.grader_inputs.append(messages[-1].content)
            if parent.grades:
                relevant = parent.grades.pop(0)
            else:
                relevant = list(range(1, messages[-1].content.count("\n[") + 1))
            return AIMessage("", tool_calls=[{"name": "grade_passages", "args": {"relevant": relevant}, "id": "g"}])
        if self._choice == "rewrite_search":
            parent.helper_choices.append(self._choice)
            return AIMessage("", tool_calls=[{"name": "rewrite_search", "args": {"query": parent.rewrites.pop(0)},
                                              "id": "r"}])
        parent.choices.append(self._choice)
        return parent.replies.pop(0)


def search_call(query="q", id_="c1"):
    return AIMessage("", tool_calls=[{"name": "search_book", "args": {"query": query}, "id": id_}])


async def start(model, library=None):  # noqa: D103
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



# ---------------------------------------------------------------- grader and rewriter

def last_tool_contents(messages):
    """The JSON contents of the tool messages that answer the last AI tool call."""
    calls = next(m for m in reversed(messages) if m.type == "ai" and m.tool_calls)
    ids = {c["id"] for c in calls.tool_calls}
    return [json.loads(m.content) for m in messages if m.type == "tool" and m.tool_call_id in ids]


async def test_grader_drops_irrelevant_passages():
    model = RecordingModel([search_call(), AIMessage("Answer.")], grades=[[2]])
    g, cfg, _ = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    messages = (await g.aget_state(cfg)).values["messages"]
    assert last_tool_contents(messages) == [{"passages": [P[1]], "not_relevant": 2}]
    assert model.helper_choices == ["grade_passages"]


async def test_none_relevant_rewrites_and_searches_again():
    model = RecordingModel([search_call(), AIMessage("Answer.")], grades=[[], [1]], rewrites=["new words"])
    g, cfg, library = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    assert [a["query"] for _, a in library.calls] == ["q", "new words"]
    messages = (await g.aget_state(cfg)).values["messages"]
    rewrite = [c for m in messages if m.type == "ai" for c in m.tool_calls][-1]
    assert rewrite["id"].startswith("rewrite-") and rewrite["args"]["query"] == "new words"
    assert model.helper_choices == ["grade_passages", "rewrite_search", "grade_passages"]


async def test_rewrite_cap():
    model = RecordingModel([search_call(), AIMessage("Nothing found.")], grades=[[], [], []],
                           rewrites=["second", "third"])
    g, cfg, library = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    assert len(library.calls) == 1 + MAX_REWRITES
    assert model.helper_choices.count("rewrite_search") == MAX_REWRITES
    assert last_tool_contents((await g.aget_state(cfg)).values["messages"]) == [{"passages": [], "not_relevant": 3}]


async def test_rewrite_same_query_still_counts():  # Review Focus 3
    model = RecordingModel([search_call(), AIMessage("Nothing found.")], grades=[[], [], []],
                           rewrites=["q", "q"])
    g, cfg, library = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    assert len(library.calls) == 1 + MAX_REWRITES


async def test_malformed_grade_passes_through():  # Review Focus 2
    model = RecordingModel([search_call(), AIMessage("Answer.")], grades=[[0, 7, 7]])
    g, cfg, _ = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    assert last_tool_contents((await g.aget_state(cfg)).values["messages"]) == [P]

    model = RecordingModel([search_call(), AIMessage("Answer.")], grades=[[0, 2, 2, 7]])
    g, cfg, _ = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    assert last_tool_contents((await g.aget_state(cfg)).values["messages"]) == [
        {"passages": [P[1]], "not_relevant": 2}]


async def test_read_passage_round_skips_grading():
    read = AIMessage("", tool_calls=[{"name": "read_passage", "args": {"book": "I", "start_line": 1, "end_line": 3},
                                      "id": "r1"}])
    model = RecordingModel([search_call(), read, AIMessage("Answer.")])
    g, cfg, _ = await start(model)
    await g.ainvoke(Command(resume="How does it begin?"), cfg)
    assert model.helper_choices == ["grade_passages"]  # the search round only


async def test_two_searches_one_relevant():  # Review Focus 1
    two = AIMessage("", tool_calls=[{"name": "search_book", "args": {"query": "a"}, "id": "s1"},
                                    {"name": "search_book", "args": {"query": "b"}, "id": "s2"}])
    model = RecordingModel([two, AIMessage("Answer.")], grades=[[2]])
    g, cfg, _ = await start(model)  # each search returns one passage: [1] from s1, [2] from s2
    await g.ainvoke(Command(resume="Which?"), cfg)
    assert last_tool_contents((await g.aget_state(cfg)).values["messages"]) == [
        {"passages": [], "not_relevant": 1}, {"passages": [P[0]], "not_relevant": 0}]
    assert "rewrite_search" not in model.helper_choices


async def test_round_cap_holds_across_rewrites():  # Review Focus 4
    replies = [search_call(id_=f"c{i}") for i in range(MAX_TOOL_ROUNDS - 1)] + [AIMessage("Done.")]
    grades = [[1]] * (MAX_TOOL_ROUNDS - 2) + [[], [1]]
    model = RecordingModel(replies, grades=grades, rewrites=["late rewrite"])
    g, cfg, _ = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Tell me everything"), cfg)
    assert model.choices[-1] == NO_TOOLS  # the rewrite took the sixth round


async def test_counters_reset_per_question():
    model = RecordingModel([search_call(), AIMessage("One."), search_call(id_="c2"), AIMessage("Two.")],
                           grades=[[], [1], [], [1]], rewrites=["r1", "r2"])
    g, cfg, library = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="First?"), cfg)
    await g.ainvoke(Command(resume="Second?"), cfg)
    assert [a["query"] for _, a in library.calls] == ["q", "r1", "q", "r2"]


async def test_grader_sees_numbered_passages_with_their_position():
    model = RecordingModel([search_call(), AIMessage("Answer.")])
    g, cfg, _ = await start(model, FakeLibrary(P))
    await g.ainvoke(Command(resume="Which passage?"), cfg)
    text = model.grader_inputs[0]
    assert text.startswith("Question: Which passage?") and "[3] Book I, 7–9:" in text
