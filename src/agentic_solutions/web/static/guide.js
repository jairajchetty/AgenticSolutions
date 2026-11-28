// Pattern Guide rendering (spec §7).
//
// Each agent's explanation.md has fixed `##` sections. They are split into
// labelled blocks; each block's body goes marked.parse -> DOMPurify.sanitize
// -> innerHTML. That is the ONLY innerHTML in the app: everything else,
// including user input and model output, is built with textContent.
//
// `[[category/pattern]]` markers (Catalog spec §8) become links to that
// pattern's page. They are found AFTER sanitising, by walking the text nodes
// (outside <code>, <pre> and existing links), and the <a> is built with
// createElement, so a marker can never smuggle markup in.

// Append `text` to `el`, turning `backtick` spans into <code> elements.
// Used for headings and pattern titles, e.g. "Human-in-the-loop: `interrupt()`".
export function renderInlineCode(el, text) {
  String(text).split(/(`[^`]+`)/).forEach((part) => {
    if (!part) return;
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      const code = document.createElement("code");
      code.textContent = part.slice(1, -1);
      el.append(code);
    } else {
      el.append(document.createTextNode(part));
    }
  });
  return el;
}

const slug = (text) =>
  text.toLowerCase().replace(/[`'’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// The one line scanner. Cuts markdown into chunks at `## ` lines outside code
// fences; each chunk is {title, heading, lines} (heading is the raw `## ` line,
// null for the preamble before the first `##`). `# ` lines in the preamble are
// the page title and are dropped.
function chunkMarkdown(markdown, level = 2) {
  const cut = new RegExp(`^#{${level}}\\s+`);
  const chunks = [{ title: null, heading: null, lines: [] }];
  let fence = null;
  for (const line of markdown.replace(/\r\n/g, "\n").split("\n")) {
    const marker = line.match(/^\s*(```+|~~~+)/);
    if (marker) {
      if (!fence) fence = marker[1][0];
      else if (marker[1][0] === fence) fence = null;
    }
    if (!fence && cut.test(line)) {
      chunks.push({ title: line.replace(cut, "").trim(), heading: line, lines: [] });
    } else if (!fence && /^#\s+/.test(line) && chunks.length === 1) {
      continue;
    } else {
      chunks[chunks.length - 1].lines.push(line);
    }
  }
  return chunks;
}

// Split markdown into {title, body} sections. The `# ` page title is dropped (the
// page heading already shows it); text before the first `##` becomes an untitled
// intro block.
function splitSections(markdown) {
  return chunkMarkdown(markdown)
    .map((c) => ({ title: c.title, body: c.lines.join("\n").trim() }))
    .filter((s) => s.title || s.body);
}

function markdownToSafeHtml(markdown) {
  return window.DOMPurify.sanitize(window.marked.parse(markdown));
}

const MARKER = /\[\[([a-z0-9-]+\/[a-z0-9-]+)\]\]/g;

// Replace the markers under `root` with links; `linkFor(route)` gives the link
// text (the pattern's name), or null to leave that marker as plain text.
function linkMarkers(root, linkFor) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => (node.parentElement.closest("code, pre, a") || !node.data.includes("[[")
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const found = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) found.push(node);
  for (const node of found) {
    const parts = [];
    let last = 0;
    for (const m of node.data.matchAll(MARKER)) {
      const name = linkFor ? linkFor(m[1]) : null;
      if (!name) continue;  // unknown target: the marker stays as text
      const a = document.createElement("a");
      a.href = `#/${m[1]}`;
      a.className = "pattern-link";
      a.textContent = name;
      parts.push(node.data.slice(last, m.index), a);
      last = m.index + m[0].length;
    }
    if (!parts.length) continue;
    parts.push(node.data.slice(last));
    node.replaceWith(...parts.filter((x) => x !== ""));
  }
}

const PURPOSE_HEADINGS = ["What it is", "When to use it"];

// splitPurpose(markdown): pull the "What it is" and "When to use it" sections
// (matched by heading text, kept with their `##` headings, in that order) out
// of the Guide. `rest` is everything else in original order, minus the leading
// `# ` title (the purpose sheet shows the title itself). If either purpose
// heading is missing, purpose is "" and rest is the whole Guide minus its title.
// Pure: no DOM, so it runs under node.
export function splitPurpose(markdown) {
  const chunks = chunkMarkdown(String(markdown || ""));
  const text = (cs) => cs.flatMap((c) => (c.heading === null ? c.lines : [c.heading, ...c.lines])).join("\n");
  const picked = PURPOSE_HEADINGS.map((t) => chunks.find((c) => c.title === t));
  if (picked.some((c) => !c)) return { purpose: "", rest: text(chunks) };
  return {
    purpose: picked.map((c) => text([c]).trim()).join("\n\n"),
    rest: text(chunks.filter((c) => !picked.includes(c))),
  };
}

const STUDIO_TITLE = "How this Studio implements it";
const STUDIO_OPEN_KEY = "studio.guide.impl.open";

// splitStudio(markdownRest): pull the `## How this Studio implements it`
// section (exact title, fence-aware) out of the Guide. `body` is everything
// else in original order; `studio` is {title, subsections: [{title, markdown}]}
// (one per `###`), or null when the Guide has no such section. Pure: no DOM.
export function splitStudio(markdown) {
  const chunks = chunkMarkdown(String(markdown || ""));
  const found = chunks.find((c) => c.title === STUDIO_TITLE);
  const text = (cs) => cs.flatMap((c) => (c.heading === null ? c.lines : [c.heading, ...c.lines])).join("\n");
  if (!found) return { body: text(chunks), studio: null };
  const subsections = chunkMarkdown(found.lines.join("\n"), 3)
    .filter((c) => c.title)
    .map((c) => ({ title: c.title, markdown: c.lines.join("\n").trim() }));
  return { body: text(chunks.filter((c) => c !== found)), studio: { title: STUDIO_TITLE, subsections } };
}

function storedOpen() {
  try { return sessionStorage.getItem(STUDIO_OPEN_KEY) === "1"; } catch { return false; }
}

// The Studio section: a closed-by-default <details class="guide-impl sheet">.
// Built with DOM APIs; each subsection goes through buildBlock (sanitised).
function buildStudioDisclosure(studio, linkFor) {
  const details = document.createElement("details");
  details.className = "guide-impl sheet";
  details.open = storedOpen();
  const summary = document.createElement("summary");
  summary.textContent = studio.title;
  details.append(summary);
  studio.subsections.forEach((sub, i) => {
    const key = slug(sub.title);
    details.append(buildBlock(`guide-block guide-impl-${key}`, `guide-impl-h-${i}-${key}`,
      sub.title, sub.markdown, linkFor));
  });
  details.addEventListener("toggle", () => {
    try { sessionStorage.setItem(STUDIO_OPEN_KEY, details.open ? "1" : "0"); } catch { /* no storage */ }
  });
  return details;
}

// One labelled block: <section class> with a heading (h3 by default) and the
// sanitised, linked body. The only innerHTML assignment in the app lives here.
function buildBlock(className, id, title, bodyMarkdown, linkFor, { level = 3 } = {}) {
  const block = document.createElement("section");
  block.className = className;
  if (title) {
    const h = document.createElement(`h${level}`);
    h.id = id;
    renderInlineCode(h, title);
    block.setAttribute("aria-labelledby", h.id);
    block.append(h);
  }
  const body = document.createElement("div");
  body.className = "guide-text";
  body.innerHTML = markdownToSafeHtml(bodyMarkdown);
  linkMarkers(body, linkFor);
  block.append(body);
  return block;
}

// CDN unavailable: show the raw Markdown as text rather than nothing.
function renderFallback(el, markdown) {
  const pre = document.createElement("pre");
  pre.className = "guide-fallback";
  pre.textContent = markdown || "";
  el.append(pre);
}

// renderGuide(el, markdown, {linkFor}): the sectioned Guide, with pattern links.
export function renderGuide(el, markdown, { linkFor } = {}) {
  el.replaceChildren();
  if (!window.marked || !window.DOMPurify) return renderFallback(el, markdown);
  const { body, studio } = splitStudio(markdown || "");
  const sections = splitSections(body);
  sections.forEach((section, i) => {
    const key = section.title ? slug(section.title) : "intro";
    el.append(buildBlock(`guide-block guide-${key}`, `guide-h-${i}-${key}`,
      section.title, section.body, linkFor));
  });
  if (studio) el.append(buildStudioDisclosure(studio, linkFor));
}

// The owner's use-case text (catalog.yaml `use_case`) as paragraphs: split on
// blank lines, each paragraph's lines joined with a space. Shown as plain text.
export function useCaseParagraphs(text) {
  return String(text ?? "")
    .split(/\n\s*\n/)
    .map((p) => p.split("\n").map((line) => line.trim()).filter(Boolean).join(" "))
    .filter(Boolean);
}
