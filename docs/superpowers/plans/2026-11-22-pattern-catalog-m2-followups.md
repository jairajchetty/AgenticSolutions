# Pattern Catalog (M2): follow-ups for the M3 and M4 plans

Milestone 2 (Pattern Catalog Menu) is complete on `feature/pattern-catalog`. The whole-branch review was clean after one fix wave, and 265 tests pass, including the Node JS tests. The items below were deferred by the task reviews and the final review. They add to `2026-11-22-patterns-studio-m1-followups.md`. In that file, the "M2" list now belongs to M3 and the "M3" list to M4, following the renumbering in Catalog spec §10.

## Carry into the M3 plan (live ReAct, Reflection, Planning)

- **Fill the three skeleton folders.** Fill `react_agent/`, `reflection_agent/` and `plan_execute_agent/` with live graphs, keeping the node names. Register `react`, `reflection` and `plan_execute`, then follow the README's "From skeleton to live demo" steps.
  - Remove each folder's row from `tests/test_skeletons.py::SKELETONS`.
  - Rewrite the guide's "skeleton/placeholders" text and its Key code.
- **Add a test that a live demo's guide no longer calls itself a skeleton.** It should fail if a registered demo's folder guide still says "skeleton" or "placeholder".
- **Backticked identifiers in "Try this" will trip `test_every_try_this_input_has_a_scripted_reply` once a pattern goes live.** The cases are `score` and `feedback` in reflection, and `deduplicate` in workflow. Either drop the backticks or extend `STATE_KEYS` in `tests/test_offline_scripts.py`. Also reconcile README step 3 ("a rule for every backticked input").
- **`plan_execute_agent/explanation.md`:** soften the unsourced claim that "2–5 steps work best" to something like "short plans are easier to check".
- **`react_agent/graph.py`:** the ASCII diagram docstring uses `\\` in a non-raw string and is hard to read. Redraw it when the graph is rewritten.
- **`hierarchy_agent/explanation.md`:** name the mechanism `Command(graph=Command.PARENT, goto=...)` instead of saying "where supported".
- **Runner:** list-of-block token content when tools are bound. This was carried from M1 and becomes urgent once ReAct is live with tools.

## Carry into the M4 plan (Live mode, hardening, deploy)

- **Catalog build:** it runs before the lifespan `try`, so a skeleton or explanation failure leaks the aiosqlite connection and the executor. Move the startup computation inside the `try`. Also wrap a missing `explanation.md` in the same named error used for skeleton failures.
- **Load errors:** a non-404 load error leaves the URL on the failed route, so clicking that pattern again on the home page does nothing until a reload.
- **Skip link:** its static text in `index.html` ("Skip to the agent console") shows before the first view renders.
- **Leaving mid-run:** navigating away mid-run, which ←/→ now makes easy, ends that chat (M1 ruling R6), and the aborted run still finishes server-side. Revisit when live runs cost money: cancel the server run on disconnect, or warn before leaving a running chat.
- **ThreadStore:** add a public `__len__` (or equivalent) so tests stop reading `ThreadStore._threads`.

## Accepted as-is

- Tool Use compiles the ReAct skeleton a second time at startup (negligible).
- The page heading outline uses one `h1` per view and `h2` panels. No focus move on the first page load (deliberate).
- Raw `[[route]]` markers show as plain text when `/api/catalog` or the CDN (marked/DOMPurify) is unavailable. This is a documented degraded mode.
