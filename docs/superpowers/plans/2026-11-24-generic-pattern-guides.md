# Generic Pattern Guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all 20 pattern Guides into a platform-neutral pattern write-up. Each Guide ends with one collapsed "How this Studio implements it" section, and tests enforce the format and its genericity.

**Architecture:**
- **Content:** Markdown only, in `agents/<folder>/explanation.md`.
- **Tests:** they gain a dual-mode harness. Old-format Guides are checked by the old rules while they are listed in an `UNMIGRATED` set, so the suite stays green while Guides migrate in batches.
- **Renderer:** `guide.js` learns to render the Studio section as a collapsed disclosure.

**Tech Stack:** Markdown, pytest, vanilla ES modules (`guide.js`), DOMPurify/marked (already loaded), Node `node:test` via Windows `node.exe`.

**Spec:** `docs/superpowers/specs/2026-11-24-generic-pattern-guides-design.md` (the "Guides spec"). §3 is the format, §4 the denylist, §5 rendering, §6 tests, §9 builder-check decisions. For the generic Approval body, use `docs/superpowers/specs/2026-11-24-approval-pattern-mcp-design.md` §3. For taxonomy names and the §3.3 dividing lines, see `docs/superpowers/specs/2026-11-22-pattern-catalog-menu-design.md`.

**Branch:** `feature/approval-mcp`. Work in place.

## Global Constraints

- **Section order (exact `##` titles):**
  1. What it is
  2. When to use it
  3. How it works
  4. Design considerations
  5. Trade-offs
  6. Related patterns
  7. How this Studio implements it

  Inside section 7, these exact `###` titles in order: Mapping, Framework concepts, Key code, Try this. The H1 is the taxonomy name.
- **Generic sections (H1 and sections 1–6):** none of the Guides spec §9.3 denylist. That means no backtick characters, no framework, protocol or vendor names, and none of `interrupt(`, `Command(`, `Send(`, `langgraph.`, `langchain`. `[[category/pattern]]` markers are allowed. Plain words like pause, resume, tool, checkpoint, handoff and supervisor are allowed.
- **Section contents:**
  - "When to use it" contains at least one bullet starting with "Not when".
  - "Design considerations" bullets each start with a **bolded decision name**.
  - The §3.3 dividing-line `[[route]]` markers live in "Related patterns".
- **Studio section:**
  - The Mapping names every node the pattern's diagram shows.
  - Key code is a single fence of ≤ 25 lines, copied from that folder's `graph.py`.
  - "Try this" inputs on live patterns keep working offline.
  - The word "skeleton" may appear only in section 7.
- **Length:** 50–130 lines per file.
- **Approval Guide (`interrupt_chat_agent/explanation.md`):** the generic body comes from the Approval spec §3. Its Studio section says honestly that this demo shows only the pause mechanism and that the full approval demo comes later.
- **Rendering:** `innerHTML` only through the existing DOMPurify path. The open state is one global `sessionStorage` key, `studio.guide.impl.open`, read and written inside try/catch. The disclosure is closed by default.
- **Tests:** none call the network. All existing tests keep passing at every commit.
- **Commits:** commit with `git -c user.name="$(git log -1 --format=%an main)" -c user.email="$(git log -1 --format=%ae main)" commit …`. Never stage `.env`, `.superpowers/` or `CV_*.pdf`. Never write the person's phone number or full email address into any file.

## Review Focus

1. **A generic section that slips in framework vocabulary through prose,** e.g. "the state graph", "a tool node", or a function name without backticks. The denylist catches the listed tokens. Reviewers of the content tasks also read for leaks the denylist can't see, such as node names (`ask`, `guard`) used as words in generic sections. Node names belong only in Mapping. Tests: Task 1's denylist, plus reviewer reading in Tasks 3–5.
2. **Facts changed during the rewrite:** a pattern's generic description must stay accurate, e.g. Session vs Episodic, Guardrails vs Review. Reviewer reading in Tasks 3–5 checks this against the catalog spec §3.3.
3. **A Studio section whose Mapping omits a node the diagram shows.** Test in Task 1 (`test_mapping_names_every_node`), applied to migrated Guides.
4. **Collapsed section and the keyboard or no-JS reader.** The `<details>` must be focusable and toggle with Enter or Space. Without JS, the raw Markdown shows everything. Browser check in Task 6.
5. **"Try this" inputs moved into section 7 must still each have a scripted offline reply.** Test in Task 1 (updated `test_offline_scripts.py` reads `### Try this`).

---

## File structure

```
tests/guide_format.py                 CREATE  parse helpers: sections(md), subsections(body), FORMAT_NEW/OLD, UNMIGRATED
tests/test_guides.py                  MODIFY  dual-mode rules; new genericity/mapping/order tests
tests/test_registry.py                MODIFY  heading test delegates to guide_format (dual-mode)
tests/test_offline_scripts.py         MODIFY  Try-this source = "### Try this" (new) or "## Try this" (old)
src/agentic_solutions/web/static/guide.js   MODIFY  render section 7 as <details> with ### sub-blocks
src/agentic_solutions/web/static/styles.css MODIFY  disclosure styling (Blueprint tokens)
tests/js/guide.test.mjs               MODIFY  node test: guide-rest split recognises section 7 + ### blocks
src/agentic_solutions/agents/*/explanation.md   MODIFY  20 Guides, in batches (Tasks 3–5)
README.md                              MODIFY  Task 6
```

