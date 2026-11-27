"""Chunks: overlapping windows of verse within one Book, each ending on a sentence.

A chunk starts at line 1 and then every STRIDE lines. Its nominal end is WINDOW
lines on, so neighbours overlap by WINDOW - STRIDE lines. The end then moves
forward to the first line that closes a sentence, at most MAX_EXTEND lines, so
a chunk rarely cuts Milton's long sentences in half. Chunks never cross a Book.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from .text import Book

STRIDE = 16
WINDOW = 20
MAX_EXTEND = 8
SENTENCE_END = re.compile(r"[.?!][’'\"”)]*$")


@dataclass(frozen=True)
class Chunk:
    id: str
    book: str
    book_number: int
    start_line: int
    end_line: int
    text: str

    @property
    def embed_text(self) -> str:
        """What is embedded: the position first, so the dense model sees it as context."""
        return f"Paradise Lost, Book {self.book}, lines {self.start_line}–{self.end_line}:\n{self.text}"


def _end(lines: tuple[str, ...], start: int) -> int:
    """The 1-based end line of the chunk starting at `start` (1-based)."""
    n = len(lines)
    nominal = min(start + WINDOW - 1, n)
    for end in range(nominal, min(nominal + MAX_EXTEND, n) + 1):
        if SENTENCE_END.search(lines[end - 1]):
            return end
    return nominal


def chunk_book(book: Book) -> list[Chunk]:
    n = len(book.lines)
    chunks = []
    for start in range(1, n + 1, STRIDE):
        # A chunk starting within the last stride takes the Book to its end.
        end = n if start + STRIDE > n else _end(book.lines, start)
        chunks.append(Chunk(
            id=str(uuid5(NAMESPACE_URL, f"paradise-lost/{book.numeral}/{start}")),
            book=book.numeral, book_number=book.number, start_line=start, end_line=end,
            text="\n".join(book.lines[start - 1:end])))
    return chunks


def chunk_all(books: Iterable[Book]) -> list[Chunk]:
    return [c for b in books for c in chunk_book(b)]
