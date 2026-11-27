"""Semantic memory: a ReAct agent that answers from Paradise Lost, through the library MCP server.

    START -> ask --(question)--> agent --(search / read)--> tools -> agent
              ^  --(stop)--> END   \\--(answer)--> ask
              +--(empty)--+

Semantic memory is facts looked up from a document store. Here the store is a
Qdrant index of the poem (hybrid dense + BM25 search), behind two MCP tools:
`search_book` and `read_passage`. The model is told to answer only from the
passages the tools return, and to cite the Book and lines.

Using the store is not left to the prompt alone. The first model call of every
question is bound with `tool_choice="search_book"`, and if a model answers in
text anyway, the agent replaces that answer with the search. After
MAX_TOOL_ROUNDS tool rounds the model must answer in text.
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from agentic_solutions.agents.chat_agent.graph import STOP_WORD
from agentic_solutions.agents.interrupt_chat_agent.graph import ask as ask_for_text
from agentic_solutions.common.llm import LLMFactory, declined_or, get_llm

from .library import LibraryClient, library_tools

MAX_TOOL_ROUNDS = 6
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
    "Cite every claim with its Book and line range, for example (Book I, 271–291). Quote exactly "
    "when quoting.",
    "If the passages don't answer the question, say so plainly and say what you searched for. "
    "Don't fill the gap from memory.",
    "Line numbers follow this edition.",
))

# What the Studio draws on each conditional edge: (short label, full rule).
EDGE_LABELS = {
    ("ask", "__end__"): ("stop", 'You typed "stop": the conversation ends.'),
    ("ask", "ask"): ("empty", "Empty message: wait for the next one."),
    ("ask", "agent"): ("question", "Any other message goes to the agent."),
    ("agent", "tools"): ("search / read",
                         f"The model called a library tool ({MAX_TOOL_ROUNDS} rounds per question at most). "
                         "The first call of every question is always a search."),
    ("agent", "ask"): ("answer", "The model answered from the passages, or said they don't cover the question."),
}


class State(TypedDict):
    messages: Annotated[list, add_messages]
    tool_rounds: int


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
            return Command(goto=END, update={**update, "tool_rounds": 0})
        return Command(goto="agent", update={**update, "tool_rounds": 0})

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
        if rounds == 0 and not calls:
            # A model that ignored the forced choice: search with the question, and drop its text.
            reply = AIMessage("", tool_calls=[
                {"name": FORCED_TOOL, "args": {"query": _question(state)}, "id": "forced-search"}])
            calls = reply.tool_calls
        if calls:
            return Command(goto="tools", update={"messages": [reply], "tool_rounds": rounds + 1})
        return Command(goto="ask", update={"messages": [reply]})

    builder = StateGraph(State)
    builder.add_node("ask", ask)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "ask")
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)
