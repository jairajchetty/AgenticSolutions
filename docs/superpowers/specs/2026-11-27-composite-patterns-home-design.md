# Composite patterns on the main page: design

Date: 2026-11-27
Status: draft for approval
Branch: new branch off `feature/edge-labels`, stacked on PR #7.

## 1. Intent

The Studio lists 21 patterns of very different sizes. Some, such as Session or ReAct, are building blocks. Others, such as Approval or Knowledge Graph, are built by combining building blocks. The owner wants the main page to focus on the larger patterns, and to show what each one is built from.

**Definitions:**
- A **composite pattern** is built by implementing simpler patterns. Examples: Approval (Session, ReAct, Tool Use and others) and Knowledge Graph.
- A **simple pattern** is a building block: it is not built from other patterns in the catalog.

The main page shows only composite patterns. Each composite pattern shows the patterns it builds on, and links to them. The catalog moves from Python code into a YAML file that the owner edits.

## 2. Goals, non-goals, anti-goals

**Goals**
- The main page shows the 14 composite patterns, grouped by category, using layout B (see §5).
- Each composite card lists its "builds on" patterns as links to their Guide pages.
- The seven simple patterns appear in a "Building blocks" strip at the foot of the catalog sheet.
- One YAML file defines categories, patterns, descriptions and "builds on". Changing the main page needs no code change.
- The app refuses to start if the file is invalid. This matches how the catalog fails today.

**Non-goals**
- No change to the Guide pages: their content, routes, breadcrumbs, and next and previous arrows stay as they are.
- No new live demos, and no change to what Guardrails or Search actually implement today.
- No phone layout. The Studio is desktop-only.

**Anti-goals**
- **Losing any Guide.** Every one of the 21 Guide pages must stay reachable from the main page, either through a card, a "builds on" link or the building-blocks strip.
- **Duplicated descriptions.** A pattern's name and description are written once in the file, however many cards refer to it.
- **Claims a live demo doesn't back up.** For the four live demos, "builds on" must describe what the demo's graph actually does.

## 3. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | One YAML file holds all 21 patterns. A composite pattern has `builds_on: [ids]`, naming other patterns. Whether a pattern is composite or simple is worked out from that list, never stored. | Each description is written once, and broken references are caught at startup. Reading a card's full content means looking at two entries. |
| B | Each `builds_on` entry writes out its name, category and description inline. | Each entry reads on its own, but Session's description would be repeated about eight times and the copies would drift. The simple patterns would still need entries of their own. |
| C | Keep `catalog.py`, and add a small YAML file for the main page only. | The smallest change, but it creates two sources of truth. |

The owner chose A.

## 4. The catalog file

**Location:** `src/agentic_solutions/web/catalog.yaml`. It ships with the package, and the owner edits it directly.

**Shape:**

```yaml
# The Studio's pattern catalog. Edit this file to change the main page.
# A pattern with `builds_on` is composite: it appears on the main page.
# A pattern without it is simple: it appears in the building-blocks strip.

categories:
  - id: governance
    name: Governance
    description: How is it kept safe and accountable?
    patterns:
      - id: approval
        name: Approval
        description: The agent drafts an action; a policy or a person approves the exact version before it runs.
        aliases: [human-in-the-loop, HITL, interrupt, sign-off]
        demo: approval            # registry id of the live demo; omit if none
        folder: approval_agent    # agent folder holding explanation.md and the skeleton
        builds_on: [memory/session, cognitive/react, execution/tool-use, execution/routing, governance/audit]

      - id: audit
        name: Audit
        description: Keep persistent, queryable records of every run.
        aliases: [logging, traceability, run history, compliance]
        folder: audit_agent

  - id: execution
    name: Execution
    description: How does it act and run?
    patterns:
      - id: tool-use
        name: Tool Use
        description: Call functions and APIs.
        aliases: [function calling, tools, actions]
        crosslist_of: cognitive/react   # no page of its own: opens ReAct's Guide
```

