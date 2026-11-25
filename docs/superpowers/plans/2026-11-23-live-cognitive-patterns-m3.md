# Live Cognitive Patterns + Local Live Mode (Milestone 3) Implementation Plan

> **Superseded in part (2026-11-25):** the local Live switch moved to the Model Picker spec (`docs/superpowers/specs/2026-11-25-model-picker-design.md`). Task 8 (Local Live backend), the Live switch and mode badge in Task 10, Task 12 (live smoke check), and Task 1's live API error mapping are superseded; skip them when M3 resumes. The tool-calling scripted model from Task 2 is already built on `feature/approval-demo`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ReAct, Reflection and Plan-and-Execute live demos (offline-scripted by default), and add a local-only Live switch that runs a conversation on real Claude.

**Architecture:**
- **New patterns:** each pattern fills its existing skeleton folder with a real LangGraph graph that keeps the skeleton's node names, and registers in `web/registry.py`, which turns it live in the catalog automatically.
- **Offline mode:** the scripted model learns tool calls and structured output.
- **Live mode:** the server compiles each pattern once per mode (`offline` / `live`), threads carry their mode, and Live is offered only when an API key is set and both the bind host and the requesting client are loopback.

**Tech Stack:** Python ≥ 3.11, LangGraph 1.2 (`ToolNode`, `interrupt`), langchain-core `@tool`, langchain-anthropic 1.7.6 (`with_structured_output(method="json_schema", include_raw=True)`), FastAPI, pytest; vanilla ES modules; Windows `node.exe` for JS unit tests.

**Spec:** `docs/superpowers/specs/2026-11-23-live-cognitive-patterns-design.md` (the "M3 spec"). It builds on the Studio spec (`…-agentic-patterns-studio-design.md` §3a, §4.7–4.9, §5, §8, §9) and the Catalog spec (`…-pattern-catalog-menu-design.md` §6). Executors read all three.

**Branch:** `feature/cognitive-live` (stacked on `feature/pattern-catalog`). Work in place.

## Global Constraints

- **Node names:** ReAct `ask`, `agent`, `tools`; Reflection `generate`, `critique`, `revise`; Planning `planner`, `executor`, `tools`, `synthesizer`. Topologies must equal the Catalog spec §6 rows. Planning's row now includes `planner ⇢ executor | synthesizer`.
- **Caps:**
  - ReAct allows 8 tool rounds per user turn (`tool_rounds`, reset by `ask`). Its final call keeps the tools bound with `tool_choice={"type":"none"}`. `recursion_limit` 60 is a backstop only.
  - Planning allows 2 tool rounds per step (`step_tool_rounds`). The final call per step uses `tool_choice={"type":"none"}`. `step_messages` is cleared when the step advances.
  - Reflection stops at `score >= 8` or `iteration == 3`.
- **Structured output:** `with_structured_output(Schema, method="json_schema", include_raw=True)`, returning `{"raw","parsed","parsing_error"}`.
  - `Critique(score: int 1–10, feedback: str)` and `Plan(steps: list[str])`.
  - A refusal or `parsed is None` ends the pattern as `completed`, with `declined=True` in state.
  - `critique` declined: keep the current draft, Drafts note "The critic declined to score this draft."
  - `planner` declined: route to `synthesizer`, result "The model declined to plan this task."
  - A plan with more than 5 steps is truncated to 5. An empty plan counts as declined.
- **Text-node refusal:** a response whose `response_metadata["stop_reason"] == "refusal"` becomes `AIMessage("The model declined this request.")`. Applies to `agent`, `generate`, `revise`, `executor` and `synthesizer`.
- **Live availability, all required:**
  1. The provider credential is set (`ANTHROPIC_API_KEY` for `anthropic:` models).
  2. `Settings.host` is loopback (`127.0.0.1`, `::1` or `localhost`).
  3. `LIVE_MODEL`'s provider package imports; startup fails loudly if not.
  4. **Per request**, `request.client.host` is in {`127.0.0.1`, `::1`}.
- **Live model:** `LIVE_MODEL` default `anthropic:claude-haiku-5-5`, `max_tokens=4096`, no `temperature`, no explicit `thinking`.
- **Safe live error copy, exact text:**
  - auth: "The Anthropic API key was rejected."
  - rate limit: "Claude is busy. Try again in a moment."
  - connection or timeout: "Couldn't reach Claude."
  - other: "The run failed."

  The thread closes, as in M1.
