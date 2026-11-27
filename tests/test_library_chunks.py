"""Chunking Books into overlapping verse windows that end on a sentence."""
from uuid import NAMESPACE_URL, uuid5

from agentic_solutions.mcp_servers.library.chunks import MAX_EXTEND, STRIDE, WINDOW, chunk_all, chunk_book
from agentic_solutions.mcp_servers.library.text import TEXT_PATH, Book, parse_text


def book(n=50, sentence_ends=(22, 45), numeral="I", number=1):
    lines = tuple(f"line {i} of the book{'.' if i in sentence_ends else ','}" for i in range(1, n + 1))
    return Book(numeral, number, lines)


def test_parameters():
    assert (STRIDE, WINDOW, MAX_EXTEND) == (16, 20, 8)


def test_starts_every_stride():
    assert [c.start_line for c in chunk_book(book())] == [1, 17, 33, 49]


def test_end_moves_to_sentence_end():
    assert chunk_book(book())[0].end_line == 22  # nominal 20, sentence ends at 22


def test_end_capped_at_max_extend():
    chunks = chunk_book(book(n=80, sentence_ends=()))
    assert chunks[0].end_line == 20  # nothing within 8 lines: nominal end


def test_closing_quote_after_full_stop_ends_a_sentence():
    b = Book("I", 1, tuple(f"l{i}," for i in range(1, 20)) + ("Better to reign in Hell than serve in Heaven.’",)
             + tuple(f"m{i}," for i in range(30)))
    assert chunk_book(b)[0].end_line == 20


def test_last_chunk_ends_at_book_end():
    assert chunk_book(book())[-1].end_line == 50


def test_every_line_covered_and_neighbours_overlap():
    chunks = chunk_book(book(n=97, sentence_ends=(10, 30, 61, 80)))
    covered = {n for c in chunks for n in range(c.start_line, c.end_line + 1)}
    assert covered == set(range(1, 98))
    assert all(b.start_line <= a.end_line for a, b in zip(chunks, chunks[1:]))


def test_text_is_the_lines_and_embed_text_has_position_prefix():
    c = chunk_book(book())[0]
    assert c.text.splitlines() == list(book().lines[0:22])
    assert c.embed_text == f"Paradise Lost, Book I, lines 1–22:\n{c.text}"


def test_ids_are_stable_uuid5():
    first = chunk_book(book())
    assert [c.id for c in first] == [c.id for c in chunk_book(book())]
    assert first[0].id == str(uuid5(NAMESPACE_URL, "paradise-lost/I/1"))


def test_real_text_chunk_count():
    books = parse_text(TEXT_PATH.read_text(encoding="utf-8"))
    chunks = chunk_all(books)
    assert 600 <= len(chunks) <= 750, len(chunks)
    lengths = {b.numeral: len(b.lines) for b in books}
    assert all(1 <= c.start_line <= c.end_line <= lengths[c.book] for c in chunks)
    assert [c.book_number for c in chunks] == sorted(c.book_number for c in chunks)
