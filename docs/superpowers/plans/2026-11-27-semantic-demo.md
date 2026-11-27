# Semantic Memory Demo (Paradise Lost) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Semantic a live Studio demo: a ReAct agent answers questions about *Paradise Lost* only from passages retrieved through an MCP `library` server over a Qdrant hybrid (dense + BM25) index.

**Architecture:**
- **Text:** a committed, cleaned text, produced once from the PDF.
- **Index:** chunked per Book, then embedded with `fastembed` into Qdrant local mode on first start. A fingerprint tells the server when to rebuild.
- **MCP server:** a FastMCP `library` server exposes `search_book` and `read_passage`. The app runs it in-process, as it does the ERP.
- **Agent:** `semantic_memory_agent` is a ReAct graph (`ask` → `agent` ⇄ `tools`). Its first model call per question is forced to call `search_book`.

**Tech Stack:** Python 3.14, LangGraph, MCP (FastMCP, in-memory transport), `qdrant-client[fastembed]>=1.20` (local mode), `pypdf` (prep extra only), pytest, Node tests through `tests/test_js.py`.

**Spec:** `docs/superpowers/specs/2026-11-27-semantic-paradise-lost-design.md`

## Global Constraints

- Models: dense `BAAI/bge-small-en-v1.5` (384 dimensions, cosine) and sparse `Qdrant/bm25` (`modifier=IDF`), both through `fastembed`. No API keys.
- Chunking parameters: `STRIDE = 16`, `WINDOW = 20`, `MAX_EXTEND = 8`. Chunks never cross a Book. The embedded text has the prefix `Paradise Lost, Book <N>, lines <a>–<b>:\n`.
- Hybrid query: one prefetch of 20 on `dense` and one of 20 on `bm25`, fused with RRF.
- Qdrant collection: `paradise_lost`, under `<LIBRARY_DIR>/qdrant`. Models are cached under `<LIBRARY_DIR>/models`. `LIBRARY_DIR` defaults to `data/library`.
- Tools: `search_book(query, limit=5, book=None)` (query 1–500 characters, limit 1–10, book I–XII) and `read_passage(book, start_line, end_line)` (clamped, at most 80 lines). Both read-only.
- Agent: rounds reset per question. Round 0 binds `tool_choice="search_book"`. At most 6 tool rounds, then `tool_choice` is `none`.
- No app test, and no default test run, may download a model or embed the book. Real-model tests run only with `RUN_SLOW=1`.
- The PDF stays git-ignored in `data/books/`. Only the cleaned text is committed.
- Desktop-only: browser checks at 1440 px.
- Copy follows the README's Writing Guidelines.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A question whose answer the passages don't contain** ("What did Milton eat for breakfast?"): the offline script and the system prompt both produce "the passages don't cover this", with no invented citation. The test is in Task 6.
2. **The index folder deleted, or `meta.json` corrupt, between starts:** the server rebuilds rather than crashing. The test is in Task 3.
3. **`read_passage` past a Book's end, or with `end < start`:** a plain tool error, not an empty result or an exception trace. The test is in Task 4.
4. **A live model that answers in text on round 0 despite the forced choice:** the graph still runs `search_book` with the question. The test is in Task 5.
5. **`search_book` with a lower-case or Arabic-numeral book (`"ii"`, `"2"`):** normalised to `II`, or rejected with a message that names the valid range. The test is in Task 4.

---

### Task 1: The cleaned text and its parser

**Files:**
- Create: `tools/prepare_paradise_lost.py` (the CLI: PDF → text)
- Create: `src/agentic_solutions/mcp_servers/library/__init__.py`
- Create: `src/agentic_solutions/mcp_servers/library/text.py` (the cleaning functions and the parser)
- Create: `src/agentic_solutions/mcp_servers/library/texts/paradise-lost.txt` (generated, committed)
- Modify: `pyproject.toml`: add `prep = ["pypdf>=5"]` to the optional dependencies, and add `"mcp_servers/library/texts/*.txt"` to the package data
- Test: `tests/test_library_text.py`

