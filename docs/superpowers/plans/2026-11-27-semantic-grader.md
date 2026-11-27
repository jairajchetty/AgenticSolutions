# Semantic Grader and Query Rewriter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `grade` and `rewrite_query` nodes to the Semantic demo. Each search result is filtered passage by passage. When nothing relevant survives, the search is rephrased and run again (at most 2 times per question).

**Architecture:**
- `tools` goes to `grade`. `grade` either rewrites the latest `search_book` `ToolMessage`s in place (same `id`) and goes to `agent`, or goes to `rewrite_query`.
- `rewrite_query` emits a new `search_book` call and goes to `tools`.
- Both nodes call the selected model with one forced tool (`grade_passages` or `rewrite_search`).
- The offline script recognises them by the first line of their system prompts.

**Tech Stack:** Python 3.14, LangGraph, LangChain tool calling, pytest.

**Spec:** `docs/superpowers/specs/2026-11-27-semantic-grader-rewriter-design.md`

## Global Constraints

- `MAX_REWRITES = 2` per question, and every rewrite also counts toward `MAX_TOOL_ROUNDS = 6`. `ask` resets both `rewrites` and `tool_rounds`.
- The grader and the rewriter use the selected model (the graph's `llm_factory`) with a forced `tool_choice` naming their own tool.
- Graded `ToolMessage` content is `json.dumps({"passages": [...survivors], "not_relevant": n})`. Ungraded results (grading failed, or `read_passage`) keep their original content.
- A grading failure (no call, bad arguments, numbers out of range) passes the passages through unchanged.
- Only `search_book` results are graded.
- Edge labels: `grade` → `agent` is "relevant", and `grade` → `rewrite_query` is "none relevant", with the full rules from spec §4. Every conditional edge stays labelled.
- Desktop-only: the browser check is at 1440 px.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Two `search_book` calls in one round, one of which finds something relevant:** the round goes to `agent`, and only the empty one carries `"passages": []`. The test is in Task 1.
2. **Grader numbers out of range, or repeated** (`[0, 7, 7]` for 3 passages): out-of-range numbers are ignored and repeats are counted once. If nothing valid remains, the passages pass through unchanged. The test is in Task 1.
3. **A rewriter that returns the same query as before:** it still counts as a rewrite, so the cap ends the loop. The test is in Task 1.
4. **A rewrite on round 5:** `tool_rounds` reaches 6, and the next `agent` call answers in text. The cap holds across rewrites. The test is in Task 1.
5. **An offline answer after grading:** the script reads the `{"passages": …}` form as well as the plain list. The test is in Task 2.

---

### Task 1: The `grade` and `rewrite_query` nodes

**Files:**
- Modify: `src/agentic_solutions/agents/semantic_memory_agent/graph.py`
- Modify: `tests/test_semantic_graph.py`
- Modify: `tests/test_edge_labels.py` (the semantic layout test: add `grade` and `rewrite_query` to the bent-pair checks only if their pairs exist; positions must cover every node)

**Interfaces:**
- Produces, in `graph.py`:
  - `MAX_REWRITES = 2`
  - `GRADER_PROMPT: str`, which starts with the line `You grade search results for a question about Paradise Lost.`
  - `REWRITER_PROMPT: str`, which starts with the line `You rewrite a search query for Paradise Lost.`
  - `State` gains `rewrites: int`
  - `EDGE_LABELS` gains the two `grade` edges
  - `LAYOUT` gains positions for `grade` and `rewrite_query`
  - `grade_input(question: str, passages: list[dict]) -> str` and `rewrite_input(question: str, tried: list[str]) -> str`, which build the human message for each call
- The grader's human message looks like this:
  ```
  Question: <q>

  Passages:
  [1] Book I, 241–263:
  <text>

  [2] …
  ```
- The rewriter's human message looks like this:
  ```
  Question: <q>
  Queries tried:
  - <q1>
  - <q2>
  ```
- Tools (`StructuredTool`s with no-op bodies, used only for binding):
  - `grade_passages(relevant: list[int])`, with the description "The numbers of the passages that help answer the question; [] if none."
  - `rewrite_search(query: str)`, with the description "One new search query, in different words."

- [ ] **Step 1: Write the failing tests** in `tests/test_semantic_graph.py`. Extend `RecordingModel` to record the bound tool names, and use a `FakeLibrary` whose `search_book` returns three passages, `p1`, `p2` and `p3`.
  - `test_grader_drops_irrelevant_passages`: the replies are a search call, then `grade_passages(relevant=[2])`, then text. The agent's last call sees one `ToolMessage` whose JSON is `{"passages": [p2], "not_relevant": 2}`.
  - `test_none_relevant_rewrites_and_searches_again`: the replies are a search call, `grade([])`, `rewrite_search("new words")`, `grade([1])`, then text. The library calls are `["q", "new words"]`, and the second `search_book` call's id starts with `rewrite-`.
  - `test_rewrite_cap`: three `grade([])` replies with two rewrites in between. After the second rewrite's grade, the run goes to `agent`, and the library receives 3 searches in total.
  - `test_rewrite_same_query_still_counts` (Review Focus 3).
  - `test_malformed_grade_passes_through` (Review Focus 2): `grade_passages(relevant=[0, 7, 7])` on 3 passages leaves the content unchanged. `[0, 2, 2, 7]` keeps passage 2 only.
  - `test_read_passage_round_skips_grading`: no model call is bound to `grade_passages` after a read-only round.
  - `test_two_searches_one_relevant` (Review Focus 1).
  - `test_round_cap_holds_across_rewrites` (Review Focus 4).
  - `test_counters_reset_per_question`.
  - `test_grader_and_rewriter_are_forced`: their recorded `tool_choice`s are `"grade_passages"` and `"rewrite_search"`.

  Existing tests whose model queues assumed `tools` → `agent` must add a grade reply after each search. Update them in place.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_semantic_graph.py -q`
  Expected: FAIL (there is no `grade` node yet).

- [ ] **Step 3: Implement.**
  - **`grade`:** takes the latest `AIMessage`'s `search_book` call ids and the matching `ToolMessage`s.
    - If there are none, it goes to `agent` with no update.
    - Otherwise it parses each message's JSON list. Content that doesn't parse, or isn't a list, passes through.
    - It numbers all passages across the messages from 1, calls the model, and keeps the valid numbers (as a set).
    - It writes `ToolMessage(content=…, tool_call_id=…, name=…, id=<same id>)` replacements.
    - Any survivor, or `rewrites >= MAX_REWRITES`, goes to `agent`; otherwise to `rewrite_query`.
  - **`rewrite_query`:** collects the `search_book` query arguments since the last human message, calls the model with a forced `rewrite_search`, and falls back to the question minus the last query's words.
    - It emits `AIMessage("", tool_calls=[{"name": "search_book", "args": {"query": q}, "id": f"rewrite-{uuid4().hex[:12]}"}])`, with `rewrites + 1` and `tool_rounds + 1`.
    - If the fallback leaves nothing, it goes to `agent` with no new call.
  - **Wiring:** `tools` → `grade`. The routing uses `Command`, with `Literal["agent", "rewrite_query"]` and `Literal["tools", "agent"]`.
  - **Labels and layout:** add the edge labels from spec §4. Positions are the builder's choice; the layout must place every node and keep the loop visible.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_semantic_graph.py tests/test_edge_labels.py -q`
  Expected: PASS.

- [ ] **Step 5: Commit** with the message "Semantic: grade search results and rewrite the query when none are relevant".

---

### Task 2: The offline grader and rewriter

**Files:**
- Modify: `src/agentic_solutions/web/offline/scripts.py`
- Modify: `tests/test_semantic_offline.py`

**Interfaces:**
- Consumes: `GRADER_PROMPT`, `REWRITER_PROMPT`, the input formats and the graded content form from Task 1.
- Produces: `_semantic_step` dispatches on `messages[0]` (a system message whose first line matches `GRADER_PROMPT` or `REWRITER_PROMPT`) to `_scripted_grade(messages)` or `_scripted_rewrite(messages)`. Otherwise it runs the existing agent step.

- [ ] **Step 1: Write the failing tests** in `tests/test_semantic_offline.py`. Give the `run` fixture a way to return the node order; for example, record `astream(stream_mode="updates")` node names.
  - `test_breakfast_shows_the_corrective_loop`: the node order after `ask` is `agent, tools, grade, rewrite_query, tools, grade, rewrite_query, tools, grade, agent`. The answer says "don't cover", and its source checks pass (it has no sources).
  - `test_samples_grade_relevant_first_time`: for each of the three samples, `grade` is followed by `agent`, never by `rewrite_query`, and `check_citations` passes.
  - `test_sources_never_cite_a_dropped_passage`: for each sample, every source's (Book, start_line) is in the graded `passages` of the final tool results.
  - `test_agent_reads_graded_form` (Review Focus 5).

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_semantic_offline.py -q`
  Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **`_scripted_grade`:** parses the `Question:` line and the `[n] Book …` blocks. A passage is relevant when no content word of the question is missing from the poem (`_in_poem`) and the passage shares a content word with the question. It returns `_call("grade_passages", relevant=[...])`.
  - **`_scripted_rewrite`:** uses a fixed rewrite list for the breakfast question, `["meal food eating at morning", "Adam and Eve eat a meal"]`, picking the first not already in "Queries tried". Otherwise it uses the question's content words, then the question itself.
  - **The agent step:** accepts `{"passages": […]}` as well as a list.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit** with the message "Offline Semantic: scripted grader and rewriter; the breakfast question shows the loop".

---

### Task 3: The Guide, layout check and live check

**Files:**
- Modify: `src/agentic_solutions/agents/semantic_memory_agent/explanation.md` (Mapping: Grader → `grade`, Query rewriter → `rewrite_query`; "Try this": the breakfast loop; Framework concepts: forced tool calls for both)
- Modify: `graph.py` `LAYOUT` only if the browser check shows overlaps

- [ ] **Step 1: Update the Guide.**
  Run `.venv/bin/python -m pytest tests/test_guides.py tests/test_offline_scripts.py -q`.
  Expected: PASS. The Guide must stay at 50–130 lines, and every backticked "Try this" input must hit a scripted rule.

- [ ] **Step 2: Browser check at 1440 × 900**, with an app on a scratch `CHECKPOINT_DB` and the existing real index at `scratchpad/semantic-run1/lib`. Run the breakfast question offline. Every label and run count must be readable, with no overlaps and no console errors. Adjust `LAYOUT` until they are, and save `images/semantic-graph-grader.png`.

- [ ] **Step 3: Live check** with `scratchpad/live_check.py` (run with `python -I`), on Claude Haiku and DeepSeek. For "Who is Abdiel?" and "What did Milton eat for breakfast?", check that:
  - both forced tools are accepted (no HTTP errors);
  - the trace contains `grade`;
  - every source's range contains its quote;
  - the breakfast question rewrites at least once.

  Note in the ledger anything a model does differently.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit** with the message "Semantic Guide: grader and rewriter; layout and live checks".
