# Pattern Catalog Menu (Milestone 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Studio's numbered tabs with a catalog of 21 agentic design patterns in 5 categories. The catalog has a home page with search, a page per pattern with breadcrumbs, the existing live workbench for the 4 live patterns, and Guide-only pages with static skeleton-graph diagrams for the other 16.

**Architecture:**
- A Python catalog module is the single source of the taxonomy, and FastAPI serves it.
- Each Guide-only pattern gets an agent folder with a no-op skeleton `StateGraph`, whose `get_graph()` gives the diagram, plus an `explanation.md`.
- The no-build frontend gains a hash router, a catalog home view, and a static mode for the graph component.

**Tech Stack:** Python ≥ 3.11 (venv 3.14), LangGraph 1.2, FastAPI, pytest; vanilla ES modules + Cytoscape/dagre (already loaded); Windows `node.exe` for the optional JS unit test.

**Spec:** `docs/superpowers/specs/2026-11-22-pattern-catalog-menu-design.md` (the "Catalog spec"), building on `docs/superpowers/specs/2026-11-22-agentic-patterns-studio-design.md` (the "Studio spec"). Executors read both.

**Branch:** `feature/pattern-catalog`, cut from `feature/patterns-studio` (M1, open as a PR). Work in place; don't touch `main`.

## Global Constraints

- **Taxonomy:** categories, order, names, questions, hints and aliases exactly as Catalog spec §3.1–§3.2. Routes are `<category>/<pattern>` with the ids from §3.2.
- **Skeletons:**
  - Node names and edges exactly as Catalog spec §6.
  - Node functions return `{}`, and routers are `Literal[...]`-annotated.
  - `build_skeleton()` is the only export.
  - No `__main__.py`, no module-level `graph`, no `langgraph.json` entry.
- **Guides (Catalog spec §7):**
  - The seven `##` headings in order (What it is, When to use it, How this graph works, LangGraph concepts, Trade-offs, Key code, Try this).
  - The Key code fence is ≤ 25 lines, and the file is 50–110 lines.
  - Every backticked `langgraph.…` dotted name must import.
  - `[[category/pattern]]` markers must name catalog routes.
- **No regressions:** M1 behaviour must not change for live patterns (workbench, threads, restore, guards). All existing tests keep passing. The only existing test assertions you may edit are ones that hard-code the old `#<patternId>` routing or the tab strip; list them in your report.
- **XSS:** no `innerHTML` anywhere except the existing DOMPurify use in `guide.js`. Build links with `document.createElement("a")`.
- **Offline-only:** tests make no network calls.
- **Commits:** commit after every task with `git -c user.name="$(git log -1 --format=%an main)" -c user.email="$(git log -1 --format=%ae main)" commit …`, and end the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never stage `.env`.

## Review Focus

1. **Searches that should find something.** "remember users" → Episodic. "human sign-off" → Approval. "HITL" → Approval. "RAG" → Semantic. "evaluator-optimizer" → Reflection. A query like "users memory" (word order reversed) also finds Episodic. Test in Task 10 (JS unit test).
2. **Old links and bookmarks.** `#qa`, `#chat_loop`, `#guardrail` and `#human_in_loop` redirect to the new routes, and a remembered M1 thread for that pattern still restores. Unknown routes show the catalog with a "That pattern wasn't found" notice and never a blank page. Test in Task 11 (browser checklist; the redirect map is a unit-tested pure function).
3. **Cross-listed Tool Use.** It opens the ReAct content with the Execution breadcrumb, and ←/→ step through Execution, not Cognitive. Its status follows ReAct's. Tests in Task 1 (status) and Task 8 (API page data).
4. **Leaving a live pattern mid-run by navigating to the catalog or a Guide-only page.** The stream is aborted, the session's run slot is freed, and no stale events land in the new view. Browser check in Task 11. The M1 guards (`chatGen`, tokens) must cover route changes.
5. **Guide-only pages with no running backend state.** Opening one creates no thread and makes no `/runs` call, and the static diagram renders with no counters or pulses. Tests in Task 8 (no thread created) and Task 11 (screenshot).

---

## File structure

