"""The library as an MCP server: search Paradise Lost, or read it by Book and line.

Both tools are read-only. Arguments are checked here, and a problem comes back
as an MCP tool error with a plain message the model can act on.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from .index import LibraryIndex
from .text import ROMAN

INSTRUCTIONS = (
    "The full text of John Milton's Paradise Lost (1674, 12 Books). Search it or read passages "
    "by Book and line. Line numbers follow this edition."
)
READ_ONLY = ToolAnnotations(readOnlyHint=True)
NO_SUCH_BOOK = "Book {} does not exist; Paradise Lost has Books I to XII."
MAX_QUERY = 500
MAX_LIMIT = 10
INTERNAL_ERROR = "The library could not complete this request."

log = logging.getLogger(__name__)


class LibraryServer(FastMCP):
    """FastMCP whose tool errors are plain, like the ERP's.

    FastMCP prefixes every tool exception with "Error executing tool <name>: ".
    A ToolError raised here keeps its own message; a schema rejection keeps
    FastMCP's validation text; anything else is logged and reaches the client
    as a generic message.
    """

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        try:
            return await super().call_tool(name, arguments)
        except ToolError as err:
            cause = err.__cause__
            if isinstance(cause, ToolError):
                raise ToolError(str(cause)) from cause
            if cause is None or isinstance(cause, ValidationError):
                raise
            log.exception("library tool %s failed", name, exc_info=cause)
            raise ToolError(INTERNAL_ERROR) from cause


def normalise_book(value: str) -> str:
    """'ii', '2', 'Book II' and 'II' all mean Book II. Raises ToolError otherwise."""
    raw = re.sub(r"(?i)^\s*book\s+", "", str(value)).strip()
    if raw.isdigit() and 1 <= int(raw) <= len(ROMAN):
        return ROMAN[int(raw) - 1]
    if raw.upper() in ROMAN:
        return raw.upper()
    raise ToolError(NO_SUCH_BOOK.format(raw.upper() or "''"))


def build_server(index: LibraryIndex, *, host: str = "127.0.0.1", port: int = 8766) -> FastMCP:
    server = LibraryServer("library", instructions=INSTRUCTIONS, host=host, port=port, stateless_http=True)

    async def run(fn, *args) -> Any:
        # Embedding a query and reading Qdrant are synchronous; keep the event loop free.
        try:
            return await anyio.to_thread.run_sync(lambda: fn(*args))
        except ValueError as err:
            raise ToolError(str(err)) from err

    @server.tool(annotations=READ_ONLY)
    async def search_book(
        query: str = Field(description="What to look for: a question, a phrase, a name or a theme."),
        limit: int = Field(5, description="How many passages to return, 1 to 10."),
        book: str | None = Field(None, description="Only search one Book, I to XII."),
    ) -> list[dict[str, Any]]:
        """Passages of Paradise Lost that best match the query (meaning and exact words), best first.

        Each has book, start_line, end_line, text and score. Line numbers follow this edition.
        """
        if not query.strip() or len(query) > MAX_QUERY:
            raise ToolError(f"The query must be 1 to {MAX_QUERY} characters.")
        if not 1 <= limit <= MAX_LIMIT:
            raise ToolError(f"limit must be 1 to {MAX_LIMIT}.")
        numeral = normalise_book(book) if book is not None else None
        hits = await run(index.search, query, limit, numeral)
        return [vars(h) for h in hits]

    @server.tool(annotations=READ_ONLY)
    async def read_passage(
        book: str = Field(description="The Book, I to XII."),
        start_line: int = Field(description="First line to read, from 1."),
        end_line: int = Field(description="Last line to read. At most 80 lines are returned."),
    ) -> dict[str, Any]:
        """Lines of one Book of Paradise Lost, by line number (this edition). Clamped to the Book's end."""
        passage = await run(index.read, normalise_book(book), start_line, end_line)
        return {k: v for k, v in vars(passage).items() if k != "score"}

    return server
