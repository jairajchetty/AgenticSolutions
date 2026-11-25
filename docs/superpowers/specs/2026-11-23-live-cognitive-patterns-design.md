# Live Cognitive Patterns (Milestone 3): Design Spec

- **Date:** 2026-11-23
- **Status:** Draft, builder-checked, awaiting the person's approval
- **Builds on:** the Studio spec (`2026-11-22-agentic-patterns-studio-design.md`) and the Catalog spec (`2026-11-22-pattern-catalog-menu-design.md`). Pattern behaviour is already specified in Studio spec §4.7–4.9 and §8. This document adds the decisions those specs left open.
- **Live model choice moved (2026-11-25):** the local Live switch that was §3 here is now the Model Picker spec (`2026-11-25-model-picker-design.md`), built on its own branch. M3's patterns use that picker for live runs.
- **Branch:** `feature/cognitive-live`, stacked on `feature/pattern-catalog`.

## 1. Intent

Make ReAct, Reflection and Planning **live demos**: they run in the workbench with an animated trace, a console and a Guide, instead of being Guide-only skeletons.

**Why:** these three patterns are where the model's own reasoning is the lesson. Scripted runs show the mechanics (which nodes fire, and in what order). Only a real model shows the intelligence: which tool it picks, what its critique says, how it splits a goal into steps. Live runs use the Model Picker (separate spec).

**Goals**
- `react`, `reflection` and `plan_execute` are registered live demos. The catalog shows them as ● with no catalog edits, and Tool Use follows ReAct.
- Every live demo works offline, scripted and free, exactly as the Studio spec §8 describes.
- The trace stays truthful in both modes: tool calls appear as real `tools` nodes and as console chips; the Reflection drafts and scores and the plan checklist are visible.

**Non-goals**
- Public Live access, access codes, budgets, rate limits and deployment. These stay in Milestone 4 (the old "M3" in the Studio spec §13).
- Live demos for the other 13 Guide-only patterns.
- Replanning in Plan-and-Execute (the Guide describes it as a variation).

**Anti-goals**
- A trace that hides tool use inside a node.
- An offline demo that silently looks like real reasoning: scripted output must stay labelled as scripted.

## 2–3. Live switch (moved)

Moved to the Model Picker spec, `2026-11-25-model-picker-design.md`, which covers model choice, who may choose, the API, error mapping and text-node refusals. Section numbers below are kept so existing references stay valid.

**Kept here, because it is specific to these patterns:** structured-node refusals with a real model.
- A refusal or a parse failure (`parsed is None`) ends the pattern cleanly with status `completed`, never `error`.
- **`critique` declined:** stop revising and keep the current draft as the result. Show "The critic declined to score this draft." in the Drafts list.
- **`planner` declined:** skip to `synthesizer`, whose result card shows "The model declined to plan this task."
- The routers gain one branch each for this: Reflection `critique → END`, which already exists, and Planning `planner → synthesizer`. Planning's topology changes, so update the Catalog spec §6 row and its tests together.
- State gains `declined: bool`.

## 4. The three patterns

Behaviour, state, routers, caps and samples follow **Studio spec §4.7 (ReAct), §4.8 (Reflection) and §4.9 (Plan-and-Execute)** exactly. Node names must equal the Catalog spec §6 skeletons, so the diagrams don't change when the patterns go live:
- ReAct: `ask`, `agent`, `tools`.
- Reflection: `generate`, `critique`, `revise`.
- Planning: `planner`, `executor`, `tools`, `synthesizer`.

Additional decisions:

- **Tools (ReAct and Planning share them):** `agents/react_agent/tools.py` holds `calculator`, `current_time`, `unit_convert` and `pattern_glossary`, as `@tool` functions.
  - **`calculator`** evaluates an AST whitelist: numbers, + − × ÷, `//`, `%`, `**` with |exponent| ≤ 10, unary minus and parentheses. Everything else is rejected with a readable error string that is returned to the model, never raised.
  - **`current_time`** takes an IANA zone (default `UTC`) and returns an ISO time. An unknown zone returns an error string.
  - **`unit_convert`** covers length (m, km, cm, mm, mi, ft, in), mass (kg, g, lb, oz) and temperature (C, F, K).
  - **`pattern_glossary`** looks a term up in the 21 catalog entries' names, hints and aliases, plus a few core terms (checkpointer, interrupt, reducer, tool node, structured output). An unknown term returns "No glossary entry".
