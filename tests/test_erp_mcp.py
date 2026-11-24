"""The ERP over MCP: the server's tool contract, the Studio client and the model-facing tools."""

import json
import threading
import time

import anyio
import pytest
import uvicorn
from mcp.shared.memory import create_connected_server_and_client_session

from agentic_solutions.common.approval_tokens import issue
from agentic_solutions.agents.approval_agent.erp import (
    MODEL_TOOL_NAMES,
    ErpToolError,
    ErpUnavailable,
    HttpErpClient,
    InProcessErpClient,
    model_tools,
)
from agentic_solutions.mcp_servers.erp.config import ErpSettings
from agentic_solutions.mcp_servers.erp.server import build_server
from agentic_solutions.mcp_servers.erp.store import ErpStore

SECRET = b"test-erp-secret"

SERVER_TOOLS = {
    "search_catalogue", "get_supplier", "check_budget", "get_price_quote", "create_requisition",
    "update_requisition", "get_requisition", "submit_purchase_order", "get_audit_trail",
    "record_approval_event",
}
READ_ONLY = {"search_catalogue", "get_supplier", "check_budget", "get_price_quote",
             "get_requisition", "get_audit_trail"}


@pytest.fixture
def settings(tmp_path):
    return ErpSettings(db=str(tmp_path / "erp.sqlite"), secret=SECRET, auto_limit_zar=5000.0,
                       tenant_ttl_hours=168.0, host="127.0.0.1", port=0)


@pytest.fixture
def store(settings):
    s = ErpStore(settings.db, secret=settings.secret, auto_limit_zar=settings.auto_limit_zar,
                 tenant_ttl_hours=settings.tenant_ttl_hours)
    yield s
    s.close()


@pytest.fixture
def server(store, settings):
    return build_server(store, settings)


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