- **API (additive; field names fixed):**
  - `GET /api/session` → `{mode:"offline", live_available, live_model, live_model_label, max_input_chars}`.
  - `POST /api/patterns/{id}/threads` takes an optional body `{"mode":"offline"|"live"}`. Requesting live when it is unavailable → 403 `{"detail":"live mode is not available"}`.
  - `GET /api/threads/{tid}/state` adds `mode`.
- **Tests:** no test calls the Anthropic API. The live paths use injected fake models.
- **Unchanged behaviour:** M1 and M2 behaviour must not change for the existing patterns. All existing tests keep passing. The only existing assertions you may edit are those whose expected values change by design, e.g. the `/api/session` dict, the SKELETONS rows for the three folders, and the catalog "4 live" counts. List each edit in the report.
- **Frontend:** no `innerHTML` outside guide.js's DOMPurify use.
- **Commits:** commit with `git -c user.name="$(git log -1 --format=%an main)" -c user.email="$(git log -1 --format=%ae main)" commit …`. Never stage `.env` or `.superpowers/`.

## Review Focus

1. **A non-loopback client must never see or use Live**, even when `HOST` says loopback (for example the app started with `--host 0.0.0.0`). Test in Task 8 (fake `request.client.host`).
2. **The live model returns unusable structured output** (refused, unparseable, an empty plan, or more than 5 steps). The run completes with the declined copy, or truncates to 5 steps; it never ends in `error`. Tests in Tasks 5 and 6.
3. **Hostile or huge calculator input**, e.g. `9**9**9`, `().__class__`, `__import__('os')`, `1/0`, or 10,000 nested parentheses, returns an error string fast and never raises or hangs. Test in Task 3.
4. **Flipping the Live switch mid-conversation** does not change the open thread's mode, and a restored thread shows its own mode. Tests: the API in Task 8, the UI in Task 10.
5. **ReAct hits the 8-round cap with a live model that keeps calling tools.** The turn ends with a text reply and the thread stays resumable at `ask`. Test in Task 4, with a scripted model that always returns tool calls.

---

## File structure

```
src/agentic_solutions/common/llm.py            MODIFY  declined_or(msg) helper
src/agentic_solutions/web/serialize.py         MODIFY  NaN/inf→None; role-pair heuristic tightened
src/agentic_solutions/web/runner.py            MODIFY  live error-copy mapping (no other behaviour change)
src/agentic_solutions/web/offline/model.py     MODIFY  bind_tools, with_structured_output, richer Rule replies
src/agentic_solutions/web/offline/scripts.py   MODIFY  scripts for react, reflection, plan_execute
src/agentic_solutions/web/registry.py          MODIFY  register react, reflection, plan_execute
src/agentic_solutions/web/config.py            MODIFY  host, port, live_model
src/agentic_solutions/web/live.py              CREATE  live availability + live factory + model label
src/agentic_solutions/web/app.py               MODIFY  graphs per (pattern, mode); session/threads/state mode
src/agentic_solutions/web/__main__.py          MODIFY  host/port from Settings
src/agentic_solutions/agents/react_agent/      MODIFY  graph.py (live), tools.py, __main__.py, explanation.md
src/agentic_solutions/agents/reflection_agent/ MODIFY  graph.py (live), __main__.py, explanation.md
src/agentic_solutions/agents/plan_execute_agent/ MODIFY graph.py (live), __main__.py, explanation.md
src/agentic_solutions/agents/hierarchy_agent/explanation.md  MODIFY (Command.PARENT wording)
src/agentic_solutions/web/static/{app.js,console.js,api.js,index.html,styles.css}  MODIFY
src/agentic_solutions/web/static/patternviews.js  CREATE  pure helpers: chip text, plan checklist reducer, drafts list data
langgraph.json                                  MODIFY  add react, reflection, plan_execute
tests/: test_serialize.py test_runner.py test_offline_model.py test_tools.py test_react_graph.py
        test_reflection_graph.py test_plan_execute_graph.py test_live.py test_api.py test_skeletons.py
        test_guides.py test_offline_scripts.py tests/js/patternviews.test.mjs
README.md                                       MODIFY
```

---

### Task 1: Serialization and runner carry-overs

**Files:**
- Modify: `web/serialize.py`, `web/runner.py`
- Test: `tests/test_serialize.py`, `tests/test_runner.py`

