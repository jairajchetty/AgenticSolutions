# Composite Patterns Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the pattern catalog into a YAML file with `builds_on`, and redesign the main page to show only composite patterns in category bands, each listing the patterns it builds on, with a building-blocks strip for the simple ones.

**Architecture:** `catalog.yaml` is loaded and validated by `catalog.py` at import time, so a broken file stops the app from starting. `catalog.py` keeps its public functions; `/api/catalog` resolves `builds_on` on the server. `catalog.js` renders bands, cards and the strip, and its pure `matches()` also searches a card's building blocks.

**Tech Stack:** Python 3.14, FastAPI, PyYAML (`yaml.safe_load`), plain ES modules, Node's test runner (via `tests/test_js.py`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-27-composite-patterns-home-design.md`

## Global Constraints

- The Studio is desktop-only: verify at 1440 px, with no phone layouts.
- Load YAML with `yaml.safe_load` only. Add `pyyaml>=6` to `[project] dependencies` in `pyproject.toml`.
- `builds_on` entries are routes, written `category/id`.
- A pattern is composite if and only if its `builds_on` is non-empty. This is never stored as a field.
- Guide pages, `/api/catalog/{route}` and the previous/next arrows don't change.
- Copy follows the README's Writing Guidelines: plain, concise and professional. The hero lede states no count of patterns.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **`builds_on` without a category prefix** (`session` rather than `memory/session`): startup fails with a message naming the pattern and the bad entry. The test is in Task 1.
2. **The same route listed twice in one `builds_on`:** startup fails. A duplicate would draw the link twice. The test is in Task 1.
3. **A YAML type slip** (`aliases: a, b` as a string, or `builds_on: memory/session` as a string): startup fails rather than iterating characters. The test is in Task 1.
4. **A card that builds on a cross-list** (Approval → `execution/tool-use`): the link opens ReAct's page, as Tool Use does everywhere else. The test is in Task 2.
5. **A search that matches only a building block's alias** (for example "function calling"): the cards that build on Tool Use match. The test is in Task 3.

---

### Task 1: The YAML catalog and its loader

**Files:**
- Create: `src/agentic_solutions/web/catalog.yaml`
- Modify: `src/agentic_solutions/web/catalog.py` (replace the `CATALOG` literal and `_p`; keep `entry`, `target`, `status`, `neighbours`)
- Modify: `pyproject.toml` (add `pyyaml>=6`), and the package data so `catalog.yaml` ships (`[tool.setuptools.package-data] "agentic_solutions.web" = ["catalog.yaml", ...]`; check what is already listed for `static/`)
- Modify: `tests/test_catalog.py` (rename `hint` → `description`, `question` → `description`; add the loader tests)
- Modify: `tests/test_guides.py` only if it reads `hint` or `question` (today it reads `.folder` and `entry()`, so it should need no change)

**Interfaces:**
- Produces:
  - `class CatalogError(ValueError)`
  - `@dataclass(frozen=True) class CatalogPattern(id: str, category: str, name: str, description: str, aliases: tuple[str, ...], demo: str | None, crosslist_of: str | None, folder: str | None, builds_on: tuple[str, ...])`, with the properties `route -> str` (`f"{category}/{id}"`) and `composite -> bool` (`bool(builds_on)`)
  - `@dataclass(frozen=True) class Category(id: str, name: str, description: str, patterns: tuple[CatalogPattern, ...])`
  - `CATALOG_PATH: Path`, which is `catalog.yaml` next to `catalog.py`
  - `load_catalog(path: Path) -> tuple[Category, ...]`, which raises `CatalogError`
  - `CATALOG = load_catalog(CATALOG_PATH)`
  - `entry`, `target`, `status`, `neighbours`, unchanged

- [ ] **Step 1: Write `catalog.yaml`**

Write all five categories and 21 patterns in today's order, with today's names, aliases, `demo`, `folder` and `crosslist_of`. Set each `description` to today's `hint` and each category `description` to today's `question`. Add the `builds_on` lists from spec §7, written as routes:

| Pattern | `builds_on` |
|---|---|
| `cognitive/planning` | `[cognitive/react, execution/workflow]` |
| `cognitive/reflection` | `[collaboration/single-agent, execution/workflow]` |
| `cognitive/search` | `[cognitive/planning, cognitive/reflection]` |
| `collaboration/supervisor` | `[execution/routing, cognitive/react, execution/tool-use]` |
| `collaboration/swarm` | `[cognitive/react, execution/tool-use, memory/session]` |
| `collaboration/hierarchy` | `[collaboration/supervisor]` |
| `memory/episodic` | `[memory/session, execution/tool-use]` |
| `memory/semantic` | `[cognitive/react, execution/tool-use]` |
| `memory/knowledge-graph` | `[memory/semantic, execution/tool-use]` |
| `execution/event-driven` | `[execution/workflow, governance/audit]` |
| `execution/autonomous` | `[cognitive/planning, cognitive/reflection, memory/episodic, cognitive/react]` |
| `governance/guardrails` | `[memory/session, execution/routing]` |
| `governance/approval` | `[memory/session, cognitive/react, execution/tool-use, execution/routing, governance/audit]` |
| `governance/review` | `[cognitive/reflection, collaboration/single-agent]` |