**Interfaces:**
- Produces, in `library/text.py`:
  - `@dataclass(frozen=True) class Book(numeral: str, number: int, lines: tuple[str, ...])`
  - `ROMAN: tuple[str, ...] = ("I", …, "XII")`
  - `clean_pages(pages: list[str]) -> list[Book]`, which raises `ValueError` on structure problems
  - `render(books: list[Book]) -> str`, which writes the `# Book I` format
  - `parse_text(text: str) -> tuple[Book, ...]`, which raises `ValueError`
  - `TEXT_PATH: Path`, the committed file

- [ ] **Step 1: Write the failing tests** in `tests/test_library_text.py`:
  - `test_clean_removes_headers_and_page_numbers`: the pages `["Download free eBooks …\nParadise Lost\nBy John Milton", "Paradise Lost\nBook I \nO\nf Man’s first disobedience, and the fruit  \nOf that forbidden tree", "11Free eBooks at Planet eBook.com\nBrought death into the World,  ", "Paradise Lost1\nBook II \nH\nigh on a throne"]` give two Books. Book I has the lines `("Of Man’s first disobedience, and the fruit", "Of that forbidden tree", "Brought death into the World,")`, and Book II starts `"High on a throne"`.
  - `test_clean_rejoins_spaced_drop_cap`: a Book opening `"M ean while the heinous"` becomes `"Meanwhile the heinous"`.
  - `test_clean_rejects_books_out_of_order`: Book I then Book III raises `ValueError`, matching `Book II`.
  - `test_render_parse_round_trip`: `parse_text(render(books)) == tuple(books)`.
  - `test_parse_rejects_lines_before_first_book`.
  - `test_committed_text_shape`: `parse_text(TEXT_PATH.read_text())` gives 12 Books numbered I–XII, a total line count `10_400 <= n <= 10_700`, and no line containing "Planet eBook".

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_library_text.py -q`
  Expected: FAIL with an `ImportError` (`library.text` doesn't exist).

- [ ] **Step 3: Implement `text.py`.** In `clean_pages`:
  1. Strip each line.
  2. Drop lines that match `^\d*Free eBooks at Planet eBook\.com$`, `^Paradise Lost\d*$`, `^Download free eBooks`, `^By John Milton$` and blank lines.
  3. Start a Book at `^Book ([IVXL]+)$`.
  4. Join a lone capital-letter line to the next line. Join `^([A-Z]) ([a-z])` only on a Book's first line.

  `parse_text` checks the order and count of the Books (12, I–XII) and raises `ValueError` with the line number on any problem. The count check against 10,400–10,700 lives in the CLI, not in `parse_text`, so the unit fixtures stay small.

- [ ] **Step 4: Implement the CLI.** `python tools/prepare_paradise_lost.py data/books/paradise-lost.pdf` reads the pages with `pypdf`, calls `clean_pages`, checks 12 Books and 10,400–10,700 lines (exiting 1 with a message otherwise), and writes `render(...)` to `TEXT_PATH`. Install the extra with `.venv/bin/pip install -e '.[prep]'`, then run the CLI.
  Expected output: `Wrote 12 Books, <n> lines to …/paradise-lost.txt`, with n in range. If the count is out of range, inspect the residue and extend the drop rules. Never widen the range.

- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_library_text.py -q`
  Expected: PASS.

- [ ] **Step 6: Commit** `tools/`, `library/__init__.py`, `text.py`, `texts/paradise-lost.txt`, `pyproject.toml` and the test, with the message "Library: the cleaned Paradise Lost text and its parser".

---

### Task 2: Chunking

**Files:**
- Create: `src/agentic_solutions/mcp_servers/library/chunks.py`
- Test: `tests/test_library_chunks.py`

