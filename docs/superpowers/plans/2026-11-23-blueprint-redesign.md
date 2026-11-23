# Blueprint Redesign + About Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Studio in the Blueprint direction, put each pattern's purpose first, and add an About title block with an obfuscated email contact on the landing page.

**Architecture:**
- **Design tokens:** a token-based restyle of the existing no-build frontend. `styles.css` `:root` holds the Blueprint palette and type, there is one theme, and Cytoscape reads the tokens.
- **Pure modules:** `about.js` (content plus `contactHref`) and `guide.js`'s `splitPurpose` are unit-tested in Node.
- **Page structure:** markup changes add a shared purpose sheet above the workbench and the Guide-only view.

**Tech Stack:** vanilla ES modules, CSS custom properties, Cytoscape 3.30 + dagre, Google Fonts (Barlow Condensed, Public Sans), pytest, `node:test` via Windows `node.exe`.

**Spec:** `docs/superpowers/specs/2026-11-23-blueprint-redesign-design.md` (the "Redesign spec"). §9 holds the builder-check decisions. It builds on the Catalog spec §4 and the Studio spec §6. Mockup option B: `.superpowers/brainstorm/redesign/directions.html`.

**Branch:** `feature/cognitive-live`. This plan runs before the Milestone 3 plan.

## Global Constraints

- **Tokens (exact hex):** `--navy #0F2B46`, `--line #9CC7E8`, `--paper #F3F6F8`, `--ink #13202B`, `--amber #E2A33B`, `--signal-red #C2412D`, `--muted-ink #51606D`. The drafting grid is `--line` at 9% opacity on a 24 px grid, on navy only.
- **Type:**
  - Barlow Condensed (500, 600) for display, labels, breadcrumbs and graph text. Public Sans (400, 600, 700) for body and controls.
  - Fonts load only from `fonts.googleapis.com`/`fonts.gstatic.com`.
  - Scale: 16 / 20 / 25 / 31 / 39 / 49 px; the hero h1 is 58 px on desktop and 38 px on mobile; body text ≤ 75 ch.
- **Copy:**
  - Sentence case throughout.
  - No all-caps labels, no eyebrow labels, no `→` appended to links.
  - Exact copy comes from Redesign spec §4.1, §4.2 and §5.
- **One theme:** remove every `prefers-color-scheme: dark` override and the graph's scheme listener.
- **Amber marks the one active node, the current step and the single primary action per view.** Use it for nothing else.
- **Motion:** the hero traces once (≈4 s). Respect `prefers-reduced-motion`.
- **Privacy:**
  - No served file contains `<the person's email address>` as one string, or the phone number in any spacing.
  - "Get in touch" elements are `<a href="#" data-contact rel="nofollow">` and are handled by one delegated listener (`preventDefault`, then `location.href = contactHref()`).
- **No regressions:** behaviour must not change (routes, search, workbench, threads, skip link, keyboard, `innerHTML` rule). All existing tests keep passing. The only existing assertions you may edit are ones that hard-code the old page order, styling or graph scheme listener. List each one.
- **Commits:** commit with `git -c user.name="$(git log -1 --format=%an main)" -c user.email="$(git log -1 --format=%ae main)" commit …`. Never stage `.env`, `.superpowers/`, or the CV PDF.

## Review Focus

1. **A visitor with no mail app clicks "Get in touch" and nothing visible happens.** After the first click (or Enter), also reveal the assembled address as selectable text next to the button: "or copy: <the person's email address>". Test in Task 2 (JS) and Task 6 (browser).
2. **Long code blocks or wide state JSON on a 375 px screen must not cause horizontal page scroll.** Code fences and the state view scroll inside their own sheet. Checked in the Task 5 browser step.
3. **Keyboard focus must be visible on navy and on paper.** Tab through the landing and pattern pages; every focusable element shows the amber or ink ring. Checked in the Task 6 browser step.
4. **Reduced motion: the hero must not animate, and live traces must keep their state colours without pulsing.** Checked in the Task 6 browser step.
5. **A guide missing "What it is" or "When to use it"** shows the full guide below, with no empty purpose sheet. Test in Task 3 (JS).

---

## File structure