**Interfaces:**
- Produces:
  - `to_jsonable` maps `float('nan')`, `inf` and `-inf` to `None`.
  - Only a 2-item tuple or list whose first item is in `{"user","human","assistant","ai","system","tool"}` and whose second item is a `str` becomes a message.
  - `runner.safe_error_message(exc: BaseException) -> str`, returning the exact copy from Global Constraints. Use `anthropic.AuthenticationError`, `anthropic.RateLimitError`, and `anthropic.APIConnectionError`/`anthropic.APITimeoutError`. Import `anthropic` lazily inside the function; check isinstance with a guarded import.
  - The runner uses `safe_error_message` on node failure. A timeout keeps "The run timed out."

- [ ] **Step 1: Write the failing tests.**
  - `test_nan_and_inf_become_null`: `to_jsonable({"a": float("nan"), "b": [float("inf")]}) == {"a": None, "b": [None]}`.
  - `test_plan_steps_stay_a_list`: `to_jsonable({"steps": ["Convert 5 mi", "Compare"]}) == {"steps": ["Convert 5 mi", "Compare"]}`.
  - `test_safe_error_copy`, parametrized over constructed anthropic exceptions. Build them via `anthropic.AuthenticationError(message="x", response=httpx2_response, body=None)`; if construction is awkward, subclass with `__new__`, and note it in the report.
  - `test_runner_reports_rate_limit_copy`: a graph whose node raises `RateLimitError` yields `{"type":"error","message":"Claude is busy. Try again in a moment."}`.
  - `test_runner_early_close_closes_stream`: break after the first event, `aclose()` the generator, and assert no warning or exception.
  - `test_tokens_from_list_of_block_chunks`: a node whose model streams `AIMessageChunk(content=[{"type":"text","text":"hi"}])` yields a `token` event with text "hi". Use a tiny custom chat model in the test.
  - `test_runner_aggregates_usage_and_tool_events`: a tiny graph whose node returns an `AIMessage` with `tool_calls` and `usage_metadata`, plus a `ToolMessage`. Assert the `tool_call`/`tool_result` events and the `run_finished.usage` totals.
- [ ] **Step 2:** Run `pytest tests/test_serialize.py tests/test_runner.py -v` and confirm it FAILS.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 5:** Commit: "Harden serialization and map live API errors to safe copy".

---

### Task 2: Scripted model: tools, structured output, richer rules

**Files:**
- Modify: `web/offline/model.py`
- Test: `tests/test_offline_model.py`

**Interfaces:**
- Produces:
  - `Rule(match, reply, kind: Literal["text","tools","structured"] | None = None, schema: type | None = None)`. `kind`/`schema` restrict a rule to a call kind; `None` matches any.
  - `reply` may be a `str`, an `AIMessage`, a pydantic `BaseModel` instance, or a callable `(messages) -> one of those`.
  - `ScriptedChatModel.bind_tools(tools, *, tool_choice=None, **kw)` returns a copy whose calls are kind `"tools"`. When `tool_choice` is `{"type":"none"}` or `"none"`, any `tool_calls` in the chosen reply are stripped and its text is kept (or the fallback text is used).
  - `ScriptedChatModel.with_structured_output(schema, *, method="json_schema", include_raw=False, **kw)` returns a Runnable. With `include_raw=True` it yields `{"raw": AIMessage, "parsed": instance | None, "parsing_error": None}`; otherwise it yields the instance. A rule reply of `None` gives `parsed=None`, which lets tests script a declined structured call.
  - `matched_rule` behaviour is unchanged, and so is streaming for text replies. Tool-call replies are returned as one chunk with no pacing.
  - `Script.fallback` may also be any reply type above.

- [ ] **Step 1: Write the failing tests:**
  - `test_tool_call_reply_round_trip`: a bound model returns an AIMessage with a `calculator` tool call.
  - `test_tool_choice_none_strips_tool_calls`.
  - `test_structured_include_raw_shape`.
  - `test_structured_none_means_declined` (`parsed is None`).
  - `test_callable_rule_sees_whole_history`.
  - `test_kind_restricts_rule`: the same text gets different replies for the text, tools and structured kinds.
  - `test_pacing_sleeps_when_scaled`: monkeypatch `time.sleep`, assert it is called for a non-zero latency and not when latency is `(0,0)`.
- [ ] **Step 2:** Run and confirm it FAILS. **Step 3:** Implement. **Step 4:** Run `pytest -q` and confirm all PASS. M1 offline tests unchanged.
- [ ] **Step 5:** Commit: "Teach the scripted model tool calls and structured output".

