# Blueprint Redesign + About Section: Design Spec

- **Date:** 2026-11-23
- **Status:** Draft, builder-checked, awaiting the person's approval
- **Builds on:** the Studio spec (§6 UI), the Catalog spec (§4 UX). It supersedes their visual styling and page order. Behaviour, routes, API and accessibility rules are unchanged unless stated here.
- **Branch:** `feature/cognitive-live`. This lands **before** Milestone 3's code, so Milestone 3's new UI pieces (the Live switch, tool chips, drafts list and plan checklist) are built in this design.

## 1. Intent

The Studio is the person's portfolio piece: it demonstrates their ability as an **AI agent architect**. It must be **attractive, concise and useful**.

Three changes, all the person's own:
1. **Purpose first.** On every pattern page, "What it is" and "When to use it" come first, so the reader gets the pattern's purpose before anything else.
2. **About the author.** The landing page has a section about the person, drawn from their CV, whose single goal is to get the reader to **contact** them. The person chose email as the contact method.
3. **A designed UI.** The frontend-design review found the current UI generic. The person chose the **Blueprint** direction.

**Anti-goals**
- Template-looking UI: identical cards, grey on grey, decorative chrome.
- Publishing the person's phone number, or putting their email address in plain text where scrapers read it.
- A hero that sells instead of showing.
- Long text on dark backgrounds.
- Breaking any existing behaviour: workbench, threads, routing, search, accessibility.

## 2. Approaches considered

Mockups are in `.superpowers/brainstorm/redesign/directions.html`.

| | Direction | Trade-offs |
|---|---|---|
| A | **A pattern language** (after Alexander): a serif reference book, problem → "Therefore:" → solution | The most "useful and concise". The quietest, and the live trace has to earn attention. |
| **B (chosen)** | **Blueprint**: an architect's drawing set. Navy drafting frame, line-art graphs as the hero, condensed drafting type, and the About section as the drawing's **title block** | The most distinctive and the strongest personal brand ("drawn by an architect"). Reading text needs light sheets for legibility. |
| C | **Live system**: Swiss, white, five category colours, a running guardrail as the hero | The most immediately engaging, but the least about the person. Five colours risk busyness. |

**Build approach (one sensible way):**
- Restyle the existing no-build frontend in place: new tokens and markup, same modules and logic.
- Keep the About content in one data file.
- Contact uses an email link assembled at runtime.
- The alternatives were dropped: a CSS framework or build step contradicts the repo's no-build rule, and a separate landing site splits the demo from the proof.

## 3. Design system

### 3.1 Colour tokens

| Token | Hex | Use |
|---|---|---|
| `--navy` | `#0F2B46` | the drafting frame: page background, masthead, hero, the graph canvas |
| `--line` | `#9CC7E8` | line work: graph edges and nodes, grid, frame rules, secondary text on navy |
| `--paper` | `#F3F6F8` | sheets: every reading surface (purpose, console, guide, catalog) |
| `--ink` | `#13202B` | text on paper |
| `--amber` | `#E2A33B` | the **one** highlight: the active node, the primary action ("Get in touch"), focus rings on navy |
| `--signal-red` | `#C2412D` | errors and refused nodes only |
| `--muted-ink` | `#51606D` | secondary text on paper |

- The drafting grid is `--line` at 9% opacity, 24 px, on navy only.
- **Contrast:** every text/background pair meets WCAG AA (4.5:1 body, 3:1 large text). In particular, `--line` on `--navy` (~7:1) and `--ink` on `--paper`. The implementer verifies every pair with a small script and reports the ratios.
- **One theme.** The Blueprint identity is a dark frame with light sheets in both colour schemes; reading surfaces are already light. The existing `prefers-color-scheme: dark` overrides are removed, and both schemes render the same design.

### 3.2 Type