@pytest.mark.anyio
async def test_server_lists_tools_with_schemas_and_annotations(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    assert set(tools) == SERVER_TOOLS
    for name, tool in tools.items():
        props = tool.inputSchema["properties"]
        assert "tenant" in props and "tenant" in tool.inputSchema["required"], name
        assert tool.description, name
        a = tool.annotations
        if name in READ_ONLY:
            assert a.readOnlyHint is True, name
        else:
            assert a.readOnlyHint is False, name
    submit = tools["submit_purchase_order"].annotations
    assert submit.destructiveHint is True and submit.idempotentHint is True
    for name in ("create_requisition", "update_requisition", "record_approval_event"):
        assert tools[name].annotations.destructiveHint is False, name
        assert tools[name].annotations.idempotentHint is False, name
    assert set(tools["submit_purchase_order"].inputSchema["required"]) == {
        "tenant", "req_id", "version", "approval_token", "idempotency_key"}
    assert set(tools["get_price_quote"].inputSchema["required"]) == {"tenant", "sku", "quantity"}
    assert set(tools["create_requisition"].inputSchema["required"]) == {
        "tenant", "cost_centre", "lines", "justification"}
    assert set(tools["search_catalogue"].inputSchema["required"]) == {"tenant", "query"}


@pytest.mark.anyio
async def test_in_process_client_returns_store_dicts_and_lists(server):
    async with InProcessErpClient(server) as erp:
        budget = await erp.call("check_budget", {"tenant": "t1", "cost_centre": "CT-OPS"})
        hits = await erp.call("search_catalogue", {"tenant": "t1", "query": "keyboard"})
        quote = await erp.call("get_price_quote",
                               {"tenant": "t1", "sku": hits[0]["sku"], "quantity": 3})
        req = await erp.call("create_requisition", {
            "tenant": "t1", "cost_centre": "CT-OPS",
            "lines": [{"quote_id": quote["quote_id"]}], "justification": "New starters"})
    assert set(budget) >= {"allocated", "committed", "remaining"}
    assert isinstance(hits, list) and hits and "keyboard" in hits[0]["category"]
    assert req["version"] == 1 and req["status"] == "draft" and req["content_hash"]


@pytest.mark.anyio
async def test_in_process_client_is_safe_concurrently(server):
    results = []
    async with InProcessErpClient(server) as erp:
        async def one(i):
            results.append(await erp.call("check_budget", {"tenant": f"t{i}", "cost_centre": "HQ-IT"}))

        async with anyio.create_task_group() as tg:
            for i in range(10):
                tg.start_soon(one, i)
    assert len(results) == 10 and all("remaining" in r for r in results)


@pytest.mark.anyio
async def test_model_tool_schemas_omit_tenant_and_submit(server):
    async with InProcessErpClient(server) as erp:
        tools = model_tools(erp)
    assert [t.name for t in tools] == list(MODEL_TOOL_NAMES)
    assert set(MODEL_TOOL_NAMES) == SERVER_TOOLS - {"submit_purchase_order", "record_approval_event"}
    for t in tools:
        schema = t.tool_call_schema.model_json_schema()
        assert "tenant" not in schema.get("properties", {}), t.name
        assert "config" not in schema.get("properties", {}), t.name
        assert t.description and "\n" not in t.description, t.name
    assert next(t for t in tools if t.name == "create_requisition").description == (
        "Draft a requisition from price quotes. Drafting does not order anything.")


@pytest.mark.anyio
async def test_model_tool_fills_tenant_from_config(server):
    async with InProcessErpClient(server) as erp:
        tools = {t.name: t for t in model_tools(erp)}
        search, quote, create, get_req = (
            tools["search_catalogue"], tools["get_price_quote"], tools["create_requisition"],
            tools["get_requisition"])
        sku = json.loads(await search.ainvoke({"query": "keyboard"}, config=cfg("a")))[0]["sku"]
        q = json.loads(await quote.ainvoke({"sku": sku, "quantity": 3}, config=cfg("a")))
        req = json.loads(await create.ainvoke(
            {"cost_centre": "CT-OPS", "lines": [{"quote_id": q["quote_id"]}],
             "justification": "New starters"}, config=cfg("a")))
        # Spend a's CT-OPS budget so the two tenants' budgets differ.
        token = issue({"req_id": req["req_id"], "version": req["version"],
                       "content_hash": req["content_hash"], "tenant": "a",
                       "approver": "policy", "requested_by": "agent", "reason": "under limit"}, SECRET)
        await erp.call("submit_purchase_order", {
            "tenant": "a", "req_id": req["req_id"], "version": req["version"],
            "approval_token": token, "idempotency_key": f"{req['req_id']}:{req['version']}"})
        # A stray tenant argument from the model is ignored; config decides.
        out_a = await tools["check_budget"].ainvoke(
            {"cost_centre": "CT-OPS", "tenant": "b"}, config=cfg("a"))
        out_b = await tools["check_budget"].ainvoke({"cost_centre": "CT-OPS"}, config=cfg("b"))
        # b cannot see a's requisition.
        missing = await get_req.ainvoke({"req_id": req["req_id"]}, config=cfg("b"))
    a, b = json.loads(out_a), json.loads(out_b)
    assert ": " not in out_a  # compact JSON
    assert a["committed"] == b["committed"] + req["total_zar"]
    assert a["remaining"] == b["remaining"] - req["total_zar"]
    assert missing.startswith("Error: ") and req["req_id"] in missing


@pytest.mark.anyio
async def test_tool_error_becomes_error_text(server):
    async with InProcessErpClient(server) as erp:
        with pytest.raises(ErpToolError) as caught:
            await erp.call("get_price_quote", {"tenant": "t", "sku": "NOPE-1", "quantity": 1})
        tool = next(t for t in model_tools(erp) if t.name == "get_price_quote")
        out = await tool.ainvoke({"sku": "NOPE-1", "quantity": 1}, config=cfg("t"))
    assert str(caught.value) == "There is no catalogue item 'NOPE-1'."
    assert out == "Error: There is no catalogue item 'NOPE-1'."


@pytest.mark.anyio
async def test_unavailable_server_becomes_plain_text():
    erp = HttpErpClient("http://127.0.0.1:9/mcp")
    started = time.monotonic()
    with pytest.raises(ErpUnavailable):
        await erp.call("check_budget", {"tenant": "t", "cost_centre": "CT-OPS"})
    tool = next(t for t in model_tools(erp) if t.name == "check_budget")
    out = await tool.ainvoke({"cost_centre": "CT-OPS"}, config=cfg("t"))
    assert out == "The ERP system is unavailable."
    assert time.monotonic() - started < 20


@pytest.fixture
def http_url(server):
    config = uvicorn.Config(app=server.streamable_http_app(), host="127.0.0.1", port=0,
                            log_level="warning", lifespan="on")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        assert thread.is_alive() and time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.02)
    port = uv.servers[0].sockets[0].getsockname()[1]
    assert port not in (8000, 8765)
    yield f"http://127.0.0.1:{port}/mcp"
    uv.should_exit = True
    thread.join(timeout=10)


