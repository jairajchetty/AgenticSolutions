"""Turn the Planet eBook PDF of Paradise Lost into the library's committed text.

One-off. Needs the `prep` extra (pypdf):

    pip install -e '.[prep]'
    python tools/prepare_paradise_lost.py data/books/paradise-lost.pdf

Writes src/agentic_solutions/mcp_servers/library/texts/paradise-lost.txt.
"""
import sys
from pathlib import Path

from pypdf import PdfReader

from agentic_solutions.mcp_servers.library.text import ROMAN, TEXT_PATH, clean_pages, render

LINES = (10_400, 10_700)  # the 1674 text has 10,565 lines; numbering follows this edition


def main(pdf: str) -> int:
    pages = [page.extract_text() or "" for page in PdfReader(pdf).pages]
    try:
        books = clean_pages(pages)
    except ValueError as err:
        print(f"Could not split the PDF into Books: {err}", file=sys.stderr)
        return 1
    total = sum(len(b.lines) for b in books)
    if [b.numeral for b in books] != list(ROMAN):
        print(f"Expected Books I to XII, found {', '.join(b.numeral for b in books)}", file=sys.stderr)
        return 1
    if not LINES[0] <= total <= LINES[1]:
        print(f"Found {total} lines, outside {LINES[0]}-{LINES[1]}: some page residue was not removed",
              file=sys.stderr)
        return 1
    TEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEXT_PATH.write_text(render(books), encoding="utf-8")
    print(f"Wrote {len(books)} Books, {total} lines to {TEXT_PATH}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python tools/prepare_paradise_lost.py <paradise-lost.pdf>")
    sys.exit(main(sys.argv[1]))
