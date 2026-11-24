"""The mock ERP as an MCP server (Approval spec §4.1).

Every tool takes `tenant` first: the Studio's client fills it from the thread
id, and the model-facing wrappers never expose it (§4.4, §9.2). The store does
all the checking; this module only maps tools onto it and turns an `ErpError`
into an MCP tool error whose text is the store's plain message.
"""

from collections.abc import Callable
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .config import ErpSettings
from .store import ErpError, ErpStore

INSTRUCTIONS = (
    "A mock procurement ERP. Search the catalogue, quote prices, check budgets and draft "
    "requisitions. Placing a purchase order needs an approval token from the Studio."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True)
DRAFT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
COMMIT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

Tenant = Field(description="The Studio thread id. The client sets it; the model never does.")


class QuoteLine(BaseModel):
    quote_id: str = Field(description="A quote_id from get_price_quote.")


class ErpServer(FastMCP):
    """FastMCP whose tool errors carry the store's message as is.

    FastMCP prefixes every tool exception with "Error executing tool <name>: ".
    The Studio shows ERP refusals to people, so the prefix is stripped here.
    """

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        try:
            return await super().call_tool(name, arguments)
        except ToolError as err:
            if isinstance(err.__cause__, ErpError):
                raise ToolError(str(err.__cause__)) from err.__cause__
            raise


def build_server(store: ErpStore, settings: ErpSettings) -> FastMCP:
    server = ErpServer("erp", instructions=INSTRUCTIONS, host=settings.host, port=settings.port,
                       stateless_http=True)

    async def run(fn: Callable[..., Any], *args) -> Any:
        # The store is synchronous and serialises on a lock; keep the event loop free.
        return await anyio.to_thread.run_sync(lambda: fn(*args))

    def plain(lines: list[QuoteLine] | None):
        return None if lines is None else [line.model_dump() for line in lines]

    @server.tool(annotations=READ_ONLY)
    async def search_catalogue(
        tenant: str = Tenant,
        query: str = Field(description="Words to match against SKU, name and category."),
        category: str | None = Field(None, description="Limit to one category, e.g. laptops."),
        max_unit_price: float | None = Field(None, description="Highest list price per unit, ZAR."),
    ) -> list[dict[str, Any]]:
        """Up to 10 catalogue items: sku, name, unit_price_zar, supplier_id, category."""
        return await run(store.search_catalogue, tenant, query, category, max_unit_price)

    @server.tool(annotations=READ_ONLY)
    async def get_supplier(
        tenant: str = Tenant,
        supplier_id: str = Field(description="A supplier_id from the catalogue."),
    ) -> dict[str, Any]:
        """A supplier's name, lead time in days, rating and preferred flag."""
        return await run(store.get_supplier, tenant, supplier_id)

    @server.tool(annotations=READ_ONLY)
    async def check_budget(
        tenant: str = Tenant,
        cost_centre: str = Field(description="CT-OPS, JHB-FIN, DBN-LOG or HQ-IT."),
    ) -> dict[str, Any]:
        """A cost centre's allocated, committed and remaining budget in ZAR."""
        return await run(store.check_budget, tenant, cost_centre)

    @server.tool(annotations=READ_ONLY)
    async def get_price_quote(
        tenant: str = Tenant,
        sku: str = Field(description="A catalogue SKU."),
        quantity: int = Field(description="Units, 1 to 999."),
    ) -> dict[str, Any]:
        """A quote: quote_id, unit price after volume discount, line total, expires_at (+30 min)."""
        return await run(store.get_price_quote, tenant, sku, quantity)

    @server.tool(annotations=DRAFT)
    async def create_requisition(
        tenant: str = Tenant,
        cost_centre: str = Field(description="The cost centre to charge."),
        lines: list[QuoteLine] = Field(description="One line per quote."),
        justification: str = Field(description="Why this is needed, in a sentence."),
    ) -> dict[str, Any]:
        """Draft a requisition (version 1, status draft) from price quotes. Orders nothing."""
        return await run(store.create_requisition, tenant, cost_centre, plain(lines), justification)

    @server.tool(annotations=DRAFT)
    async def update_requisition(
        tenant: str = Tenant,
        req_id: str = Field(description="The requisition to change."),
        lines: list[QuoteLine] | None = Field(None, description="Replacement lines, one per quote."),
        justification: str | None = Field(None, description="A replacement justification."),
    ) -> dict[str, Any]:
        """A new version and content hash for a draft. Any prior approval is void."""
        return await run(store.update_requisition, tenant, req_id, plain(lines), justification)

    @server.tool(annotations=READ_ONLY)
    async def get_requisition(
        tenant: str = Tenant,
        req_id: str = Field(description="The requisition id, e.g. REQ-0001."),
    ) -> dict[str, Any]:
        """A requisition's current version, lines, total, status and content hash."""
        return await run(store.get_requisition, tenant, req_id)

    @server.tool(annotations=COMMIT)
    async def submit_purchase_order(
        tenant: str = Tenant,
        req_id: str = Field(description="The requisition to order."),
        version: int = Field(description="The approved version."),
        approval_token: str = Field(description="The signed approval for this exact version."),
        idempotency_key: str = Field(description="The same key returns the same PO."),
    ) -> dict[str, Any]:
        """Place the purchase order if the approval, quotes and budget all hold; returns po_number."""
        return await run(store.submit_purchase_order, tenant, req_id, version, approval_token,
                         idempotency_key)

    @server.tool(annotations=READ_ONLY)
    async def get_audit_trail(
        tenant: str = Tenant,
        req_id: str = Field(description="The requisition id."),
    ) -> list[dict[str, Any]]:
        """A requisition's audit events in order, refusals with their reasons."""
        return await run(store.get_audit_trail, tenant, req_id)

    @server.tool(annotations=DRAFT)
    async def record_approval_event(
        tenant: str = Tenant,
        req_id: str = Field(description="The requisition id."),
        version: int = Field(description="The version the decision is about."),
        event: str = Field(description="approval_requested, approved, rejected or auto_approved."),
        actor: str = Field(description="Who decided: a visitor id or policy."),
        reason: str | None = Field(None, description="The decision's reason, if any."),
    ) -> dict[str, Any]:
        """Studio only: audit an approval decision the server cannot otherwise see."""
        return await run(store.record_approval_event, tenant, req_id, version, event, actor, reason)

    return server