**Fields:**
- **Category:** `id`, `name` and `description`, all required, plus `patterns`. The category's `description` replaces today's `question` field.
- **Pattern:** `id`, `name` and `description`, all required.
  - **Optional:** `aliases` (default empty), `demo`, `folder`, `crosslist_of` and `builds_on`.
  - **`folder` and `crosslist_of`:** a pattern has exactly one of them. This is today's rule.
  - **`builds_on`:** a list of pattern routes, written `category/id`. Routes are unique across the catalog, and they are already what the app uses to identify a pattern.
- **Order:** categories and patterns keep the order in which they appear in the file.

**Derived, never stored:**
- **Composite or simple:** `composite` is true when `builds_on` is not empty.
- **Live or Guide only:** status works as it does today, from `demo` and the registry.

**Startup checks:** any failure stops the app, with a message that names the file and the offending entry. The app checks that:
- the file parses, and the required fields are present and non-empty;
- category ids are unique, and pattern routes are unique;
- every `builds_on` entry and every `crosslist_of` names a route that exists;
- no pattern builds on itself, and the `builds_on` links never form a cycle;
- a pattern has exactly one of `folder` and `crosslist_of`;
- every category has at least one composite pattern (otherwise it would show as an empty band);
- the YAML is loaded with `yaml.safe_load`.

**Code:** `catalog.py` keeps its public functions (`CATALOG`, `entry`, `target`, `status`, `neighbours`), so the rest of the app is unchanged. Its data now comes from the YAML file instead of Python literals. `CatalogPattern` gains `description` and `builds_on`, and `hint` is renamed to `description`. `Category.question` becomes `description`. Tests move to the new names.

**Dependency:** add `pyyaml>=6` to `pyproject.toml`. It is already installed, but only as another package's dependency.

## 5. The main page (layout B)

The hero, search box and title block stay as they are. The hero's lede changes from "Twenty-one agentic design patterns…" to describe composites without a number, for example "Composite agentic patterns, each built from simpler patterns you can open on their own." A number written there would go wrong as soon as someone edits the file. The copy follows the README's writing guidelines.

The catalog sheet becomes a stack of **category bands**, in file order:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Governance            ┌───────────────┐ ┌───────────────┐ ┌──────────────┐ │
│ How is it kept safe   │● Guardrails   │ │● Approval     │ │○ Review      │ │
│ and accountable?      │ description…  │ │ description…  │ │ description… │ │
│                       │ BUILDS ON     │ │ BUILDS ON     │ │ BUILDS ON    │ │
│                       │ [Session]     │ │ [Session]     │ │ [Reflection] │ │
│                       │ [Routing]     │ │ [ReAct] …     │ │ [Single Agt] │ │
│                       └───────────────┘ └───────────────┘ └──────────────┘ │
│──────────────────────────────────────────────────────────────────────────│
│ Memory …                                                                  │
│══════════════════════════════════════════════════════════════════════════│
│ BUILDING BLOCKS  [Single Agent·Collaboration] [Session·Memory] [ReAct·…]  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Category band:** on the left, the category name and description; on the right, a grid of three cards per row. Only composite patterns get a card.

**Card:** made up of these parts:
- **Status mark:** ● for a live demo, ○ for Guide only.
- **Name:** opens the pattern's Guide page.
- **Description.**
- **"Builds on" row:** one link per entry, in file order.
  - **Solid border:** the entry is a simple pattern.
  - **Dashed border:** the entry is another composite pattern.
  - **Hover text** (`title`): the entry's category and description.
  - **Target:** each link opens that pattern's page. A cross-listed pattern (Tool Use) opens its target's page, as it does today.

**Building-blocks strip:** every simple pattern, in file order, as a link carrying its name and category. This keeps every Guide reachable from the main page.

**Legend:** keeps ● and ○, adds solid versus dashed links, and keeps ↗ for a cross-list.

**Breadcrumb:** a Guide page's category link still lands on its category, now the band heading (`#cat-<id>`). For a simple pattern, it lands on the band of the pattern's category, even though the pattern itself sits in the strip.

