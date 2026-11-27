"""Offline scripts: canned, teaching-oriented replies for each pattern.

Each script is an ordered list of rules. A rule matches when its keyword is a
case-insensitive substring of the latest human message, and the first match
wins. Every sample input offered in the UI, and every input a Guide's "Try
this" section suggests, has its own rule; anything else falls through to the
pattern's fallback reply.
"""

import json
import re

from langchain_core.messages import AIMessage, BaseMessage

from agentic_solutions.web.offline.model import Rule, Script

OFFLINE_NOTE = "(Offline demo: scripted response. Unlock Live mode for real answers.)"


def _fallback(lead: str) -> str:
    return f"{lead} {OFFLINE_NOTE}"


_NAME = re.compile(r"\bmy name is\s+([A-Za-z][\w'-]*)", re.IGNORECASE)


def _given_name(messages: list[BaseMessage]) -> str | None:
    """The latest name the user gave with "My name is ..." in this thread."""
    for m in reversed(messages):
        if m.type == "human" and isinstance(m.content, str):
            found = _NAME.search(m.content)
            if found:
                return found.group(1)
    return None


def _greet(messages: list[BaseMessage]) -> str:
    name = _given_name(messages) or "there"
    return (f"Nice to meet you, {name}. Your message is now in the messages list, which "
            "the checkpointer saves for this thread. Ask 'What is my name?' next to see the "
            "graph remember it.")


def _recall(messages: list[BaseMessage]) -> str:
    name = _given_name(messages[:-1])
    if name is None:
        return ("You haven't told me your name in this chat yet. Say 'My name is Sam.' first, "
                "then ask again.")
    return (f"You told me your name is {name}. This reply is scripted, but the name is real: "
            "it was read from the earlier message in this thread, because every turn sends "
            "the whole message list back to the model.")


QA = Script(
    rules=(
        Rule("reducer",
             "A reducer decides how a node's update merges into one state key. Without one the "
             "new value replaces the old; with Annotated[list, add_messages] LangGraph "
             "appends the new messages instead. That is how chat graphs keep their history."),
        Rule("langgraph",
             "LangGraph models an agent as a graph: nodes are Python functions that read and "
             "update a shared state, and edges decide which node runs next. Because the flow is "
             "explicit, you can loop, branch, pause and inspect every step."),
        Rule("single llm call",
             "A single LLM call sends one prompt and gets one answer, with no loop, tools or "
             "memory. It is the simplest pattern and often the right one: start here, and add "
             "structure only when the task proves it needs it."),
        Rule("explain that",
             "I can't tell what \"that\" refers to: this graph makes one fresh call per run "
             "and keeps no memory, so your earlier question is not in my input. The Chat loop "
             "pattern fills this gap by keeping the message list between turns."),
        Rule("state",
             "State is the data that flows through a graph, usually a TypedDict. Each node "
             "returns a partial update, and a reducer such as add_messages decides how that "
             "update merges in, for example by appending to the message list."),
    ),
    fallback=_fallback("This pattern makes one model call: your question goes in and one answer "
                       "comes out, with nothing remembered afterwards."),
)

CHAT_LOOP = Script(
    rules=(
        Rule("what is my name", _recall),
        Rule("my name is", _greet),
        Rule("remember",
             "The graph remembers through its state: the add_messages reducer appends every "
             "question and answer to the message list, and a checkpointer saves that list per "
             "thread. Each new turn sends the whole history back to the model."),
        Rule("conditional edge",
             "A conditional edge is a router function that looks at the state and returns the "
             "name of the next node. Here it sends 'stop' to the end, empty input back to ask, "
             "and everything else to answer."),
        Rule("loop",
             "Graphs can contain cycles: after answer, an edge leads back to ask, so the "
             "conversation continues until the router sends you to END. Loops are what turn a "
             "single call into a chat."),
    ),
    fallback=_fallback("In this loop the graph asks for your message, routes it to the model, "
                       "appends the reply to its memory, then asks again."),
)

GUARDRAIL = Script(
    rules=(
        Rule("capital of france",
             "The capital of France is Paris. Your question passed the guard, so it reached "
             "the model: the trace went ask, guard, answer."),
        Rule("embedding",
             "An embedding turns text into a vector so similar meanings land close together. "
             "The guard embeds your prompt and compares it with a library of known attack "
             "phrases, so reworded attacks can still be caught."),
        Rule("guardrail",
             "A guardrail is a check placed around the model. This one screens the prompt "
             "before the model sees it, so a risky request is refused by fixed code instead of "
             "relying on the model to resist it."),
        Rule("prompt injection",
             "Prompt injection hides instructions in the input to hijack the model, such as "
             "'ignore previous instructions'. Screening input before it reaches the model, as "
             "this graph does, is one layer of defense, not a complete one."),
    ),
    fallback=_fallback("Your message passed the guard, so it reached the model. Had it matched "
                       "a known attack, the refuse node would have answered instead."),
)