```
src/agentic_solutions/web/catalog.py                CREATE  taxonomy data + pure helpers
src/agentic_solutions/web/app.py                    MODIFY  /api/catalog endpoints, skeleton topologies at startup
src/agentic_solutions/agents/<16 folders>/          CREATE  __init__.py, graph.py (build_skeleton), explanation.md
    react_agent reflection_agent plan_execute_agent search_agent
    supervisor_agent swarm_agent hierarchy_agent
    episodic_memory_agent semantic_memory_agent knowledge_graph_agent
    routing_agent workflow_agent event_driven_agent autonomous_agent
    audit_agent review_agent
src/agentic_solutions/agents/{qa,chat,secure_chat,interrupt_chat}_agent/explanation.md   MODIFY  content pass
src/agentic_solutions/web/static/router.js          CREATE  parse/format routes, legacy redirect map
src/agentic_solutions/web/static/catalog.js         CREATE  home view + search (pure `matches()` exported)
src/agentic_solutions/web/static/app.js             MODIFY  route-driven views replace tabs
src/agentic_solutions/web/static/graph.js           MODIFY  createGraph(el, topology, {static})
src/agentic_solutions/web/static/guide.js           MODIFY  [[category/pattern]] links
src/agentic_solutions/web/static/index.html, styles.css, api.js   MODIFY
tests/test_catalog.py  tests/test_skeletons.py  tests/test_guides.py  tests/test_catalog_api.py
tests/js/search.test.mjs  tests/js/router.test.mjs  tests/test_js.py
README.md                                           MODIFY
```

---

### Task 1: Catalog data module

**Files:** Create `src/agentic_solutions/web/catalog.py`. Test `tests/test_catalog.py`.

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) CatalogPattern(id, category, name, hint, aliases: tuple[str, ...], demo: str | None, crosslist_of: str | None, folder: str | None)`, with a `route` property returning `f"{category}/{id}"`.
  - `@dataclass(frozen=True) Category(id, name, question, patterns: tuple[CatalogPattern, ...])`.
  - `CATALOG: tuple[Category, ...]`.
  - `def entry(route: str) -> CatalogPattern | None`.
  - `def target(p: CatalogPattern) -> CatalogPattern`, which follows `crosslist_of` once.
  - `def status(p: CatalogPattern, live_ids: Collection[str]) -> Literal["live","guide"]`, computed through `target(p)`.
  - `def neighbours(route: str) -> tuple[str, str]`, the previous and next routes within the route's own category, wrapping.
- Values come from Catalog spec §3.1–3.2.
  - `demo`: `qa`, `chat_loop`, `guardrail`, `human_in_loop` for the four live entries; `react`, `reflection`, `plan_execute` for the three M3 entries; `None` for the rest.
  - `folder`: the live entries use their existing folders; Guide-only entries use the §6 folder names; `tool-use` uses `None`.
  - `crosslist_of`: `"cognitive/react"` for `tool-use`, otherwise `None`.

- [ ] **Step 1: Write the failing tests:**

```python
from agentic_solutions.web import catalog as c
from agentic_solutions.web.registry import PATTERNS

def test_categories_in_order_with_questions():
    assert [(k.id, k.name, k.question) for k in c.CATALOG] == [
        ("cognitive", "Cognitive", "How should the agent think?"),
        ("collaboration", "Collaboration", "How many agents, and who leads?"),
        ("memory", "Memory", "What must it remember?"),
        ("execution", "Execution", "How does it act and run?"),
        ("governance", "Governance", "How is it kept safe and accountable?")]

def test_twenty_one_patterns_in_spec_order():
    assert [p.route for k in c.CATALOG for p in k.patterns] == [
        "cognitive/react", "cognitive/reflection", "cognitive/planning", "cognitive/search",
        "collaboration/single-agent", "collaboration/supervisor", "collaboration/swarm", "collaboration/hierarchy",
        "memory/session", "memory/episodic", "memory/semantic", "memory/knowledge-graph",
        "execution/tool-use", "execution/routing", "execution/workflow", "execution/event-driven", "execution/autonomous",
        "governance/guardrails", "governance/approval", "governance/audit", "governance/review"]

