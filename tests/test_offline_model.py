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