```
src/agentic_solutions/web/static/styles.css   MODIFY  tokens, type, one theme, all component styles
src/agentic_solutions/web/static/index.html   MODIFY  font links, #purpose sheet, hero, title block, footer, noscript
src/agentic_solutions/web/static/about.js     CREATE  ABOUT copy + contactHref() + bindContact(root)
src/agentic_solutions/web/static/hero.js      CREATE  hero SVG build + one-shot trace animation
src/agentic_solutions/web/static/guide.js     MODIFY  splitPurpose(markdown) + renderPurpose(el, md, opts)
src/agentic_solutions/web/static/graph.js     MODIFY  read new tokens; drop scheme listener; navy line-art style
src/agentic_solutions/web/static/app.js       MODIFY  render purpose first; title block/footer contact wiring
src/agentic_solutions/web/static/catalog.js   MODIFY  catalog sheet markup (columns + rules, no cards)
tests/test_contrast.py  tests/test_static.py  tests/js/about.test.mjs  tests/js/guide.test.mjs
```

---

### Task 1: Tokens, type, single theme, contrast test

**Files:**
- Modify: `static/styles.css` (`:root` tokens; remove dark overrides), `static/index.html` (Google Fonts link), `static/graph.js` (read new tokens; remove the `matchMedia` scheme listener).
- Create: `tests/test_contrast.py`.
- Modify: `tests/test_static.py` (font-host rule).

**Interfaces:**
- Produces the CSS custom properties named in Global Constraints. Legacy token names used elsewhere in `styles.css` are mapped onto them or replaced, so no component is left unstyled.
- `graph.js` reads these through `getComputedStyle(document.documentElement)`.

- [ ] **Step 1: Write the failing tests.** `tests/test_contrast.py` parses `--name: #hex` from the `:root` block of `styles.css` and computes the WCAG relative-luminance contrast:

```python
PAIRS_AA = [("--ink","--paper"),("--muted-ink","--paper"),("--line","--navy"),
            ("--paper","--navy"),("--ink","--amber"),("--signal-red","--paper")]
PAIRS_LARGE = [("--amber","--navy")]
def test_text_pairs_meet_aa():      assert all(ratio(a,b) >= 4.5 for a,b in PAIRS_AA)
def test_large_pairs_meet_3_to_1():  assert all(ratio(a,b) >= 3.0 for a,b in PAIRS_LARGE)
def test_tokens_have_exact_values(): assert TOKENS["--navy"].lower() == "#0f2b46"  # …and the other six
```

  Also add `test_fonts_only_from_google` to `tests/test_static.py`: every `<link rel="stylesheet">` href in `index.html` starts with `https://fonts.googleapis.com/`. Add `test_no_dark_scheme_override`: `styles.css` contains no `prefers-color-scheme`.
- [ ] **Step 2:** Run `pytest tests/test_contrast.py tests/test_static.py -v` and confirm it FAILS.
- [ ] **Step 3: Implement.** In the report, record each pair's computed ratio. If any pair fails, report it rather than changing a token value, because the token values are spec-fixed.
- [ ] **Step 4:** Run `pytest -q` and confirm all PASS; `node.exe --check graph.js`. Take a quick headless-Chrome screenshot of `#/` to confirm nothing is unstyled.
- [ ] **Step 5:** Commit: "Introduce Blueprint tokens and type; single theme".

---

### Task 2: About content and contact

**Files:**
- Create: `static/about.js`, `tests/js/about.test.mjs`.
- Modify: `tests/test_static.py` (privacy test).

**Interfaces:**
- Produces:
  - `ABOUT = {name, role, record, builtWith}` holding the exact Redesign spec §4.1 copy.
  - `contactHref() -> "mailto:<the person's email address>?subject=Agentic%20Patterns%20Studio"`, built from parts (`["jairajchetty", "gmail.com"]`).
  - `contactAddress() -> string`.
  - `bindContact(root: Element) -> void`: one delegated `click`/`keydown` (Enter) listener on `root` for `[data-contact]`. It calls `preventDefault()`, sets `location.href = contactHref()`, and on the first use reveals `[data-contact-reveal]` text "or copy: <address>" next to the element (Review Focus 1).
  - DOM work happens only inside functions, so the module imports cleanly in Node.