---

### Task 3: Tools

**Files:**
- Create: `agents/react_agent/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Produces `calculator(expression: str) -> str`, `current_time(timezone: str = "UTC") -> str`, `unit_convert(value: float, from_unit: str, to_unit: str) -> str`, `pattern_glossary(term: str) -> str`, all as langchain `@tool`s, plus `TOOLS = [calculator, current_time, unit_convert, pattern_glossary]`. Every error is returned as a string starting `"Error: "` and never raised.
- calculator:
  - Uses an `ast.parse(mode="eval")` whitelist: numbers, `+ - * / // % **`, unary `-`/`+`, parentheses.
  - `**` is allowed only when |exponent| ≤ 10 and |base| ≤ 1e6.
  - Input is limited to 200 characters before parsing.
  - The result is formatted with `repr` for ints, and with 12 significant digits for floats.
- unit_convert:
  - Length units: m, km, cm, mm, mi, ft, in.
  - Mass units: kg, g, lb, oz.
  - Temperature units: C, F, K.
  - Converting across dimensions returns `"Error: cannot convert <a> to <b>"`.
- pattern_glossary:
  - Matches case-insensitively against catalog entries' name, hint and aliases (import `agentic_solutions.web.catalog`).
  - Also covers a small `CORE_TERMS` dict: checkpointer, interrupt, reducer, tool node, structured output.
  - A miss returns "No glossary entry for '<term>'."

- [ ] **Step 1: Write the failing tests**, including the Review Focus 3 cases:

```python
@pytest.mark.parametrize("expr", ["9**9**9", "().__class__", "__import__('os')", "a+1", "(" * 10000 + "1" + ")" * 10000, "2**11", "1/0"])
def test_calculator_rejects_safely(expr):
    out = calculator.invoke({"expression": expr})
    assert out.startswith("Error: ")

def test_calculator_basic():
    assert calculator.invoke({"expression": "17*23"}) == "391"
    assert calculator.invoke({"expression": "-(2+3)**2"}) == "-25"

def test_unit_convert():
    assert unit_convert.invoke({"value": 5, "from_unit": "mi", "to_unit": "km"}).startswith("8.04672")
    assert unit_convert.invoke({"value": 100, "from_unit": "C", "to_unit": "F"}).startswith("212")
    assert unit_convert.invoke({"value": 1, "from_unit": "kg", "to_unit": "m"}).startswith("Error: ")

def test_current_time_zones():
    assert "T" in current_time.invoke({"timezone": "Asia/Tokyo"})
    assert current_time.invoke({"timezone": "Mars/Base"}).startswith("Error: ")

def test_glossary():
    assert "conversation" in pattern_glossary.invoke({"term": "checkpointer"}).lower()
    assert pattern_glossary.invoke({"term": "HITL"}).startswith("Approval")
    assert pattern_glossary.invoke({"term": "zzz"}) == "No glossary entry for 'zzz'."
```

  Each rejection must also complete in under 1 s (`time.perf_counter`).
- [ ] **Step 2:** Run and confirm it FAILS. **Step 3:** Implement. **Step 4:** Run and confirm it PASSES.
- [ ] **Step 5:** Commit: "Add safe tools for ReAct and Planning".

---

### Task 4: ReAct live graph

**Files:**
- Modify: `agents/react_agent/graph.py` (replace the skeleton), `agents/react_agent/explanation.md`, `web/registry.py`, `web/offline/scripts.py`, `tests/test_skeletons.py` (remove the react row), `langgraph.json`.
- Create: `agents/react_agent/__main__.py`.
- Test: `tests/test_react_graph.py`.

**Interfaces:**
- Consumes: `TOOLS` (Task 3), `Rule`/`Script`/`ScriptedChatModel` (Task 2), and `interrupt_chat_agent.graph.ask` (reused for `ask`, extended to reset `tool_rounds`; wrap it). Also `common.llm.declined_or(msg: AIMessage) -> AIMessage`, created here in `common/llm.py`: it returns `AIMessage("The model declined this request.")` when `msg.response_metadata.get("stop_reason") == "refusal"`, else `msg`.
- Produces:
  - `build_graph(checkpointer=None, llm_factory=None)` and `graph = build_graph()`.
  - State `{messages, tool_rounds: int}`.
  - Routers:
    - `route_after_ask -> Literal["agent","ask","__end__"]` (stop / empty / else).
    - `route_after_agent -> Literal["tools","ask"]`.
  - `MAX_TOOL_ROUNDS = 8`.
  - Registry `react`: title "ReAct tool use", mode `chat`, folder `react_agent`, samples from M3 spec §4.
  - The offline script `SCRIPTS["react"]` has specific rules per sample and the generic fallback (one calculator round on "2+2").
  - `langgraph.json` gets `"react_agent": "./src/agentic_solutions/agents/react_agent/graph.py:graph"`, and likewise for the other two in Tasks 5 and 6.
