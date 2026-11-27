"""The library MCP server, through the Studio's in-process client and model tools."""
import pytest

from agentic_solutions.agents.semantic_memory_agent.library import InProcessLibraryClient, library_tools
from agentic_solutions.mcp_servers.library.index import LibraryIndex
from agentic_solutions.mcp_servers.library.server import build_server, normalise_book
from fakes import FakeEmbedder, library_fixture_text

pytestmark = pytest.mark.anyio


@pytest.fixture
def index(tmp_path):
    idx = LibraryIndex.open(tmp_path, library_fixture_text(), FakeEmbedder())
    yield idx
    idx.close()


@pytest.fixture
async def client(index):
    async with InProcessLibraryClient(build_server(index)) as c:
        yield c


async def test_search_book_returns_passages(client):
    hits = await client.call("search_book", {"query": "pandemonium council"})
    assert isinstance(hits, list) and hits
    assert set(hits[0]) == {"book", "start_line", "end_line", "text", "score"}
    assert hits[0]["book"] == "II"


async def test_search_book_limit_bounds(client):
    for limit in (0, 11):
        result = await client.call("search_book", {"query": "verse", "limit": limit})
        assert isinstance(result, str) and result.startswith("Error:"), result


async def test_query_length_bounds(client):
    for query in ("", "x" * 501):
        result = await client.call("search_book", {"query": query})
        assert isinstance(result, str) and result.startswith("Error:"), result


async def test_book_normalisation(client):  # Review Focus 5
    for book in ("ii", "2", "Book II", "II"):
        hits = await client.call("search_book", {"query": "verse line", "book": book, "limit": 10})
        assert {h["book"] for h in hits} == {"II"}, book
    result = await client.call("search_book", {"query": "verse", "book": "XIII"})
    assert result == "Error: Book XIII does not exist; Paradise Lost has Books I to XII."


def test_normalise_book_values():
    assert [normalise_book(v) for v in ("i", "12", " book xii ", "IV")] == ["I", "XII", "XII", "IV"]


async def test_read_passage_returns_lines(client):
    p = await client.call("read_passage", {"book": "I", "start_line": 1, "end_line": 3})
    assert p["text"].splitlines() == ["Verse I line 1 of the fixture,", "Verse I line 2 of the fixture,",
                                      "Verse I line 3 of the fixture,"]


async def test_read_passage_errors(client):  # Review Focus 3
    past = await client.call("read_passage", {"book": "I", "start_line": 41, "end_line": 45})
    assert past.startswith("Error:") and "40 lines" in past
    backwards = await client.call("read_passage", {"book": "I", "start_line": 10, "end_line": 5})
    assert backwards.startswith("Error:") and "end_line" in backwards


async def test_tools_are_read_only(index):
    tools = await build_server(index).list_tools()
    assert {t.name for t in tools} == {"search_book", "read_passage"}
    assert all(t.annotations and t.annotations.readOnlyHint for t in tools)


async def test_library_tools_schema(client):
    tools = {t.name: t for t in library_tools(client)}
    assert set(tools) == {"search_book", "read_passage"}
    assert "this edition" in tools["read_passage"].description
    out = await tools["search_book"].ainvoke({"query": "pandemonium"})
    assert '"book":"II"' in out


def test_book_name_with_trailing_full_stop():  # deferred minor 4
    assert normalise_book("II.") == "II" and normalise_book("Book 2.") == "II"


async def test_invalid_arguments_have_one_plain_prefix(client):  # deferred minor 3
    result = await client.call("read_passage", {"book": "I", "start_line": "x", "end_line": 5})
    assert result.startswith("Error: Invalid arguments for read_passage:"), result
    assert "Error executing tool" not in result and "start_line" in result


async def test_searches_run_at_most_two_at_a_time():  # deferred minor 5
    import threading
    import time

    import anyio

    from agentic_solutions.mcp_servers.library.index import Passage

    class SlowIndex:
        def __init__(self):
            self.now = self.peak = 0
            self.lock = threading.Lock()

        def search(self, query, limit, book):
            with self.lock:
                self.now += 1
                self.peak = max(self.peak, self.now)
            time.sleep(0.05)
            with self.lock:
                self.now -= 1
            return [Passage("I", 1, 2, "text", 0.5)]

    index = SlowIndex()
    async with InProcessLibraryClient(build_server(index)) as c:
        async with anyio.create_task_group() as tg:
            for i in range(8):
                tg.start_soon(c.call, "search_book", {"query": f"q{i}"})
    assert index.peak == 2
