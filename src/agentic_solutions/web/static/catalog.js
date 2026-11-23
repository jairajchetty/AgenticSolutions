// The catalog home (Catalog spec §4.2, Blueprint spec §4.1): a search box in
// the hero and the five categories as columns on one paper sheet.
//
// `matches()` is the search rule and is pure, so Node's test runner imports
// this module directly (tests/js/search.test.mjs): nothing here touches the
// DOM until renderHome() is called.
//
// Search is word-wise. The query is split on whitespace and punctuation other
// than "-", and a pattern matches when EVERY word is a case-insensitive
// substring of its text: name, hint, aliases, category name and category
// question. A word of 4+ characters ending in "s" also matches without it, so
// "remember users" finds Episodic: "remember" from Memory's question, "user"
// from its hint. Shorter words get no fallback, or "is" would match every "i".

export const queryWords = (query) =>
  String(query ?? "").toLowerCase().split(/[^\p{L}\p{N}-]+/u).filter(Boolean);

export function matches(query, pattern, category) {
  const haystack = [pattern.name, pattern.hint, ...(pattern.aliases ?? []), category.name, category.question]
    .join("\n").toLowerCase();
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

function patternRow(p, names) {
  const li = make("li", "cat-row");
  const a = make("a", "cat-link");
  a.href = `#/${p.route}`;
  const title = make("span", "cat-name");
  title.append(statusMark(p.status), make("span", "cat-label", p.name));
  if (p.target !== p.route) {
    // A cross-list (Tool Use) opens another pattern's page: say whose.
    const xref = make("span", "cat-xref");
    xref.append(make("span", null, `↗ ${names.get(p.target)}`));
    xref.firstChild.setAttribute("aria-hidden", "true");
    xref.append(make("span", "visually-hidden", ` (opens the ${names.get(p.target)} page)`));
    title.append(xref);
  }
  a.append(title, make("span", "cat-hint", p.hint));
  li.append(a);
  return li;
}

function categoryColumn(c, names) {
  const card = make("section", "cat-col");
  const h = make("h2", "cat-title", c.name);
  h.id = `cat-${c.id}`;
  h.tabIndex = -1;  // the breadcrumb's category link lands here
  card.setAttribute("aria-labelledby", h.id);
  card.dataset.category = c.id;
  const list = make("ul", "cat-list");
  list.setAttribute("aria-labelledby", h.id);
  const rows = c.patterns.map((p) => {
    const li = patternRow(p, names);
    list.append(li);
    return { li, p };
  });
  const none = make("p", "cat-none", "no matches");
  none.hidden = true;
  card.append(h, make("p", "cat-question", c.question), list, none);
  return { card, list, none, rows, category: c };
}

function legend() {
  const ul = make("ul", "cat-legend");
  ul.setAttribute("aria-label", "Legend");
  for (const [glyph, cls, text] of [
    ["●", "mark-live", "live demo"],
    ["○", "mark-guide", "guide only (demo coming)"],
    ["↗", "cat-xref", "opens another pattern's page"],
  ]) {
    const li = make("li");
    const g = make("span", `mark ${cls}`, glyph);
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
  const cards = catalog.categories.map((c) => categoryColumn(c, names));
  nav.append(...cards.map((x) => x.card));

  let first = null;
  function filter() {
    const q = input.value.trim();
    let count = 0;
    first = null;
    for (const card of cards) {
      let shown = 0;
      for (const { li, p } of card.rows) {
        const hit = matches(q, p, card.category);
        li.hidden = !hit;
        if (hit) {
          shown++;
          first ??= p.route;
        }
      }
      count += shown;
      card.list.hidden = shown === 0;
      card.none.hidden = shown !== 0;
      card.card.classList.toggle("is-empty", shown === 0);
    }
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
