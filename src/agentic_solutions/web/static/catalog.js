// The catalog home (composite patterns spec §5): a search box in the hero,
// then one band per category holding cards for its composite patterns, each
// listing the patterns it builds on, and a strip of the simple patterns
// (building blocks) at the foot of the sheet.
//
// `matches()` is the search rule and is pure, so Node's test runner imports
// this module directly (tests/js/search.test.mjs): nothing here touches the
// DOM until renderHome() is called.
//
// Search is word-wise. The query is split on whitespace and punctuation other
// than "-", and a pattern matches when EVERY word is a case-insensitive
// substring of its text: name, description, aliases, category name and
// category description, plus the names and aliases of the patterns it builds
// on, so "tool use" finds Approval. A word of 4+ characters ending in "s" also
// matches without it, so "remember users" finds Episodic: "remember" from
// Memory's description, "user" from its own. Shorter words get no fallback,
// or "is" would match every "i".

export const queryWords = (query) =>
  String(query ?? "").toLowerCase().split(/[^\p{L}\p{N}-]+/u).filter(Boolean);

export function matches(query, pattern, category) {
  const blocks = (pattern.builds_on ?? []).flatMap((b) => [b.name, ...(b.aliases ?? [])]);
  const haystack = [pattern.name, pattern.description, ...(pattern.aliases ?? []),
    category.name, category.description, ...blocks].join("\n").toLowerCase();
  return queryWords(query).every((w) =>
    haystack.includes(w) || (w.length >= 4 && w.endsWith("s") && haystack.includes(w.slice(0, -1))));
}

const STATUS_LABEL = { live: "Live demo", guide: "Guide" };
const STATUS_MARK = { live: "●", guide: "○" };

const countText = (n) => (n === 1 ? "1 pattern matches" : `${n} patterns match`);
const emptyText = (q) => `No pattern matches "${q}". Try a broader word, or browse the categories.`;

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// The status mark: a shape for the eye, a word for everyone (Catalog spec §4.4).
function statusMark(status) {
  const mark = make("span", `mark mark-${status}`);
  const glyph = make("span", "mark-glyph", STATUS_MARK[status]);
  glyph.setAttribute("aria-hidden", "true");
  mark.title = STATUS_LABEL[status];
  mark.append(glyph, make("span", "visually-hidden", `${STATUS_LABEL[status]}: `));
  return mark;
}

// Where the main page's links go: always the pattern's own route. A cross-list
// (Tool Use) has its own page, which shows its target's Guide under its own
// category, breadcrumb and arrows, so linking the route keeps that page reachable.
export const cardHref = (p) => `#/${p.route}`;
export const blockHref = (b) => `#/${b.route}`;

// A link to a building block. `b` is either a resolved `builds_on` item or a
// simple pattern from the listing (both carry name, target and route).
function blockLink(b, { categoryName, names }) {
  const a = make("a", `cat-block${b.composite ? " is-composite" : ""}`);
  a.href = blockHref(b);
  a.title = `${categoryName}: ${b.description}`;
  a.append(make("span", "cat-block-name", b.name));
  if (b.target !== b.route) {
    // A cross-list (Tool Use) opens another pattern's page: say whose.
    const xref = make("span", "cat-xref", ` ↗ ${names.get(b.target)}`);
    xref.setAttribute("aria-hidden", "true");
    a.append(xref, make("span", "visually-hidden", ` (opens the ${names.get(b.target)} page)`));
  }
  return a;
}

function patternCard(p, names) {
  const li = make("li", "cat-card");
  const a = make("a", "cat-card-link");
  a.href = cardHref(p);
  a.append(statusMark(p.status), make("span", "cat-label", p.name));
  li.append(a, make("p", "cat-card-description", p.description));
  if (p.builds_on.length) {
    const row = make("div", "cat-builds");
    row.append(make("span", "cat-builds-label", "Builds on"));
    for (const b of p.builds_on) row.append(blockLink(b, { categoryName: b.category, names }));
    li.append(row);
  }
  return li;
}

function categoryBand(c, names) {
  const band = make("section", "cat-band");
  const h = make("h2", "cat-title", c.name);
  h.id = `cat-${c.id}`;
  h.tabIndex = -1;  // the breadcrumb's category link lands here
  band.setAttribute("aria-labelledby", h.id);
  band.dataset.category = c.id;
  const head = make("div", "cat-band-head");
  head.append(h, make("p", "cat-description", c.description));
  const list = make("ul", "cat-cards");
  list.setAttribute("aria-labelledby", h.id);
  const rows = c.patterns.filter((p) => p.composite).map((p) => {
    const li = patternCard(p, names);
    list.append(li);
    return { li, p };
  });
  band.append(head, list);
  return { band, rows, category: c };
}