@pytest.mark.anyio
async def test_http_transport_round_trip(http_url):
    erp = HttpErpClient(http_url)
    budget = await erp.call("check_budget", {"tenant": "h", "cost_centre": "JHB-FIN"})
    assert set(budget) >= {"allocated", "committed", "remaining"}
    with pytest.raises(ErpToolError) as caught:
        await erp.call("check_budget", {"tenant": "h", "cost_centre": "NOPE"})
    assert str(caught.value).startswith("There is no cost centre 'NOPE'.")
    hits = await erp.call("search_catalogue", {"tenant": "h", "query": "monitor"})
    assert isinstance(hits, list) and hits


@pytest.mark.anyio
async def test_silent_server_times_out_as_unavailable():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        erp = HttpErpClient(f"http://127.0.0.1:{port}/mcp", timeout_s=0.5)
        with pytest.raises(ErpUnavailable):
            await erp.call("check_budget", {"tenant": "t", "cost_centre": "CT-OPS"})


@pytest.mark.anyio
async def test_internal_server_error_is_logged_not_shown(server, store, monkeypatch, caplog):
    import sqlite3

    from agentic_solutions.mcp_servers.erp.server import INTERNAL_ERROR

    def locked(*_a, **_k):
        raise sqlite3.OperationalError("database is locked at /secret/path")

    monkeypatch.setattr(store, "check_budget", locked)
    async with InProcessErpClient(server) as erp:
        with caplog.at_level("ERROR", logger="agentic_solutions.mcp_servers.erp.server"):
            with pytest.raises(ErpToolError) as caught:
                await erp.call("check_budget", {"tenant": "t", "cost_centre": "CT-OPS"})
    assert str(caught.value) == INTERNAL_ERROR
    assert "database is locked" in caplog.text


@pytest.mark.anyio
async def test_model_tool_args_match_server_schemas(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        listed = {t.name: t.inputSchema for t in (await session.list_tools()).tools}
    async with InProcessErpClient(server) as erp:
        tools = model_tools(erp)
    for t in tools:
        mine = t.tool_call_schema.model_json_schema()
        theirs = listed[t.name]
        assert mine["properties"] == {k: v for k, v in theirs["properties"].items()
                                      if k != "tenant"}, t.name
        assert set(mine.get("required", [])) == set(theirs["required"]) - {"tenant"}, t.name
        assert mine.get("$defs", {}) == theirs.get("$defs", {}), t.name


@pytest.mark.anyio
async def test_quantity_bounds_on_both_sides(server):
    async with InProcessErpClient(server) as erp:
        sku = (await erp.call("search_catalogue", {"tenant": "t", "query": "keyboard"}))[0]["sku"]
        for bad in (0, 1000):
            with pytest.raises(ErpToolError):
                await erp.call("get_price_quote", {"tenant": "t", "sku": sku, "quantity": bad})
        tool = next(t for t in model_tools(erp) if t.name == "get_price_quote")
        out = await tool.ainvoke({"sku": sku, "quantity": 1000}, config=cfg("t"))
    assert out.startswith("Error: invalid arguments (quantity:")


@pytest.mark.anyio
async def test_model_tool_without_thread_id_raises_and_calls_nothing():
    class Recorder:
        def __init__(self):
            self.calls = []

        async def call(self, tool, args):
            self.calls.append((tool, args))
            return {}

    erp = Recorder()
    tool = next(t for t in model_tools(erp) if t.name == "check_budget")
    for config in ({}, {"configurable": {}}, {"configurable": {"thread_id": ""}}):
        with pytest.raises(ValueError):
            await tool.ainvoke({"cost_centre": "CT-OPS"}, config=config)
    assert erp.calls == []