- The `__main__.py` is an interactive loop like `interrupt_chat_agent/__main__.py`, using the default `get_llm()`.

- [ ] **Step 1: Write the failing tests** (scripted factory, `InMemorySaver`):
  - `test_topology_matches_catalog_row`: nodes {ask, agent, tools} and the M2 SKELETONS react edges, moved here.
  - `test_tool_round_then_answer`: the sample "What is 17 × 23, and what's that in hex?" produces tool messages and a final AI text, and the thread is paused at `ask`.
  - `test_cap_ends_turn_with_text` (Review Focus 5): a script whose tools-kind rule always returns a tool call. After 8 tool rounds the agent's final reply has no `tool_calls`, `next == ("ask",)`, and the ToolMessage count is 8.
  - `test_tool_rounds_reset_each_turn`.
  - `test_empty_and_stop_routes`.
  - `test_refusal_becomes_declined_text`: a fake model returns an AIMessage whose response_metadata has `stop_reason="refusal"`.
- [ ] **Step 2:** Run and confirm it FAILS.
- [ ] **Step 3: Implement the graph, script, registry entry, `__main__.py` and `langgraph.json` entry, then rewrite the guide.**
  - In the guide, Key code comes from the live graph, every "Try this" input has a scripted rule, and the skeleton wording is gone.
  - Redraw the module docstring diagram legibly: use a raw docstring, or no backslashes.
  - Remove the react row from `SKELETONS`.
- [ ] **Step 4:** Run `pytest -q` and confirm all PASS. The catalog API now reports `cognitive/react` and `execution/tool-use` as live; update those tests' expected live counts and list them.
- [ ] **Step 5:** Commit: "Make ReAct a live demo".

---

### Task 5: Reflection live graph

**Files:**
- Modify: `agents/reflection_agent/graph.py`, `explanation.md`, `web/registry.py`, `web/offline/scripts.py`, `tests/test_skeletons.py` (remove the row), `langgraph.json`.
- Create: `agents/reflection_agent/__main__.py` (task from argv).
- Test: `tests/test_reflection_graph.py`.

**Interfaces:**
- Produces:
  - `build_graph(checkpointer=None, llm_factory=None)` and `graph`.
  - State `{task: str, draft: str, critique: dict | None, score: int, feedback: str, iteration: int, history: list[dict], declined: bool}`. `history` items are `{"draft", "score", "feedback"}`. `score` stays a top-level key, as the M2 guide and exercise expect.
  - `Critique` is a pydantic model with `score: int` (1–10, validated with `Field(ge=1, le=10)`) and `feedback: str`.
  - `route_after_critique -> Literal["revise","__end__"]`.
  - `MAX_ITERATIONS = 3`, `PASS_SCORE = 8`.
  - Registry `reflection`: title "Reflection (generate → critique → revise)", mode `trigger`, `make_input(text)` → `{"task": text}`. `output(values)` returns the final draft, plus "\n\nScore {score}/10 after {iteration} draft(s)", or the declined note.
  - Offline script: per sample, critique scores 6 then 9; the generic fallback does the same.

- [ ] **Step 1: Write the failing tests:**
  - `test_topology_matches_catalog_row`.
  - `test_revises_once_then_passes`: the history has 2 entries with scores [6, 9], and the output contains "Score 9/10".
  - `test_stops_at_three_iterations` with scores always 5.
  - `test_declined_critique_keeps_draft` (Review Focus 2): the structured rule returns `None`, the status is completed, `declined=True`, and the output is the current draft plus "The critic declined to score this draft."
  - `test_out_of_range_score_is_declined`: a raw score of 11 fails parsing and is handled as declined.
  - `test_generate_refusal_text`.
- [ ] **Step 2:** Run and confirm it FAILS. **Step 3:** Implement and rewrite the guide. Its exercise answers must match the State keys exactly. **Step 4:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 5:** Commit: "Make Reflection a live demo".

