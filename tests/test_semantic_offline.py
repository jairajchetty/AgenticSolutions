"""The Semantic demo on the offline (scripted) model, against the real text.

The index uses the fake embedder (exact words), so these runs are fast and need
no model download. Citations must exist in the text and contain what they quote.
"""
import re

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_solutions.agents.semantic_memory_agent.library import InProcessLibraryClient
from agentic_solutions.mcp_servers.library.server import build_server
from agentic_solutions.mcp_servers.library.text import TEXT_PATH, parse_text
from agentic_solutions.web.offline.scripts import OFFLINE_NOTE
from agentic_solutions.web.registry import PATTERNS, BuildContext, offline_factory
from fakes import make_guard

pytestmark = pytest.mark.anyio

BOOKS = {b.numeral: b for b in parse_text(TEXT_PATH.read_text(encoding="utf-8"))}
SOURCE = re.compile(r"^- Book ([IVX]+), (\d+)–(\d+): “([^”]+)”$", re.M)
QUOTE = re.compile(r"“([^”]+)”")
MAX_ANSWER_WORDS = 40


@pytest.fixture
async def run(library_index):
    async with InProcessLibraryClient(build_server(library_index)) as client:
        spec = PATTERNS["semantic"]
        graph = spec.build(BuildContext(offline_factory("semantic", 0), InMemorySaver(), make_guard(),
                                        library=client))

        async def ask(question, with_nodes=False):
            cfg = {"configurable": {"thread_id": question[:40]}}
            await graph.ainvoke(spec.start_input(), cfg)
            nodes = []
            async for update in graph.astream(Command(resume=question), cfg, stream_mode="updates"):
                nodes += [name for name in update if not name.startswith("__")]
            messages = (await graph.aget_state(cfg)).values["messages"]
            return (messages, nodes) if with_nodes else messages

        yield ask


def tool_calls(messages):
    return [c for m in messages if m.type == "ai" for c in m.tool_calls]


def split_answer(answer):
    """(the short answer, the Sources list). The offline note is not part of either."""
    text = answer.replace(OFFLINE_NOTE, "").strip()
    assert "\n\nSources:\n" in text, answer
    body, sources = text.split("\n\nSources:\n", 1)
    return body.strip(), sources.strip()


def check_citations(answer):
    body, sources = split_answer(answer)
    # A simple, concise answer, with every source at the end and none in the text.
    assert len(body.split()) <= MAX_ANSWER_WORDS, body
    assert "Book " not in body and "“" not in body, body
    cited = SOURCE.findall(sources)
    assert cited and len(cited) == len(sources.splitlines()), sources
    for book, a, b, quote in cited:
        a, b = int(a), int(b)
        assert book in BOOKS and 1 <= a <= b <= len(BOOKS[book].lines), (book, a, b)
        assert any(quote in line for line in BOOKS[book].lines[a - 1:b]), quote


async def test_each_sample_searches_then_answers_with_real_citations(run):
    for sample in PATTERNS["semantic"].samples:
        messages = await run(sample)
        assert tool_calls(messages)[0]["name"] == "search_book", sample
        check_citations(messages[-1].content)


async def test_end_of_poem_sample_reads_book_xii(run):
    messages = await run("How does the poem end?")
    reads = [c for c in tool_calls(messages) if c["name"] == "read_passage"]
    assert reads and reads[0]["args"]["book"] == "XII"
    assert "They, hand in hand, with wandering steps and slow" in messages[-1].content
    check_citations(messages[-1].content)


async def test_uncovered_question_says_so(run):  # Review Focus 1
    messages = await run("What did Milton eat for breakfast?")
    assert tool_calls(messages)[0]["name"] == "search_book"
    answer = messages[-1].content
    assert "don't cover" in answer and "(Book" not in answer


async def test_answer_never_quotes_the_same_line_twice(run):
    # Overlapping passages can share a line; the answer should quote it once.
    for sample in PATTERNS["semantic"].samples:
        quotes = QUOTE.findall((await run(sample))[-1].content)
        assert len(quotes) == len(set(quotes)), (sample, quotes)


async def test_question_about_something_the_poem_never_mentions_is_not_covered(run):  # deferred minor 1
    # "Satan" and "think" are in the poem; "smartphones" is not, so no passage can answer it.
    answer = (await run("What does Satan think about smartphones?"))[-1].content
    assert "don't cover" in answer and "(Book" not in answer



async def test_breakfast_shows_the_corrective_loop(run):
    messages, nodes = await run("What did Milton eat for breakfast?", with_nodes=True)
    assert nodes == ["ask", "agent", "tools", "grade", "rewrite_query", "tools", "grade", "rewrite_query",
                     "tools", "grade", "agent"], nodes
    answer = messages[-1].content
    assert "don't cover" in answer and "Sources:" not in answer


async def test_samples_grade_relevant_first_time(run):
    for sample in PATTERNS["semantic"].samples:
        messages, nodes = await run(sample, with_nodes=True)
        assert "rewrite_query" not in nodes, (sample, nodes)
        assert nodes[nodes.index("grade") + 1] == "agent", (sample, nodes)
        check_citations(messages[-1].content)


def graded_passages(messages):
    """(Book, start_line) of every passage that survived grading in this run."""
    import json

    kept = set()
    for m in messages:
        if m.type == "tool":
            try:
                data = json.loads(m.content)
            except ValueError:
                continue
            passages = data["passages"] if isinstance(data, dict) and "passages" in data else (
                [data] if isinstance(data, dict) else data)
            kept |= {(p["book"], p["start_line"]) for p in passages}
    return kept


async def test_sources_never_cite_a_dropped_passage(run):
    for sample in PATTERNS["semantic"].samples:
        messages = await run(sample)
        _, sources = split_answer(messages[-1].content)
        kept = graded_passages(messages)
        for book, a, _b, _quote in SOURCE.findall(sources):
            assert (book, int(a)) in kept, (sample, book, a)


async def test_agent_reads_graded_form(run):  # Review Focus 5
    messages = await run(PATTERNS["semantic"].samples[0])
    tool_texts = [m.content for m in messages if m.type == "tool"]
    assert any('"passages":' in t for t in tool_texts)
    check_citations(messages[-1].content)
