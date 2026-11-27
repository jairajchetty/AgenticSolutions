# Semantic

## What it is
The Semantic pattern answers questions from a trusted set of documents, not from what the model learned in training.

The documents are prepared in advance: split into passages and stored in a searchable index. For each question, the agent searches the index, answers only from the passages it finds, and cites them. This is often called retrieval-augmented generation (RAG).

Because the knowledge is held outside the model, it can be updated without retraining, restricted to what each user is allowed to see, and checked against its source.

## When to use it
- Answers must come from your own documents, such as manuals, policies or articles.
- The knowledge is too large, or changes too often, to include in the prompt.
- Readers need to check each answer against its source.
- Not when the answer depends on how facts connect, such as a chain of who reports to whom. Passage search finds text that resembles the question; it does not follow relationships between entities.

## How it works
Roles:
- **Index**: the documents, split into passages and stored for search.
- **Retriever**: searches the index for the question and returns the best-matching passages.
- **Grader** (optional): checks that the passages are relevant to the question.
- **Query rewriter** (optional): rephrases the search when the passages miss.
- **Agent**: answers from the passages and cites them.

Flow:
1. In advance, the documents are split into passages and indexed.
2. The retriever searches the index for the question and returns the best-matching passages.
3. If a grader is used and the passages are not relevant, the search is rephrased and run again, up to a set limit.
4. The agent answers from the passages. If they do not contain the answer, it says so.

## Design considerations
- **Search method:** Keyword search matches exact terms, names and codes. Similarity search matches meaning and paraphrase, but can miss exact identifiers. Hybrid search combines both, at more cost.
- **Passage size:** Small passages match precisely but lose context. Large passages keep context but match less precisely and cost more to process. Store each passage's source and position, so answers can cite it.
- **Number of passages:** Returning more passages raises the chance that the answer is included, but adds cost and irrelevant text.
- **Checking the passages:** One search followed by an answer is the cheapest option. A grading step that rephrases and searches again rescues poor first searches, at the cost of more model calls. Limit the retries.
- **Who decides to search:** Searching on every request is simple and predictable. Letting the agent decide allows it to search several times, but its behaviour is harder to predict.
- **Freshness:** Re-index when the sources change. A stale index produces confident but outdated answers.
- **Access control:** Filter passages by what the user is allowed to see before they reach the model, not after.

## Trade-offs
- Answers are grounded in sources, which can be updated without retraining the model.
- Answer quality is limited by search: a passage that is not found cannot be used.
- Each search adds time and cost to every question, and grading or retries add more.
- The index must be built, kept up to date and monitored.
- Retrieved text is untrusted input to the model and can carry injected instructions.

## Related patterns
- The dividing line with [[memory/knowledge-graph]]: Semantic retrieves passages of text that resemble the question. Knowledge Graph retrieves entities and the relationships between them, so it can follow a chain of facts that no single passage states.
- [[memory/episodic]] recalls one user's past interactions. Semantic looks up knowledge shared by all users.
- [[cognitive/reflection]] critiques a draft answer. The grading step here checks the evidence before any answer is drafted.
- [[cognitive/react]] is the loop to use when search is one of several tools the agent calls as needed. This Studio's demo is built on it.

## How this Studio implements it

### Mapping
- **Index** → the `library` MCP server: John Milton's *Paradise Lost*, split into overlapping passages of about 20 lines within each Book. Each passage is stored in Qdrant with a meaning vector (`bge-small-en-v1.5`) and a keyword vector (BM25), both computed locally.
- **Retriever** → the `search_book` tool: hybrid search, which combines the meaning and keyword matches by reciprocal rank fusion. `read_passage` reads lines by position, for questions such as how the poem ends.
- **Agent** → `agent`: the model. It is told to answer only from the passages, simply and concisely, and to list its sources at the end, each with its Book, lines and the words it relied on. Line numbers follow this edition.
- **Tools** → `tools`: runs the model's calls on the library server over MCP.
- **Between questions** → `ask`: waits for your next message.
- **Grader and query rewriter** → not separate nodes. When the passages miss, the agent searches again with other words, up to 6 tool rounds per question.

### Framework concepts
- **Forced first search:** the first model call of each question is bound with `tool_choice="search_book"`. If a model answers in text or calls another tool instead, `agent` replaces that reply with the search.
- **Prebuilt tool node:** `tools` is LangGraph's `ToolNode`. It runs the model's tool calls and returns each result as a message.
- **`Command(goto=...)` routing:** `ask` and `agent` return a `Command` that names the next node.
- **MCP client:** the library server runs in-process over MCP's in-memory transport. The same server runs on its own with `python -m agentic_solutions.mcp_servers.library`.
- **Index lifecycle:** the index is built on the first start (about a minute, including the model download). It is reused until the text, the passage settings or the models change.

### Key code
How `agent` makes the first step of every question a search:
```python
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
```

### Try this
- Send `What does Satan mean by 'Better to reign in Hell'?`. The first step is `search_book`. The answer is two sentences, and its sources at the end quote Book I with the line range.
- Send `How does the poem end?`. A passage search cannot know what comes last, so the agent calls `read_passage` on the end of Book XII.
- Send `What did Milton eat for breakfast?`. The search finds nothing relevant, and the agent says the passages don't cover it instead of answering from memory.
- Compare with [[memory/knowledge-graph]]: which question about Satan and Beelzebub would need relations between entities rather than passages?
