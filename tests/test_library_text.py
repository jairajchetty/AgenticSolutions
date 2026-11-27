"""The cleaned Paradise Lost text: cleaning the PDF's pages and parsing the committed file."""
import pytest

from agentic_solutions.mcp_servers.library.text import ROMAN, TEXT_PATH, Book, clean_pages, parse_text, render

PAGES = [
    "Download free eBooks of classic literature, books and \nnovels at Planet eBook.\nParadise Lost\nBy John Milton",
    "Paradise Lost\nBook I \nO\nf Man’s first disobedience, and the fruit  \nOf that forbidden tree",
    "11Free eBooks at Planet eBook.com\nBrought death into the World,  ",
    "Paradise Lost1\nBook II \nH\nigh on a throne",
]


def test_clean_removes_headers_and_page_numbers():
    books = clean_pages(PAGES)
    assert [b.numeral for b in books] == ["I", "II"]
    assert books[0].lines == ("Of Man’s first disobedience, and the fruit", "Of that forbidden tree",
                              "Brought death into the World,")
    assert books[1].lines[0] == "High on a throne"
    assert books[1].number == 2


def test_clean_joins_drop_cap_and_strips_control_characters():
    # Book X opens "M" + "ean while" (Milton's spelling); Book IV opens "O" + ", for that".
    books = clean_pages(["Book I\nM\nean while the heinous\nand despiteful act\n\\ \n\x18\x181Free eBooks at Planet eBook.com"])
    assert books[0].lines == ("Mean while the heinous", "and despiteful act")


def test_clean_rejects_books_out_of_order():
    with pytest.raises(ValueError, match="Book II"):
        clean_pages(["Book I\nOne line.", "Book III\nAnother line."])


def test_render_parse_round_trip():
    books = clean_pages(PAGES)
    assert parse_text(render(books)) == tuple(books)


def test_parse_rejects_lines_before_first_book():
    with pytest.raises(ValueError, match="line 1"):
        parse_text("A stray line\n# Book I\nOf Man's first disobedience\n")


def test_committed_text_shape():
    books = parse_text(TEXT_PATH.read_text(encoding="utf-8"))
    assert [b.numeral for b in books] == list(ROMAN)
    assert [b.number for b in books] == list(range(1, 13))
    total = sum(len(b.lines) for b in books)
    assert 10_400 <= total <= 10_700, total
    assert not any("Planet eBook" in line for b in books for line in b.lines)
    assert isinstance(books[0], Book)


def test_clean_rejoins_lines_the_pdf_wrapped():
    # A wrapped verse line's first half ends in one space; whole lines end in two.
    page = "Book I\nThrough Heaven’s wide champain held his way; till \nMorn,  \nWaked by the circling Hours,  \n"
    assert clean_pages([page])[0].lines == ("Through Heaven’s wide champain held his way; till Morn,",
                                           "Waked by the circling Hours,")
    # A short line after a whole line (two trailing spaces) is a line of its own.
    assert clean_pages(["Book I\nAnd of their vain contest appeared no end.  \nO Heaven!  \n"])[0].lines == (
        "And of their vain contest appeared no end.", "O Heaven!")
