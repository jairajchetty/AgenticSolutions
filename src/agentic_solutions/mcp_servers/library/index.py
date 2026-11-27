"""The library's vector index: Qdrant in local mode, hybrid dense + BM25 search.

`LibraryIndex.open(root, text, embedder)` opens the collection under
`root/qdrant` if `root/meta.json` holds the same fingerprint (the text, the
chunking parameters and the two model names); otherwise it rebuilds it. The
fingerprint is written last, so a build that stops halfway is redone next time.

Search fuses two prefetches, dense (bge-small) and sparse (BM25), with RRF.
Reading by line comes from the parsed text in memory, not from Qdrant.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from qdrant_client import QdrantClient, models

from .chunks import MAX_EXTEND, STRIDE, WINDOW, Chunk, chunk_all
from .text import Book, parse_text

log = logging.getLogger(__name__)

COLLECTION = "paradise_lost"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
DENSE_SIZE = 384
PREFETCH = 20
MAX_READ_LINES = 80
BATCH = 64


class Embedder(Protocol):
    names: tuple[str, str]  # (dense model, sparse model): part of the fingerprint

    def load(self) -> None:
        """Load the models now (and download them if needed), before the first query."""
        ...

    def dense(self, texts: list[str]) -> list[list[float]]: ...
    def sparse(self, texts: list[str]) -> list[tuple[list[int], list[float]]]: ...
    def dense_query(self, text: str) -> list[float]: ...
    def sparse_query(self, text: str) -> tuple[list[int], list[float]]: ...


class FastEmbedder:
    """bge-small-en-v1.5 and BM25 through fastembed (ONNX, CPU).

    `load` builds both models together under a lock, so concurrent searches
    never see one model loaded and the other not. `LibraryIndex.open` calls it,
    so the models are ready before the app serves requests.
    """

    names = (DENSE_MODEL, SPARSE_MODEL)

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self._pair = None
        self._lock = threading.Lock()

    def load(self) -> None:
        self._models()

    def _models(self):
        pair = self._pair
        if pair is None:
            with self._lock:
                if self._pair is None:
                    from fastembed import SparseTextEmbedding, TextEmbedding

                    dense = TextEmbedding(DENSE_MODEL, cache_dir=str(self.cache_dir))
                    sparse = SparseTextEmbedding(SPARSE_MODEL, cache_dir=str(self.cache_dir))
                    self._pair = (dense, sparse)  # both at once, only once both are built
                pair = self._pair
        return pair

    def dense(self, texts):
        return [v.tolist() for v in self._models()[0].embed(texts, batch_size=BATCH)]

    def sparse(self, texts):
        return [(v.indices.tolist(), v.values.tolist()) for v in self._models()[1].embed(texts)]

    def dense_query(self, text):
        return next(iter(self._models()[0].query_embed(text))).tolist()

    def sparse_query(self, text):
        v = next(iter(self._models()[1].query_embed(text)))
        return v.indices.tolist(), v.values.tolist()


def fingerprint(text: str, embedder: Embedder) -> str:
    h = hashlib.sha256(text.encode("utf-8"))
    h.update(json.dumps([STRIDE, WINDOW, MAX_EXTEND, *embedder.names]).encode("utf-8"))
    return h.hexdigest()


@dataclass
class Passage:
    book: str
    start_line: int
    end_line: int
    text: str
    score: float | None = None


class LibraryIndex:
    def __init__(self, client: QdrantClient, books: tuple[Book, ...], embedder: Embedder, built: bool):
        self._client = client
        self._books = {b.numeral: b for b in books}
        self._order = [b.numeral for b in books]
        self._embedder = embedder
        self.built = built

    @classmethod
    def open(cls, root: Path, text: str, embedder: Embedder) -> "LibraryIndex":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        books = parse_text(text)
        meta = root / "meta.json"
        wanted = fingerprint(text, embedder)
        try:
            current = json.loads(meta.read_text(encoding="utf-8")).get("fingerprint")
        except (OSError, ValueError, AttributeError):
            current = None  # missing or corrupt: rebuild
        embedder.load()  # a cached start loads the models here too, not on the first search
        try:
            client = QdrantClient(path=str(root / "qdrant"))
        except RuntimeError as err:
            if "already accessed" not in str(err):
                raise
            # Qdrant's local mode allows one process per folder.
            raise RuntimeError(
                f"The library index at {root} is in use by another process (the Studio or the standalone "
                "library server). Stop it, or give this one its own LIBRARY_DIR.") from err
        built = current != wanted or not client.collection_exists(COLLECTION)
        if built:
            meta.unlink(missing_ok=True)
            _build(client, chunk_all(books), embedder)
            meta.write_text(json.dumps({"fingerprint": wanted}), encoding="utf-8")
        return cls(client, books, embedder, built)

    def close(self) -> None:
        self._client.close()

    def search(self, query: str, limit: int, book: str | None) -> list[Passage]:
        dense = self._embedder.dense_query(query)
        indices, values = self._embedder.sparse_query(query)
        where = None
        if book is not None:
            where = models.Filter(must=[models.FieldCondition(key="book", match=models.MatchValue(value=book))])
        points = self._client.query_points(
            COLLECTION,
            prefetch=[
                models.Prefetch(query=dense, using="dense", limit=PREFETCH, filter=where),
                models.Prefetch(query=models.SparseVector(indices=indices, values=values), using="bm25",
                                limit=PREFETCH, filter=where),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        ).points
        return [Passage(p.payload["book"], p.payload["start_line"], p.payload["end_line"], p.payload["text"],
                        round(p.score, 4)) for p in points]

    def read(self, book: str, start: int, end: int) -> Passage:
        b = self._books.get(book)
        if b is None:
            raise ValueError(f"Book {book} does not exist; this text has Books {self._order[0]} to {self._order[-1]}.")
        n = len(b.lines)
        if start < 1 or start > n:
            raise ValueError(f"Book {book} has {n} lines; start_line {start} is outside it.")
        if end < start:
            raise ValueError("end_line must not be before start_line.")
        end = min(end, n, start + MAX_READ_LINES - 1)
        return Passage(book, start, end, "\n".join(b.lines[start - 1:end]))


def _build(client: QdrantClient, chunks: list[Chunk], embedder: Embedder) -> None:
    started = time.monotonic()
    log.info("Indexing Paradise Lost: %d chunks; the first run downloads the embedding models.", len(chunks))
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        COLLECTION,
        vectors_config={"dense": models.VectorParams(size=DENSE_SIZE, distance=models.Distance.COSINE)},
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        texts = [c.embed_text for c in batch]
        dense = embedder.dense(texts)
        sparse = embedder.sparse(texts)
        client.upsert(COLLECTION, [
            models.PointStruct(
                id=c.id,
                vector={"dense": d, "bm25": models.SparseVector(indices=s[0], values=s[1])},
                payload={"book": c.book, "book_number": c.book_number, "start_line": c.start_line,
                         "end_line": c.end_line, "text": c.text})
            for c, d, s in zip(batch, dense, sparse)])
    log.info("Indexed Paradise Lost in %.1f s.", time.monotonic() - started)