# ------------------------------------------------------------------ approval
#
# The approval agent always calls a tool-bound model, so these rules are kind
# "tools". The ERP is real; only the model's choices are scripted. Each call
# reads the tool results so far in this turn and makes the next step:
# search -> budget -> quote -> draft -> propose_order. After propose_order is
# answered (a reject, an ERP refusal, an expired draft) it explains in text.

APPROVAL_SAMPLES = (
    "Order 12 laptops for the Cape Town office under CT-OPS",
    "Order 3 keyboards for CT-OPS",
    "Order 40 monitors for JHB-FIN",
)

# An order must start the message ("Order 3 ...", "Please buy 3 ..."), so
# "Don't order ...", "reorder ..." and questions about an order never place one.
_ORDER = re.compile(
    r"\s*(?:please\s+)?(?:order|buy)\s+(\d+)\s+(.+?)\s+(?:for|under)\s+.*?\b(CT-OPS|JHB-FIN|DBN-LOG|HQ-IT)\b",
    re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:don'?t|do\s+not|never|not|cancel|stop)\b", re.IGNORECASE)


def _find_order(text: str) -> re.Match | None:
    """The order in this message, or None if it does not start with one or says not to."""
    if _NEGATION.search(text.replace("\u2019", "'")):
        return None
    return _ORDER.match(text)


def _singular(word: str) -> str:
    """Drop a simple plural: "laptops" -> "laptop". Short words and "-ss" words stay."""
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "scripted"}])