---

### Task 6: Plan-and-Execute live graph

**Files:**
- Modify: `agents/plan_execute_agent/graph.py`, `explanation.md` (also soften "2–5 steps work best" to "short plans are easier to check"), `web/registry.py`, `web/offline/scripts.py`, `tests/test_skeletons.py` (remove the row), `langgraph.json`.
- Create: `agents/plan_execute_agent/__main__.py`.
- Test: `tests/test_plan_execute_graph.py`.

**Interfaces:**
- Produces:
  - `build_graph(checkpointer=None, llm_factory=None)` and `graph`.
  - State `{goal: str, steps: list[str], current_step: int, results: list[str], step_messages: list (add_messages reducer; cleared via RemoveMessage on advance), step_tool_rounds: int, answer: str, declined: bool}`.
  - `Plan` is a pydantic model with `steps: list[str]`.
  - Routers: `route_after_planner -> Literal["executor","synthesizer"]` and `route_after_executor -> Literal["tools","executor","synthesizer"]`.
  - `MAX_STEPS = 5`, `MAX_STEP_TOOL_ROUNDS = 2`.
  - `executor` binds the Task 3 `TOOLS`; `tools` is a `ToolNode(TOOLS, messages_key="step_messages")`.
  - Registry `plan_execute`: title "Plan-and-Execute", mode `trigger`, `make_input(text)` → `{"goal": text}`, and `output(values)` → `answer`.
  - Offline script: a three-step plan per sample, at least one step with a tool round; the generic fallback is a three-step plan.
- Topology edges:
  - `__start__>planner`
  - `planner>executor`
  - `planner>synthesizer`
  - `executor>tools`
  - `executor>executor`
  - `executor>synthesizer`
  - `tools>executor`
  - `synthesizer>__end__`

- [ ] **Step 1: Write the failing tests:**
  - `test_topology_matches_catalog_row`, using the edges above.
  - `test_each_step_runs_once_then_synthesizes`: the results length equals the steps length (3), and the answer is set.
  - `test_step_tool_rounds_capped_at_two`: the script always returns tool calls for a step, so exactly 2 ToolMessages for that step and then advance.
  - `test_step_messages_cleared_on_advance`.
  - `test_declined_plan_goes_to_synthesizer` (Review Focus 2): `parsed=None` gives answer "The model declined to plan this task." and status completed.
  - `test_empty_plan_is_declined`.
  - `test_long_plan_truncated_to_five`: 7 steps give 5.
- [ ] **Step 2:** Run and confirm it FAILS.
- [ ] **Step 3:** Implement. Update the Catalog-spec topology expectations wherever a test pins them, e.g. tests/test_catalog_api.py topology for `cognitive/planning`.
- [ ] **Step 4:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 5:** Commit: "Make Plan-and-Execute a live demo".

---

### Task 7: Guide and offline-script test upgrades

**Files:**
- Modify: `tests/test_guides.py`, `tests/test_offline_scripts.py`, `agents/hierarchy_agent/explanation.md`.

**Interfaces:**
- Consumes: `catalog`, `registry.PATTERNS`, and the compiled graphs, through `registry`'s `BuildContext` with offline factories.

- [ ] **Step 1: Write the failing or extended tests:**
  - `test_live_guides_do_not_say_skeleton`: for every catalog entry whose `demo` is in `PATTERNS`, its guide contains neither "skeleton" nor "placeholder" (case-insensitive).
  - Generalize `test_every_try_this_input_has_a_scripted_reply`:
    - It now covers every registered pattern.
    - The non-input allow-list is derived automatically: node ids from `graph_topology(compiled)`, plus keys of the graph's state schema (`compiled.get_input_jsonschema()` or `builder.schemas`; pick whichever the installed langgraph exposes and note it), plus existing literals.
- [ ] **Step 2: Edit `hierarchy_agent/explanation.md`.** Replace "where supported" with an exact mention of `Command(graph=Command.PARENT, goto=...)` from inside a subgraph. Verify against langgraph 1.2.16.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 4:** Commit: "Check live guides and derive Try-this allow-list from the graphs".

---

### Task 8: Local Live mode (backend)

**Files:**
- Modify: `web/config.py`, `web/__main__.py`, `web/app.py`, `web/threads.py` (if needed).
- Create: `web/live.py`.
- Test: `tests/test_live.py`, `tests/test_api.py` (session dict update).

