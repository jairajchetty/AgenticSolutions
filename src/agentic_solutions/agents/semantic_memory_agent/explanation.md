# Semantic

## What it is
The agent looks things up in a trusted source before answering, instead of relying on what the model remembers from training. Documents are indexed in advance; when a question comes in, the agent fetches the passages that match it best and answers from them, which is often called retrieval-augmented generation (RAG). Because the knowledge lives outside the model, it can be kept up to date, limited to what each person may see, and cited.

## When to use it
- Answers must come from your own documents, such as manuals, policies or articles.
- The knowledge is too large, or changes too often, to put in the prompt.
- Answers should point back to a source passage a reader can check.
- Not when the question is about how things connect across many facts, such as a chain of who reports to whom. Passage search finds text that resembles the question, not paths between entities.

## How it works
Roles:
- **Index**: the documents, split into passages and stored with whatever the search method needs.
- **Retriever**: turns the question into a query and returns the top passages.
- **Grader** (optional): judges whether the passages are relevant to the question.
- **Query rewriter** (optional): rephrases the query when the passages miss.
- **Agent**: answers from the passages, citing them where it can.

Flow:
1. Ahead of time, documents are split into passages and indexed.
2. The question becomes a query, and the retriever fetches the best-matching passages.
3. If a grader is used and the passages are poor, the query is rewritten and retrieval runs again, up to a retry limit.
4. The agent answers from the passages, and says so when they do not contain the answer.

## Design considerations
- **Retrieval method:** keyword search matches exact terms, names and codes; similarity search over embeddings matches meaning and paraphrase but can miss exact identifiers; hybrid search with a re-ranking step combines both at more cost.
- **Chunking:** small passages match precisely but lose surrounding context; large ones keep context but dilute the match and cost more tokens. Keep source and position with each passage so answers can cite it.
- **How many passages:** fetching more raises the chance the answer is there, and also the cost and the noise the model must ignore.
- **Check before answering:** a single retrieve-then-answer pass is cheapest; a grading step that rewrites the query and retries rescues poor first searches, at the cost of more model calls. Cap the retries.
- **Who decides to retrieve:** retrieving on every request is simple and predictable; giving the agent search as a tool lets it skip retrieval or search several times, but its choices are harder to predict.
- **Freshness:** re-index when sources change. A stale index gives confident, outdated answers.
- **Access control:** filter passages by what the asker may see before they reach the prompt, not after.

## Trade-offs
- Answers are grounded in sources and can be updated without retraining the model.
- Quality is bounded by retrieval: a passage that is not found cannot be used.
- Retrieval, and any grading or retries, add latency and cost to every question.
- The index needs building, re-indexing and monitoring.
- Retrieved text is untrusted input to the prompt and can carry injected instructions.

## Related patterns
- The dividing line with [[memory/knowledge-graph]]: Semantic retrieves passages of text that resemble the query. Knowledge Graph retrieves entities and the relations between them, so it can follow a chain of facts that no single passage states.
- [[memory/episodic]] recalls one user's own history; Semantic looks up shared knowledge, not tied to one user's history.
- [[cognitive/reflection]] critiques a draft; the grading step here judges the evidence before any draft exists.
- [[cognitive/react]] is the loop to use when search is one tool among several that the agent calls as needed.

## How this Studio implements it

### Mapping
- **Index** → the `library` MCP server: John Milton's *Paradise Lost*, split into overlapping passages of about 20 lines within each Book. Each passage is stored in Qdrant with a dense embedding (`bge-small-en-v1.5`) and a BM25 keyword vector, both computed locally.
- **Retriever** → the `search_book` tool: hybrid search that fuses the dense and keyword results with reciprocal rank fusion. `read_passage` reads lines by position, for questions such as how the poem ends.
- **Agent** → `agent`: the model. It is told to answer only from the passages and to cite each claim's Book and line range. Line numbers follow this edition.
- **Tools** → `tools`: runs the model's calls on the library server over MCP.
- **Between questions** → `ask`: waits for your next message.
- **Grader and query rewriter** → not separate nodes. The agent searches again with other words when the passages miss, up to 6 tool rounds per question.

### Framework concepts
- **Forced first search:** the first model call of each question is bound with `tool_choice="search_book"`. If a model answers in text anyway, `agent` replaces that answer with the search.
- **Prebuilt tool node:** `tools` is LangGraph's `ToolNode`. It runs the model's tool calls and returns each result as a message.
- **`Command(goto=...)` routing:** `ask` and `agent` return a `Command` that names the next node.
- **MCP client:** the library server runs in-process over MCP's in-memory transport. The same server runs on its own with `python -m agentic_solutions.mcp_servers.library`.
- **Index lifecycle:** the index is built on the first start (about a minute, including the model download) and reused while the text, chunking and models are unchanged.

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
        if rounds == 0 and not calls:
            # A model that ignored the forced choice: search with the question, and drop its text.
            reply = AIMessage("", tool_calls=[
                {"name": FORCED_TOOL, "args": {"query": _question(state)}, "id": "forced-search"}])
            calls = reply.tool_calls
```

### Try this
- Send `What does Satan mean by 'Better to reign in Hell'?`. The first step is `search_book`, and the answer quotes Book I with its line range.
- Send `How does the poem end?`. A passage search cannot know what comes last, so the agent calls `read_passage` on the end of Book XII.
- Send `What did Milton eat for breakfast?`. The search finds nothing relevant, and the agent says the passages don't cover it instead of answering from memory.
- Compare with [[memory/knowledge-graph]]: which question about Satan and Beelzebub would need relations between entities rather than passages?