---

### Task 1: Dual-mode Guide test harness

**Files:**
- Create: `tests/guide_format.py`.
- Modify: `tests/test_guides.py`, `tests/test_registry.py`, `tests/test_offline_scripts.py`.

**Interfaces:**
- Produces, in `tests/guide_format.py`:
  - `NEW_SECTIONS` holds the seven titles.
  - `STUDIO_SUBSECTIONS` holds the four `###` titles.
  - `OLD_SECTIONS` is today's seven-title list.
  - `UNMIGRATED: set[str]` starts as **all 20 folder names**.
  - `sections(md) -> list[tuple[str, str]]` splits on `## `, fence-aware.
  - `subsections(body) -> list[tuple[str, str]]` splits on `### `, fence-aware.
  - `generic_text(md) -> str` returns the H1 line plus sections 1–6.
  - `DENY_WORDS` and `DENY_SUBSTRINGS` hold the exact Guides spec §9.3 lists.
- All tests import from `guide_format`. Keep `from fakes import …` style imports working: `tests/` is on `sys.path` already.

- [ ] **Step 1: Write the tests.** Each new-format test is parametrized over **migrated** folders, i.e. all folders minus `UNMIGRATED`. Each old-format test is parametrized over `UNMIGRATED`, keeping today's behaviour.
  - `test_new_format_sections_in_order`: the `##` titles equal `NEW_SECTIONS`, and section 7's `###` titles equal `STUDIO_SUBSECTIONS`.
  - `test_generic_sections_have_no_framework_vocabulary` (Review Focus 1): `generic_text` contains no backtick, no `DENY_WORDS` match (case-insensitive `\b…\b`) and no `DENY_SUBSTRINGS` match (case-insensitive).
  - `test_when_to_use_has_a_not_when_bullet`.
  - `test_design_considerations_bullets_start_bold`.
  - `test_dividing_line_in_related_patterns`: the existing `DIVIDING` dict moves the check from "How this graph works" to "Related patterns" for migrated Guides. Old-format Guides keep the old check.
  - `test_mapping_names_every_node` (Review Focus 3): every node id from that folder's graph topology, excluding `__start__` and `__end__`, appears in the Mapping subsection. Get the topology via `graph_topology` and `build_skeleton()` or the registry build with offline factories, matching what `test_skeletons.py` and `test_registry.py` already do.
  - `test_key_code_at_most_25_lines`: in new format, the first fence in `### Key code`; in old format, today's rule.
  - `test_skeleton_word_only_in_studio_section`: no case-insensitive "skeleton" in `generic_text`.
  - Length: new format 50–130 lines; old format 50–110.
  - The existing `test_crosslinks_name_catalog_routes`, `test_langgraph_names_import` and H1 tests apply to both formats unchanged.
  - Update `test_registry.py::test_every_explanation_has_required_sections` to check new or old format by membership in `UNMIGRATED`.
  - Update `test_offline_scripts.py` to read the "Try this" text from `### Try this` inside section 7 for migrated Guides, and from `## Try this` for unmigrated ones. Put the selector in `guide_format.try_this_text(md, folder)`.
  - `test_unmigrated_is_shrinking_toward_empty`: assert `UNMIGRATED` only contains real folders. Task 6 replaces it with an emptiness assert.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_guides.py tests/test_registry.py tests/test_offline_scripts.py -q`. Expected: PASS, because every Guide is still unmigrated and the new-format tests collect zero cases.
- [ ] **Step 3: Prove the new-format tests can fail.** Temporarily remove one folder from `UNMIGRATED` (e.g. `audit_agent`), run, and confirm the new-format tests FAIL on the old-format Guide. Restore it. Paste both outputs in the report.
- [ ] **Step 4: Run** `pytest -q`. Expected: all PASS.
- [ ] **Step 5: Commit:** "Add a dual-mode Guide format harness".

---

### Task 2: Render the Studio section as a collapsed disclosure

**Files:**
- Modify: `static/guide.js`, `static/styles.css`, `tests/js/guide.test.mjs`.

**Interfaces:**
- Produces:
  - `guide.js` gains a pure exported function, `splitStudio(markdownRest) -> {body: string, studio: {title, subsections: [{title, markdown}]} | null}`. It is fence-aware and detects the `## How this Studio implements it` section by exact title.
  - `renderGuide(el, markdown, {linkFor})` renders `body` as today's blocks. When `studio` is present, it appends a `<details class="guide-impl sheet">` with `<summary>` "How this Studio implements it", closed by default, and one labelled sub-block per `###` subsection, using the same sanitise and link-marker pipeline.
  - Build `details`/`summary` with DOM APIs. DOMPurify output stays the only `innerHTML`.
  - Open state: on `toggle`, write `sessionStorage["studio.guide.impl.open"] = "1" | "0"`. Read it on render. Both reads and writes are wrapped in try/catch.
  - Old-format Guides have no section 7, so their output is unchanged.