def _this_turn(messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
    """The latest human text and the messages after it."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].type == "human":
            return _text_of(messages[i]), messages[i + 1:]
    return "", []


def _text_of(message: BaseMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def _explain_outcome(result: str) -> str:
    """Plain words for whatever answered propose_order, and a next step."""
    if result.startswith("The approver rejected this order."):
        return (f"{result} Nothing was ordered. Tell me what to change, for example fewer units "
                "or another cost centre, and I'll draft a new requisition.")
    refused = "The ERP refused the order: "
    if result.startswith(refused):
        return (f"The ERP refused the order, so nothing was ordered. Its reason: "
                f"{result[len(refused):]} Try a smaller quantity, or a cost centre with more "
                "budget left, and I'll draft it again.")
    return (f"{result} Nothing new was ordered. Send the order again and I'll draft a fresh "
            "requisition.")


def _order_step(messages: list[BaseMessage]) -> str | AIMessage:
    human, turn = _this_turn(messages)
    found = _find_order(human)
    if not found:
        return _approval_fallback(messages)
    qty, item, cc = int(found.group(1)), found.group(2), found.group(3).upper()
    query = " ".join(_singular(w) for w in item.split())
    results = {m.name: _text_of(m) for m in turn if m.type == "tool"}
    last = next((m for m in reversed(turn) if m.type == "tool"), None)
    if last is None:
        return _call("search_catalogue", query=query)
    content = _text_of(last)
    if last.name == "propose_order":
        return _explain_outcome(content)
    if content.startswith("Error") or not content.startswith(("{", "[")):
        return f"I couldn't finish drafting that order: {content} Nothing was ordered."
    if last.name == "search_catalogue":
        if not json.loads(content):
            return (f"I couldn't find \"{query}\" in the catalogue, so nothing was drafted. "
                    "Try laptops, keyboards or monitors.")
        return _call("check_budget", cost_centre=cc)
    if last.name == "check_budget":
        sku = json.loads(results["search_catalogue"])[0]["sku"]
        return _call("get_price_quote", sku=sku, quantity=qty)
    if last.name == "get_price_quote":
        return _call("create_requisition", cost_centre=cc,
                     lines=[{"quote_id": json.loads(content)["quote_id"]}], justification=human)
    if last.name == "create_requisition":
        req = json.loads(content)
        return _call("propose_order", req_id=req["req_id"],
                     summary=f"{qty} x {query} for {cc}")
    return "I've done what I can for this order. Nothing more was changed."


def _approval_fallback(_messages: list[BaseMessage]) -> str:
    listed = "; ".join(f'"{s}"' for s in APPROVAL_SAMPLES)
    return _fallback(
        "I'm a procurement assistant: I can draft a purchase order on the mock ERP and propose "
        "it, but a policy or you must approve it before anything is ordered. Ask in the form "
        "\"Order <quantity> <item> for <cost centre>\", with a cost centre of CT-OPS, JHB-FIN, "
        f"DBN-LOG or HQ-IT. Try one of: {listed}.")


APPROVAL = Script(
    rules=(
        Rule(lambda text: bool(_find_order(text)), _order_step, kind="tools"),
    ),
    fallback=_approval_fallback,
)

# ------------------------------------------------------------------ semantic
#
# The library is real; only the model's choices are scripted. Each call reads
# this turn's tool results: search first (a fixed query for each sample), then,
# for the end of the poem, read the last lines of Book XII. The answer quotes a
# line from a passage the tools returned and cites that passage's own Book and
# lines, so its citations are real whatever the index ranked first.

SEMANTIC_SAMPLES = (
    "What does Satan mean by 'Better to reign in Hell'?",
    "What does Mammon propose in the council in Hell?",
    "How does the poem end?",
)
_SEMANTIC_QUERIES = {
    SEMANTIC_SAMPLES[0]: "Better to reign in Hell than serve in Heaven",
    SEMANTIC_SAMPLES[1]: "Mammon speaks in the council",
    SEMANTIC_SAMPLES[2]: "the end of the poem: Adam and Eve leave Eden",
}
_END_OF_POEM = re.compile(r"\b(?:poem|book|story)\s+end\b|\bend\s+of\s+the\s+(?:poem|book|story)\b", re.IGNORECASE)
_SEMANTIC_STOP = {"about", "after", "before", "could", "does", "doesn", "their", "there", "these", "those",
                  "what", "when", "where", "which", "while", "would", "paradise", "poem", "milton", "propose"}


def _content_words(text: str) -> set[str]:
    """Words of 5+ letters that carry meaning, so "eat" or "the" never count as a match."""
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in _SEMANTIC_STOP}


def _cite(p: dict) -> str:
    return f"(Book {p['book']}, {p['start_line']}–{p['end_line']})"


def _semantic_step(messages: list[BaseMessage]) -> str | AIMessage:
    human, turn = _this_turn(messages)
    results = [(m.name, _text_of(m)) for m in turn if m.type == "tool"]
    query = _SEMANTIC_QUERIES.get(human.strip(), human.strip())
    if not results:
        return _call("search_book", query=query, limit=3)
    end_of_poem = bool(_END_OF_POEM.search(human))
    if end_of_poem and not any(name == "read_passage" for name, _ in results):
        last = _book_length("XII")
        return _call("read_passage", book="XII", start_line=max(1, last - 19), end_line=last)
    name, text = results[-1]
    try:
        data = json.loads(text)
    except ValueError:
        return f"The library could not answer: {text} {OFFLINE_NOTE}"
    if name == "read_passage":
        lines = data["text"].splitlines()
        return (f"The poem ends as Adam and Eve leave Eden together:\n\n“{lines[-2]}”\n“{lines[-1]}” "
                f"{_cite(data)}\n\nI read the last lines of Book XII to answer this. {OFFLINE_NOTE}")
    wanted = _content_words(human)
    unknown = sorted(w for w in wanted if not _in_poem(w))
    hits = [] if unknown else [h for h in data if wanted & _content_words(h["text"])]
    if not hits:
        return (f"The passages I found don't cover this. I searched for \"{query}\" and none of the "
                f"passages mentioned it. {OFFLINE_NOTE}")
    parts, quoted = [], set()
    for h in hits:
        # Overlapping passages can share a line: quote each line once.
        lines = [ln.strip() for ln in h["text"].splitlines() if ln.strip() not in quoted]
        line = next((ln for ln in lines if wanted & _content_words(ln)), None)
        if line is None:
            continue
        quoted.add(line)
        parts.append(f"“{line}” {_cite(h)}")
        if len(parts) == 2:
            break
    if not parts:
        return (f"The passages I found don't cover this. I searched for \"{query}\" and none of the "
                f"passages mentioned it. {OFFLINE_NOTE}")
    return "From the passages I found:\n\n" + "\n\n".join(parts) + f"\n\n{OFFLINE_NOTE}"


_BOOK_LENGTHS: dict[str, int] = {}
_POEM_WORDS: set[str] = set()


def _in_poem(word: str) -> bool:
    """Whether the poem uses the word (or its singular). A question about something the poem
    never mentions ("smartphones") cannot be answered from it, whatever else matches."""
    if not _POEM_WORDS:
        from agentic_solutions.mcp_servers.library.text import TEXT_PATH

        _POEM_WORDS.update(re.findall(r"[a-z]+", TEXT_PATH.read_text(encoding="utf-8").lower()))
    return word in _POEM_WORDS or (word.endswith("s") and word[:-1] in _POEM_WORDS)


def _book_length(numeral: str) -> int:
    if not _BOOK_LENGTHS:
        from agentic_solutions.mcp_servers.library.text import TEXT_PATH, parse_text

        _BOOK_LENGTHS.update({b.numeral: len(b.lines) for b in parse_text(TEXT_PATH.read_text(encoding="utf-8"))})
    return _BOOK_LENGTHS[numeral]


def _semantic_fallback(_messages: list[BaseMessage]) -> str:
    listed = "; ".join(f'"{s}"' for s in SEMANTIC_SAMPLES)
    return _fallback(f"I answer questions about Paradise Lost from passages I search for. Try: {listed}.")


SEMANTIC = Script(
    rules=(Rule(match=lambda _text: True, reply=_semantic_step, kind="tools"),),
    fallback=_semantic_fallback,
)

SCRIPTS: dict[str, Script] = {
    "qa": QA,
    "chat_loop": CHAT_LOOP,
    "guardrail": GUARDRAIL,
    "approval": APPROVAL,
    "semantic": SEMANTIC,
}