- [ ] **Step 1: Write the failing tests:**
  - Node: `contactHref()` equals the exact string above; `contactAddress()` equals the address; `ABOUT.record` starts with "20+ years of integration architecture".
  - pytest `test_no_personal_contact_strings_in_served_files`: for every file under `web/static/`, the bytes contain neither `<the person's email address>` nor any South African phone number (`+27…` or a local `0xx xxx xxxx` form, allowing spaces, dashes or dots between groups).
- [ ] **Step 2:** Run and confirm it FAILS. **Step 3:** Implement. **Step 4:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 5:** Commit: "Add About content and obfuscated email contact".

---

### Task 3: Purpose-first split

**Files:**
- Modify: `static/guide.js`.
- Create: `tests/js/guide.test.mjs`.

**Interfaces:**
- Produces:
  - `splitPurpose(markdown: string) -> {purpose: string, rest: string}`. It pure-splits on `## ` headings, and `purpose` holds the "What it is" and "When to use it" sections, matched by heading name, with their headings. `rest` holds the H1 (if any) plus every other section in original order. If either purpose heading is missing, `purpose` is `""` and `rest` is the full markdown (Review Focus 5). Headings inside code fences are ignored.
  - `renderPurpose(el, markdownPurpose, {linkFor})`: the same sanitising and link-marker pipeline as `renderGuide`, laid out as two blocks (`.purpose-what`, `.purpose-when`).
  - `renderGuide` is unchanged and is used for `rest`.

- [ ] **Step 1: Write the failing node tests:**
  - A 7-section sample yields purpose headings `["What it is","When to use it"]` and rest headings `["How this graph works","LangGraph concepts","Trade-offs","Key code","Try this"]`.
  - Sections in a different order are still split by name.
  - A guide missing "When to use it" gives `purpose === ""` and `rest === input`.
  - A `## What it is` line inside a fenced code block is not treated as a heading.
- [ ] **Step 2:** Run `pytest tests/test_js.py -v` and confirm it FAILS. **Step 3:** Implement. **Step 4:** Run and confirm it PASSES; `node.exe --check`.
- [ ] **Step 5:** Commit: "Split each Guide into purpose and the rest".

---

### Task 4: Landing page: hero, title block, catalog sheet, footer

> Use the `frontend-design:frontend-design` skill. Follow Redesign spec §3–§4.1 and mockup option B.

**Files:**
- Modify: `static/index.html`, `static/styles.css`, `static/catalog.js`, `static/app.js`.
- Create: `static/hero.js`.

**Interfaces:**
- Consumes: `ABOUT` and `bindContact` (Task 2); the existing `renderHome` behaviour (search, marks, legend, keyboard). Only the markup and styling change.
- Produces `hero.js`:
  - `buildHero(svgEl)` draws the ReAct topology (start, ask, agent, tools, end) in `--line` strokes with Barlow labels.
  - `playHero(svgEl)` traces `start → ask → agent → tools → agent → end` once (≈4 s), ending with `end` lit. Edges draw with `stroke-dashoffset` and the active node is amber.
  - Under `prefers-reduced-motion` it renders the final static state with `agent` amber and no animation.
  - The SVG is `aria-hidden="true"`, and an `.sr-only` caption reads "Diagram of the ReAct pattern's graph".
- Layout per Redesign spec §4.1:
  - The navy frame with grid.
  - Hero: the exact h1 and lede, the search box, and the graph.
  - The title block: three cells, the exact copy, and a primary amber "Get in touch" `[data-contact]` with its reveal span.
  - The catalog on one paper sheet: five columns separated by rules, not cards, with the questions in muted ink.
  - The legend on navy.
  - The footer: "Built by Jairaj Chetty with LangGraph and Claude." plus a "Get in touch" text link `[data-contact]`.
  - A `<noscript>` line: "jairajchetty at gmail dot com".
- Breakpoints: below 900 px the hero stacks and the catalog wraps 3 + 2. Below 700 px everything is one column, the title-block cells stack, and the hero graph sits at 80% under the copy.

