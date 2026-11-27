"""Semantic memory: a ReAct agent that answers from Paradise Lost, through the library MCP server.

    START -> ask --(question)--> agent --(search / read)--> tools -> grade --(relevant)--> agent
              ^  --(stop)--> END   \\--(answer)--> ask              \\--(none relevant)--> rewrite_query -> tools
              +--(empty)--+

Semantic memory is facts looked up from a document store. Here the store is a
Qdrant index of the poem (hybrid dense + BM25 search), behind two MCP tools:
`search_book` and `read_passage`. The model is told to answer only from the
passages the tools return, and to cite the Book and lines.

Every search result is graded passage by passage: `grade` drops passages that
don't help answer the question before the agent sees them. When none are
relevant, `rewrite_query` rephrases the search and it runs again, at most
MAX_REWRITES times per question. The grader and the rewriter each call the
selected model with one forced tool, so their replies are structured.

Using the store is not left to the prompt alone. The first model call of every
question is bound with `tool_choice="search_book"`, and if a model answers in
text anyway, the agent replaces that answer with the search. After
MAX_TOOL_ROUNDS tool rounds the model must answer in text.
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import uuid4

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from agentic_solutions.agents.chat_agent.graph import STOP_WORD
from agentic_solutions.agents.interrupt_chat_agent.graph import ask as ask_for_text
from agentic_solutions.common.llm import LLMFactory, declined_or, get_llm

from .library import LibraryClient, library_tools

MAX_TOOL_ROUNDS = 6
MAX_REWRITES = 2
FORCED_TOOL = "search_book"
# Anthropic's form; ChatAnthropic turns the bare string "none" into "force a tool named none".
NO_TOOLS = {"type": "none"}
STEP_LIMIT = "I've reached the search limit for this question. Here is what the passages showed."

SYSTEM_PROMPT = "\n".join((
    "You answer questions about John Milton's Paradise Lost using only passages returned by the "
    "search_book and read_passage tools. Do not use what you already know about the poem, its plot, "
    "or its criticism.",
    "Search before answering. Search again with different words if the passages don't answer the "
    "question. Use read_passage to read around a passage, or to reach a known place such as the end "
    "of Book XII.",
    "Answer simply and concisely, in two or three plain sentences. Put no citations, quotations or "
    "line numbers in the answer itself.",
    'Then list your sources at the end, under the heading "Sources:", one per line, in this form: '
    '- Book I, 254–263: “the exact words you relied on”. Quote the text exactly.',
    "For each source, give the passage's Book, start_line and end_line exactly as the tool returned "
    "them. Do not count lines within a passage yourself.",
    "If the passages don't answer the question, say so in one sentence, say what you searched for, "
    "and list no sources. Don't fill the gap from memory.",
    "Line numbers follow this edition.",
))

GRADER_PROMPT = "\n".join((
    "You grade search results for a question about Paradise Lost.",
    "Decide which passages help answer the question. A passage is relevant if it contains information "
    "the answer needs. It is not relevant if it only shares words or names with the question.",
    "Call grade_passages with the numbers of the relevant passages; an empty list if none are.",
))
REWRITER_PROMPT = "\n".join((
    "You rewrite a search query for Paradise Lost.",
    "The searches so far found no relevant passages. Write one new search query that uses different "
    "words: the poem's own vocabulary, a character's name, or the event or place involved. Do not "
    "repeat a query already tried. Call rewrite_search with the new query.",
))


def _grade_passages(relevant: list[int]) -> str:
    """The numbers of the passages that help answer the question; [] if none."""
    return ""


def _rewrite_search(query: str) -> str:
    """One new search query, in different words."""
    return ""


GRADE_TOOL = StructuredTool.from_function(_grade_passages, name="grade_passages")
REWRITE_TOOL = StructuredTool.from_function(_rewrite_search, name="rewrite_search")


def grade_input(question: str, passages: list[dict]) -> str:
    listed = "\n\n".join(f"[{i}] Book {p['book']}, {p['start_line']}–{p['end_line']}:\n{p['text']}"
                          for i, p in enumerate(passages, start=1))
    return f"Question: {question}\n\nPassages:\n{listed}"


def rewrite_input(question: str, tried: list[str]) -> str:
    return f"Question: {question}\nQueries tried:\n" + "\n".join(f"- {q}" for q in tried)


# What the Studio draws on each conditional edge: (short label, full rule).
EDGE_LABELS = {
    ("ask", "__end__"): ("stop", 'You typed "stop": the conversation ends.'),
    ("ask", "ask"): ("empty", "Empty message: wait for the next one."),
    ("ask", "agent"): ("question", "Any other message goes to the agent."),
    ("agent", "tools"): ("search / read",
                         f"The model called a library tool ({MAX_TOOL_ROUNDS} rounds per question at most). "
                         "The first call of every question is always a search."),
    ("agent", "ask"): ("answer", "The model answered from the passages, or said they don't cover the question."),
    ("grade", "agent"): ("relevant", "At least one passage is relevant (the others are dropped), or the search "
                                     "was a read by position, or the rewrite limit was reached."),
    ("grade", "rewrite_query"): ("none relevant", f"No passage is relevant: rephrase the search "
                                                  f"({MAX_REWRITES} times per question at most)."),
    ("rewrite_query", "tools"): ("new query", "Search again with the rewritten query."),
    ("rewrite_query", "agent"): ("no new query", "No new query could be written: the agent answers from what it has."),
}


# The Studio draws Semantic from fixed positions, as it does Approval: in the
# automatic layout the paired edges (ask <-> agent, agent <-> tools) overlap and
# their labels and run counts collide. A bend bows an edge's curve, so the two
# directions between a pair of nodes stay apart.
LAYOUT = {
    "positions": {
        "__start__": (250, 0), "ask": (250, 120), "__end__": (520, 120),
        "agent": (250, 300), "tools": (500, 300), "grade": (750, 300),
        "rewrite_query": (625, 450),
    },
    "bends": {
        ("ask", "agent"): 60, ("agent", "ask"): 60,
        ("grade", "agent"): 110,  # arcs back over the agent -> tools -> grade row
    },
}


class State(TypedDict):
    messages: Annotated[list, add_messages]
    tool_rounds: int
    rewrites: int


def _this_question(messages: list) -> list:
    """The messages since the latest human message."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].type == "human":
            return messages[i + 1:]
    return list(messages)


