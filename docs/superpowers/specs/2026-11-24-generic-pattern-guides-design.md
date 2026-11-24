# Generic Pattern Guides: Design Spec

- **Date:** 2026-11-24
- **Status:** Draft, builder-checked, awaiting the person's approval
- **Builds on:** the Catalog spec (`2026-11-22-pattern-catalog-menu-design.md`, §7 Guide content) and the Blueprint redesign spec (§4.2 purpose-first pages). This spec **supersedes Catalog spec §7's section list** and the LangGraph-specific parts of its rules.
- **Branch:** `feature/approval-mcp` (stacked on `feature/cognitive-live`).

## 1. Intent

The 21 pattern write-ups are the Studio's teaching content and the visible proof of the author's architectural thinking. The person's rule:

> **The design pattern write-ups should avoid technical details specific to the architecture. These patterns should be generic, implementable on any agentic platform.**

So each Guide becomes a **generic pattern write-up** that holds equally for LangGraph, another agent framework, a hosted agent service or a hand-written loop. The person also chose to **keep a clearly separated, collapsed "How this Studio implements it" section** at the end. That section links the generic pattern to the running demo the visitor is watching.

**Goals**
- Every Guide's main body is platform-neutral. It describes roles, flow, decisions and consequences, and names no library, framework, class, function or protocol.
- Every Guide ends with one collapsed section that maps the generic roles onto this Studio's graph: node names, the framework features used, the key code, and "Try this" inputs for the demo.
- The format is enforced by tests, as today.

**Non-goals**
- Changing what any pattern *is*, or the catalog taxonomy.
- Changing the demos themselves.

**Anti-goals**
- A "generic" body that still leaks framework vocabulary (`interrupt()`, `StateGraph`, `ToolNode`, reducers, checkpointers, MCP).
- A Studio section that repeats the generic body instead of mapping it.
- Losing the purpose-first layout from the Blueprint redesign.

## 2. Approaches considered

The person chose **A**.

| | Approach | Trade-offs |
|---|---|---|
| **A (chosen)** | **Two layers.** The generic pattern body comes first. Then a single collapsed "How this Studio implements it" section holds the mapping, the framework concepts, the key code and "Try this". | Each pattern reads as a portable reference, while the demo stays explainable. It means restructuring all 20 existing Guides. |
| B | Generic only: remove all framework content | The purest form, but visitors lose the link between what they read and what they watch running. |
| C | Approval only now, the rest later | The smallest change, but it leaves 20 Guides inconsistent with the stated rule. |

## 3. The Guide format

Each `agents/<folder>/explanation.md` has the H1 (the taxonomy name, as today), then exactly these `##` sections in order:

| # | Section | Layer | Content rules |
|---|---|---|---|
| 1 | **What it is** | generic | 2–4 sentences: the problem the pattern solves and the core idea. Rendered first in the purpose sheet (Blueprint spec §4.2). |
| 2 | **When to use it** | generic | Bullets: situations where it fits, plus at least one "not when …" bullet. Rendered in the purpose sheet. |
| 3 | **How it works** | generic | The **roles** (e.g. *agent*, *tool*, *approver*, *executor*, *system of record*), then the **flow** as numbered steps between those roles. Plain words, no node names. |
| 4 | **Design considerations** | generic | The decisions an implementer must get right on *any* platform: guarantees/invariants, failure modes, where state lives, idempotency, limits, security, cost. Bullets, each starting with a bolded decision name. |
| 5 | **Trade-offs** | generic | What the pattern costs: latency, money, complexity, failure modes it introduces. |
| 6 | **Related patterns** | generic | `[[category/pattern]]` links, each with one line on the relationship. **The §3.3 dividing-line sentences live here** (moved from "How this graph works"). |
| 7 | **How this Studio implements it** | Studio-specific (collapsed) | Exactly these `###` subsections in order: **Mapping** (generic role → this graph's node names; one line per role), **Framework concepts** (formerly "LangGraph concepts": the framework features this demo uses), **Key code** (≤ 25-line excerpt from this folder's `graph.py`, unchanged rule), **Try this** (inputs for the demo, unchanged offline-script rule). |

- **Length:** 50–130 lines per file. The limit is raised from 110 to fit the added sections.
- **Diagrams:** a generic body may include a small plain-text flow sketch using role names, with no node names. Optional.
- **Skeleton patterns (Guide-only):** the Studio section's Mapping says the demo is a skeleton and names its nodes. Its Key code shows the skeleton wiring, as today.

## 4. Genericity rule (enforced)

Sections 1–6 must not contain framework-specific vocabulary. A test checks each generic section against a **denylist**, case-insensitive whole-word or code-span matches:

- **Frameworks and protocols:** `LangGraph`, `LangChain`, `MCP`, `Model Context Protocol`, `langgraph.`, `langchain`.
- **Framework constructs:** `StateGraph`, `ToolNode`, `interrupt(`, `Command(`, `Send(`, `add_messages`, `reducer`, `checkpointer`, `thread_id`, `RemoveMessage`, `get_graph`, `build_graph`, `build_skeleton`.
- **Code formatting:** any backticked token in the generic sections. Generic sections use **no code spans**. Role names are plain words.
- **Vendors and models:** `Claude`, `Anthropic`, `OpenAI`, `GPT`.