**Search:** keeps today's word rule (`matches()`). A composite card matches on its own text (name, description, aliases, category name and description) or on the names and aliases of its "builds on" patterns. That way "tool use" finds Approval. Building-block links in the strip match on their own text. A band with no matching cards hides. Enter opens the first matching card, or the first matching building block if no card matches. The match count counts cards and building blocks together.

## 6. API

`GET /api/catalog` keeps its shape and adds fields:
- Each category gains `description`. `question` is removed, and the frontend changes to match.
- Each pattern gains `description` (replacing `hint`), `composite` (true or false) and `builds_on`. `builds_on` is a list of `{route, target, name, category, description, aliases, composite}`, resolved on the server, so the browser needs no lookups.

`/api/catalog/page/...` (the Guide page data) is unchanged.

## 7. Initial content (first draft, for the owner to correct)

| Category | Composite pattern | Builds on |
|---|---|---|
| Cognitive | Planning | ReAct, Workflow |
| | Reflection | Single Agent, Workflow |
| | Search | Planning, Reflection |
| Collaboration | Supervisor | Routing, ReAct, Tool Use |
| | Swarm | ReAct, Tool Use, Session |
| | Hierarchy | Supervisor |
| Memory | Episodic | Session, Tool Use |
| | Semantic | ReAct, Tool Use |
| | Knowledge Graph | Semantic, Tool Use |
| Execution | Event Driven | Workflow, Audit |
| | Autonomous | Planning, Reflection, Episodic, ReAct |
| Governance | Guardrails | Session, Routing |
| | Approval | Session, ReAct, Tool Use, Routing, Audit |
| | Review | Reflection, Single Agent |

**Simple patterns:** Single Agent, Session, ReAct, Tool Use (cross-list of ReAct), Routing, Workflow and Audit.

**Live demos:** Guardrails and Approval are composite. Single Agent and Session are simple, so their live demos are reached from the building-blocks strip.

**Checking the live demos:** Approval's graph has the `ask` loop (Session), `agent` ↔ `tools` (ReAct and Tool Use), `policy` routing (Routing) and the ERP audit trail (Audit). Guardrails' graph has the `ask` loop (Session) and the `guard` router (Routing).

The initial descriptions are today's hints. The owner can lengthen them in the file.

## 8. Testing

- **Python:**
  - The shipped file loads.
  - Each startup check fails with a clear message: unknown `builds_on` route, cycle, duplicate route, missing field, a category with no composites, `folder` and `crosslist_of` both set.
  - The `/api/catalog` shape, including the resolved `builds_on`.
  - Every one of the 21 routes is reachable from the main page: as a card, a building block or a `builds_on` link.
  - Existing tests (guides, catalog API, registry) pass after the field renames.
- **JS (`tests/js/search.test.mjs`):**
  - A card matches on a building block's name ("tool use" finds Approval).
  - A building block matches on its own text.
  - The fixture regenerates from the YAML through `_catalog_listing`, as it does today.
- **Browser:** the main page at 1440 px, with a search for "tool use" and the breadcrumb landing on a band, and no console errors.

## 9. Calls made in this design (for the owner to check)

- **Guide pages are unchanged.** A composite's Guide page doesn't list its building blocks; only the main page does.
- **Session and Single Agent have live demos but are simple,** so they appear only in the building-blocks strip.
- **`builds_on` refers to patterns by route** (`memory/session`), not by bare id, because ids are only unique within a category.
- **The category description replaces today's category question.** The shipped file keeps the current questions as descriptions.
- **The previous and next arrows on Guide pages** still step through every pattern in the category, simple ones included.

## 10. Left to the builder

- Exact card and strip styling, within the Blueprint tokens and the mockup (`images/home-mockups.html`, option B).
- How the startup checks are split into functions, and the exact wording of the error messages.
- Whether the hero graph keeps drawing ReAct. That is out of scope; leave it unless it reads wrongly.
