"""The Studio's side of the library: an in-process MCP client and the model's tools.

`InProcessLibraryClient` keeps one in-memory MCP session to the library server
open for the app's lifetime, like the ERP's in-process client. `library_tools`
wraps `search_book` and `read_passage` for the model; a tool error reaches the
model as text starting "Error:", so it can correct itself.
"""
from __future__ import annotations

import json
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, Protocol

import anyio
from langchain_core.tools import BaseTool, StructuredTool
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

TIMEOUT_S = 30.0
UNAVAILABLE = "Error: the library is unavailable."


class LibraryClient(Protocol):
    async def call(self, tool: str, args: dict) -> Any:
        """Call a library tool. A tool error comes back as a str starting 'Error:'."""
        ...


def _parse(result: CallToolResult) -> Any:
    text = next((c.text for c in result.content if isinstance(c, TextContent)), None)
    if result.isError:
        return f"Error: {text or 'the library tool failed.'}"
    data = result.structuredContent
    if data is not None:
        return data["result"] if set(data) == {"result"} else data  # FastMCP wraps lists
    try:
        return json.loads(text) if text is not None else None
    except ValueError:
        return text


class InProcessLibraryClient:
    """One in-memory MCP session to `server`. Enter and exit it in the same task."""

    def __init__(self, server: FastMCP, *, timeout_s: float = TIMEOUT_S):
        self._server = server
        self.timeout_s = timeout_s
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "InProcessLibraryClient":
        stack = AsyncExitStack()
        try:
            self._session = await stack.enter_async_context(create_connected_server_and_client_session(
                self._server._mcp_server, read_timeout_seconds=timedelta(seconds=self.timeout_s)))
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        return self

    async def __aexit__(self, *exc) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack is not None:
            await stack.aclose()

    async def call(self, tool: str, args: dict) -> Any:
        if self._session is None:
            return UNAVAILABLE
        try:
            with anyio.fail_after(self.timeout_s):
                return _parse(await self._session.call_tool(tool, args))
        except Exception:
            return UNAVAILABLE


class SearchArgs(BaseModel):
    query: str = Field(description="What to look for: a question, a phrase, a name or a theme.")
    limit: int = Field(5, description="How many passages to return, 1 to 10.")
    book: str | None = Field(None, description="Only search one Book, I to XII.")


class ReadArgs(BaseModel):
    book: str = Field(description="The Book, I to XII.")
    start_line: int = Field(description="First line to read, from 1.")
    end_line: int = Field(description="Last line to read. At most 80 lines are returned.")


SEARCH_DESCRIPTION = (
    "Search the text of Paradise Lost. Returns the passages that best match the query, by meaning "
    "and by exact words, each with its Book, start_line, end_line and text. Line numbers follow this edition."
)
READ_DESCRIPTION = (
    "Read lines of one Book of Paradise Lost by line number, to see around a passage or reach a known "
    "place such as the end of Book XII. At most 80 lines. Line numbers follow this edition."
)


def _tool(client: LibraryClient, name: str, schema: type[BaseModel], description: str) -> BaseTool:
    async def run(**kwargs: Any) -> str:
        result = await client.call(name, {k: v for k, v in kwargs.items() if v is not None})
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return StructuredTool.from_function(coroutine=run, name=name, description=description, args_schema=schema)


def library_tools(client: LibraryClient) -> list[BaseTool]:
    return [_tool(client, "search_book", SearchArgs, SEARCH_DESCRIPTION),
            _tool(client, "read_passage", ReadArgs, READ_DESCRIPTION)]
