"""The Qdrant hybrid index: build once, reuse by fingerprint, search and read."""
import os

import pytest

from agentic_solutions.mcp_servers.library.index import LibraryIndex, fingerprint
from fakes import FakeEmbedder, library_fixture_text


@pytest.fixture
def text():
    return library_fixture_text()


def open_index(root, text, embedder=None):
    return LibraryIndex.open(root, text, embedder or FakeEmbedder())


def test_first_open_builds_then_reuses(tmp_path, text):
    emb = FakeEmbedder()
    first = open_index(tmp_path, text, emb)
    assert first.built is True
    first.close()
    calls = emb.dense_calls
    second = open_index(tmp_path, text, emb)
    assert second.built is False and emb.dense_calls == calls
    second.close()


def test_changed_text_rebuilds(tmp_path, text):
    open_index(tmp_path, text).close()
    again = open_index(tmp_path, text.replace("fixture", "changed"))
    assert again.built is True
    again.close()


def test_fingerprint_depends_on_text_and_models(text):
    emb = FakeEmbedder()
    assert fingerprint(text, emb) == fingerprint(text, emb)
    assert fingerprint(text, emb) != fingerprint(text + "x", emb)


def test_missing_or_corrupt_meta_rebuilds(tmp_path, text):  # Review Focus 2
    open_index(tmp_path, text).close()
    (tmp_path / "meta.json").unlink()
    idx = open_index(tmp_path, text)
    assert idx.built is True
    idx.close()
    (tmp_path / "meta.json").write_text("{bad", encoding="utf-8")
    idx = open_index(tmp_path, text)
    assert idx.built is True
    idx.close()


def test_search_finds_exact_words_and_filters_by_book(tmp_path, text):
    idx = open_index(tmp_path, text)
    hits = idx.search("pandemonium council", limit=3, book=None)
    assert hits[0].book == "II" and "pandemonium" in hits[0].text
    assert hits[0].score is not None
    assert {h.book for h in idx.search("verse line", limit=10, book="I")} == {"I"}
    idx.close()


def test_read_clamps_and_caps(tmp_path, text):
    idx = open_index(tmp_path, text)
    p = idx.read("I", 30, 500)
    assert (p.start_line, p.end_line) == (30, 40)
    assert p.text.splitlines()[0] == "Verse I line 30 of the fixture,"
    long = LibraryIndex.open(tmp_path / "long", "# Book I\n" + "".join(f"l{i},\n" for i in range(300)), FakeEmbedder())
    assert long.read("I", 1, 200).end_line == 80
    long.close()
    idx.close()


def test_read_rejects_bad_ranges(tmp_path, text):
    idx = open_index(tmp_path, text)
    with pytest.raises(ValueError, match="Book IX"):
        idx.read("IX", 1, 5)
    with pytest.raises(ValueError, match="40 lines"):
        idx.read("I", 41, 50)
    with pytest.raises(ValueError, match="end_line"):
        idx.read("I", 10, 5)
    idx.close()


@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="RUN_SLOW=1 downloads the embedding models")
def test_real_models_find_famous_passages(tmp_path):
    from agentic_solutions.mcp_servers.library.index import FastEmbedder
    from agentic_solutions.mcp_servers.library.text import TEXT_PATH

    idx = LibraryIndex.open(tmp_path, TEXT_PATH.read_text(encoding="utf-8"), FastEmbedder(tmp_path / "models"))
    assert "I" in [h.book for h in idx.search("Better to reign in Hell than serve in Heaven", 3, None)]
    assert "II" in [h.book for h in idx.search("What does Mammon propose?", 3, None)]
    idx.close()


def test_cached_open_loads_the_models_before_serving(tmp_path, text):  # review: lazy load at first search
    emb = FakeEmbedder()
    open_index(tmp_path, text, emb).close()
    loads = emb.loads
    open_index(tmp_path, text, emb).close()  # fingerprint matches: nothing embedded
    assert emb.loads == loads + 1


def test_fast_embedder_loads_both_models_once_under_concurrency(tmp_path, monkeypatch):  # review: race
    import threading
    import time
    import types

    import fastembed

    from agentic_solutions.mcp_servers.library.index import FastEmbedder

    made = []

    class Vec(list):
        def tolist(self):
            return list(self)

    class Dense:
        def __init__(self, *a, **k):
            made.append("dense")

        def query_embed(self, text):
            yield Vec([0.0])

    class Sparse:
        def __init__(self, *a, **k):
            time.sleep(0.2)  # slow to load: another thread would see dense set and sparse missing
            made.append("sparse")

        def query_embed(self, text):
            yield types.SimpleNamespace(indices=Vec([1]), values=Vec([1.0]))

    monkeypatch.setattr(fastembed, "TextEmbedding", Dense)
    monkeypatch.setattr(fastembed, "SparseTextEmbedding", Sparse)
    emb = FastEmbedder(tmp_path)
    errors = []

    def search():
        try:
            emb.dense_query("x")
            emb.sparse_query("x")
        except Exception as err:  # noqa: BLE001
            errors.append(err)

    threads = [threading.Thread(target=search) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and sorted(made) == ["dense", "sparse"]


def test_folder_in_use_says_to_use_another_library_dir(tmp_path, text):  # deferred minor 2
    first = open_index(tmp_path, text)
    try:
        with pytest.raises(RuntimeError, match="LIBRARY_DIR"):
            open_index(tmp_path, text)
    finally:
        first.close()
