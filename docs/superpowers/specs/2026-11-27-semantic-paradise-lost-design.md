# Semantic memory demo: Paradise Lost: design

Date: 2026-11-27
Status: draft for approval
Branch: new branch off `feature/composite-home`, stacked on PR #8.

## 1. Intent

Semantic is a composite pattern on the main page with no live demo. This design makes it live. Milton's *Paradise Lost* goes into a vector database, which the agent reaches through an MCP tool. The agent answers questions about the book from passages it retrieves, not from what the model already knows, and it cites where each answer comes from.

The audience is solution and enterprise architects. The demo should show the parts they would use in production: a real vector database, hybrid search, a retrieval tool behind MCP, and an agent that is instructed and constrained to use it.

## 2. Goals, non-goals, anti-goals

**Goals**
- **Cleaned text in the repository:** a cleaned, committed text of the book, split into its 12 Books with one verse line per line.
- **A vector index:** a Qdrant collection with a dense embedding and a BM25 keyword vector for each chunk, built from that text on first start and cached.
- **An MCP server, `library`, with two read-only tools:** `search_book` (hybrid search) and `read_passage` (read lines by position).
- **A ReAct agent:** it must call `search_book` before its first answer to each question, answers only from retrieved passages, and cites the Book and lines.
- **A Studio demo:** Semantic becomes a live chat demo with offline (scripted) and live models, edge labels, a Guide, and sample questions.

**Non-goals**
- No other books, no uploading documents, no index management in the UI.
- No Qdrant server. Local mode only, although the code would work against a server unchanged.
- No corrective loop (`grade` and `rewrite_query`) from the old skeleton. The agent can search again on its own, which is the ReAct behaviour.
- No phone layout.

**Anti-goals**
- **Answers from memory.** If the passages don't cover the question, the agent says so rather than drawing on the model's own knowledge of Milton.
- **Made-up citations.** Every Book and line range the agent cites must come from a tool result.
- **A slow or fragile everyday start.** Only the first start, and starts after the text or chunking changes, may take the embedding cost.

## 3. Approaches considered

| Decision | Options | Chosen | Why |
|---|---|---|---|
| Agent shape | (a) Graph always retrieves first, as in the skeleton; (b) ReAct agent that chooses to call the tool | **(b), with a forced first tool call** | Shows the pattern the catalog says Semantic is built from (ReAct and Tool Use), while forcing the first call guarantees a search. |
| Vector database | SQLite with `sqlite-vec` and FTS5; **Qdrant**; Chroma; pgvector | **Qdrant, local mode** | A product architects recognise. Moving to a server is a configuration change, and it has built-in hybrid search and metadata filters. |
| Embeddings | `bge-small` locally; `bge-base` locally; OpenAI `text-embedding-3-small`; Voyage lite | **`BAAI/bge-small-en-v1.5` through `fastembed`**, plus `Qdrant/bm25` | Free, no API key, no network call per query, and it embeds the book in about 30 seconds on a CPU. BM25 covers the names and archaic words. |
| Index lifecycle | (A) build and commit the index; **(B) commit the text and build on first start**; (C) rebuild on every start | **B** | The text can be read and diffed, there's no binary file in git, and a fingerprint makes later starts instant. |

**Spike (2026-11-27):** `qdrant-client` 1.20, `fastembed` 0.9.1 and `onnxruntime` 1.32 install on Python 3.14.4. With 613 chunks, dense embedding takes about 30 s, BM25 about 0.2 s, and a hybrid query 35–50 ms. Quotes and character questions hit. A question about position ("How does the poem end?") misses, which is why `read_passage` exists.

## 4. The text

**Source:** `data/books/paradise-lost.pdf`, from Planet eBook. It is git-ignored and is not shipped. The poem is in the public domain.

**Preparation script:** `tools/prepare_paradise_lost.py` is a one-off that writes `src/agentic_solutions/mcp_servers/library/texts/paradise-lost.txt`, which is committed. It uses `pypdf`, added as an optional `prep` extra rather than a runtime dependency.

**Text format:**
```
# Book I
Of Man's first disobedience, and the fruit
Of that forbidden tree whose mortal taste
...
# Book II
...
```
Each Book starts with a `# Book <Roman numeral>` line. After that, one verse line per line, with no blank lines inside a Book.

**Cleaning rules:** the script removes:
- the title page and the "Download free eBooks…" lines;
- page headers and footers ("Paradise Lost", "Free eBooks at Planet eBook.com"), including when they are stuck to a page number ("11Free eBooks…", "Paradise Lost1");
- trailing spaces.

It also rejoins split drop capitals: a line holding a single capital letter is joined to the next line ("O" + "f Man's" → "Of Man's"), and so is a capital separated by a space at the start of a Book ("M ean while" → "Meanwhile").

The script then checks that there are 12 Books in order, I to XII, and that the total line count is between 10,400 and 10,700. The standard 1674 text has 10,565 lines, and the spike's raw count of 10,943 included residue. If either check fails, the script stops and says why.