**Interfaces:**
- Consumes: `Book` and `parse_text` from Task 1.
- Produces:
  - `STRIDE = 16`, `WINDOW = 20`, `MAX_EXTEND = 8`
  - `@dataclass(frozen=True) class Chunk(id: str, book: str, book_number: int, start_line: int, end_line: int, text: str)`, with the property `embed_text -> str` (`f"Paradise Lost, Book {book}, lines {start_line}–{end_line}:\n{text}"`)
  - `chunk_book(book: Book) -> list[Chunk]`
  - `chunk_all(books) -> list[Chunk]`
  - `SENTENCE_END = re.compile(r"[.?!][’'\"”)]*$")`

- [ ] **Step 1: Write the failing tests**, using a synthetic Book of 50 lines where lines 22 and 45 end with "." and the others end with ",":
  - `test_starts_every_stride`: the start lines are `[1, 17, 33, 49]`.
  - `test_end_moves_to_sentence_end`: the first chunk's `end_line == 22`, because its nominal end is 20 and line 22 ends in ".".
  - `test_end_capped_at_max_extend`: a chunk with no sentence end within 8 lines ends at its nominal end.
  - `test_last_chunk_ends_at_book_end`: the last chunk's `end_line == 50`.
  - `test_every_line_covered_and_neighbours_overlap`.
  - `test_ids_are_stable_uuid5`: two runs give equal ids, and the id is `str(uuid5(NAMESPACE_URL, "paradise-lost/I/1"))`.
  - `test_embed_text_has_position_prefix`.
  - `test_real_text_chunk_count`: `600 <= len(chunk_all(parse_text(TEXT_PATH.read_text()))) <= 750`, and no chunk spans two Books.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_library_chunks.py -q`
  Expected: FAIL with an `ImportError`.

- [ ] **Step 3: Implement** `chunk_book` according to spec §5. The nominal end is `min(start + WINDOW - 1, n)`. Move forward to the first line matching `SENTENCE_END` within `MAX_EXTEND`. A chunk that starts within the last stride ends at `n`.

- [ ] **Step 4: Run** the same command.
  Expected: PASS.

- [ ] **Step 5: Commit** with the message "Library: chunk Books into overlapping verse windows".

---

### Task 3: The Qdrant index

**Files:**
- Create: `src/agentic_solutions/mcp_servers/library/index.py`
- Modify: `tests/fakes.py` (add `FakeEmbedder`)
- Modify: `pyproject.toml` (add `qdrant-client[fastembed]>=1.20` to `dependencies`)
- Test: `tests/test_library_index.py`

**Interfaces:**
- Consumes: `Chunk` and `chunk_all` from Task 2, and `Book` from Task 1.
- Produces:
  - `class Embedder(Protocol)`: `names: tuple[str, str]`, `dense(texts: list[str]) -> list[list[float]]`, `sparse(texts: list[str]) -> list[tuple[list[int], list[float]]]`, `dense_query(text: str) -> list[float]` and `sparse_query(text: str) -> tuple[list[int], list[float]]`
  - `class FastEmbedder` implements it, taking `cache_dir: Path`. It loads `TextEmbedding("BAAI/bge-small-en-v1.5")` and `SparseTextEmbedding("Qdrant/bm25")` lazily.
  - `fingerprint(text: str, embedder: Embedder) -> str`
  - `@dataclass class Passage(book: str, start_line: int, end_line: int, text: str, score: float | None = None)`
  - `class LibraryIndex`:
    - `open(cls, root: Path, text: str, embedder: Embedder) -> "LibraryIndex"` (a classmethod)
    - `.built: bool`, which is True if this open (re)built the index
    - `.search(query: str, limit: int, book: str | None) -> list[Passage]`
    - `.read(book: str, start: int, end: int) -> Passage`, which raises `ValueError`
    - `.close()`
- `FakeEmbedder` (tests): deterministic dense vectors of 384 dimensions, built from a token hash. Sparse vectors are token ids with tf values, so BM25-like matching works on exact words. It counts calls in `.dense_calls`.

- [ ] **Step 1: Write the failing tests**, on a fixture text of three Books with about 40 distinct lines each:
  - `test_first_open_builds_then_reuses(tmp_path)`: the first open has `built is True`; the second has `built is False` and `embedder.dense_calls` unchanged.
  - `test_changed_text_rebuilds(tmp_path)`.
  - `test_missing_or_corrupt_meta_rebuilds(tmp_path)`: delete `meta.json`, then write `{bad`. Each reopen rebuilds without raising. This is Review Focus 2.
  - `test_search_finds_exact_words_and_filters_by_book`: a word unique to Book II puts Book II first, and `book="I"` returns only Book I passages.
  - `test_read_clamps_and_caps`: `read("I", 30, 500)` ends at the Book's last line, and a 200-line request returns at most 80 lines.
  - `test_read_rejects_bad_ranges`: an unknown Book, `start > n` and `end < start` each raise `ValueError` with a plain message.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_library_index.py -q`
  Expected: FAIL with an `ImportError`.

- [ ] **Step 3: Implement** according to spec §6:
  - **Client:** `QdrantClient(path=root / "qdrant")`.
  - **Collection:** created with `create_collection` (not the deprecated `recreate_collection`): dense `VectorParams(size=384, distance=COSINE)` and sparse `SparseVectorParams(modifier=IDF)`. Delete it first when rebuilding.
  - **Upserts:** in batches of 64.
  - **`meta.json`:** `{"fingerprint": …}`, written last, so a build that fails halfway rebuilds next time.
  - **`read`:** served from the parsed Books held in memory, not from Qdrant.
  - **`search`:** uses `query_points` with the two `Prefetch`es and `FusionQuery(fusion=Fusion.RRF)`, plus an optional `Filter` on `book`.
  - **Logging:** one line at the start of a rebuild and one at the end (spec §6).

- [ ] **Step 4: Run** the same command.
  Expected: PASS.

- [ ] **Step 5: Add the slow test** `test_real_models_find_famous_passages`, decorated `@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="RUN_SLOW=1 downloads models")`. It builds from `TEXT_PATH` with `FastEmbedder`. "Better to reign in Hell than serve in Heaven" must have Book I in its top 3, and "What does Mammon propose?" must have Book II in its top 3.
  Run it once: `RUN_SLOW=1 .venv/bin/python -m pytest tests/test_library_index.py -q -k real_models`.
  Expected: PASS, in about a minute.

- [ ] **Step 6: Commit** with the message "Library: Qdrant hybrid index with a rebuild fingerprint".

---

### Task 4: The `library` MCP server and its client

**Files:**
- Create: `src/agentic_solutions/mcp_servers/library/server.py`, `config.py` and `__main__.py`
- Create: `src/agentic_solutions/agents/semantic_memory_agent/library.py` (the client and the model tools)
- Test: `tests/test_library_server.py`

**Interfaces:**
- Consumes: `LibraryIndex`, `Passage` and `FastEmbedder` from Task 3, and `TEXT_PATH` and `ROMAN` from Task 1.
- Produces:
  - **`config.py`:** `@dataclass(frozen=True) class LibrarySettings(dir: Path = Path("data/library"))` and `open_index(settings, embedder=None) -> LibraryIndex`, where the default embedder is `FastEmbedder(settings.dir / "models")`.
  - **`server.py`:**
    - `build_server(index: LibraryIndex) -> FastMCP`, with the tools `search_book(query: str, limit: int = 5, book: str | None = None) -> list[dict]` and `read_passage(book: str, start_line: int, end_line: int) -> dict`. The dict keys are `book`, `start_line`, `end_line` and `text`, plus `score` for search results.
    - `normalise_book(value: str) -> str`: accepts `"ii"`, `"II"`, `"2"` and `"Book II"`; returns `"II"`; raises `ToolError("Book XIII does not exist; Paradise Lost has Books I to XII.")`.
  - **`library.py` (agent side):**
    - `class LibraryUnavailable(Exception)`
    - `class InProcessLibraryClient`, with the same shape and lifecycle as `InProcessErpClient`: `__aenter__`, `__aexit__` and `async call(tool, args) -> Any`. A tool error returns its text, prefixed `Error: `.
    - `class LibraryClient(Protocol)`
    - `library_tools(client) -> list[BaseTool]`, built with `StructuredTool`. Tool names and argument schemas match the server's, with descriptions from spec §7, including "Line numbers follow this edition."
  - **`__main__.py`:** `python -m agentic_solutions.mcp_servers.library` runs streamable HTTP on `LIBRARY_HOST`/`LIBRARY_PORT` (defaults `127.0.0.1:8766`).

- [ ] **Step 1: Write the failing tests**, async over the in-memory client, on the Task 3 fixture and `FakeEmbedder`:
  - `test_search_book_returns_passages`: the result is a list of dicts with `book`, `start_line`, `end_line`, `text` and `score`.
  - `test_search_book_limit_bounds`: `limit=0` and `limit=11` give `Error: …`.
  - `test_query_length_bounds`: `""` and 501 characters give `Error: …`.
  - `test_book_normalisation` (Review Focus 5): `"ii"`, `"2"` and `"Book II"` filter to II. `"XIII"` gives `Error: Book XIII does not exist; Paradise Lost has Books I to XII.`
  - `test_read_passage_errors` (Review Focus 3): `end < start` and `start` past the end each give a plain `Error: …` naming the Book's line count.
  - `test_tools_are_read_only`: every tool's annotations have `readOnlyHint` set to True.
  - `test_library_tools_schema`: the model tools are named `search_book` and `read_passage`, and the description mentions "this edition".

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_library_server.py -q`
  Expected: FAIL with an `ImportError`.

- [ ] **Step 3: Implement** the server (FastMCP, built like `mcp_servers/erp/server.py`, with `INSTRUCTIONS` taken from spec §7), the config, `__main__`, and the client and tools.

- [ ] **Step 4: Run** the same command.
  Expected: PASS.

- [ ] **Step 5: Commit** with the message "Library MCP server: search_book and read_passage".

---

### Task 5: The ReAct agent graph

**Files:**
- Modify: `src/agentic_solutions/agents/semantic_memory_agent/graph.py` (replace the skeleton)
- Modify: `tests/test_skeletons.py` (drop `semantic_memory_agent` from the skeleton list, the way Approval's entry was removed)
- Test: `tests/test_semantic_graph.py`

**Interfaces:**
- Consumes: `library_tools(client)` and `LibraryClient` from Task 4. Reuses `ask_for_text`, `STOP_WORD`, `declined_or`, `get_llm` and `LLMFactory` from the modules Approval imports them from.
- Produces:
  - `MAX_TOOL_ROUNDS = 6`
  - `SYSTEM_PROMPT: str`, the bullets from spec §8 joined
  - `EDGE_LABELS: dict[tuple[str, str], tuple[str, str]]`, the five edges from spec §8
  - `build_graph(*, library: LibraryClient, checkpointer=None, llm_factory: LLMFactory | None = None)`
  - `State(TypedDict)`: `messages: Annotated[list, add_messages]` and `tool_rounds: int`

- [ ] **Step 1: Write the failing tests.** Use a recording fake chat model, a `ScriptedChatModel` subclass or a small `BaseChatModel` that records `tool_choice` per call, and a fake library client:
  - `test_first_call_of_each_question_forces_search_book`: two questions give recorded choices `["search_book", None, "search_book", None]`.
  - `test_model_ignoring_forced_choice_still_searches` (Review Focus 4): the model answers in text on round 0. The graph inserts an `AIMessage` tool call to `search_book` with `{"query": <question>}`, the fake library records the call, and the model is then called again.
  - `test_round_cap_forces_text`: after 6 tool rounds, the next binding has `tool_choice="none"`.
  - `test_stop_and_empty_routing`: "stop" goes to END, and "" goes back to `ask`.
  - `test_edge_labels_cover_conditional_edges`: every conditional edge of `graph_topology(build_graph(...))` is in `EDGE_LABELS`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_semantic_graph.py tests/test_skeletons.py -q`
  Expected: FAIL, because `build_graph` doesn't exist.

- [ ] **Step 3: Implement** with `Command(goto=…)` routing, as Approval does.
  - **`ask`:** returns `Command[Literal["agent", "ask", "__end__"]]`.
  - **`agent`:** returns `Command[Literal["tools", "ask"]]` and binds per round:

    | Round | Binding |
    |---|---|
    | 0 | `bind_tools(tools, tool_choice="search_book")` |
    | 1 to 5 | `bind_tools(tools)` |
    | 6 or later | `bind_tools(tools, tool_choice="none")` |

  - **Fallback on round 0:** if round 0 returns no tool calls, replace the reply with `AIMessage("", tool_calls=[{"name": "search_book", "args": {"query": question}, "id": "forced-search"}])` and go to `tools`.
  - **`tools`:** `ToolNode(library_tools(library))`, with an edge `tools` → `agent`.

- [ ] **Step 4: Run** the same command.
  Expected: PASS.

- [ ] **Step 5: Commit** with the message "Semantic agent: ReAct over the library, first search forced".

---

### Task 6: The Studio: registry, catalog, app, offline script

**Files:**
- Modify: `src/agentic_solutions/web/registry.py`: add `library` to `BuildContext`, add `_build_semantic`, and add the spec `semantic`
- Modify: `src/agentic_solutions/web/app.py`: `create_app(..., library=None)`, plus `_open_library(settings, stack, app, library)`, which opens `InProcessLibraryClient(build_server(open_index(...)))`, called from `lifespan` next to `_open_erp`
- Modify: `src/agentic_solutions/web/config.py`: `library_dir: str = "data/library"`, read from `LIBRARY_DIR`
- Modify: `src/agentic_solutions/web/catalog.yaml`: in `memory/semantic`, add `demo: semantic` and `builds_on: [memory/session, cognitive/react, execution/tool-use]`
- Modify: `src/agentic_solutions/web/offline/scripts.py`: add the `SEMANTIC` script and the `SEMANTIC_SAMPLES`
- Modify: `tests/conftest.py` (pass a fake-embedder library), `tests/fakes.py` (`make_library(tmp_path)`), `tests/test_registry.py` (`EXPECTED_EDGES["semantic"]`, catalog order and modes), `tests/test_catalog_api.py` (`LIVE_ROUTES` gains `memory/semantic`, and the guide count drops by one), and `tests/test_catalog.py` (Semantic's `builds_on`)
- Test: `tests/test_semantic_offline.py`

**Interfaces:**
- Consumes: Tasks 3–5.
- Produces:
  - `BuildContext.library: LibraryClient | None = None`
  - `PATTERNS["semantic"]`, with mode `chat`, title "Semantic memory: answers from a vector database", the samples from spec §8, `edge_labels=lambda limit: semantic_graph.EDGE_LABELS`, and no `layout`
  - `SCRIPTS["semantic"]`

- [ ] **Step 1: Write the failing tests** in `tests/test_semantic_offline.py`. Run the offline graph against a library built on the real text but with `FakeEmbedder`, so the runs are fast and deterministic.
  - `test_each_sample_searches_then_answers_with_real_citations`: for each sample, the first AI message calls `search_book`. The final answer cites at least one `(Book <N>, <a>–<b>)`, each cited range exists in `parse_text(TEXT_PATH)`, and every quoted phrase in the answer (text in “…” or '…') appears in those lines.
  - `test_end_of_poem_sample_reads_book_xii`: the "How does the poem end?" run calls `read_passage` with `book="XII"`, and its answer quotes "They, hand in hand, with wandering steps and slow".
  - `test_uncovered_question_says_so` (Review Focus 1): "What did Milton eat for breakfast?" searches, then answers with a sentence saying the passages don't cover it, and contains no `(Book` citation.

  Update the existing tests listed under Files to the new state.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_semantic_offline.py tests/test_registry.py tests/test_catalog_api.py tests/test_catalog.py -q`
  Expected: FAIL (there is no `semantic` pattern yet).

- [ ] **Step 3: Implement the script.** It's tool-bound and reads its turn, the same way as `_order_step`:
  - **First step:** call `search_book` with a fixed query per sample. The Mammon sample uses the query "Mammon speaks in the council".
  - **End-of-poem sample:** next, call `read_passage("XII", <last line - 20>, <last line>)`. Compute the last line from the tool result or from the `parse_text` line count, not from a constant.
  - **Answer:** build it from the passages the tool returned, quoting a line from the returned text and citing the passage's own `book`, `start_line` and `end_line`. Citations then come from real results by construction, whatever embedder ranked them.
  - **Uncovered questions:** a search whose results share no content words with the question (stop words excluded) produces "The passages I found don't cover this. I searched for "<query>"."
  - **Fallback:** list the samples.

  Then wire the registry, the config, `app.py` and `conftest.py`.

- [ ] **Step 4: Run** the full suite: `.venv/bin/python -m pytest -q`
  Expected: all pass, with no model downloaded. Check that no `data/library/models` appears under the test `tmp_path`.

- [ ] **Step 5: Commit** with the message "Studio: Semantic is a live demo over the library MCP server".

---

### Task 7: The Guide, first-start check and browser check

**Files:**
- Modify: `src/agentic_solutions/agents/semantic_memory_agent/explanation.md` (rewrite to the standard sections, per spec §9)
- Modify: `README.md` (one short paragraph under the existing demos: the Semantic demo, `LIBRARY_DIR`, the about-50-second first start, and `python tools/prepare_paradise_lost.py` with the `prep` extra)

- [ ] **Step 1: Rewrite the Guide** to the sections `tests/guide_format.py` requires. The Mapping section names `ask`, `agent`, `tools`, the `library` MCP server, Qdrant hybrid search (dense plus BM25 with RRF), the forced first search, and "Line numbers follow this edition."
  Run `.venv/bin/python -m pytest tests/test_guides.py tests/test_registry.py -q`.
  Expected: PASS.

- [ ] **Step 2: First real start.** Start the app with a fresh `LIBRARY_DIR` in the scratchpad, plus scratch `CHECKPOINT_DB`, `ERP_DB` and `ERP_APPROVAL_SECRET`, and `PORT=8741`.
  Expected: the log shows "Indexing Paradise Lost: <n> chunks…" and then the time taken (under 120 s). Restart, and the log shows no indexing line.

- [ ] **Step 3: Browser check at 1440 × 900** (CDP through Windows Chrome and Windows Node, as in the earlier sessions). Check that:
  - the home page Semantic card shows ● (live);
  - on `#/memory/semantic`, each sample runs on Offline, the trace shows `ask` → `agent` → `tools` → `agent`, edge labels show, and answers carry citations;
  - "How does the poem end?" shows a `read_passage` call;
  - there are no console errors.

  Then pick a live model if a key is configured, ask "Who is Abdiel?", and confirm that the first tool call is `search_book`. Skip this with a note in the ledger if there's no key. Save the screenshots to `images/semantic-*.png`.

- [ ] **Step 4: Run the full suite:** `.venv/bin/python -m pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit** with the message "Semantic Guide and README; first-start and browser checks".