Start the file with the comment block shown in spec §4.

- [ ] **Step 2: Write the failing tests in `tests/test_catalog.py`**

Rename the existing assertions: `k.question` → `k.description` and `p.hint` → `p.description`. The expected values stay the same, and `test_hints_and_aliases_match_spec` becomes `test_descriptions_and_aliases_match_spec`. Then add:

```python
SIMPLE = {"cognitive/react", "collaboration/single-agent", "memory/session", "execution/tool-use",
          "execution/routing", "execution/workflow", "governance/audit"}

def test_composite_is_derived_from_builds_on():
    routes = {p.route: p for k in c.CATALOG for p in k.patterns}
    assert {r for r, p in routes.items() if not p.composite} == SIMPLE
    assert routes["governance/approval"].builds_on == (
        "memory/session", "cognitive/react", "execution/tool-use", "execution/routing", "governance/audit")
    assert routes["collaboration/hierarchy"].builds_on == ("collaboration/supervisor",)

def write(tmp_path, text):  # helper: a catalog file from a YAML string
    p = tmp_path / "catalog.yaml"; p.write_text(text, encoding="utf-8"); return p
```

Use one minimal valid YAML text, `MINI`, as the base for the failure tests. It has one category, `gov`, with a simple pattern `gov/log` (`folder: log_agent`) and a composite `gov/ok` (`folder: ok_agent`, `builds_on: [gov/log]`). Each failure test edits `MINI` and asserts `pytest.raises(c.CatalogError, match=...)`. Each `match` must be the route or field named in the message:

- `test_loads_minimal_file`: `load_catalog(write(tmp_path, MINI))` gives one category, with `patterns[1].composite is True`.
- `test_unknown_builds_on_route_fails`: `builds_on: [log]` raises, matching `gov/ok.*log`. This is Review Focus 1.
- `test_duplicate_builds_on_fails`: `[gov/log, gov/log]` raises, matching `gov/ok.*gov/log`. This is Review Focus 2.
- `test_builds_on_and_aliases_must_be_lists`: `builds_on: gov/log` raises, matching `builds_on`, and `aliases: a, b` raises, matching `aliases`. This is Review Focus 3.
- `test_self_and_cycle_fail`: a pattern that builds on itself raises, and so does `gov/ok → gov/log → gov/ok`. Both match `cycle`.
- `test_duplicate_route_fails`: two patterns with the same id in a category.
- `test_missing_or_empty_required_field_fails`: an empty `description`, and a missing `name`.
- `test_folder_xor_crosslist`: both set, and neither set.
- `test_unknown_crosslist_target_fails`.
- `test_category_without_composite_fails`: a category whose patterns are all simple. The match is the category id.
- `test_invalid_yaml_fails_with_file_name`: a tab-indented line raises, and the match includes the file name `catalog.yaml`.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -q`
Expected: FAIL. `CatalogError` and `load_catalog` don't exist yet, and `description` isn't an attribute yet.

- [ ] **Step 4: Implement `load_catalog` in `catalog.py`**

1. Parse the file with `yaml.safe_load`, wrapping `yaml.YAMLError` in a `CatalogError` that names the path.
2. Build the dataclasses with strict type checks. Strings must be non-empty, and lists must be lists of strings.
3. Run the cross-checks: unique category ids and routes, `builds_on` and `crosslist_of` targets exist, no duplicates within one `builds_on`, exactly one of `folder` and `crosslist_of`, and at least one composite per category.
4. Detect cycles with a depth-first search over `builds_on`, and name the route where the cycle closes.

Every message starts with the file name and the pattern route or category id. Update the module docstring: the data now lives in `catalog.yaml`. Add `pyyaml>=6` to `pyproject.toml` and make sure `catalog.yaml` is included as package data.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_catalog.py tests/test_guides.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentic_solutions/web/catalog.yaml src/agentic_solutions/web/catalog.py pyproject.toml tests/test_catalog.py
git commit -m "Load the pattern catalog from catalog.yaml, with builds_on"
```

---

### Task 2: `/api/catalog` serves descriptions and resolved `builds_on`