- **ReAct samples:**
  - "What is 17 × 23, and what's that in hex?" (two calculator rounds)
  - "Convert 5 miles to kilometres"
  - "What time is it in Tokyo?"
  - "What does 'checkpointer' mean here?"
- **Plan-and-Execute samples:**
  - "Compare the boiling point of water in °F and K, then say which scale is larger"
  - "Work out the area of a 12 ft × 15 ft room in square metres"
  - "Explain how a checkpointer lets a chat resume, in three steps"
- **Reflection samples:** Studio spec §4.8.
- **Structured output (builder's call, from the builder check):** Reflection's `Critique(score: int 1–10, feedback: str)` and Planning's `Plan(steps: list[str] 2–5)` are Pydantic models used with `with_structured_output(schema, method="json_schema", include_raw=True)`.
  - That is Claude's native structured output, through `output_config.format` in langchain-anthropic 1.7.6 (verified), not forced tool use, which conflicts with the adaptive thinking Haiku 5.5 runs by default.
  - `include_raw=True` keeps the raw message so refusals and parse failures can be detected.
  - The scripted model's `with_structured_output` accepts the same keyword arguments and returns the same `{raw, parsed, parsing_error}` shape.
- **Final call at a tool cap (builder's call):** at the ReAct 8-round cap and the Planning 2-round step cap, the last call keeps the tools bound with `tool_choice={"type": "none"}` instead of unbinding them. The Anthropic API rejects histories containing `tool_use`/`tool_result` blocks when no tools are defined. The scripted model honours `tool_choice="none"` by never returning tool calls.
- **Graph modules:** each fills its existing skeleton folder (`react_agent`, `reflection_agent`, `plan_execute_agent`).
  - Each exports `build_graph(checkpointer=None, llm_factory=None)` and a module-level `graph = build_graph()`, then follows the README's "From skeleton to live demo" steps:
    - register in `web/registry.py`;
    - add offline scripts;
    - remove the `SKELETONS` rows;
    - rewrite the guides;
    - add a `langgraph.json` entry, because these graphs now run in Studio.
  - The `build_skeleton()` export is removed. The catalog now draws these three diagrams from the live graphs.
  - The existing `tests/test_skeletons.py` topology expectations for these three move into the new pattern tests, to prove the node names didn't change.
- **CLI entry points:** each pattern gets a `__main__.py` like the existing agents. ReAct is an interactive loop. Reflection and Planning take the task as a command-line argument and print the result. They use `get_llm()` (real Claude), as the existing CLIs do.

## 5. Offline mode for the new patterns

- **The scripted model needs tool calls and structured output:**
  - `bind_tools(tools)` returns a scripted model that may answer with an `AIMessage` carrying `tool_calls`.
  - `with_structured_output(schema)` returns a runnable producing scripted instances of `schema`.
- **A rule's reply** may be:
  - a string;
  - an `AIMessage` (for tool calls);
  - a schema instance;
  - a callable `(messages) -> one of those`, used for multi-step scripts such as "second call after a tool result".
- **Rule matching is unchanged:** the latest human message, case-insensitive substring. Scripts may also key on the call kind (plain, tools bound, or structured output with schema X), so one pattern can script its `agent`, `critique` and `planner` calls separately.
- **Every sample has a specific scripted path through every branch:**
  - ReAct: at least one tool round.
  - Reflection: a revise round, so the critique scores 6 and then 9.
  - Planning: three steps, at least one with a tool round.
- **Generic fallbacks for free text (Studio spec §8):**
  - ReAct: one calculator round on "2+2".
  - Reflection: scores 6 then 9.
  - Planning: a generic three-step plan.
  - Every fallback reply carries the offline note.
- **Pacing:** offline latency and pacing apply as in M1.

## 6. UI additions for the new patterns

- **Tool chips:** the console renders `tool_call` and `tool_result` events as a paired chip: `🔧 calculator("17*23") → 391`. Long results are cut at 200 characters with "…". This uses the existing event fields (Studio spec §5). Chips are also rebuilt from `/state` on restore, from AI messages' `tool_calls` and ToolMessages.
- **Reflection (trigger):**
  - The result card shows the final draft and "Score 9/10 after 2 drafts".
  - A collapsible "Drafts" list in the console shows each draft with its critique score and feedback, from state `history`.
- **Plan-and-Execute (trigger):**
  - The result card shows the synthesized answer.
  - The console shows the plan as a checklist that ticks each step as its `executor` round finishes, from `node_finished` updates on `current_step`/`results`.
  - Each step's result is expandable.
- **ReAct (chat):** behaves like the M1 chat patterns plus tool chips. The 8-round cap message is the model's own final text reply.

## 7. Guides

- The three guides are rewritten from "skeleton" to "live":
  - "Key code" excerpts come from the live `graph.py`.
  - "Try this" uses inputs that each have a specific offline rule.
  - The "this is a skeleton / placeholders / live demo coming" wording is removed.
- All existing guide tests still apply, including the DIVIDING test (react→tool-use and autonomous; reflection→review; plan_execute→workflow).
- **New test:** no guide whose catalog entry is live may contain "skeleton" or "placeholder" (M2 follow-up).
- **Offline-script test:** backticked identifiers in "Try this" (`score`, `feedback`, `deduplicate`) would trip `test_every_try_this_input_has_a_scripted_reply`. Extend that test's non-input allow-list to state keys and node names from the pattern's graph, derived automatically from the compiled topology and the state schema, not hand-listed.

## 8. Carry-overs folded into this milestone

From `docs/superpowers/plans/2026-11-22-patterns-studio-m1-followups.md` ("M2" list, now M3) and `2026-11-22-pattern-catalog-m2-followups.md` ("M3" list):
- `to_jsonable` maps NaN/±inf to `null`.
- `to_jsonable`'s two-string-list heuristic must not turn Plan `steps` (lists of strings) into messages: only `(role, text)` pairs whose role is a known role.
- `ScriptedChatModel` tests for callable rules, multi-turn matching and pacing.
- Runner tests for early-close and for `tool_call`/`tool_result`/usage aggregation.
- Runner token streaming with list-of-block content when tools are bound (`text_of(chunk)`), verified with a fake chunk stream offline and in the live smoke check.
- A failed pattern switch leaves the old chrome on screen: navigate home with the error notice instead.
- `plan_execute` guide: soften "2–5 steps work best" to "short plans are easier to check".
- `react_agent/graph.py` docstring diagram redrawn readably.
- `hierarchy_agent` guide names `Command(graph=Command.PARENT, goto=...)` instead of "where supported".

## 9. Testing

- **All offline in pytest. No test calls the Anthropic API.**
- **Pattern graphs:** a routing test for every branch with the scripted model:
  - ReAct: the tool loop, the cap at 8 rounds ending with a text reply, empty input, and `stop`.
  - Reflection: stops at score ≥ 8, stops at iteration 3, and records history.
  - Planning: each step runs once, tool rounds per step are capped at 2, `step_messages` is cleared on each advance, then synthesis.
  - Topology for each equals the Catalog spec §6 rows.
- **Tools:** calculator safety (rejects `__import__`, names, attributes, huge exponents, division by zero as an error string); time zones; unit conversions and unknown units; glossary hit and miss.
- **Offline scripts:** every sample hits specific rules; free text completes through the fallbacks; the "Try this" inputs are scripted.
- **JS:** a node unit test for the tool-chip text formatter and the plan-checklist reducer (pure functions).
- **Browser checklist** (headless Chrome over CDP, offline):
  - ReAct: chips and the loop animating.
  - Reflection: a drafts list with two scores.
  - Planning: the checklist ticking, and a `tools` node lighting up.
  - The catalog shows the three as ● and Tool Use as ●.
- **Live smoke check (manual, needs the person's go-ahead):** with the person's key, run one sample of each of the three patterns live and record a screenshot plus the token totals. The controller asks before spending on the key.

## 10. Out of scope / left to the builder

- **Out of scope:**
  - Milestone 4 items: unlock, budgets, rate limits, CSP, deployment and the load test.
  - Showing thinking.
  - Streaming of tool-call arguments.
  - Per-pattern model overrides.
- **Left to the builder:**
  - Visual styling of the switch, chips, drafts list and checklist, within the existing tokens.
  - The exact scripted reply text, within §5.
  - The glossary's core-term definitions.