def test_hints_and_aliases_match_spec():   # transcribe Catalog spec §3.2 into EXPECTED = {route: (name, hint, aliases)}
    for k in c.CATALOG:
        for p in k.patterns:
            assert (p.name, p.hint, p.aliases) == EXPECTED[p.route], p.route

def test_every_registered_demo_is_reachable_exactly_once():
    demos = [p.demo for k in c.CATALOG for p in k.patterns if p.demo and not p.crosslist_of]
    assert sorted(set(PATTERNS) & set(demos)) == sorted(PATTERNS) and len(demos) == len(set(demos))

def test_tool_use_crosslists_react_and_follows_its_status():
    tool = c.entry("execution/tool-use")
    assert c.target(tool).route == "cognitive/react"
    assert c.status(tool, live_ids={"qa"}) == "guide"
    assert c.status(tool, live_ids={"react"}) == "live"

def test_status_live_only_when_demo_registered():
    assert c.status(c.entry("governance/approval"), PATTERNS) == "live"
    assert c.status(c.entry("cognitive/reflection"), PATTERNS) == "guide"

def test_neighbours_wrap_within_category():
    assert c.neighbours("execution/tool-use") == ("execution/autonomous", "execution/routing")
    assert c.neighbours("governance/review") == ("governance/audit", "governance/guardrails")

def test_unknown_route_is_none():
    assert c.entry("memory/nope") is None and c.entry("nonsense") is None
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_catalog.py -v` and confirm it FAILS (ModuleNotFoundError).
- [ ] **Step 3: Implement** `catalog.py`.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS.
- [ ] **Step 5: Commit** with "Add pattern catalog data module".

---

### Task 2: Skeleton and guide test harness + Cognitive skeletons

**Files:**
- Create: `tests/test_skeletons.py`, `tests/test_guides.py`.
- Create: `agents/{react_agent,reflection_agent,plan_execute_agent,search_agent}/{__init__.py,graph.py,explanation.md}`.
- Modify: `tests/test_registry.py` only if its heading test must also accept the new files. It already globs `agents/*/explanation.md`, so it should need no change.

**Interfaces:**
- Produces:
  - `tests/test_skeletons.py::SKELETONS: dict[str, tuple[set[str], set[tuple[str, str]]]]`, mapping folder → (nodes without `__start__`/`__end__`, edges as `(src, dst)` including `__start__`/`__end__`). Later tasks append their rows.
  - `tests/test_guides.py`, which applies to every `agents/*/explanation.md`.
- Consumes: `catalog.CATALOG` (Task 1), for link validation and the folder list.

- [ ] **Step 1: Write the failing tests.** `tests/test_skeletons.py`:

```python
import importlib, inspect, typing
import pytest
from agentic_solutions.web.topology import graph_topology

SKELETONS = {
    "react_agent": ({"ask", "agent", "tools"},
        {("__start__","ask"), ("ask","agent"), ("ask","ask"), ("ask","__end__"), ("agent","tools"), ("agent","ask"), ("tools","agent")}),
    "reflection_agent": ({"generate", "critique", "revise"},
        {("__start__","generate"), ("generate","critique"), ("critique","revise"), ("critique","__end__"), ("revise","critique")}),
    "plan_execute_agent": ({"planner", "executor", "tools", "synthesizer"},
        {("__start__","planner"), ("planner","executor"), ("executor","tools"), ("executor","executor"),
         ("executor","synthesizer"), ("tools","executor"), ("synthesizer","__end__")}),
    "search_agent": ({"propose", "score", "answer"},
        {("__start__","propose"), ("propose","score"), ("score","propose"), ("score","answer"), ("answer","__end__")}),
}

@pytest.mark.parametrize("folder", sorted(SKELETONS))
def test_skeleton_topology_matches_spec(folder):
    mod = importlib.import_module(f"agentic_solutions.agents.{folder}.graph")
    t = graph_topology(mod.build_skeleton())
    nodes = {n["id"] for n in t["nodes"]} - {"__start__", "__end__"}
    edges = {(e["source"], e["target"]) for e in t["edges"]}
    assert (nodes, edges) == SKELETONS[folder]