- [ ] **Step 1: Write the failing node tests:**
  - `splitStudio` on a new-format sample returns 4 subsections in order with correct markdown.
  - A sample without section 7 returns `studio === null` and an unchanged `body`.
  - A `## How this Studio implements it` line inside a code fence is ignored.
  - CRLF input works.
- [ ] **Step 2:** Run `pytest tests/test_js.py -q` and confirm it FAILS.
- [ ] **Step 3: Implement.** Style the disclosure with Blueprint tokens: a paper sheet, the summary in Barlow Condensed, an ink focus ring, and a visible open/closed indicator that isn't colour-only.
- [ ] **Step 4:** Run `pytest -q` and confirm all PASS. Run `node.exe --check guide.js`. The `innerHTML` static rule must still hold.
- [ ] **Step 5: Commit:** "Render the Studio implementation section as a collapsed disclosure".

---

### Task 3: Migrate the four live Guides

**Files:** Modify `agents/{qa_agent,chat_agent,secure_chat_agent,interrupt_chat_agent}/explanation.md`, and remove those four from `UNMIGRATED` in `tests/guide_format.py`.

- [ ] **Step 1:** Remove the four folders from `UNMIGRATED`. Run the guide tests and confirm they FAIL on the four Guides.
- [ ] **Step 2: Rewrite each Guide** into the Global Constraints format.
  - The generic body is written fresh, in roles and flow, not as a node walkthrough.
  - The Studio section's Mapping maps roles to nodes. Framework concepts carries today's "LangGraph concepts" content. Key code and Try this keep today's content.
  - Approval (`interrupt_chat_agent`) takes its generic body from the Approval spec §3: roles, flow, design musts, trade-offs, related patterns. Its Studio section says the current demo shows only the pause mechanism and that the full approval demo comes later.
  - Guardrails vs Review, Session vs Episodic and Approval vs Review keep their dividing lines, now in Related patterns.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS, including `test_offline_scripts.py`.
- [ ] **Step 4: Commit:** "Rewrite the live pattern Guides in the generic format".

---

### Task 4: Migrate Cognitive and Collaboration Guides

**Files:** Modify `agents/{react_agent,reflection_agent,plan_execute_agent,search_agent,supervisor_agent,swarm_agent,hierarchy_agent}/explanation.md`, and update `UNMIGRATED`.

- [ ] **Step 1:** Remove the 7 folders from `UNMIGRATED`, then run and confirm the tests FAIL.
- [ ] **Step 2: Rewrite.** These are skeleton patterns, so each Studio section's Mapping says the demo is a Guide-only skeleton and maps roles to the skeleton's nodes. Keep the §3.3 dividing lines in Related patterns: ReAct vs Tool Use and Autonomous; Reflection vs Review; Planning vs Workflow; Supervisor vs Hierarchy vs Swarm.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS. **Step 4: Commit:** "Rewrite Cognitive and Collaboration Guides in the generic format".

---

### Task 5: Migrate Memory, Execution and Governance Guides

**Files:** Modify `agents/{episodic_memory_agent,semantic_memory_agent,knowledge_graph_agent,routing_agent,workflow_agent,event_driven_agent,autonomous_agent,audit_agent,review_agent}/explanation.md`, and update `UNMIGRATED`, which should now be empty.

- [ ] **Step 1:** Remove the 9 folders, then run and confirm the tests FAIL.
- [ ] **Step 2: Rewrite**, as in Task 4. Keep the dividing lines: Session vs Episodic; Semantic vs Knowledge Graph; Routing vs Supervisor; Workflow vs Planning; Autonomous vs ReAct; Audit vs the live trace (generic: a live view of one run vs durable records across runs); Review vs Reflection.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS. **Step 4: Commit:** "Rewrite Memory, Execution and Governance Guides in the generic format".

---

### Task 6: Retire the old format, README, browser check

**Files:** Modify `tests/guide_format.py`, `tests/test_guides.py`, `tests/test_registry.py`, `tests/test_offline_scripts.py` (delete the old-format rules and `OLD_SECTIONS`; replace the shrinking test with `assert UNMIGRATED == set()`, then delete `UNMIGRATED`), and `README.md`.

- [ ] **Step 1:** Delete the old-format branches and run `pytest -q` (all PASS).
- [ ] **Step 2: README.** Describe the Guide format in the Patterns Studio section: generic pattern body, the collapsed "How this Studio implements it" section, and the genericity rule with its test.
- [ ] **Step 3: Browser check over CDP.** Put screenshots in the scratchpad, never the repo. Check:
  - (a) Approval at 1440 and 375 px: the Studio section is collapsed by default and opens with Enter or Space.
  - (b) The open state persists across patterns.
  - (c) Episodic: the generic body reads cleanly, and the collapsed section shows Mapping, Framework concepts, Key code and Try this.
  - (d) No console errors.
  - (e) Without JS, Markdown is visible.

  Stop only your own server and Chrome, by PID or `--user-data-dir`. Never kill processes by name.
- [ ] **Step 4: Commit:** "Retire the old Guide format; document the generic Guide format".
