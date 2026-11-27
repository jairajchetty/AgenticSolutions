"""The library's text: Paradise Lost, cleaned from the PDF and parsed from the committed file.

`clean_pages` turns the PDF's extracted pages into Books. `render` writes them as
the committed text, and `parse_text` reads that text back:

    # Book I
    Of Man's first disobedience, and the fruit
    ...

One verse line per line, with no blank lines inside a Book. Line numbers count
verse lines within a Book from 1 and follow this edition.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROMAN: tuple[str, ...] = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
TEXT_PATH = Path(__file__).with_name("texts") / "paradise-lost.txt"

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_BOOK = re.compile(r"Book ([IVXL]+)")
_DROP = (
    re.compile(r"\d*Free eBooks at Planet eBook\.com"),  # footer, maybe after a page number
    re.compile(r"Paradise Lost\d*"),  # running header, maybe before a page number
    re.compile(r"By John Milton"),
)
_HEADING = re.compile(r"# Book ([IVXL]+)")


@dataclass(frozen=True)
class Book:
    numeral: str
    number: int
    lines: tuple[str, ...]


def _check_order(numerals: list[str]) -> None:
    for i, numeral in enumerate(numerals):
        if i >= len(ROMAN) or numeral != ROMAN[i]:
            expected = ROMAN[i] if i < len(ROMAN) else "no more Books"
            raise ValueError(f"expected Book {expected} next, found Book {numeral}")


def clean_pages(pages: list[str]) -> list[Book]:
    """Books from the PDF's page texts. Text before Book I (the title page) is dropped.

    Removes the Planet eBook headers and footers, control characters and lines
    with no letters, and joins each Book's drop capital (a lone capital letter
    on its own line) to the line after it. A whole verse line ends in two
    spaces; one the PDF wrapped ends its first half in one space, so a short
    fragment (three words or fewer) after that is joined back to it.
    """
    books: list[tuple[str, list[str]]] = []
    pending_cap = ""
    wrapped = False  # the last verse line kept ended in a single space
    for page in pages:
        for raw in page.splitlines():
            raw = _CONTROL.sub("", raw)
            line = raw.strip()
            if not line or not any(ch.isalpha() for ch in line):
                continue
            if any(p.fullmatch(line) for p in _DROP) or line.startswith("Download free eBooks"):
                continue
            heading = _BOOK.fullmatch(line)
            if heading:
                books.append((heading.group(1), []))
                continue
            if not books:
                continue  # the title page
            if len(line) == 1 and line.isupper():
                pending_cap = line  # a drop capital: joins the next line
                continue
            if wrapped and books[-1][1] and len(line.split()) <= 3:
                books[-1][1][-1] += " " + line
            else:
                books[-1][1].append(pending_cap + line)
            pending_cap = ""
            wrapped = raw.endswith(" ") and not raw.endswith("  ")
    _check_order([numeral for numeral, _ in books])
    return [Book(numeral, i + 1, tuple(lines)) for i, (numeral, lines) in enumerate(books)]


def render(books: list[Book]) -> str:
    return "".join(f"# Book {b.numeral}\n" + "".join(f"{line}\n" for line in b.lines) for b in books)


def parse_text(text: str) -> tuple[Book, ...]:
    """Books from the committed text format. Raises ValueError naming the line."""
    books: list[tuple[str, list[str]]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        heading = _HEADING.fullmatch(line)
        if heading:
            books.append((heading.group(1), []))
        elif not books:
            raise ValueError(f"line {n}: text before the first '# Book' heading")
        elif not line.strip():
            raise ValueError(f"line {n}: blank line inside Book {books[-1][0]}")
        else:
            books[-1][1].append(line)
    _check_order([numeral for numeral, _ in books])
    return tuple(Book(numeral, i + 1, tuple(lines)) for i, (numeral, lines) in enumerate(books))