@pytest.mark.parametrize("folder", sorted(SKELETONS))
def test_skeleton_exports_only_build_skeleton_and_routers_are_literal(folder):
    mod = importlib.import_module(f"agentic_solutions.agents.{folder}.graph")
    assert not hasattr(mod, "graph")
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("route_"):
            assert typing.get_origin(typing.get_type_hints(fn)["return"]) is typing.Literal, name
```

`tests/test_guides.py` covers every `agents/*/explanation.md`:
- `test_key_code_fence_at_most_25_lines`: count the lines inside the first fenced block under `## Key code`.
- `test_length_50_to_110_lines`.
- `test_langgraph_names_import`: for each backticked token matching `^langgraph(\.\w+)+$`, check that `importlib.import_module` on the module part plus `getattr` on the attribute succeeds.
- `test_crosslinks_name_catalog_routes`: every `[[x/y]]` marker is a valid `catalog.entry` route.
- `test_guide_only_h1_is_taxonomy_name`: for every catalog entry with a `folder`, the file's first line is `# {name}`, or for the live four it is the taxonomy name per Task 7.
  - In this task, restrict that test to the folders in `SKELETONS`, using a module-level `H1_CHECK = set(SKELETONS)`. Task 7 extends it to the live four.

- [ ] **Step 2: Run** `pytest tests/test_skeletons.py tests/test_guides.py -v`. Expected: the skeleton tests FAIL with ModuleNotFoundError, and the guide tests PASS for the existing four guides, apart from the H1 check, which is restricted for now.
- [ ] **Step 3: Implement the four folders.**
  - `graph.py` has a docstring saying the module is a skeleton and naming "Live demo: milestone 3" for react, reflection and plan_execute. It defines a small `TypedDict` state and no-op node functions, and its `route_*` functions return one fixed branch.
  - `explanation.md` per Catalog spec §7. Dividing lines (§3.3) appear in react (vs Tool Use and Autonomous), reflection (vs Review) and plan_execute (vs Workflow).
  - Ground the content in the Studio spec §4.7–4.9 for the three M3 patterns.
  - Search describes tree-of-thoughts/LATS-style exploration. Its LangGraph concepts name `langgraph.types.Send` for parallel candidate expansion.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS.
- [ ] **Step 5: Commit** with "Add skeleton/guide tests and Cognitive pattern skeletons".

---

### Task 3: Collaboration skeletons (Supervisor, Swarm, Hierarchy)

**Files:** Create `agents/{supervisor_agent,swarm_agent,hierarchy_agent}/…`. Modify `tests/test_skeletons.py`, adding rows to `SKELETONS`.

- [ ] **Step 1: Add the rows** (the test now fails). Edges per Catalog spec §6:
  - supervisor: `__start__>supervisor`, `supervisor>researcher`, `supervisor>writer`, `supervisor>__end__`, `researcher>supervisor`, `writer>supervisor`
  - swarm: `__start__>triage`, `triage>billing`, `triage>technical`, `triage>__end__`, `billing>technical`, `billing>__end__`, `technical>billing`, `technical>__end__`
  - hierarchy: `__start__>director`, `director>research_lead`, `director>writing_lead`, `director>__end__`, `research_lead>searcher`, `research_lead>analyst`, `research_lead>director`, `searcher>research_lead`, `analyst>research_lead`, `writing_lead>drafter`, `writing_lead>editor`, `writing_lead>director`, `drafter>writing_lead`, `editor>writing_lead`
- [ ] **Step 2: Run** `pytest tests/test_skeletons.py -v` and confirm it FAILS.
- [ ] **Step 3: Implement.**
  - Each guide states the Supervisor vs Hierarchy vs Swarm line (§3.3).
  - LangGraph concepts: supervisor uses a conditional router or `langgraph.types.Command` with `goto`; swarm handoffs use `langgraph.types.Command`; hierarchy uses subgraphs, described in prose.
  - Each "Try this" points to `[[collaboration/single-agent]]` as the live baseline.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS. **Step 5: Commit** with "Add Collaboration pattern skeletons".

---

### Task 4: Memory skeletons (Episodic, Semantic, Knowledge Graph)

**Files:** Create `agents/{episodic_memory_agent,semantic_memory_agent,knowledge_graph_agent}/…`. Modify `tests/test_skeletons.py`.

- [ ] **Step 1: Add the rows:**
  - episodic: `__start__>recall_episodes`, `recall_episodes>answer`, `answer>store_episode`, `store_episode>__end__`
  - semantic: `__start__>retrieve`, `retrieve>grade`, `grade>answer`, `grade>rewrite_query`, `rewrite_query>retrieve`, `answer>__end__`
  - knowledge-graph: `__start__>extract_entities`, `extract_entities>query_graph`, `query_graph>answer`, `answer>update_graph`, `update_graph>__end__`
- [ ] **Step 2: Run** the test and confirm it FAILS.
- [ ] **Step 3: Implement.**
  - The Episodic guide states the Session vs Episodic line and names `langgraph.store.base.BaseStore` (verify the exact import path in langgraph 1.2 before writing it).
  - Semantic describes RAG with a relevance-grading loop.
  - Knowledge Graph describes extracting entities and relations into a graph store and querying it.
  - Each "Try this" points to `[[memory/session]]`.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS. **Step 5: Commit** with "Add Memory pattern skeletons".

---

### Task 5: Execution skeletons (Routing, Workflow, Event Driven, Autonomous)

**Files:** Create `agents/{routing_agent,workflow_agent,event_driven_agent,autonomous_agent}/…`. Modify `tests/test_skeletons.py`.

- [ ] **Step 1: Add the rows:**
  - routing: `__start__>classify`, `classify>billing`, `classify>technical`, `classify>general`, `billing>__end__`, `technical>__end__`, `general>__end__`
  - workflow: `__start__>extract`, `extract>validate`, `validate>transform`, `validate>handle_error`, `transform>load`, `load>__end__`, `handle_error>__end__`
  - event-driven: `__start__>receive_event`, `receive_event>handle_order`, `receive_event>handle_refund`, `receive_event>ignore`, `handle_order>emit_result`, `handle_refund>emit_result`, `ignore>__end__`, `emit_result>__end__`
  - autonomous: `__start__>set_goal`, `set_goal>plan`, `plan>act`, `act>observe`, `observe>check_goal`, `check_goal>plan`, `check_goal>report`, `report>__end__`
- [ ] **Step 2: Run** the test and confirm it FAILS.
- [ ] **Step 3: Implement.**
  - Workflow states the Planning vs Workflow line.
  - Autonomous states the ReAct vs Autonomous line and the narrowed definition ("long-running, self-directed until the goal is met").
  - Event Driven explains that the graph is started by an external trigger, such as a queue consumer, webhook or cron, calling `invoke`, and that the trigger itself sits outside the graph.
  - Routing explains its difference from Supervisor: it routes once, with no loop back.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS. **Step 5: Commit** with "Add Execution pattern skeletons".

---

### Task 6: Governance skeletons (Audit, Review)

**Files:** Create `agents/{audit_agent,review_agent}/…`. Modify `tests/test_skeletons.py`.

- [ ] **Step 1: Add the rows:**
  - audit: `__start__>act`, `act>record`, `record>act`, `record>summarize`, `summarize>__end__`
  - review: `__start__>draft`, `draft>review`, `review>draft`, `review>approve`, `approve>__end__`
- [ ] **Step 2: Run** the test and confirm it FAILS.
- [ ] **Step 3: Implement.**
  - Audit states the narrowed definition and the "Audit vs the trace panel" line, and names the checkpointer history (`aget_state_history`) as one source of records.
  - Review states the Reflection vs Review line.
  - Both point to `[[governance/approval]]` and `[[governance/guardrails]]`.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS. **Step 5: Commit** with "Add Governance pattern skeletons".

---

### Task 7: Content pass on the four live guides

**Files:** Modify `agents/{qa_agent,chat_agent,secure_chat_agent,interrupt_chat_agent}/explanation.md` and `tests/test_guides.py`, extending `H1_CHECK` to all catalog folders.

- [ ] **Step 1:** Extend `H1_CHECK` to every catalog entry with a folder. The test then FAILS, because the live four have M1 titles.
- [ ] **Step 2: Edit the guides.**
  - **H1:** `# Single Agent`, `# Session`, `# Guardrails`, `# Approval`.
  - **Dividing lines:**
    - Session vs Episodic, in chat_agent.
    - Approval vs Review, in interrupt_chat_agent.
    - Guardrails vs Review, in secure_chat_agent.
    - Single Agent vs Supervisor/Swarm/Hierarchy, in qa_agent.
  - **Pointers:** add `[[…]]` links to related patterns.
  - **Keep** every existing "Try this" input: `tests/test_offline_scripts.py` must still pass unchanged. The 50–110 line limit applies.
- [ ] **Step 3: Run** `pytest -q` and confirm all PASS, including the M1 offline-script tests.
- [ ] **Step 4: Commit** with "Align live pattern guides with the catalog".

---

### Task 8: Catalog API

**Files:** Modify `src/agentic_solutions/web/app.py`. Test `tests/test_catalog_api.py`.

**Interfaces:**
- Consumes: `catalog` (Task 1), `PATTERNS` and the registry titles, `graph_topology`, and `build_skeleton` from each Guide-only folder.
- Produces (Catalog spec §5.2; field names fixed):
  - `GET /api/catalog` returns `{"categories": [{"id","name","question","patterns": [{"id","name","hint","aliases","status","route","target"}]}]}`.
  - `GET /api/catalog/{category}/{pattern}` returns `{"route","target","category": {"id","name"},"name","status","demo","demo_title","explanation_md","topology","prev","next"}`.
    - `prev` and `next` come from `catalog.neighbours(route)`.
    - For a cross-list, the content (`name`, `explanation_md`, `topology`, `demo`, `demo_title`, `status`) comes from the target, while `route`, `category`, `prev` and `next` come from the requested route.
  - Unknown route → 404 `{"detail": "not found"}`.
- At startup, inside `create_app`'s lifespan, after the live graphs are compiled:
  - Compute the page data for every route once.
  - Topology: live entries use `app.state.topologies[demo]`. Guide entries use `graph_topology(import_module(f"agentic_solutions.agents.{folder}.graph").build_skeleton())`.
  - Store the results in `app.state.catalog_pages`.
- Accept an optional `registry` parameter on `create_app` (default `PATTERNS`) so tests can flip status. If the existing code makes that awkward, inject the set of live ids instead and say which in the report.

- [ ] **Step 1: Write the failing tests** (using the conftest `client`/`app` fixtures):
  - `test_catalog_listing_shape_and_order`: 5 categories, 21 patterns, and the statuses: live for single-agent, session, guardrails and approval; guide for the other 17, including tool-use.
  - `test_page_for_live_pattern`: `governance/approval` has status live, demo `human_in_loop`, the `demo_title` equal to the registry title, `explanation_md` starting with `# Approval`, a topology that includes `ask`, and prev/next `governance/guardrails` / `governance/audit`.
  - `test_page_for_guide_only_pattern`: `memory/episodic` has status guide, `demo is None`, and topology nodes ⊇ {recall_episodes, answer, store_episode}.
  - `test_crosslist_page_uses_target_content_and_request_category`: `execution/tool-use` has `target == "cognitive/react"`, `category["id"] == "execution"`, `explanation_md` starting with `# ReAct`, and prev/next within execution.
  - `test_unknown_route_404`: covers both `memory/nope` and `nope/nope`.
  - `test_status_flips_when_demo_registered`: build an app whose registry includes a fake `reflection` spec (or a live-ids set that includes it), and check `cognitive/reflection` reports live.
  - `test_opening_guide_page_creates_no_thread`: GET the episodic page, then check `app.state.store` (or the ThreadStore) holds no records (Review Focus 5).
- [ ] **Step 2: Run** and confirm it FAILS. **Step 3: Implement.** **Step 4: Run** `pytest -q` and confirm all PASS.
- [ ] **Step 5: Commit** with "Serve the pattern catalog API".

---

### Task 9: Frontend router and legacy redirects

**Files:**
- Create `static/router.js` and `tests/js/router.test.mjs`. Create `tests/test_js.py`, which runs `node --test tests/js/` with `NODE_BIN` (default: `node` on PATH, else `/mnt/c/Program Files/nodejs/node.exe`) and **skips** when neither exists.
- Modify `static/app.js`, `static/api.js` (add `getCatalog()` and `getCatalogPage(route)`) and `static/index.html` (remove the tab strip; add a breadcrumb header container and a `#home` view container).

**Interfaces:**
- `router.js` exports pure functions:
  - `parseHash(hash) -> {view: "home"} | {view: "pattern", route: "<category>/<pattern>"} | {view: "legacy", route} | {view: "unknown"}`.
  - `LEGACY = {qa: "collaboration/single-agent", chat_loop: "memory/session", guardrail: "governance/guardrails", human_in_loop: "governance/approval"}`.
  - `formatHash(route) -> "#/" + route`, and `"#/"` for home.
- `app.js`:
  - Drives views from the hash. A legacy hash uses `history.replaceState` to the new hash.
  - `unknown` goes home and shows the notice "That pattern wasn't found".
  - The pattern view loads `getCatalogPage(route)`. When `demo` is set it opens the existing M1 workbench for `demo`; the workbench code is reused unchanged, with the registry title as the subtitle. Otherwise it uses the Guide-only view (Task 10).
  - Remembered threads stay keyed by registry id, so M1 threads survive the redirect.
  - Route changes run the same stale-load and abort logic as M1 tab changes: `requestedId` becomes `requestedRoute`, and the stream aborts.
  - Focus moves to the view heading, `document.title` is set (Catalog spec §4.3), and the announcer says "Opened {Pattern}".

- [ ] **Step 1: Write** `tests/js/router.test.mjs` with `node:test` + `node:assert`. Cover: `""`, `"#"` and `"#/"` → home; `"#/governance/approval"` → pattern; `"#guardrail"` → legacy `governance/guardrails`; `"#/x"` and `"#%E0"` → unknown; `formatHash` round-trips. Write `tests/test_js.py`.
- [ ] **Step 2: Run** `pytest tests/test_js.py -v` and confirm it FAILS (router.js missing).
- [ ] **Step 3: Implement** router.js, the api.js additions and the app.js view switching. Update any existing `tests/test_static.py` assertion that hard-codes the tab strip, and list it in the report.
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS. `node.exe --check` every changed `.js`.
- [ ] **Step 5: Commit** with "Route the Studio by catalog paths".

---

### Task 10: Catalog home, search, Guide-only view, breadcrumbs, guide links

> Use the `frontend-design:frontend-design` skill. Keep the existing design tokens and lab-bench look. The mockup in `.superpowers/brainstorm/menu/menu-layouts.html` (option C) shows the intended structure.

**Files:**
- Create `static/catalog.js` and `tests/js/search.test.mjs`.
- Modify `static/app.js`, `static/graph.js`, `static/guide.js`, `static/styles.css` and `static/index.html`.

**Interfaces:**
- `catalog.js` exports:
  - `matches(query: string, pattern, category) -> boolean`, a pure function following Catalog spec §4.2: word-wise, every word must match, a trailing `s` is dropped, and the haystack is name + hint + aliases + category name + question.
  - `renderHome(el, catalogJson, {onOpen})`, which builds the cards with DOM APIs. Status marks: `●` labelled "Live demo", `○` labelled "Guide", and `↗ ReAct` on cross-lists. It also wires the search box: filtering, the `aria-live` count, Enter opens the first match, `/` focuses the box, Esc clears it, and the empty-results text from §4.2.
- `graph.js`: `createGraph(el, topology, {static = false} = {})`. In static mode, nodes are idle-styled, conditional edges are dashed and labelled, there are no counters or pulses, and the returned API is no-ops except `destroy`.
- `guide.js`: `renderGuide(el, markdown, {linkFor} = {})`. `[[category/pattern]]` markers become `<a href="#/category/pattern">` whose text is `linkFor(route)` (the pattern name), built with `createElement`. When `linkFor` returns null the marker renders as plain text. Markers inside code spans or fences are left alone.
- Pattern header: breadcrumb links Catalog › {Category} › {Pattern}, ←/→ buttons from `prev`/`next`, and plain ←/→ keys when focus is not in an input, textarea or contenteditable element (Catalog spec §4.3).
- Guide-only view: the banner with the exact §4.3 copy, then the static diagram, then the Guide. No console, no timeline, no thread calls.
- Accessibility (Catalog spec §4.4): the home page is a `nav` containing one list per category, and the search input has a label. The breadcrumb is `nav aria-label="Breadcrumb"` with `aria-current="page"`. Status marks are not colour-only.

- [ ] **Step 1: Write** `tests/js/search.test.mjs`. Build fixtures from a JSON snapshot of `/api/catalog` (generate it in the test via `tests/test_js.py`, writing `tests/js/catalog.fixture.json` from `catalog.py` before running node, or commit a generated fixture plus a pytest check that it is current). Assert (Review Focus 1):

```js
const hits = (q) => all.filter(({p, c}) => matches(q, p, c)).map(({p}) => p.route);
assert.deepEqual(hits("remember users"), ["memory/episodic"]);
assert.ok(hits("human sign-off").includes("governance/approval"));
assert.deepEqual(hits("HITL"), ["governance/approval"]);
assert.ok(hits("RAG").includes("memory/semantic"));
assert.deepEqual(hits("evaluator-optimizer"), ["cognitive/reflection"]);
assert.deepEqual(hits("users memory"), ["memory/episodic"]);
assert.deepEqual(hits("zzz"), []);
assert.equal(hits("").length, 21);
```

  If a query returns more than the asserted pattern because of the wording of hints in §3.2, the spec's examples win. Adjust the matching rule only within §4.2, and report it.
- [ ] **Step 2: Run** `pytest tests/test_js.py -v` and confirm it FAILS.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest -q` and confirm all PASS. `node.exe --check` every changed `.js`. Confirm the `innerHTML` rule still passes.
- [ ] **Step 5: Commit** with "Add catalog home, search, Guide-only pages and breadcrumbs".

---

### Task 11: Browser checklist and README

**Files:** Modify `README.md`. Screenshots go in the scratchpad, not the repo.

- [ ] **Step 1: Browser checklist.** Drive headless Windows Chrome over CDP, as in M1. Start the server with `OFFLINE_LATENCY_SCALE=1 HF_HUB_OFFLINE=1`, and stop it with `kill $(cat pidfile)`, never `pkill -f`. Save a screenshot per item:
  - (a) The home page at 1440, 900 and 375 px, in both themes.
  - (b) Searches: "HITL", "remember users", "human sign-off" and "zzz".
  - (c) Opening Approval runs a sample, and the trace animates.
  - (d) Opening Episodic shows the banner and the static diagram, with no network call to `/threads` (check the CDP network log).
  - (e) `#/execution/tool-use` shows the Execution breadcrumb and ReAct content.
  - (f) ←/→ wrap within Execution.
  - (g) `#guardrail` redirects, and the remembered thread restores.
  - (h) Navigating from a mid-run Approval stream to the catalog: no stale events, and the next run on Approval works (Review Focus 4).
  - (i) Reloading on a pattern route.
  - (j) `#/memory/nope` shows the home page with the notice.
- [ ] **Step 2: README.** Update the "Patterns Studio" section: the catalog home, routes, Guide-only pages, the 21-pattern taxonomy table (category → patterns, live marked), and how a skeleton becomes a live demo (add a registry entry whose id matches the catalog `demo`). Add the new folders to the Architecture block.
- [ ] **Step 3: Run** `pytest -q` and confirm all PASS. Check that the four CLI modules import.
- [ ] **Step 4: Commit** with "Document the pattern catalog".

---

## After this plan

- **M3 (live ReAct, Reflection, Planning):** fill the three skeleton folders with live graphs, keeping the node names, and register `react`, `reflection` and `plan_execute`. Carry the M1 follow-ups' "M2" list into it (`docs/superpowers/plans/2026-11-22-patterns-studio-m1-followups.md`).
- **M4 (Live mode, hardening, deploy):** the M1 follow-ups' "M3" list.