def _relevant_numbers(reply: AIMessage) -> list | None:
    """The grader's numbers, or None if it did not call grade_passages properly."""
    for call in reply.tool_calls:
        if call["name"] == "grade_passages":
            relevant = call["args"].get("relevant")
            return relevant if isinstance(relevant, list) else None
    return None


def _question(state: State) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return message.content if isinstance(message.content, str) else str(message.content)
    return ""


def build_graph(*, library: LibraryClient, checkpointer=None, llm_factory: LLMFactory | None = None):
    """Wire the Semantic agent. `library` is the MCP client for the library server."""
    tools = library_tools(library)

    def ask(state: State) -> Command[Literal["agent", "ask", "__end__"]]:
        """Wait for the visitor's next question (the reused interrupt `ask`)."""
        update = ask_for_text(state)
        text = str(update["messages"][0][1]).strip()
        if not text:
            return Command(goto="ask")
        if text.lower() == STOP_WORD:
            return Command(goto=END, update={**update, "tool_rounds": 0, "rewrites": 0})
        return Command(goto="agent", update={**update, "tool_rounds": 0, "rewrites": 0})

    async def agent(state: State, config: RunnableConfig) -> Command[Literal["tools", "ask"]]:
        rounds = state.get("tool_rounds", 0)
        llm = (llm_factory or get_llm)()
        if rounds == 0:
            llm = llm.bind_tools(tools, tool_choice=FORCED_TOOL)  # the first step is always a search
        elif rounds >= MAX_TOOL_ROUNDS:
            llm = llm.bind_tools(tools, tool_choice=NO_TOOLS)
        else:
            llm = llm.bind_tools(tools)
        reply = declined_or(await llm.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]], config))
        calls = reply.tool_calls
        if rounds >= MAX_TOOL_ROUNDS and calls:
            # Defence in depth: a model that ignores tool_choice still cannot pass the cap.
            reply = AIMessage(reply.text.strip() or STEP_LIMIT)
            calls = []
        if rounds == 0 and not any(c["name"] == FORCED_TOOL for c in calls):
            # A model that ignored the forced choice: search with the question, and drop its reply.
            reply = AIMessage("", tool_calls=[{"name": FORCED_TOOL, "args": {"query": _question(state)},
                                               "id": f"forced-search-{uuid4().hex[:12]}"}])
            calls = reply.tool_calls
        if calls:
            return Command(goto="tools", update={"messages": [reply], "tool_rounds": rounds + 1})
        return Command(goto="ask", update={"messages": [reply]})

    async def grade(state: State, config: RunnableConfig) -> Command[Literal["agent", "rewrite_query"]]:
        """Drop the passages that don't help answer the question; rewrite the query if none do."""
        messages = state["messages"]
        call_msg = next((m for m in reversed(messages) if m.type == "ai" and m.tool_calls), None)
        search_ids = {c["id"] for c in (call_msg.tool_calls if call_msg else []) if c["name"] == "search_book"}
        results = [m for m in messages if m.type == "tool" and m.tool_call_id in search_ids]
        if not results:
            return Command(goto="agent")  # a read by position: nothing to grade
        parsed = []  # (tool message, its passages) for results that are lists of passages
        for m in results:
            try:
                data = json.loads(m.content)
            except (TypeError, ValueError):
                continue
            if isinstance(data, list) and all(isinstance(p, dict) and "text" in p for p in data):
                parsed.append((m, data))
        passages = [p for _, data in parsed for p in data]
        rounds, rewrites = state.get("tool_rounds", 0), state.get("rewrites", 0)
        can_rewrite = rewrites < MAX_REWRITES and rounds < MAX_TOOL_ROUNDS
        if not parsed:
            return Command(goto="agent")  # errors or unexpected content: pass through
        if not passages:
            return Command(goto="rewrite_query" if can_rewrite else "agent")
        try:
            llm = (llm_factory or get_llm)().bind_tools([GRADE_TOOL], tool_choice="grade_passages")
            reply = await llm.ainvoke([SystemMessage(GRADER_PROMPT),
                                       HumanMessage(grade_input(_question(state), passages))], config)
            numbers = _relevant_numbers(reply)
        except Exception:  # a failing grader must not lose the passages
            numbers = None
        valid = {n for n in numbers or [] if isinstance(n, int) and not isinstance(n, bool)
                 and 1 <= n <= len(passages)}
        if numbers is None or (numbers and not valid):
            return Command(goto="agent")  # malformed: pass the passages through unchanged
        graded, start = [], 1
        for m, data in parsed:
            kept = [p for i, p in enumerate(data, start=start) if i in valid]
            start += len(data)
            content = json.dumps({"passages": kept, "not_relevant": len(data) - len(kept)},
                                 ensure_ascii=False, separators=(",", ":"))
            graded.append(ToolMessage(content=content, tool_call_id=m.tool_call_id, name=m.name, id=m.id))
        if valid or not can_rewrite:
            return Command(goto="agent", update={"messages": graded})
        return Command(goto="rewrite_query", update={"messages": graded})

    async def rewrite_query(state: State, config: RunnableConfig) -> Command[Literal["tools", "agent"]]:
        """Rephrase the search after a round with no relevant passages, and run it again."""
        question = _question(state)
        tried = [c["args"].get("query", "") for m in _this_question(state["messages"]) if m.type == "ai"
                 for c in m.tool_calls if c["name"] == "search_book"]
        query = None
        try:
            llm = (llm_factory or get_llm)().bind_tools([REWRITE_TOOL], tool_choice="rewrite_search")
            reply = await llm.ainvoke([SystemMessage(REWRITER_PROMPT),
                                       HumanMessage(rewrite_input(question, tried))], config)
            call = next((c for c in reply.tool_calls if c["name"] == "rewrite_search"), None)
            if call and isinstance(call["args"].get("query"), str) and call["args"]["query"].strip():
                query = call["args"]["query"].strip()
        except Exception:
            query = None
        if query is None:  # fallback: the question without the last query's words
            last = set((tried[-1] if tried else "").lower().split())
            query = " ".join(w for w in question.split() if w.lower() not in last).strip() or None
        if query is None:
            return Command(goto="agent")
        call = {"name": FORCED_TOOL, "args": {"query": query}, "id": f"rewrite-{uuid4().hex[:12]}"}
        return Command(goto="tools", update={
            "messages": [AIMessage("", tool_calls=[call])],
            "rewrites": state.get("rewrites", 0) + 1,
            "tool_rounds": state.get("tool_rounds", 0) + 1})

    builder = StateGraph(State)
    builder.add_node("ask", ask)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("grade", grade)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_edge(START, "ask")
    builder.add_edge("tools", "grade")
    return builder.compile(checkpointer=checkpointer)