function blockStrip(catalog, names) {
  const strip = make("section", "cat-strip");
  const h = make("h2", "cat-strip-title", "Building blocks");
  h.id = "cat-building-blocks";
  strip.setAttribute("aria-labelledby", h.id);
  const list = make("ul", "cat-strip-list");
  const rows = [];
  for (const c of catalog.categories) {
    for (const p of c.patterns.filter((x) => !x.composite)) {
      const li = make("li");
      const a = blockLink(p, { categoryName: c.name, names });
      a.append(make("small", "cat-block-category", c.name));
      li.append(a);
      list.append(li);
      rows.push({ li, p, category: c });
    }
  }
  strip.append(h, list);
  return { strip, rows };
}

function legend() {
  const ul = make("ul", "cat-legend");
  ul.setAttribute("aria-label", "Legend");
  for (const [glyph, cls, text] of [
    ["●", "mark mark-live", "live demo"],
    ["○", "mark mark-guide", "guide only (demo coming)"],
    ["", "lg-block", "simple pattern"],
    ["", "lg-block is-composite", "composite pattern"],
    ["↗", "mark cat-xref", "opens another pattern's page"],
  ]) {
    const li = make("li");
    const g = make("span", cls, glyph);
    g.setAttribute("aria-hidden", "true");
    li.append(g, text);
    ul.append(li);
  }
  return ul;
}

const isEditable = (node) =>
  node instanceof Element && (node.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])") !== null);

let activeInput = null;  // the search box of the home page currently rendered
let slashBound = false;

// "/" focuses the search box from anywhere on the home page, unless the person
// is typing in another field. One listener for the page's lifetime.
function bindSlash() {
  if (slashBound) return;
  slashBound = true;
  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
    const input = activeInput;
    if (!input || !input.isConnected || input.closest("[hidden]") || isEditable(e.target)) return;
    e.preventDefault();
    input.focus();
    input.select();
  });
}

// renderHome(el, catalog, {onOpen, searchEl}): the search box (with its match
// count) in `searchEl`, or at the top of `el` without one; the catalog sheet
// and the legend in `el`. `onOpen(route)` is called when Enter picks the first
// visible match; the rows themselves are plain links.
export function renderHome(el, catalog, { onOpen, searchEl = null } = {}) {
  const names = new Map(catalog.categories.flatMap((c) => c.patterns.map((p) => [p.route, p.name])));

  const form = make("form", "cat-search");
  form.setAttribute("role", "search");
  const label = make("label", "cat-search-label", "What are you trying to do?");
  label.htmlFor = "cat-search-input";
  const field = make("div", "cat-search-field");
  const input = make("input", "cat-search-input");
  Object.assign(input, { id: "cat-search-input", type: "search", autocomplete: "off", spellcheck: false });
  input.placeholder = 'e.g. "remember users", "human sign-off"';
  input.setAttribute("aria-describedby", "cat-search-hint");
  input.setAttribute("aria-controls", "cat-cards");
  const key = make("kbd", "cat-search-key", "/");
  key.setAttribute("aria-hidden", "true");
  field.append(input, key);
  const hint = make("p", "cat-search-hint", "Press Enter to open the first match, Esc to clear.");
  hint.id = "cat-search-hint";
  form.append(label, field, hint);

  const status = make("p", "cat-count");
  status.setAttribute("aria-live", "polite");
  const empty = make("p", "cat-empty");
  empty.hidden = true;

  const nav = make("nav", "cat-sheet");
  nav.id = "cat-cards";
  nav.setAttribute("aria-label", "Patterns by category");
  const bands = catalog.categories.map((c) => categoryBand(c, names));
  const strip = blockStrip(catalog, names);
  nav.append(...bands.map((x) => x.band), strip.strip);

  let first = null;
  function filter() {
    const q = input.value.trim();
    let count = 0;
    let firstCard = null;
    let firstBlock = null;
    for (const band of bands) {
      let shown = 0;
      for (const { li, p } of band.rows) {
        const hit = matches(q, p, band.category);
        li.hidden = !hit;
        if (hit) {
          shown++;
          firstCard ??= p.route;
        }
      }
      count += shown;
      band.band.hidden = shown === 0;
    }
    let blocks = 0;
    for (const { li, p, category } of strip.rows) {
      const hit = matches(q, p, category);
      li.hidden = !hit;
      if (hit) {
        blocks++;
        firstBlock ??= p.route;
      }
    }
    strip.strip.hidden = blocks === 0;
    count += blocks;
    first = firstCard ?? firstBlock;
    status.textContent = q ? countText(count) : "";
    empty.hidden = !q || count > 0;
    empty.textContent = empty.hidden ? "" : emptyText(q);
  }

  input.addEventListener("input", filter);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && input.value) {
      e.preventDefault();
      input.value = "";
      filter();
    }
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    // A blank box shows every pattern; Enter there would just open the first.
    if (input.value.trim() && first) onOpen?.(first);
  });

  if (searchEl) {
    searchEl.replaceChildren(form, status, empty);
    el.replaceChildren(nav, legend());
  } else {
    el.replaceChildren(form, status, empty, nav, legend());
  }
  activeInput = input;
  bindSlash();
  filter();
  return { focusCategory: (id) => el.querySelector(`#cat-${CSS.escape(id)}`)?.focus() };
}
