# Pattern Catalog Menu — Design Spec

- **Date:** 2026-11-22
- **Status:** Draft, builder-checked, awaiting the person's approval
- **Builds on:** `docs/superpowers/specs/2026-11-22-agentic-patterns-studio-design.md` (the "Studio spec"). This document **supersedes Studio spec §6's header tab strip** and adds a catalog layer. Everything else in the Studio spec still applies.

## 1. Intent

The Studio currently opens on one pattern and switches between patterns with numbered tabs. This milestone replaces that with a **catalog for looking up patterns**, organised by a five-category taxonomy of 21 agentic design patterns.

**Why:** people arrive with a problem ("my agent must remember users", "a human must sign off") and need to find the pattern that solves it, then see it explained and, where one exists, running. The person chose **lookup** over a guided learning path.

**Goals**
- Show every pattern in the taxonomy, findable by category, by name, by alias, or by the problem it solves.
- Give every pattern a page. Patterns with a live demo keep the existing trace/console/Guide workbench. Every other pattern gets a **Guide-only page**: the full explanation plus a static diagram of its graph, marked "Live demo coming".
- Make every page linkable (`#/governance/approval`).

**Non-goals**
- Building live demos for the Guide-only patterns. They arrive one milestone at a time, starting with ReAct, Reflection and Planning.
- Live mode, budgets, deployment: Studio spec milestone 3, unchanged.
- A learning path, progress tracking, or user accounts.

**Anti-goals**
- A diagram on a Guide-only page that does not match the graph the live demo will eventually run. This is why diagrams come from skeleton graphs (§6).
- A reference with dead ends: no pattern in the menu may lead nowhere.
- Explanations that blur the overlapping patterns. Each pair in §3.3 must be distinguishable from its page alone.

## 2. Approaches considered

The person chose **A**.

| | Approach | Trade-offs |
|---|---|---|
| **A (chosen)** | A Python **catalog module** holds categories, questions, patterns, hints, aliases, cross-links and status. The API serves it. Each Guide-only pattern gets an `explanation.md` and a **skeleton LangGraph graph**: real nodes and edges whose node functions do nothing. Its static diagram comes from `get_graph()`. | Keeps the Studio rule "topology comes from the compiled graph, never hand-written". Each skeleton becomes the starting point for that pattern's live demo. Tests can check that the catalog, registry and files agree. Costs 16 small skeletons. |
| B | A catalog file plus hand-written diagram JSON for Guide-only patterns. | Faster to write, but the diagram can drift from the eventual code, and it breaks the topology rule. |
| C | A catalog hard-coded in the frontend JS. | Fastest, but the pattern list lives in two places, and there is no automated test coverage because there is no JS test runner. |

Layout options considered (mockups in `.superpowers/brainstorm/menu/menu-layouts.html`): a persistent sidebar, a header mega-menu, and a **catalog home page with breadcrumbs**. The person chose **the catalog home page**.

Taxonomy changes the person chose after review: **add Routing; narrow Autonomous; narrow Audit.**

## 3. The taxonomy

### 3.1 Categories (order fixed)

| Order | Category id | Name | Question shown on its card |
|---|---|---|---|
| 1 | `cognitive` | Cognitive | How should the agent think? |
| 2 | `collaboration` | Collaboration | How many agents, and who leads? |
| 3 | `memory` | Memory | What must it remember? |
| 4 | `execution` | Execution | How does it act and run? |
| 5 | `governance` | Governance | How is it kept safe and accountable? |

### 3.2 Patterns (order within each category fixed)

`Live now` = a demo exists today. `M3` = its live demo is the next pattern milestone (§10). Everything else is Guide-only until a later milestone.