- **Display, labels and graph text:** **Barlow Condensed** (600, 500). Headings, the masthead, title-block labels, node labels and breadcrumbs.
- **Body and controls:** **Public Sans** (400, 600, 700).
- **Source:** Google Fonts, the stylesheet host already allowed by the Studio's constraints, with `display=swap` and system fallbacks.
- **Scale:** 1.25 ratio from 16 px body: 16 / 20 / 25 / 31 / 39 / 49, with hero h1 at 58 px desktop and 38 px mobile. Body line length ≤ 75 ch. Sentence case everywhere.
- **Avoid** all-caps labels, eyebrow labels above headings, `→` appended to links, and middle-dot meta strings in new copy.

### 3.3 Principles

1. **The graph is the hero.** Line art on navy, the signature element. Spend boldness there; keep everything else quiet.
2. **Read on paper.** Any block of more than two lines sits on a `--paper` sheet.
3. **Amber means "here/now/act".** It is used for the active node, the current step and the single primary action per view, and nowhere else.
4. **Structure encodes information.** Rules and frames follow drawing conventions (title block, sheet edges). No decorative cards, gradients or shadows beyond one subtle sheet shadow.
5. **Motion only for meaning.** The hero graph traces one path, once per load (≈4 s), then rests. Live traces animate as today. `prefers-reduced-motion` shows the final state with no animation.

## 4. Pages

### 4.1 Landing (`#/`)

```
┌ navy frame (drafting grid) ───────────────────────────────────────────────┐
│ Agentic Patterns Studio                                ● Offline (scripted)│
│                                                                           │
│ Agent architectures,                 ┌─ line-art graph (ReAct) ─┐          │
│ drawn to scale and running live.     │  ask → agent ⇄ tools      │          │
│ Twenty-one agentic design patterns…  │  (traces once, amber)     │          │
│ [ What are you trying to do? …     ] └───────────────────────────┘          │
│                                                                           │
│ ┌ title block ────────────────────────────────────────────────────────────┐ │
│ │ Architect          │ Record                              │ Contact      │ │
│ │ Jairaj Chetty      │ 20+ years … 120+ integrations …     │ [Get in touch]│ │
│ │ Solution architect,│ Eskom, Equity Bank … TOGAF …        │              │ │
│ │ enterprise integr. │ Oracle GenAI + AI Vector Search     │              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ┌ paper sheet: catalog ───────────────────────────────────────────────────┐ │
│ │ Cognitive        Collaboration    Memory         Execution   Governance │ │
│ │ How should…      How many…        What must…     How does…   How is…    │ │
│ │ ● ReAct …        ● Single Agent … ● Session …    ● Tool Use… ● Guard…   │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

- **Hero copy, exact:**
  - h1: "Agent architectures, drawn to scale and running live."
  - Lede: "Twenty-one agentic design patterns, each with the problem it solves, when to use it, and a working graph you can step through."
  - The search box keeps the Catalog spec §4.2 behaviour, label, placeholder and keyboard shortcuts, restyled.
- **Hero graph:**
  - An inline SVG of the ReAct topology (`ask`, `agent`, `tools`, with start and end), in `--line` strokes and Barlow Condensed labels.
  - On load it traces `start → ask → agent → tools → agent → end` once (§9.2). The active node turns amber, and edges draw with `stroke-dashoffset`.
  - It is decorative: `aria-hidden="true"`, with an `sr-only` caption "Diagram of the ReAct pattern's graph".
  - The SVG is hand-built from a fixed layout. It is not the live Cytoscape graph.
  - Below 700 px it sits under the copy at 80% scale.
- **Title block** (the About section): a three-cell bordered panel in drawing-title-block style, `--line` rules on navy. Copy is exact:
  - **Architect:** "Jairaj Chetty" / "Solution architect, enterprise integration and agentic AI".
  - **Record:** "20+ years of integration architecture across Africa and the Middle East. 120+ integrations for MTN's group-wide Oracle Fusion ERP. Reference architectures for Eskom and Equity Bank. TOGAF 10, Oracle Generative AI and AI Vector Search certified. Built this Studio with LangGraph and Claude."
  - **Contact:** an amber **"Get in touch"** button.
  - Cell labels ("Architect", "Record", "Contact") are small sentence-case Barlow Condensed in `--line`.
  - Below 700 px the cells stack.
- **Catalog:** the five categories on one paper sheet; five columns at ≥ 1100 px, 3 + 2 below 1100 px, one column below 700 px (builder's call: five columns at 900 px broke pattern names). Columns are separated by hairline `--line`-tinted rules, not cards. Each column has its name (Barlow Condensed), its question (muted ink) and its pattern rows, with the existing status marks, hints, cross-link mark and search filtering. The legend sits under the sheet, on navy.
- **Footer:** one line on navy: "Built by Jairaj Chetty with LangGraph and Claude." and a "Get in touch" text link.

### 4.2 Pattern page (`#/<category>/<pattern>`)