**Files:**
- Modify: `src/agentic_solutions/web/app.py` (`_catalog_listing`, about lines 323–330)
- Modify: `tests/test_catalog_api.py` (`test_catalog_listing_shape_and_order`, plus new tests)

**Interfaces:**
- Consumes: `CATALOG`, `CatalogPattern.description`, `CatalogPattern.builds_on`, `CatalogPattern.composite`, `Category.description`, `entry()`, `target()` and `status()` from Task 1.
- Produces: the JSON shape that Task 3 relies on.
  - **Category:** `{id, name, description, patterns}`.
  - **Pattern:** `{id, name, description, aliases, status, route, target, composite, builds_on}`.
  - **`builds_on` item:** `{route, target, name, category, description, aliases, composite}`, where `category` is the category's display name.

- [ ] **Step 1: Write the failing tests**

In `test_catalog_listing_shape_and_order`, change the key sets to the ones above (`question` → `description`; `hint` → `description`, `composite`, `builds_on`). Add:

```python
def test_builds_on_is_resolved(client):
    rows = {p["route"]: p for c in client.get("/api/catalog").json()["categories"] for p in c["patterns"]}
    approval = rows["governance/approval"]
    assert approval["composite"] is True
    assert [b["route"] for b in approval["builds_on"]] == [
        "memory/session", "cognitive/react", "execution/tool-use", "execution/routing", "governance/audit"]
    session = approval["builds_on"][0]
    assert session == {"route": "memory/session", "target": "memory/session", "name": "Session",
                       "category": "Memory", "description": "Remember the current conversation",
                       "aliases": ["short-term memory", "thread", "conversation history", "checkpointer"],
                       "composite": False}
    assert rows["memory/session"]["builds_on"] == [] and rows["memory/session"]["composite"] is False

def test_builds_on_a_crosslist_targets_its_page(client):  # Review Focus 4
    rows = {p["route"]: p for c in client.get("/api/catalog").json()["categories"] for p in c["patterns"]}
    tool = next(b for b in rows["governance/approval"]["builds_on"] if b["route"] == "execution/tool-use")
    assert tool["target"] == "cognitive/react"

def test_every_route_is_reachable_from_the_main_page(client):
    rows = [p for c in client.get("/api/catalog").json()["categories"] for p in c["patterns"]]
    shown = {p["route"] for p in rows if p["composite"]}          # cards
    shown |= {p["route"] for p in rows if not p["composite"]}     # building-blocks strip
    shown |= {b["route"] for p in rows for b in p["builds_on"]}   # card links
    assert shown == {p["route"] for p in rows} and len(shown) == 21
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_catalog_api.py -q`
Expected: FAIL, with a key-set mismatch and `KeyError: 'composite'`.

- [ ] **Step 3: Update `_catalog_listing(registry) -> dict` in `app.py`**

Build the shape above. Resolve each `builds_on` route with `catalog.entry()`, set `target` to `catalog.target(b).route`, and look up the category's display name from `CATALOG`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_catalog_api.py tests/test_catalog.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentic_solutions/web/app.py tests/test_catalog_api.py
git commit -m "Serve descriptions and resolved builds_on from /api/catalog"
```

---

### Task 3: Search matches a card's building blocks

**Files:**
- Modify: `src/agentic_solutions/web/static/catalog.js` (`matches`)
- Modify: `tests/js/search.test.mjs`

**Interfaces:**
- Consumes: the Task 2 JSON (`p.description`, `c.description`, `p.builds_on[].name`, `p.builds_on[].aliases`).
- Produces: `matches(query, pattern, category) -> boolean`. Its haystack is the pattern's name, description and aliases, the category's name and description, and every `builds_on` item's name and aliases. The word rule (split, every word must match, the "s" fallback for words of 4+ characters) is unchanged.

- [ ] **Step 1: Update and extend the tests**

In `plainHits`, replace `p.hint` with `p.description` and `c.question` with `c.description`, and add `...(p.builds_on ?? []).flatMap((b) => [b.name, ...b.aliases])`. Re-check the expected arrays in the existing tests against the new haystack. For example, `hits("remember users")` may now also find composites that build on Session, so assert with `includes` where a composite can legitimately join. Keep `deepEqual` where only one pattern can match, such as `HITL` and `evaluator-optimizer`. Add:

```javascript
test("a card matches on the names of the patterns it builds on", () => {
  assert.ok(hits("tool use").includes("governance/approval"));
  assert.ok(hits("tool use").includes("execution/tool-use"));
});