Generic synonyms are allowed: checkpoint, saved state, pause, resume, tool, function call, state, message history, store.

Section 7 has no denylist.

## 5. Rendering

- **The purpose sheet is unchanged.** It still shows "What it is" and "When to use it" (Blueprint §4.2, `splitPurpose` by heading name).
- **The rest of the Guide** (`#guide-rest`) renders sections 3–6 as today's labelled blocks. Section 7 renders as a **collapsed disclosure block**: a `<details>` whose `<summary>` reads "How this Studio implements it", **closed by default**. Inside it, the four `###` subsections render as labelled sub-blocks.
  - The disclosure must be keyboard-operable and use the Blueprint tokens: a paper sheet with an ink focus ring.
  - Opening state persists per browser in `sessionStorage`, wrapped in try/catch.
- `guide.js` keeps a single DOMPurify `innerHTML` path. `<details>` and `<summary>` are built with DOM APIs, or allowed by the sanitiser configuration. The builder decides which and states it.
- **CDN-down fallback:** when the Markdown or sanitiser library fails to load, the raw Markdown shows as today, and the Studio section is simply part of it. (Without JavaScript the single-page app renders nothing at all; that is pre-existing and out of scope here.)

## 6. Tests (update existing, add new)

- **Heading test** (`tests/test_registry.py`): the seven `##` sections in the §3 order. Inside section 7, the four `###` subsections in order.
- **Genericity test** (new): the §4 denylist applied to sections 1–6 of every Guide.
- **DIVIDING test** (`tests/test_guides.py`): the required `[[route]]` markers must appear in **Related patterns** instead of "How this graph works". Same entries.
- **Key code ≤ 25 lines, LangGraph-name import check, crosslink validity:** unchanged, now scoped to section 7.
- **Offline "Try this" test** (`tests/test_offline_scripts.py`): reads the `### Try this` subsection inside section 7. Same rule.
- **H1, length (50–130) and live-guide "no skeleton wording" rules:** "skeleton" is allowed only in section 7.
- **JS:** `splitPurpose` is unchanged. Add a node test that the guide-rest split recognises section 7 and its four subsections.

## 7. Content migration

All 20 existing Guides are rewritten into the format. The generic body is written fresh, not converted mechanically: role and flow language instead of node walkthroughs. Facts must stay accurate. Each Studio section's Mapping must name every node the diagram shows.

The new Approval Guide (separate spec, `2026-11-24-approval-pattern-mcp-design.md`) is written in this format from the start. If Milestone 3 (deferred for now) is resumed later, its three rewritten Guides (ReAct, Reflection, Planning) follow this format.

## 8. Out of scope / left to the builder

- **Out of scope:** translations, and per-pattern diagrams in the generic body beyond optional text sketches.
- **Left to the builder:**
  - Exact prose, within the rules.
  - The styling of the disclosure, within the Blueprint tokens.
  - Whether `<details>` is built in the DOM or allowed through the sanitiser.

## 9. Builder-check decisions (builder's calls)

1. **Which Guides.** M3 is deferred, so this work migrates every Guide present at the time: all 20 catalog folders, including the three skeleton Guides (react, reflection, plan_execute), which stay Guide-only skeletons.
   - The current Approval Guide (`interrupt_chat_agent`) gets the **generic Approval body** from the Approval spec §3 now.
   - Its Studio section says honestly that this demo currently shows only the pause mechanism and that the full approval demo comes later. The Approval spec then moves the Guide to `approval_agent`.
2. **Migration slicing.** Guides migrate in category batches. `tests/test_guides.py` carries a temporary `UNMIGRATED` set, and old-format Guides are checked by the old rules. The final task asserts `UNMIGRATED` is empty and deletes the old-format rules, so the suite stays green at every commit.
3. **Denylist semantics** (sections 1–6 and the H1; section 7 is exempt; `[[category/pattern]]` markers are allowed everywhere):
   - **Case-insensitive whole words:** LangGraph, LangChain, MCP, "Model Context Protocol", StateGraph, ToolNode, add_messages, reducer, checkpointer, thread_id, RemoveMessage, get_graph, build_graph, build_skeleton, Claude, Anthropic, OpenAI, GPT.
   - **Literal substrings:** `interrupt(`, `Command(`, `Send(`, `langgraph.`, `langchain`.
   - **Any backtick** character.
   - The plain English words "interrupt", "handoff", "supervisor", "merge", "tool", "checkpoint", "pause" and "resume" are allowed.
4. **Splitting.** `#guide-rest` splits on `## ` as today. The section titled exactly "How this Studio implements it" is detected by name and rendered as the collapsed `<details>`, with its `### ` subsections as sub-blocks.
   - The open state is **one global preference** (`sessionStorage["studio.guide.impl.open"]`): a reader who wants implementation detail wants it on every pattern.
