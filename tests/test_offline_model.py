from langchain_core.messages import HumanMessage
from agentic_solutions.web.offline.model import Rule, Script, ScriptedChatModel

SCRIPT = Script(rules=(Rule("langgraph", "LangGraph builds agents as graphs."),), fallback="(Offline demo) fallback")

def model():
    return ScriptedChatModel(script=SCRIPT, latency=(0, 0), tokens_per_second=0)  # 0 = no pacing

def test_matching_rule_replies_and_records_index():
    m = model()
    assert m.invoke([HumanMessage("What is LangGraph?")]).content == "LangGraph builds agents as graphs."
    assert m.matched_rule == 0

def test_fallback_when_nothing_matches():
    m = model()
    assert m.invoke([HumanMessage("weather?")]).content == "(Offline demo) fallback"
    assert m.matched_rule is None

def test_stream_yields_several_chunks_that_join_to_reply():
    chunks = list(model().stream([HumanMessage("langgraph")]))
    assert len(chunks) > 1 and "".join(c.content for c in chunks) == "LangGraph builds agents as graphs."

def test_reply_reports_usage_metadata():
    assert model().invoke([HumanMessage("langgraph")]).usage_metadata["total_tokens"] > 0


# --- tool calling ---------------------------------------------------------
import asyncio
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

CALL = {"name": "create_po", "args": {"sku": "A1", "qty": 3}, "id": "call_x", "type": "tool_call"}


@tool
def create_po(sku: str, qty: int) -> str:
    """Create a purchase order."""
    return "ok"


def na(calls):
    return [(c["name"], c["args"]) for c in calls]


def tool_model(reply=None, fallback="fb"):
    reply = reply or AIMessage(content="Ordering.", tool_calls=[CALL])
    s = Script(rules=(Rule("order", reply),), fallback=fallback)
    return ScriptedChatModel(script=s, latency=(0, 0), tokens_per_second=0)


def test_tool_call_reply_round_trip():
    bound = tool_model().bind_tools([create_po])
    msgs = [HumanMessage("please order")]
    out = asyncio.run(bound.ainvoke(msgs))
    assert na(out.tool_calls) == na([CALL]) and out.content == "Ordering."

    async def stream():
        agg = None
        async for c in bound.astream(msgs):
            agg = c if agg is None else agg + c
        return agg

    agg = asyncio.run(stream())
    assert na(agg.tool_calls) == na([CALL]) and agg.content == "Ordering."

    class S(TypedDict):
        messages: Annotated[list, add_messages]

    async def node(state):
        return {"messages": [await bound.ainvoke(state["messages"])]}

    g = StateGraph(S)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    app = g.compile()

    async def run():
        final = None
        async for mode, data in app.astream({"messages": msgs}, stream_mode=["messages", "values"]):
            if mode == "values":
                final = data
        return final

    final = asyncio.run(run())
    assert na(final["messages"][-1].tool_calls) == na([CALL])


def test_tool_call_without_id_gets_one_unused():
    bound = tool_model(AIMessage(content="", tool_calls=[{"name": "create_po", "args": {}, "id": None}])).bind_tools([create_po])
    out = bound.invoke([HumanMessage("order")])
    assert out.tool_calls[0]["id"].startswith("call_")


def test_bind_tools_returns_independent_copy():
    m = tool_model()
    b = m.bind_tools([create_po])
    assert b is not m and b.bound and not m.bound
    assert b.bound_tool_names == ("create_po",)


def test_tool_choice_none_strips_tool_calls():
    m = tool_model()
    out = m.bind_tools([create_po], tool_choice="none").invoke([HumanMessage("order")])
    assert out.tool_calls == [] and out.content == "Ordering."
    out = m.bind_tools([create_po], tool_choice={"type": "none"}).invoke([HumanMessage("order")])
    assert out.tool_calls == []
    empty = tool_model(AIMessage(content="", tool_calls=[CALL]), fallback="Summary text.")
    out = empty.bind_tools([create_po], tool_choice="none").invoke([HumanMessage("order")])
    assert out.tool_calls == [] and out.content == "Summary text."


def test_callable_rule_sees_whole_history():
    seen = []

    def reply(messages):
        seen.append(len(messages))
        return "got %d" % len(messages)

    m = tool_model(reply)
    out = m.invoke([HumanMessage("order"), AIMessage("a"), HumanMessage("order again")])
    assert seen == [3] and out.content == "got 3"


def test_kind_restricts_rule():
    s = Script(
        rules=(
            Rule("order", AIMessage(content="", tool_calls=[CALL]), kind="tools"),
            Rule("order", "plain", kind="text"),
        ),
        fallback="fb",
    )
    m = ScriptedChatModel(script=s, latency=(0, 0), tokens_per_second=0)
    assert m.invoke([HumanMessage("order")]).content == "plain" and m.matched_rule == 1
    out = m.bind_tools([create_po]).invoke([HumanMessage("order")])
    assert na(out.tool_calls) == na([CALL])
    only_tools = ScriptedChatModel(script=Script(rules=(s.rules[0],), fallback="fb"), latency=(0, 0), tokens_per_second=0)
    assert only_tools.invoke([HumanMessage("order")]).content == "fb"


def test_unbound_text_streaming_unchanged():
    chunks = list(model().stream([HumanMessage("langgraph")]))
    assert len(chunks) > 1 and all(not c.tool_call_chunks for c in chunks)
    assert "".join(c.content for c in chunks) == "LangGraph builds agents as graphs."


def test_tool_call_ids_are_unique_per_call_and_per_message():
    two = AIMessage(content="", tool_calls=[CALL, {**CALL, "args": {"sku": "B"}}])
    bound = tool_model(two).bind_tools([create_po])
    a = bound.invoke([HumanMessage("order")])
    b = bound.invoke([HumanMessage("order")])
    ids = [c["id"] for c in a.tool_calls + b.tool_calls]
    assert len(set(ids)) == 4 and all(i.startswith("call_") for i in ids)
    assert "call_x" not in ids


def test_stream_and_invoke_ids_match_within_a_call():
    bound = tool_model().bind_tools([create_po])

    async def stream():
        agg = None
        async for c in bound.astream([HumanMessage("order")]):
            agg = c if agg is None else agg + c
        return agg

    agg = asyncio.run(stream())
    assert agg.tool_calls[0]["id"].startswith("call_") and agg.tool_calls[0]["id"] != "call_x"


def test_tool_choice_none_streaming_has_no_tool_chunks():
    bound = tool_model().bind_tools([create_po], tool_choice="none")

    async def stream():
        return [c async for c in bound.astream([HumanMessage("order")])]

    chunks = asyncio.run(stream())
    assert all(not c.tool_call_chunks for c in chunks)
    assert "".join(c.content for c in chunks) == "Ordering."