test("a card matches on a building block's alias (Review Focus 5)", () => {
  const found = hits("function calling");
  assert.ok(found.includes("governance/approval") && found.includes("memory/semantic"));
  assert.ok(!found.includes("governance/review"));  // Review builds on Reflection and Single Agent only
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_js.py -q`. This regenerates the fixture from the YAML and runs Node.
Expected: FAIL on the two new tests.

- [ ] **Step 3: Extend the haystack in `matches()`**

Update the comment at the top of `catalog.js` to describe the new fields.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_js.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentic_solutions/web/static/catalog.js tests/js/search.test.mjs
git commit -m "Search a card's building blocks too"
```

---

### Task 4: The main page in layout B

**Files:**
- Modify: `src/agentic_solutions/web/static/catalog.js` (`renderHome` and its helpers: replace `categoryColumn` and `patternRow` with a band, a card and a strip; update `legend`)
- Modify: `src/agentic_solutions/web/static/styles.css` (replace `.cat-col`, `.cat-list` and `.cat-link`, about lines 362–421; keep the search, count, mark and legend rules)
- Modify: `src/agentic_solutions/web/static/index.html` (the hero lede at line 53)

**Interfaces:**
- Consumes: the Task 2 JSON and `matches()` from Task 3.
- Produces: `renderHome(el, catalog, {onOpen, searchEl}) -> {focusCategory(id)}`, with the same signature as today. `focusCategory` focuses the band heading `#cat-<id>`.

- [ ] **Step 1: Render the sheet**

The sheet `nav#cat-cards.cat-sheet` holds these parts:
- **Bands:** one `section.cat-band` per category, in order. On the left, `h2#cat-<id>.cat-title` (`tabIndex=-1`) and `p.cat-description`. On the right, `ul.cat-cards`, which holds only the composite patterns.
- **Card:** a `li.cat-card` containing a link `a.cat-card-link` to `#/<route>`, with the status mark and the name, then `p.cat-card-description`. If the pattern has `builds_on`, a `div.cat-builds` follows, with a "Builds on" label and one `a.cat-block` per item (`href="#/<item.target>"`). An item with `composite` gets the `is-composite` class (dashed border). The link's `title` is `` `${item.category}: ${item.description}` ``, and the link's accessible name is the pattern name.
- **Strip:** after the bands, `div.cat-strip` with a "Building blocks" label. It holds one `a.cat-block` per simple pattern, in file order, showing the name and a `small` category. A cross-list keeps the ↗ marker and the visually hidden "opens the … page" text from today's `patternRow`.
- **Legend:** ● live demo, ○ Guide only, a solid block "simple pattern", a dashed block "composite pattern", and ↗ "opens another pattern's page".

- [ ] **Step 2: Filter**

- A card hides when `!matches(q, p, category)`.
- A strip block hides when `!matches(q, p, category)`, using its own pattern and category.
- A band hides when none of its cards match. The strip hides when none of its blocks match.
- `first` is the first visible card, or the first visible block if no card is visible.
- The count is visible cards plus visible blocks, using the existing `countText`.
- Escape and Enter behave as they do today.

- [ ] **Step 3: Styles**

Follow `images/home-mockups.html`, option B, using the existing tokens (`--paper`, `--ink`, `--rule`, `--paper-sunk`, `--muted-ink`, `--font-display`):
- **Band grid:** `220px 1fr`, with three cards per row.
- **Card:** a white background with a `--rule` border.
- **`.cat-block`:** `--paper-sunk`, a `--rule` border, and the display font at 14px. `.cat-block.is-composite` uses `border-style: dashed`.
- **Strip:** separated by a 2px `--ink` rule.
- **Focus:** `:focus-visible` outlines match the existing `.cat-title` rules.

- [ ] **Step 4: Hero lede**

In `index.html` line 53, use: `Composite agentic patterns, each built from simpler patterns you can open on their own, with a working graph you can step through.`

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. If `tests/test_static.py` asserts on removed class names or on the old lede, update those assertions to the new names.

- [ ] **Step 6: Browser check at 1440 × 900**

Start the app with a scratch `CHECKPOINT_DB`, `ERP_DB`, `ERP_APPROVAL_SECRET` and `PORT=8741`, and drive headless Chrome over CDP (see the edge-labels session: Windows Chrome with `--user-data-dir` on a `C:\` path). Check that:
- the home page shows five bands, 14 cards and seven strip blocks;
- searching "tool use" shows Approval, Supervisor, Swarm, Episodic, Semantic and Knowledge Graph, plus the Tool Use block, and Enter opens Approval;
- Escape clears the search;
- a Guide page's category breadcrumb lands focus on its band heading;
- there are no console errors.

Save the screenshots to `images/` (git-ignored).

- [ ] **Step 7: Commit**

```bash
git add src/agentic_solutions/web/static/catalog.js src/agentic_solutions/web/static/styles.css src/agentic_solutions/web/static/index.html tests/
git commit -m "Main page: composite patterns in category bands, with a building-blocks strip"
```
