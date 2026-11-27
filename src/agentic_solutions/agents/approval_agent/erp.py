"""The Studio's side of the ERP: an MCP client and the tools the model may use.

Two clients speak the same protocol:
- `HttpErpClient` opens one streamable-HTTP session per call, for a separate server.
- `InProcessErpClient` keeps one in-memory MCP session open, for the default
  one-command demo (plan ruling 3).

`model_tools` wraps the read and draft tools for the model. Their schemas have
no `tenant`: it comes from the run's thread id, so the model can never choose
or switch it (§9.2). `submit_purchase_order` and `record_approval_event` are
never wrapped, so the model cannot commit an order or forge an audit event.
"""

import json
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, Protocol

import anyio
import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

TIMEOUT_S = 10.0
UNAVAILABLE = "The ERP system is unavailable."


class ErpUnavailable(Exception):
    """The ERP could not be reached, or did not answer in time."""


class ErpToolError(Exception):
    """The ERP answered with a tool error. `str()` is the server's message."""


class ErpClient(Protocol):
    async def call(self, tool: str, args: dict) -> Any:
        """Call one ERP tool. Raises ErpToolError or ErpUnavailable."""
        ...


def _parse(result: CallToolResult) -> Any:
    text = next((c.text for c in result.content if isinstance(c, TextContent)), None)
    if result.isError:
        raise ErpToolError(text or "The ERP tool failed.")
    data = result.structuredContent
    if data is not None:
        # FastMCP wraps a non-object return (a list) as {"result": ...}.
        return data["result"] if set(data) == {"result"} else data
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


class HttpErpClient:
    """One streamable-HTTP MCP session per call, under a 10 s timeout."""

    def __init__(self, url: str, *, timeout_s: float = TIMEOUT_S):
        self.url = url
        self.timeout_s = timeout_s

    async def call(self, tool: str, args: dict) -> Any:
        try:
            with anyio.fail_after(self.timeout_s):
                # The transport does not close a client it is given, hence the async with.
                async with (
                    httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s)) as http,
                    streamable_http_client(self.url, http_client=http) as (read, write, _),
                    ClientSession(read, write) as session,
                ):
                    await session.initialize()
                    result = await session.call_tool(tool, args)
        except Exception as err:
            # Connection refused, HTTP errors and timeouts, often wrapped in an
            # ExceptionGroup by the transport's task group. A tool error never
            # raises here: it arrives as a result with isError set.
            raise ErpUnavailable(f"{UNAVAILABLE} ({self.url}: {type(err).__name__})") from err
        return _parse(result)


class InProcessErpClient:
    """One in-memory MCP session to `server`, held open for the client's lifetime.

    Enter and exit it in the same task (the session runs in an anyio task
    group). `call` may be used concurrently from many tasks in between.
    """

    def __init__(self, server: FastMCP, *, timeout_s: float = TIMEOUT_S):
        self._server = server
        self.timeout_s = timeout_s
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "InProcessErpClient":
        stack = AsyncExitStack()
        try:
            self._session = await stack.enter_async_context(
                create_connected_server_and_client_session(
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
        session = self._session
        if session is None:
            raise ErpUnavailable(f"{UNAVAILABLE} (the in-process session is not open)")
        try:
            with anyio.fail_after(self.timeout_s):
                result = await session.call_tool(tool, args)
        except Exception as err:
            raise ErpUnavailable(f"{UNAVAILABLE} ({type(err).__name__})") from err
        return _parse(result)


# ---------------------------------------------------------------- model tools


class _Args(BaseModel):
    # A stray argument (a `tenant` the model invents, say) is dropped, not an error.
    model_config = ConfigDict(extra="ignore")


class QuoteLine(_Args):
    quote_id: str = Field(description="A quote_id from get_price_quote.")


class SearchCatalogueArgs(_Args):
    query: str = Field(description="Words to match against SKU, name and category.")
    category: str | None = Field(None, description="Limit to one category, e.g. laptops.")
    max_unit_price: float | None = Field(None, description="Highest list price per unit, ZAR.")


class GetSupplierArgs(_Args):
    supplier_id: str = Field(description="A supplier_id from the catalogue.")


class CheckBudgetArgs(_Args):
    cost_centre: str = Field(description="CT-OPS, JHB-FIN, DBN-LOG or HQ-IT.")


class GetPriceQuoteArgs(_Args):
    sku: str = Field(description="A catalogue SKU.")
    quantity: int = Field(ge=1, le=999, description="Units, 1 to 999.")


class CreateRequisitionArgs(_Args):
    cost_centre: str = Field(description="The cost centre to charge.")
    lines: list[QuoteLine] = Field(description="One line per quote.")
    justification: str = Field(description="Why this is needed, in a sentence.")


class UpdateRequisitionArgs(_Args):
    req_id: str = Field(description="The requisition to change.")
    lines: list[QuoteLine] | None = Field(None, description="Replacement lines, one per quote.")
    justification: str | None = Field(None, description="A replacement justification.")


class ReqIdArgs(_Args):
    req_id: str = Field(description="The requisition id, e.g. REQ-0001.")


_MODEL_TOOLS: tuple[tuple[str, type[BaseModel], str], ...] = (
    ("search_catalogue", SearchCatalogueArgs,
     "Search the catalogue by keyword, optionally by category and highest unit price in ZAR."),
    ("get_supplier", GetSupplierArgs,
     "Look up a supplier's name, lead time, rating and preferred flag."),
    ("check_budget", CheckBudgetArgs,
     "Check a cost centre's allocated, committed and remaining budget in ZAR."),
    ("get_price_quote", GetPriceQuoteArgs,
     "Get a price quote for a quantity of one SKU, with volume discount; it expires in 30 minutes."),
    ("create_requisition", CreateRequisitionArgs,
     "Draft a requisition from price quotes. Drafting does not order anything."),
    ("update_requisition", UpdateRequisitionArgs,
     "Change a draft requisition's lines or justification. This makes a new version."),
    ("get_requisition", ReqIdArgs,
     "Read a requisition's current version, lines, total, status and content hash."),
    ("get_audit_trail", ReqIdArgs,
     "List a requisition's audit events in order."),
)

MODEL_TOOL_NAMES: tuple[str, ...] = tuple(name for name, _, _ in _MODEL_TOOLS)


def _tenant(config: RunnableConfig | None) -> str:
    tenant = ((config or {}).get("configurable") or {}).get("thread_id")
    if not isinstance(tenant, str) or not tenant:
        raise ValueError("ERP tools need config['configurable']['thread_id'] as the tenant")
    return tenant


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _invalid_args(err: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in err.errors())
    return f"Error: invalid arguments ({problems})."


def _make_tool(erp: ErpClient, name: str, schema: type[BaseModel], description: str) -> BaseTool:
    async def run(config: RunnableConfig, **kwargs: Any) -> str:
        args = {"tenant": _tenant(config)}
        for key, value in kwargs.items():
            if key == "tenant" or value is None:
                continue
            if isinstance(value, list):
                value = [v.model_dump() if isinstance(v, BaseModel) else v for v in value]
            args[key] = value
        try:
            return _compact(await erp.call(name, args))
        except ErpToolError as err:
            return f"Error: {err}"
        except ErpUnavailable:
            return UNAVAILABLE

    return StructuredTool.from_function(
        coroutine=run, name=name, description=description, args_schema=schema,
        handle_validation_error=_invalid_args)


def model_tools(erp: ErpClient) -> list[BaseTool]:
    """The read and draft ERP tools for the model, tenant filled from the run's thread id."""
    return [_make_tool(erp, name, schema, description) for name, schema, description in _MODEL_TOOLS]