**Interfaces:**
- Produces:
  - `Settings` gains `host: str = "127.0.0.1"`, `port: int = 8000` and `live_model: str = "anthropic:claude-haiku-5-5"`, read from the env vars `HOST`, `PORT` and `LIVE_MODEL`.
  - `__main__` uses `settings.host` and `settings.port`.
  - `live.py`:
    - `LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}`.
    - `def live_configured(settings) -> tuple[bool, str]`: whether Live is configured, plus a reason for the startup log. Covers rules 1–3 of Global Constraints.
    - `def client_is_loopback(request) -> bool`: rule 4.
    - `def live_factory(settings) -> LLMFactory`: builds `make_chat_model(settings.live_model, max_tokens=4096)` per call.
    - `def model_label(model: str) -> str`: `"anthropic:claude-haiku-5-5"` → "Claude Haiku 5.5", `"anthropic:claude-sonnet-5-5"` → "Claude Sonnet 5.5", `"anthropic:claude-opus-5-5"` → "Claude Opus 5.5"; anything else returns the raw id after the colon.
  - `create_app` takes a new keyword `live_factory_override: LLMFactory | None = None` for tests. When given, Live counts as configured, even without a key.
  - Graphs are stored in `app.state.graphs[(pattern_id, mode)]`. Live graphs are compiled only when Live is configured.
  - Every existing lookup by `spec.id` becomes `(spec.id, record.mode)`.
  - Routes:
    - `/api/session`: `live_available = configured and client_is_loopback(request)`.
    - `POST /api/patterns/{id}/threads`: optional body `{"mode"}`; live requires `live_available`, otherwise 403.
    - `/state` adds `mode`.
    - Runs on a live thread from a non-loopback client → 403 `{"detail":"live mode is not available"}`.
- Thread priming (chat patterns) uses the thread's mode graph.

- [ ] **Step 1: Write the failing tests**, using `create_app(..., live_factory_override=...)` and a `FakeListChatModel`-style live model:
  - `test_session_live_unavailable_without_key` (no key, no override).
  - `test_session_live_available_with_override_and_loopback`. TestClient's client host is `testclient`; set the client via `TestClient(app, client=("127.0.0.1", 50000))`, or check the installed starlette signature, and note it.
  - `test_non_loopback_client_never_sees_live` (Review Focus 1): client `("10.0.0.5", 1)` gives `live_available false`, a live thread POST gives 403, and a run on an existing live thread gives 403.
  - `test_non_loopback_host_setting_disables_live`: `Settings(host="0.0.0.0")` with the override gives unavailable.
  - `test_live_thread_runs_and_reports_mode` (Review Focus 4, API side): create a live `chat_loop` thread, run one message, check `/state` mode is "live", and confirm a new offline thread still reports "offline".
  - `test_model_label`.
  - Update the `/api/session` expected dict in `test_api.py`.
- [ ] **Step 2:** Run and confirm it FAILS. **Step 3:** Implement. **Step 4:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 5:** Commit: "Add local-only Live mode with per-thread mode".

---

### Task 9: Pattern views: pure helpers + JS tests

**Files:**
- Create: `web/static/patternviews.js`, `tests/js/patternviews.test.mjs`.

**Interfaces:**
- Produces pure ES-module exports, with no DOM at import time:
  - `chipText(name: string, args: object, result?: string) -> string`. Example: `🔧 calculator("17*23") → 391`. A single-argument object shows its value JSON-quoted; multiple arguments show compact JSON. The result is cut at 200 characters with "…".
  - `planChecklist(steps: string[], currentStep: number, results: string[]) -> {text, state: "done"|"active"|"pending", result?}[]`.
  - `draftsList(history: {draft, score, feedback}[], declined: boolean) -> {n, score, feedback, draft}[]`. When `declined` is true, append the note entry `{note: "The critic declined to score this draft."}`.

- [ ] **Step 1: Write the node tests:**
  - `chipText("calculator", {expression:"17*23"}, "391") === '🔧 calculator("17*23") → 391'`.
  - A 300-character result is truncated to 200 characters plus "…".
  - `planChecklist(["a","b","c"], 1, ["ra"])` gives the states `["done","active","pending"]`.
  - `draftsList` with declined appends the note.

  The existing `tests/test_js.py` runs them.