**Line numbers** count verse lines within a Book, starting at 1. They follow this edition and may differ from scholarly line numbering by a few lines. The tool descriptions and the Guide say so.

## 5. Chunking

**Unit:** chunks never cross a Book boundary.

**Window:** a chunk starts at line 1, then every 16 lines. Its nominal end is 20 lines after its start, so neighbouring chunks overlap by 4 lines. The end then moves forward to the first line ending in `.`, `?` or `!`, closing quotes allowed after the mark, so the chunk doesn't cut a sentence. It moves at most 8 lines. If no sentence ends within 8 lines, the chunk keeps its nominal end. The last chunk in a Book ends at the Book's last line.

**Chunk text:** the lines joined with newlines. The embedded text starts with `Paradise Lost, Book <N>, lines <a>–<b>:` followed by the lines. That gives the dense model the position as context.

**Payload:** `{book: "I", book_number: 1, start_line, end_line, text}`. `text` is the lines without the prefix.

**Id:** a UUID5 of `paradise-lost/<book>/<start_line>`, so rebuilds are deterministic.

**Size:** expect about 600–700 chunks.

## 6. The index

**Location:** Qdrant local mode at `<LIBRARY_DIR>/qdrant`. `LIBRARY_DIR` defaults to `data/library`. `fastembed` caches its models under `<LIBRARY_DIR>/models`.

**Collection:** `paradise_lost`, with:
- a named dense vector `dense`: 384 dimensions, cosine distance;
- a named sparse vector `bm25`, with `modifier=IDF`.

**Fingerprint:** sha256 of the text file's bytes, the chunking parameters (16, 20, 8) and the two model names. It is stored in a `meta.json` next to the Qdrant folder.
- **On start:** if the fingerprint matches, the server opens the collection as it is. If it differs or is missing, the server rebuilds the collection from scratch.
- **Logging:** the server logs one line at the start of a rebuild ("Indexing Paradise Lost: N chunks; first run downloads the embedding models") and one line at the end, with the time taken.

**Hybrid query:** two prefetches of 20 each, one on `dense` (query embedding from `query_embed`) and one on `bm25`, combined with RRF fusion. An optional filter on `book` applies to both.

## 7. The MCP server: `library`

**Location:** `src/agentic_solutions/mcp_servers/library/`. It is a FastMCP server, built like the ERP's (`server.py`, `config.py`, `store.py` for the index, `__main__.py` for running standalone over streamable HTTP).

**Instructions:** "The full text of John Milton's *Paradise Lost* (1674, 12 Books). Search it or read passages by Book and line. Line numbers follow this edition."

**Tools:** both are annotated `readOnlyHint=True`.

| Tool | Arguments | Returns |
|---|---|---|
| `search_book` | `query: str` (1–500 characters), `limit: int = 5` (1–10), `book: str \| None` (Roman numeral I–XII) | A list of `{book, start_line, end_line, text, score}`, best first |
| `read_passage` | `book: str` (I–XII), `start_line: int ≥ 1`, `end_line: int` | `{book, start_line, end_line, text}`, clamped to the Book's length and capped at 80 lines |

**Errors:** an unknown Book, `end_line < start_line`, a `start_line` past the Book's end, or an out-of-range `limit` raises a `ToolError` with a plain message, such as "Book XIII does not exist; Paradise Lost has Books I to XII."

**How the app starts it:** in-process over MCP's in-memory transport for the app's lifetime, the same way as the ERP. The index is built or opened at that point, before the app serves requests. There is no URL option.

## 8. The agent: `semantic_agent`

**Folder:** `src/agentic_solutions/agents/semantic_memory_agent/`. The catalog's `folder` doesn't change. The skeleton is replaced by a live graph. `build_skeleton` goes, and so does the folder's entry in the skeleton tests, the same way Approval's was handled.

**Graph:**
```
START → ask ─(message)→ agent ─(tool calls)→ tools → agent
         ↑  ─(stop)→ END      └─(reply)→ ask
         └─(empty)┘
```

**Nodes:**
- **`ask`:** the shared interrupt `ask`, with the same stop and empty rules as Approval.
- **`agent`:** the model, bound to the two library tools.
- **`tools`:** runs the MCP calls.

The routing uses `Command(goto=...)`, as Approval's does. These are the conditional edges for the Studio's labels:

| Edge | Label | Full rule |
|---|---|---|
| `ask` → `__end__` | `stop` | You typed "stop": the conversation ends. |
| `ask` → `ask` | `empty` | Empty message: wait for the next one. |
| `ask` → `agent` | `question` | Any other message goes to the agent. |
| `agent` → `tools` | `search / read` | The model called a library tool (6 rounds per question at most). |
| `agent` → `ask` | `answer` | The model answered from the passages, or said they don't cover the question. |

