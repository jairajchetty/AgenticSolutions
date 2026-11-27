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

// Split markdown into {title, body} sections on `## ` lines outside code fences.
// The `# ` page title is dropped (the page heading already shows it); text before the
// first `##` becomes an untitled intro block.
function splitSections(markdown) {
  const sections = [{ title: null, lines: [] }];
  let fence = null;
  for (const line of markdown.replace(/\r\n/g, "\n").split("\n")) {
    const marker = line.match(/^\s*(```+|~~~+)/);
    if (marker) {
      if (!fence) fence = marker[1][0];
      else if (marker[1][0] === fence) fence = null;
    }
    if (!fence && /^##\s+/.test(line)) {
      sections.push({ title: line.replace(/^##\s+/, "").trim(), lines: [] });
    } else if (!fence && /^#\s+/.test(line) && sections.length === 1) {
      continue;
    } else {
      sections[sections.length - 1].lines.push(line);
    }
  }
  return sections
    .map((s) => ({ title: s.title, body: s.lines.join("\n").trim() }))
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

// renderGuide(el, markdown, {linkFor}): the sectioned Guide, with pattern links.
export function renderGuide(el, markdown, { linkFor } = {}) {
  el.replaceChildren();
  const sections = splitSections(markdown || "");
  if (!window.marked || !window.DOMPurify) {
    // CDN unavailable: show the raw Markdown as text rather than nothing.
    const pre = document.createElement("pre");
    pre.className = "guide-fallback";
    pre.textContent = markdown || "";
    el.append(pre);
    return;
  }
  sections.forEach((section, i) => {
    const block = document.createElement("section");
    const key = section.title ? slug(section.title) : "intro";
    block.className = `guide-block guide-${key}`;
    if (section.title) {
      const h = document.createElement("h3");
      h.id = `guide-h-${i}-${key}`;
      renderInlineCode(h, section.title);
      block.setAttribute("aria-labelledby", h.id);
      block.append(h);
    }
    const body = document.createElement("div");
    body.className = "guide-text";
    body.innerHTML = markdownToSafeHtml(section.body);
    linkMarkers(body, linkFor);
    block.append(body);
    el.append(block);
  });
}