- [ ] **Step 1: Implement**, then run `node.exe --check` on every changed `.js`.
- [ ] **Step 2: Headless-Chrome screenshots** of `#/` at 1440, 900 and 375 px. Also screenshot a search for "remember users" (filtering still works on the new sheet), and a reduced-motion emulation (CDP `Emulation.setEmulatedMedia` with `prefers-reduced-motion: reduce`).
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS, including the privacy and `innerHTML` rules.
- [ ] **Step 4:** Commit: "Redesign the landing page: hero, title block, catalog sheet".

---

### Task 5: Pattern pages and components

> Use the `frontend-design:frontend-design` skill. Follow Redesign spec §4.2, §4.3 and §9.3–§9.4.

**Files:**
- Modify: `static/index.html`, `static/styles.css`, `static/app.js`, `static/graph.js`, `static/console.js`, `static/trace.js`.

**Interfaces:**
- Consumes `splitPurpose` and `renderPurpose` (Task 3).
- Produces the page structure:
  - `#pattern-view` contains `#purpose` (a paper sheet holding the page **h1**, the cross-list note, `.purpose-what` and `.purpose-when`).
  - Then `#bench` (live) or `#guide-only` (diagram).
  - Then `#guide-rest` (a paper sheet).
  - The page h1 moves from its current place into `#purpose`. Keep its id `page-title`, so focus, title and announcer logic is unchanged.
  - Live: the trace graph sits on navy in line-art style (`--line` strokes and labels, amber active, `--signal-red` error, paused with an icon). The timeline, state and console panels are paper sheets.
  - Guide-only: a slim "Live demo coming" line on navy, then the static diagram on navy.
  - The skip link lands on the console input on live pages, and on `#page-title` on Guide-only pages.
- Restyle per §4.3:
  - The masthead.
  - Buttons: primary amber, secondary outline.
  - A visible focus ring: amber on navy, ink on paper.
  - Bubbles, chips, notices and result cards on paper. Code fences and the state view scroll inside their sheet (Review Focus 2).

- [ ] **Step 1: Implement**, then run `node.exe --check` on every changed `.js`.
- [ ] **Step 2: Headless-Chrome screenshots** at 1440 and 375 px:
  - `#/governance/approval`, before and after running a sample: purpose first, the trace animating on navy, chat working.
  - `#/memory/episodic`: purpose first, then the diagram, then the rest of the guide.
  - `#/execution/tool-use`: the cross-list note in the purpose sheet.
  - At 375 px, check `document.documentElement.scrollWidth <= innerWidth` on each page.
- [ ] **Step 3:** Run `pytest -q` and confirm all PASS.
- [ ] **Step 4:** Commit: "Put purpose first and restyle the workbench in Blueprint".

---

### Task 6: Full browser checklist, Milestone 3 plan pointer, README

**Files:**
- Modify: `docs/superpowers/plans/2026-11-23-live-cognitive-patterns-m3.md` (Task 10: add "Build in the Blueprint design: `docs/superpowers/specs/2026-11-23-blueprint-redesign-design.md` tokens, sheets, amber rule"), and `README.md` (a short "Design" note: the Blueprint system, tokens in `styles.css`, the About content in `static/about.js`).

- [ ] **Step 1: Run the checklist over CDP** and save screenshots to the scratchpad. Record pass or fail for each:
  - (a) The landing page at 1440, 900 and 375 px, with no horizontal scroll.
  - (b) The hero traces once and ends on `end`. Under reduced motion it is static with `agent` amber.
  - (c) "Get in touch" (title block and footer), by click and by Enter: the location becomes the mailto, the reveal text appears, and the URL hash is unchanged.
  - (d) Tab through the landing page and a live pattern page: focus is visible on every element, `/` focuses search, and ←/→ step patterns.
  - (e) A full chat turn on Approval and a refusal on Guardrails: the trace colours are correct on navy.
  - (f) Episodic and Tool Use pages are purpose first.
  - (g) Search "zzz" shows the empty-state copy on the new sheet.
  - (h) Reload on a pattern route restores the conversation.
  - (i) No console errors.
- [ ] **Step 2:** Update the M3 plan pointer and the README. Run `pytest -q` and confirm all PASS.
- [ ] **Step 3:** Commit: "Record the Blueprint redesign in the README and M3 plan".