**Forced first search:** each question resets `tool_rounds` to 0. While `tool_rounds == 0`, the model is bound with `tool_choice="search_book"`. LangChain maps a tool name to each provider's own form of a forced tool call, for Anthropic and for the OpenAI-compatible models in the picker alike. Later rounds use automatic tool choice. After 6 rounds, tool choice is `none`, as Approval's step limit does. A model that ignores the forced choice still can't answer first: if round 0 returns no tool call, the node calls `search_book` itself, with the question as the query.

**System prompt:**
- You answer questions about John Milton's *Paradise Lost* using only passages returned by the `search_book` and `read_passage` tools. Do not use what you already know about the poem, its plot, or its criticism.
- Search before answering. Search again with different words if the passages don't answer the question. Use `read_passage` to read around a passage, or to reach a known place such as the end of Book XII.
- Cite every claim with its Book and line range, for example (Book I, 271–291). Quote exactly when quoting.
- If the passages don't answer the question, say so plainly and say what you searched for. Don't fill the gap from memory.
- Line numbers follow this edition.

**Models:** offline (scripted) and live, through the existing model picker. The offline script covers the three samples. It calls `search_book` with fixed queries, and its answers quote passages that the real index returns for those queries. A test checks that each cited Book and line range exists and contains the quoted words.

**Samples:**
- "What does Satan mean by 'Better to reign in Hell'?"
- "What does Mammon propose in the council in Hell?"
- "How does the poem end?" This one shows `read_passage` on Book XII.

## 9. The Studio

- **Registry:** a new `PatternSpec` with id `semantic`, mode `chat`, title "Semantic memory: answers from a vector database", the samples above, the edge labels from §8, and automatic layout.
- **Catalog:** `memory/semantic` gains `demo: semantic`, so it shows as live. Its `builds_on` becomes `[memory/session, cognitive/react, execution/tool-use]`. Session is added because the demo has the `ask` loop.
- **App startup:** opens the library client next to the ERP and passes it in `BuildContext` (a new `library` field), the same way as `erp`. `create_app` gains a `library` parameter, as it has `erp`. Tests pass a client over an in-process server built on the fake embedder and a small fixture text, so no app test downloads a model or embeds the book.
- **Guide:** rewrite `semantic_memory_agent/explanation.md` to the standard Guide sections. The Mapping section describes `ask`, `agent`, `tools`, the library MCP server, Qdrant, hybrid search, and the forced first search. It says line numbers follow this edition.

## 10. Dependencies and configuration

**Runtime:** `qdrant-client[fastembed]>=1.20`. Optional extra `prep`: `pypdf`.

**Settings:**
- `LIBRARY_DIR` (default `data/library`).
- No API keys: embeddings run locally.

**First start:** about 20 s to download the models into `LIBRARY_DIR/models`, plus about 30 s to embed. Both happen once per machine, or once after the text or chunking changes. This needs network access to Hugging Face the first time.

## 11. Testing

- **Preparation:** on a small synthetic "PDF text" fixture (plain text input to the cleaning function, no PDF needed), headers are removed, page numbers stuck to headers are removed, drop capitals are rejoined, and Books are split and numbered. A test also checks the committed text: 12 Books in order, and a total line count within 10,400–10,700.
- **Chunking:**
  - Chunks never cross a Book boundary.
  - Each chunk ends on a sentence end, or at the 8-line limit.
  - Neighbouring chunks overlap.
  - The last chunk ends at the Book's end.
  - Ids are stable between runs.
  - Every line of the text appears in at least one chunk.
- **Index:**
  - The fingerprint changes when the text or a parameter changes, which triggers a rebuild.
  - A matching fingerprint opens the collection without re-embedding.
  - Unit tests use a fake deterministic embedder (hash-based vectors) on a 3-Book fixture, so they need no model download.
- **Server:**
  - `search_book` returns well-formed results and respects `book`.
  - `read_passage` clamps and caps.
  - Every error case in §7 returns a plain `ToolError`.
- **Agent:**
  - The first model call of each question is bound with the forced `search_book` choice.
  - A model that ignores it still gets a search.
  - The 6-round cap holds.
  - Every conditional edge has a label.
- **Real models (marked slow):** one test builds the real index and checks that "Better to reign in Hell" returns Book I in its top 3 and "Mammon" returns Book II in its top 3. It is skipped unless `RUN_SLOW=1`.
- **Browser check at 1440 px:** the three samples run offline, the Semantic card shows as live, and there are no console errors.

## 12. Calls made in this design (for the owner to check)

- **Line numbers follow this edition.** They may be a few lines off scholarly numbering, and the tools and Guide say so.
- **`read_passage` exists** because the spike showed similarity search can't answer questions about position.
- **The first start blocks the app** for about 50 s while it indexes, rather than serving a "library not ready" state.
- **Semantic's `builds_on` gains Session,** because the demo has the chat loop.
- **The PDF stays git-ignored;** only the cleaned text is committed.

## 13. Left to the builder

- How the offline script picks its canned passages, as long as the citation test holds.
- Module layout inside `mcp_servers/library/`, following the ERP's.
- Log wording, and the exact wording of the Guide, within the README's writing guidelines.