| Category | Pattern id | Name | Hint (exact copy) | Aliases (search) | Demo |
|---|---|---|---|---|---|
| cognitive | `react` | ReAct | Reason and call tools in a loop | reason act, tool loop, agent loop | M3 (`react`) |
| cognitive | `reflection` | Reflection | Critique and revise its own output | self-critique, evaluator-optimizer, self-refine | M3 (`reflection`) |
| cognitive | `planning` | Planning | Break a goal into steps before acting | plan-and-execute, task decomposition | M3 (`plan_execute`) |
| cognitive | `search` | Search | Explore several paths and keep the best | tree of thoughts, LATS, beam search, MCTS | — |
| collaboration | `single-agent` | Single Agent | One model handles the whole task | single LLM call, baseline, one-shot | Live now (`qa`) |
| collaboration | `supervisor` | Supervisor | A coordinator delegates to specialists | orchestrator-workers, manager, delegation | — |
| collaboration | `swarm` | Swarm | Peers hand work to each other directly | handoffs, peer-to-peer, network | — |
| collaboration | `hierarchy` | Hierarchy | Teams of agents led by supervisors | hierarchical teams, nested supervisors | — |
| memory | `session` | Session | Remember the current conversation | short-term memory, thread, conversation history, checkpointer | Live now (`chat_loop`) |
| memory | `episodic` | Episodic | Recall past interactions with this user | long-term memory, user memory, experiences | — |
| memory | `semantic` | Semantic | Look up facts from a document store | RAG, retrieval, vector search, knowledge base | — |
| memory | `knowledge-graph` | Knowledge Graph | Reason over entities and relationships | graph RAG, entity memory, ontology | — |
| execution | `tool-use` | Tool Use | Call functions and APIs | function calling, tools, actions | cross-listed → `cognitive/react` |
| execution | `routing` | Routing | Send each request to the right specialist | router, classifier, intent routing, dispatch | — |
| execution | `workflow` | Workflow | Run fixed steps defined in code | pipeline, prompt chaining, DAG | — |
| execution | `event-driven` | Event Driven | Start agents from events, queues or schedules | triggers, webhooks, background agents, cron | — |
| execution | `autonomous` | Autonomous | Work on its own for a long time until a goal is met | long-running, self-directed, background agent | — |
| governance | `guardrails` | Guardrails | Screen inputs and outputs for unsafe content | input filter, prompt injection, safety screen | Live now (`guardrail`) |
| governance | `approval` | Approval | Pause for a human to sign off | human-in-the-loop, HITL, interrupt, sign-off | Live now (`human_in_loop`) |
| governance | `audit` | Audit | Keep persistent, queryable records of every run | logging, traceability, run history, compliance | — |
| governance | `review` | Review | Have a separate agent or a person check the result | peer review, critic agent, second opinion | — |

The display name on a page is the taxonomy **Name**. The live demo's existing registry title (e.g. "Human-in-the-loop: `interrupt()` + checkpointer") appears as the workbench subtitle.

### 3.3 Dividing lines (each Guide states its own line explicitly)

- **Reflection vs Review:** Reflection is the same agent critiquing its own output. Review is a separate agent or a person checking it.
- **Planning vs Workflow:** in Planning the model writes the steps at run time. In Workflow the steps are fixed in code.
- **ReAct vs Autonomous:** ReAct answers one request in a short loop. Autonomous pursues an open goal over a long run, deciding for itself when it is done.
- **ReAct vs Tool Use:** the same page. Tool Use is the capability, ReAct is the loop that uses it.
- **Audit vs the trace panel:** the trace is a live view of one run. Audit means durable records that can be searched across runs.
- **Session vs Episodic:** Session is one conversation, held in the thread's checkpoints. Episodic carries memories across conversations.
- **Supervisor vs Hierarchy vs Swarm:** one coordinator; supervisors of supervisors; no coordinator at all.

## 4. User experience

### 4.1 Routes (hash-based, shareable)

| Hash | Page |
|---|---|
| `#/` (or empty) | Catalog home |
| `#/<category>/<pattern>` | Pattern page, e.g. `#/governance/approval` |
| `#/execution/tool-use` | The ReAct page; the breadcrumb shows **Execution › Tool Use** |
| Legacy `#qa`, `#chat_loop`, `#guardrail`, `#human_in_loop` | `replaceState` to the new route (`#/collaboration/single-agent`, `#/memory/session`, `#/governance/guardrails`, `#/governance/approval`) |
| Unknown route | Catalog home, with a notice "That pattern wasn't found" |