- [ ] **Step 2:** Run `pytest tests/test_js.py -v` and confirm it FAILS. **Step 3:** Implement. **Step 4:** Run and confirm it PASSES; also run `node.exe --check`.
- [ ] **Step 5:** Commit: "Add pure view helpers for tool chips, plan checklist and drafts".

---

### Task 10: Frontend: Live switch, mode badge, chips, drafts, checklist

> Use the `frontend-design:frontend-design` skill and keep the existing tokens.
>
> Build in the Blueprint design: `docs/superpowers/specs/2026-11-23-blueprint-redesign-design.md` tokens, sheets, amber rule.

**Files:**
- Modify: `web/static/app.js`, `console.js`, `api.js` (`createThread(patternId, {mode})`), `index.html`, `styles.css`.

**Interfaces:**
- Consumes: Task 8's API and Task 9's helpers.
- Behaviour, from M3 spec §3.4 and §6:
  - **The switch:** rendered only when `live_available`. Its two states are `Offline · scripted` and `Live · {live_model_label}`. It's remembered in `sessionStorage` (try/catch), defaults to Offline, and shows the note "Applies to your next chat." It applies at the next New chat or Run.
  - **The masthead badge:** shows the mode of the conversation on screen. On restore, the mode comes from `/state`.
  - **After a live run:** a muted note shows "N tokens" from `run_finished.usage.total_tokens`.
  - **Tool chips:** use `chipText`, live and on restore.
  - **Reflection:** a result card plus a collapsible "Drafts" list built with `draftsList`, from the state's `history`/`declined` (from `node_finished` updates and from `/state` on restore).
  - **Planning:** a result card plus a checklist built with `planChecklist`, updated on each `node_finished` for `planner`/`executor`. Each step's result can be expanded.
  - **Failed pattern switch (carry-over):** a non-404 load failure navigates home with a notice instead of leaving the old chrome on screen.

- [ ] **Step 1:** Implement, and `node.exe --check` every changed `.js`.
- [ ] **Step 2: Headless-Chrome checks (offline).** Screenshots go to the scratchpad. Check:
  - (a) ReAct sample: chips appear and `agent⇄tools` animates.
  - (b) Reflection sample: Drafts shows 6 then 9.
  - (c) Planning sample: the checklist ticks, and `tools` lights up during a step.
  - (d) Without a key, the switch is absent.
  - (e) Start the server with a dummy `ANTHROPIC_API_KEY` (no test-only env hooks). Check that the switch appears, that flipping it shows the note, and that the open thread's badge doesn't change (Review Focus 4, UI side). Do NOT send a live run with the dummy key.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS, including `test_static` (no `innerHTML`).
- [ ] **Step 4:** Commit: "Add Live switch, mode badge, tool chips, drafts and plan checklist".

---

### Task 11: Browser checklist + README

**Files:**
- Modify: `README.md`.

- [ ] **Step 1: Run the offline browser checklist over CDP.** Screenshots go to the scratchpad. Check:
  - The catalog shows ReAct, Reflection, Planning and Tool Use as ●.
  - Each of the three runs a sample end to end.
  - Restoring a ReAct thread after a reload rebuilds its chips.
  - Reflection and Planning result cards.
  - Mobile at 375 px.
  - Dark theme.
- [ ] **Step 2: README.**
  - The taxonomy table shows 7 live patterns.
  - New CLI commands for the three patterns.
  - A "Local Live mode" section covering: the requirements (key and loopback), `LIVE_MODEL`/`HOST`/`PORT`, that a conversation keeps its mode, that there are no budgets locally, and the error messages.
  - The tools list.
  - Verify every fact against the code.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS; the CLI modules import.
- [ ] **Step 4:** Commit: "Document live cognitive patterns and local Live mode".

---

### Task 12 (controller only, needs the person's go-ahead): live smoke check

- [ ] **Step 1: Ask the person before spending on their key.** With approval, start the server locally (key from `.env`) and run one sample of each of ReAct, Reflection and Planning in Live mode via CDP.
- [ ] **Step 2: Record the results:** screenshots, `run_finished.usage` totals, and any error copy seen. Fix-forward anything broken as a new task through the normal implement and review loop.

## After this plan

- **M4 (public Live, hardening, deploy):** access-code unlock deciding who may flip the switch, budgets, rate limits, CSP, Docker/Caddy and the load test.
- Carry the M4 lists from `docs/superpowers/plans/2026-11-22-patterns-studio-m1-followups.md` and `2026-11-22-pattern-catalog-m2-followups.md`.