**New order** (the person's change #1):

1. The masthead, with breadcrumb and prev/next (restyled).
2. **Purpose sheet** (paper), placed first:
   - The page **h1** (pattern name, Barlow Condensed).
   - **"What it is"** as the lead paragraph(s) at 20 px.
   - **"When to use it"** beside it on wide screens and below it under 900 px.
   - Both come from the guide markdown's first two `##` sections, rendered with the same sanitising pipeline and link markers.
3. **Live patterns:** the workbench.
   - The **trace graph sits on the navy frame** as blueprint line art. Cytoscape styles come from the tokens: `--line` strokes and labels, amber active node, `--signal-red` error node, paused state with an icon.
   - The timeline and state view sit on a paper sheet beside or below it.
   - The console sits on a paper sheet.

   **Guide-only patterns:** the "Live demo coming" note as a slim line on navy, then the static diagram on navy.
4. **The rest of the Guide** on a paper sheet: How this graph works, LangGraph concepts, Trade-offs, Key code, Try this. Rendered exactly as today, minus the two sections moved up.

The cross-list note (Tool Use → ReAct) sits under the h1 inside the purpose sheet.

### 4.3 Components (restyle only; behaviour unchanged)

- **Masthead:** "Agentic Patterns Studio" in Barlow Condensed on navy, plus the mode badge with a hairline outline.
- **Buttons:** primary is amber with ink text (one per view). Secondary is an outline in `--line` on navy, or in `--ink` on paper.
- **Focus:** a visible 2 px ring, amber on navy and ink on paper. Every interactive element keeps keyboard access.
- **Chat bubbles, notices, chips and result cards** use the paper palette, with the error and refusal styling in `--signal-red`.

## 5. Contact (email)

- The email address is never present as one string in any served file:
  - `about.js` holds it split, e.g. `["jairajchetty", "gmail.com"]`.
  - It builds `mailto:` on click, or on focus for keyboard users, with the subject "Agentic Patterns Studio".
  - Until then the button's `href` is `#contact` and it has `rel="nofollow"`.
- Without JavaScript the button shows the text "jairajchetty at gmail dot com".
- **No phone number anywhere** in the repo's served files.
- About copy and contact parts live in `web/static/about.js`, a pure ES module exporting `ABOUT` (text fields) and `contactHref()`, so the person can edit one file.

## 6. Repository hygiene

- Add `CV_*.pdf` to `.gitignore`. The CV is never committed.

## 7. Testing

- **Static (pytest):**
  - No served file under `web/static/` contains any South African phone number (`+27…` or `0xx xxx xxxx`, in any spacing), or the full email string `<the person's email address>`.
  - `index.html` loads fonts only from `fonts.googleapis.com`/`fonts.gstatic.com`.
  - The existing `innerHTML` and CDN rules still hold.
- **JS unit tests (node):**
  - `contactHref()` → `mailto:<the person's email address>?subject=Agentic%20Patterns%20Studio`.
  - A new pure `splitPurpose(markdown) → {purpose, rest}` in guide.js returns the first two sections in `purpose`, and the other five in `rest` in order.
  - Markers inside code are untouched.
- **Contrast:** a script computes WCAG ratios for every text/background token pair. Every pair passes AA, and the report records them.
- **Browser checklist** (headless Chrome over CDP), with screenshots at 1440, 900 and 375 px:
  - The landing page: the hero animates once, and with `prefers-reduced-motion` emulated there is no animation; the title block; the catalog with search working; the "Get in touch" href becomes the mailto on click.
  - A live pattern page (Approval): purpose first; the trace on navy animates during a run; a full chat turn works; the state view and timeline are legible.
  - A Guide-only page (Episodic): purpose first, then the diagram, then the rest of the guide.
  - Keyboard: Tab order, visible focus everywhere, `/` and ←/→ still work.
  - No horizontal scroll at 375 px.
- **Everything else unchanged:** all existing pytest and JS tests pass unchanged, except assertions that hard-code the old page order or styling, which the report lists.

## 8. Out of scope / left to the builder

- **Out of scope:**
  - Rewriting guide prose. The two sections move; their text is unchanged.
  - Milestone 3 features, which come next on this branch in this design.
  - A contact form (Milestone 4 at the earliest).
- **Left to the builder, within §3:** exact spacing, the hero graph's SVG geometry, sheet shadow and radius (≤ 4 px), and the masthead and breadcrumb arrangement at each breakpoint.

## 9. Builder-check decisions (builder's calls)

1. **Contact link and the hash router.**
   - Every "Get in touch" element (title block and footer) is `<a href="#" data-contact rel="nofollow">`.
   - One delegated handler calls `preventDefault()` on click (and on Enter) and then sets `window.location.href = contactHref()`. The URL hash never changes, so the router never sees it, and `router.js` and its tests are unchanged.
   - Without JS, a `<noscript>` line shows "jairajchetty at gmail dot com". The phone number never appears.
2. **Hero path:**
   - The hero traces `start → ask → agent → tools → agent → end`. `end` is drawn, and the trace finishes with `end` lit.
   - With `prefers-reduced-motion`, the full graph is drawn statically with `agent` in amber and no animation.
3. **One theme for graphs.**
   - `graph.js` drops its `prefers-color-scheme` listener and reads the new tokens (`--line`, `--amber`, `--signal-red`, `--navy`, `--paper`).
   - The live trace and the Guide-only static diagram always sit on navy in line-art style.
   - The timeline and state panels beside the trace are paper sheets.
   - Existing JS or static tests that assert the old listener or variable names may be updated and must be listed.
4. **The purpose-first structure.**
   - `#pattern-view` gets a shared `#purpose` sheet above both `#bench` and `#guide-only`. It holds the page h1, the cross-list note, "What it is" and "When to use it".
   - The guide markdown is split once with `splitPurpose`, by **heading name** ("What it is", "When to use it"), not position. The two parts are rendered into the purpose sheet and the remaining guide sheet.
   - If either heading is missing, the purpose sheet shows only the h1 and everything goes to the rest.
   - The skip link still lands on the console input on live pages and on the purpose sheet's h1 on Guide-only pages.
5. **Milestone 3 components** (the Live switch, tool chips, drafts list and plan checklist) are not designed here. Milestone 3 builds them with these tokens and the "read on paper / amber means act" rules. The M3 plan's Task 10 gains a pointer to this spec.
6. **The contrast check is a persistent test**, `tests/test_contrast.py`.
   - It parses the token hex values from `styles.css` `:root` and asserts WCAG AA for the defined text pairs:
     - `--ink`/`--paper`
     - `--muted-ink`/`--paper`
     - `--line`/`--navy`
     - `--paper`/`--navy`
     - `--ink`/`--amber`
     - `--signal-red`/`--paper`
     - `--amber`/`--navy` (large text and UI, 3:1)
   - The decorative grid lines are exempt.