### 4.2 Catalog home

```
┌ Agentic Patterns Studio     Catalog                       ● Offline (scripted) ┐
│ ⌕ What are you trying to do?   (e.g. "remember users", "human sign-off")       │
│ ┌Cognitive──────┐┌Collaboration──┐┌Memory─────────┐┌Execution─────┐┌Governance┐│
│ │How should the ││How many agents││What must it   ││How does it   ││How is it ││
│ │agent think?   ││and who leads? ││remember?      ││act and run?  ││kept safe…││
│ │○ ReAct        ││● Single Agent ││● Session      ││○ Tool Use ↗  ││● Guardr. ││
│ │  Reason and…  ││  One model…   ││  Remember…    ││○ Routing     ││● Approval││
│ │○ Reflection   ││○ Supervisor   ││○ Episodic     ││○ Workflow    ││○ Audit   ││
│ │○ Planning     ││○ Swarm        ││○ Semantic     ││○ Event Driven││○ Review  ││
│ │○ Search       ││○ Hierarchy    ││○ Knowledge Gr.││○ Autonomous  ││          ││
│ └───────────────┘└───────────────┘└───────────────┘└──────────────┘└──────────┘│
│  ● live demo   ○ guide only (demo coming)   ↗ opens another pattern's page     │
└────────────────────────────────────────────────────────────────────────────────┘
```

