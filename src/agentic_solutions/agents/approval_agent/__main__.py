"""Run the approval agent:  python -m agentic_solutions.agents.approval_agent

Ask for an order, e.g. "Order 12 laptops for the Cape Town office under CT-OPS".
Small orders are approved by policy; larger ones pause and ask YOU to approve,
edit or reject. Type "stop" to quit.

By default the mock ERP runs in this process (over MCP's in-memory transport)
with a random approval secret. Set ERP_MCP_URL (and ERP_APPROVAL_SECRET, the
same one the server uses) to talk to a separate ERP server over HTTP instead.

Like the interrupt chat lesson, this file is the CALLER: it runs the graph until
it pauses, asks the person, then resumes it with `Command(resume=...)`.
"""

import asyncio
import os
from contextlib import AsyncExitStack
from uuid import uuid4

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_solutions.agents.approval_agent.erp import HttpErpClient, InProcessErpClient
from agentic_solutions.agents.approval_agent.graph import STOP_WORD, build_graph
from agentic_solutions.common.approval_tokens import issue
from agentic_solutions.common.errors import UserFacingError
from agentic_solutions.common.llm import get_llm
from agentic_solutions.mcp_servers.erp.config import ErpSettings
from agentic_solutions.mcp_servers.erp.policy import format_zar
from agentic_solutions.mcp_servers.erp.server import build_server
from agentic_solutions.mcp_servers.erp.store import ErpStore


async def prompt(text: str) -> str:
    # input() blocks; run it in a thread so the in-process ERP session stays alive.
    try:
        return await asyncio.to_thread(input, text)
    except EOFError:  # Ctrl+Z / Ctrl+D: same as "stop"
        return STOP_WORD


def show_card(card: dict) -> None:
    print(f"\n=== Approval needed: {card['req_id']} v{card['version']} "
          f"(#{card['short_hash']}) ===")
    if card["requoted"]:
        print("Prices were re-quoted.")
    print(f"{'SKU':<9} {'Item':<36} {'Qty':>4} {'Unit':>10} {'Line':>11}")
    for line in card["lines"]:
        print(f"{line['sku']:<9} {line['name'][:36]:<36} {line['quantity']:>4} "
              f"{format_zar(line['unit_price_zar']):>10} {format_zar(line['line_total_zar']):>11}")
    print(f"Total {format_zar(card['total_zar'])} on {card['cost_centre']} "
          f"(budget remaining {format_zar(card['budget_remaining'])})")
    print(f"{card['policy_reason']}. Quotes expire at {card['quote_expires_at']}.")


async def ask_decision(card: dict) -> dict:
    while True:
        choice = (await prompt("\n[a]pprove, [e]dit or [r]eject? ")).strip().lower()
        if choice in ("a", "approve"):
            return {"decision": "approve"}
        if choice in ("r", "reject"):
            return {"decision": "reject", "reason": (await prompt("Reason: ")).strip()}
        if choice in ("e", "edit"):
            sku = (await prompt("SKU: ")).strip().upper()
            if sku not in {line["sku"] for line in card["lines"]}:
                print("That SKU is not on this order.")
                continue
            try:
                quantity = int(await prompt("New quantity (1-999): "))
            except ValueError:
                print("Give a whole number.")
                continue
            return {"decision": "edit", "edits": [{"sku": sku, "quantity": quantity}]}


async def chat(erp, issue_token, limit: float) -> None:
    graph = build_graph(erp=erp, issue_token=issue_token, auto_limit_zar=limit,
                        checkpointer=InMemorySaver(), llm_factory=get_llm)
    # The thread id is also the ERP tenant: a fresh one gets fresh budgets.
    config = {"configurable": {"thread_id": f"cli-{uuid4().hex[:8]}", "approver": "visitor:cli"}}
    print(f'Ask me to order something. Type "{STOP_WORD}" to quit.')

    graph_input = {"messages": []}
    while True:
        try:
            async for update in graph.astream(graph_input, config, stream_mode="updates"):
                for node in ("agent", "submit_po"):
                    for msg in ((update.get(node) or {}).get("messages") or []):
                        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                            print(f"\nAgent: {msg.content}")
        except UserFacingError as err:
            print(f"\nError: {err}")

        state = await graph.aget_state(config)
        if not state.next:
            break
        interrupts = [i for task in state.tasks for i in task.interrupts]
        if not interrupts:
            # A node failed (e.g. the ERP went down in policy or submit_po), so
            # nothing is waiting for input. The error was printed above.
            print("\nThe run stopped. Start the agent again to retry.")
            break
        pause = interrupts[0].value
        if isinstance(pause, dict) and pause.get("kind") == "approval_request":
            show_card(pause)
            graph_input = Command(resume=await ask_decision(pause))
        else:
            graph_input = Command(resume=await prompt(f"\n{pause}\nYou: "))
    print("\nGoodbye!")


async def main() -> None:
    url = os.environ.get("ERP_MCP_URL")
    async with AsyncExitStack() as stack:
        if url:
            secret = os.environ.get("ERP_APPROVAL_SECRET")
            if not secret:
                raise SystemExit("ERP_MCP_URL is set, so ERP_APPROVAL_SECRET must be too "
                                 "(the same secret the ERP server uses).")
            settings = ErpSettings.from_env()
            erp = HttpErpClient(url)
        else:
            settings = ErpSettings.from_env()  # random secret unless ERP_APPROVAL_SECRET is set
            store = ErpStore(settings.db, secret=settings.secret,
                             auto_limit_zar=settings.auto_limit_zar,
                             tenant_ttl_hours=settings.tenant_ttl_hours)
            stack.callback(store.close)
            erp = await stack.enter_async_context(
                InProcessErpClient(build_server(store, settings)))
        await chat(erp, lambda claims: issue(claims, settings.secret), settings.auto_limit_zar)


if __name__ == "__main__":
    asyncio.run(main())