- Five cards in category order. Each card shows its name, its question, and its patterns in order. Each pattern row shows a status mark, the name, the hint, and `↗ ReAct` on a cross-listed row.
- **Status marks:** `●` with the label "Live demo", and `○` with the label "Guide". Each mark is shown by both shape and text (an accessible label), not by colour alone.
- **Search box (builder's call: word-wise match):** split the query on whitespace and punctuation other than `-`. A pattern matches when **every** query word is a case-insensitive substring of its combined text: name, hint, aliases, category name and category question. A query word ending in `s` also matches without the `s`. So "remember users" finds Episodic ("remember" from the Memory question, "user" from the hint) and "human sign-off" finds Approval.
  - As the person types, non-matching rows are hidden, and a card with no matches collapses to its header with "no matches".
  - An `aria-live` line announces "N patterns match".
  - Enter opens the first visible match. `/` focuses the box from anywhere on the home page, and Esc clears it.
  - With no matches at all, the page says: "No pattern matches "…". Try a broader word, or browse the categories."
- **Layout:** at ≥ 1200 px the five cards sit side by side; from 700 to 1199 px they wrap 3 + 2; below 700 px they form one column. The page never scrolls horizontally.

### 4.3 Pattern page

- **Header:** breadcrumb **Catalog › {Category} › {Pattern}**. Each part is a link, and Catalog goes to `#/`. Then `←`/`→` buttons step to the previous or next pattern **within the breadcrumb's category**, wrapping at the ends.
- **Keyboard (builder's call):** plain ←/→ do the same, but only when focus is not in an input, textarea or contenteditable element. Alt+←/→ are left alone, because browsers use them for Back and Forward. The offline/live badge stays.
- **Live pattern:** the Milestone 1 workbench, unchanged: trace, console and Guide, with thread handling, restore and so on. The Studio spec §6 tab strip is removed.
- **Guide-only pattern:**
  - A "Live demo coming" banner: *"This pattern doesn't have a live demo yet. The diagram below is its graph; the explanation covers how it works."*
  - The static diagram, drawn by the same graph component in a non-animated mode: idle node styling, conditional edges dashed and labelled, no counters.
  - The Pattern Guide below it.
  - No console and no timeline.
- The page title (`document.title`) is "{Pattern} · {Category} · Agentic Patterns Studio".

### 4.4 Accessibility

- The home page is a `nav` containing one list per category. The search input is labelled.
- On the pattern page, the breadcrumb uses `nav aria-label="Breadcrumb"` with `aria-current="page"`.
- Focus moves to the page heading on each route change, and the existing announcer reports "Opened {Pattern}".

## 5. Data and API

### 5.1 Catalog module: `src/agentic_solutions/web/catalog.py`

```python
@dataclass(frozen=True)
class CatalogPattern:
    id: str                    # "approval"
    category: str              # "governance"
    name: str                  # "Approval"
    hint: str
    aliases: tuple[str, ...]
    demo: str | None           # registry PatternSpec id when a live demo exists, else None
    crosslist_of: str | None   # "cognitive/react" for tool-use, else None
    folder: str | None         # agent folder holding explanation.md (+ skeleton); None for cross-lists

@dataclass(frozen=True)
class Category:
    id: str
    name: str
    question: str
    patterns: tuple[CatalogPattern, ...]

CATALOG: tuple[Category, ...]   # exactly §3.1/§3.2, in order
```

- **Status is derived, never stored:** `live` when `demo` is in the web registry `PATTERNS`, otherwise `guide`.
- **Cross-list rows (builder's call)** take `status`, `demo` and `demo_title` from their target. Tool Use shows ● as soon as ReAct is live. The rule "each PATTERNS id is referenced by exactly one entry" counts only non-cross-list entries. When milestone 3 registers `react`, the ReAct entry turns live with no catalog edit, provided the entry already names `demo="react"`. So entries for patterns with planned demos carry their future registry id now, and status goes live only once that id is registered.
- `folder` values: live patterns use their existing agent folders (`qa_agent`, `chat_agent`, `secure_chat_agent`, `interrupt_chat_agent`). Guide-only patterns use the folders in §6. For ReAct, Reflection and Planning, those are the same folders milestone 3 will fill: `react_agent`, `reflection_agent`, `plan_execute_agent`.

### 5.2 Endpoints (additive; the existing `/api/patterns/...` demo routes are unchanged)

- `GET /api/catalog` returns `{categories: [{id, name, question, patterns: [{id, name, hint, aliases, status: "live"|"guide", route: "<category>/<id>", target: "<category>/<id>"}]}]}`. `target` equals `route` except for cross-lists, where it is the canonical page, e.g. `cognitive/react`.
- `GET /api/catalog/{category}/{pattern}` returns `{route, target, category: {id, name}, name, status, demo, demo_title, explanation_md, topology}`.
  - `demo` is the registry id or `null`, and `demo_title` is that registry entry's title or `null`.
  - `topology` comes from the live graph when there is a demo, otherwise from the skeleton.
  - A cross-list route returns its target's page data, but with the requested `route` and `category`, so the breadcrumb and arrows follow the category it was reached from.
  - Unknown route → 404 `{"detail": "not found"}`.
- Both responses are computed once at startup. Topology for skeletons comes from compiling each skeleton once, with no checkpointer.

## 6. Skeleton graphs

For each Guide-only pattern there is an agent folder `src/agentic_solutions/agents/<folder>/` containing:
- `graph.py` with `build_skeleton()`, which returns a compiled `StateGraph`. Node functions return `{}` (no-ops). Routers are real functions annotated `Literal[...]` that return a fixed branch, so the topology is complete. The module docstring states that the module is a skeleton and names the milestone that will make it live, if one is known.
- `explanation.md` with the Studio §7 headings (see §7 below).
- **No** `__main__.py`, **no** `langgraph.json` entry (a no-op graph has nothing to show in Studio), and **no** module-level `graph` export, so tooling can't mistake a skeleton for a working agent.

Topology per pattern (node names exactly as listed; `→` normal edge, `⇢` conditional edge):

| Folder | Pattern | Nodes and edges |
|---|---|---|
| `react_agent` | ReAct | START→ask; ask ⇢ agent \| ask \| END; agent ⇢ tools \| ask; tools→agent (Studio spec §4.7) |
| `reflection_agent` | Reflection | START→generate→critique; critique ⇢ revise \| END; revise→critique (§4.8) |
| `plan_execute_agent` | Planning | START→planner→executor; executor ⇢ tools \| executor \| synthesizer; tools→executor; synthesizer→END (§4.9) |
| `search_agent` | Search | START→propose→score; score ⇢ propose \| answer; answer→END |
| `supervisor_agent` | Supervisor | START→supervisor; supervisor ⇢ researcher \| writer \| END; researcher→supervisor; writer→supervisor |
| `swarm_agent` | Swarm | START→triage; triage ⇢ billing \| technical \| END; billing ⇢ technical \| END; technical ⇢ billing \| END |
| `hierarchy_agent` | Hierarchy | START→director; director ⇢ research_lead \| writing_lead \| END; research_lead ⇢ searcher \| analyst \| director; searcher→research_lead; analyst→research_lead; writing_lead ⇢ drafter \| editor \| director; drafter→writing_lead; editor→writing_lead |
| `episodic_memory_agent` | Episodic | START→recall_episodes→answer→store_episode→END |
| `semantic_memory_agent` | Semantic | START→retrieve→grade; grade ⇢ answer \| rewrite_query; rewrite_query→retrieve; answer→END |
| `knowledge_graph_agent` | Knowledge Graph | START→extract_entities→query_graph→answer→update_graph→END |
| `routing_agent` | Routing | START→classify; classify ⇢ billing \| technical \| general; billing→END; technical→END; general→END |
| `workflow_agent` | Workflow | START→extract→validate; validate ⇢ transform \| handle_error; transform→load→END; handle_error→END |
| `event_driven_agent` | Event Driven | START→receive_event; receive_event ⇢ handle_order \| handle_refund \| ignore; handle_order→emit_result; handle_refund→emit_result; ignore→END; emit_result→END |
| `autonomous_agent` | Autonomous | START→set_goal→plan→act→observe→check_goal; check_goal ⇢ plan \| report; report→END |
| `audit_agent` | Audit | START→act→record; record ⇢ act \| summarize; summarize→END |
| `review_agent` | Review | START→draft→review; review ⇢ draft \| approve; approve→END |

Topology note: the ReAct, Reflection and Planning skeletons must keep the node names their Studio-spec sections give, so the milestone 3 live graphs keep the same diagram.

## 7. Guide content for Guide-only patterns

- **Same seven `##` headings, in order:** What it is, When to use it, How this graph works, LangGraph concepts, Trade-offs, Key code, Try this. The existing heading test applies to every `explanation.md` in `agents/*/`.
- **H1** is the taxonomy name, e.g. `# Episodic` or `# Routing`.
- **"How this graph works"** names every skeleton node exactly as the diagram shows it, and states the pattern's dividing line from §3.3 where one applies.
- **"LangGraph concepts"** names the real LangGraph features a live version would use, e.g. `Send` for fan-out, `Command(goto=...)` for handoffs, `Store` for episodic memory, subgraphs for hierarchy. The text says "a live version would use…" rather than implying the skeleton does it.
- **"Key code":**
  - Shows the skeleton's wiring (≤ 25 lines, from `graph.py`) and says plainly that the node bodies are placeholders.
  - A test enforces the 25-line limit for every guide. This was deferred from milestone 1.
- **"Try this":** since there is no demo yet, it offers one or two concrete thought exercises tied to the diagram, plus a link-style pointer to the closest live pattern, e.g. Review → "compare with Reflection (live demo coming) and Approval (live)". The text names patterns; the UI turns `[[category/pattern]]` markers into links to those routes, built safely as DOM anchors.
- **Accuracy:** each guide must describe the pattern as established practice describes it, without inventing APIs. Every LangGraph name mentioned must exist in the installed langgraph 1.2 (`langgraph.types.Send`, `langgraph.types.Command`, `langgraph.store`, etc.). A test imports each backticked dotted name that starts with `langgraph.`.
- **Length:** 50–110 lines per file.

## 8. Changes to existing pieces

- **Frontend:**
  - The router in `app.js` moves from `#<patternId>` to the routes in §4.1, with legacy redirects.
  - The tab strip is replaced by the breadcrumb header.
  - Two views: `home` (new `catalog.js`) and `pattern`. The pattern view reuses the M1 workbench when `demo` is set; otherwise it renders the static diagram (graph.js gains a `static` option) and the Guide.
  - The stale-load guards (`requestedId` / tokens / `chatGen`) and stream aborts apply to route changes exactly as they did to tab changes.
- **`guide.js`:** supports `[[category/pattern]]` link markers. The link text is the target pattern's name from the catalog; unknown targets render as plain text. Built with DOM APIs, never through `innerHTML`.
- **The four existing live guides (builder's call):** add a content pass to the `explanation.md` files of `qa_agent`, `chat_agent`, `secure_chat_agent` and `interrupt_chat_agent`. Each gets an H1 matching its taxonomy name, the §3.3 dividing-line sentence where one applies (Session vs Episodic; Approval vs Review; Single Agent vs Supervisor/Swarm/Hierarchy; Guardrails vs Review), and `[[category/pattern]]` pointers to related patterns. All the §9 file tests, including the LangGraph-name import test, apply to them too. Their "Try this" steps must keep working offline; the existing M1 test covers that.
- **Registry:** unchanged. The catalog refers to registry ids, and a test asserts every non-null `demo` that is registered exists.
- **Default landing:** `#/` (catalog home) instead of `qa`.

## 9. Testing

- **Catalog:**
  - Exactly 5 categories and 21 entries, in the §3 order, with exact names, hints and questions.
  - Ids are unique within each category, and route strings are unique.
  - Each cross-list target exists and is not itself a cross-list.
  - Each live entry's `demo` is in `PATTERNS`. Each `PATTERNS` id is referenced by exactly one catalog entry, so no demo is unreachable.
- **Files:** every non-cross-list entry's folder has an `explanation.md` that passes the heading test, the ≤ 25-line Key code test, the 50–110 line length, and the LangGraph-name import test. Every Guide-only folder's `build_skeleton()` compiles, its topology node set equals §6's list, and its routers are `Literal`-annotated (the topology has no "edge to every node" fan-out).
- **API:**
  - `/api/catalog` shape and order.
  - Page data for a live pattern, a Guide-only pattern and the cross-list (route/category of the request, content of the target).
  - 404 for an unknown route.
  - Status flips to `live` when a registry entry with that id is added. Test with a fake registry.
- **Static checks:** the existing `innerHTML` rule still holds. A Python test asserts that `catalog.js` and `guide.js` build links with `createElement("a")` and contain no `innerHTML` (guide.js keeps its single DOMPurify use).
- **Browser checklist,** run via headless Chrome over CDP as in M1, with screenshots:
  - The home page at 1440, 900 and 375 px.
  - Search for "HITL" (→ Approval), "remember users" (→ Episodic), "human sign-off" (→ Approval) and "zzz" (no matches).
  - Opening a live pattern and a Guide-only pattern.
  - Tool Use showing the Execution breadcrumb.
  - ← / → wrapping.
  - A legacy `#guardrail` redirect.
  - Reload on a pattern route.
  - Dark and light themes.

## 10. Milestones (proposal; renumbers the Studio spec's)

The Studio spec §13 listed M1 Core, M2 New patterns, M3 Hardening + deploy. This spec inserts the catalog before the new patterns:

1. **M1 Core.** Done, on `feature/patterns-studio`.
2. **M2 Catalog & menu (this spec):** the catalog module and API, 16 skeletons + guides, the home page, routing, breadcrumbs, and the Guide-only view.
3. **M3 Live patterns: ReAct, Reflection, Planning** (the old M2). Each fills its existing skeleton folder and turns live via its registry id. The M1 follow-ups list for "M2" moves here.
4. **M4 Hardening + deploy** (the old M3). The M1 follow-ups list for "M3" moves here.
5. **Later:** a live demo per remaining pattern, in any order, each its own small plan.

## 11. Out of scope / left to the builder

- **Out of scope:**
  - Live demos for the 16 Guide-only patterns, beyond the three in M3.
  - Fuzzy search ranking: substring matching is enough at 21 entries.
  - Telemetry on searches.
  - Translations.
- **Left to the builder:**
  - The visual styling of cards, the banner and the static diagram, within the existing design tokens.
  - The exact wording of guide prose (within §7) and of the notices quoted in §4, where no exact copy is fixed.
  - Internal file split of the frontend modules beyond `catalog.js`.
