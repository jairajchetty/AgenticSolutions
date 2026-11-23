// The landing page's hero graph (Blueprint spec §4.1, §9.2): the ReAct
// topology hand-drawn as blueprint line art, on fixed coordinates. It is
// decorative (the SVG is aria-hidden; the page carries a text caption) and is
// not the live Cytoscape graph.
//
// buildHero(svg) draws the finished drawing. playHero(svg) then traces one run,
// start -> ask -> agent -> tools -> agent -> end, once per page load (~4 s):
// the topology starts as faint construction lines, each edge inks in along its
// length and the node it reaches turns amber, ending with `end` lit. Under
// prefers-reduced-motion it shows the finished drawing with `agent` amber.

const NS = "http://www.w3.org/2000/svg";
const BOX_W = 96;
const BOX_H = 36;

const NODES = [
  { id: "start", kind: "start", x: 150, y: 24 },
  { id: "ask", kind: "box", x: 150, y: 84 },
  { id: "agent", kind: "box", x: 150, y: 168 },
  { id: "tools", kind: "box", x: 330, y: 168 },
  { id: "end", kind: "end", x: 150, y: 266 },
];

// Conditional edges are dashed, as on the pattern pages' graphs.
const EDGES = [
  { id: "start-ask", d: "M150 30 V66" },
  { id: "ask-agent", d: "M150 102 V150", dashed: true },
  { id: "agent-tools", d: "M198 160 H282", dashed: true },
  { id: "tools-agent", d: "M282 176 H198" },
  { id: "agent-ask", d: "M102 168 C56 168 56 84 102 84", dashed: true },
  { id: "agent-end", d: "M150 186 V256", dashed: true },
];

const TRACE = ["start", "ask", "agent", "tools", "agent", "end"];
const EDGE_MS = 420;
const DWELL_MS = 320;

let played = false;  // once per page load, not on every return to #/

function svgEl(tag, attrs = {}, className) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (className) node.setAttribute("class", className);
  return node;
}

function drawNode(n) {
  const g = svgEl("g", { "data-node": n.id }, `hero-node hero-${n.kind}`);
  if (n.kind === "box") {
    g.append(
      svgEl("rect", { x: n.x - BOX_W / 2, y: n.y - BOX_H / 2, width: BOX_W, height: BOX_H }),
      svgEl("text", { x: n.x, y: n.y + 6, "text-anchor": "middle" }),
    );
    g.lastChild.textContent = n.id;
  } else if (n.kind === "start") {
    g.append(svgEl("circle", { cx: n.x, cy: n.y, r: 6 }, "hero-dot"));
  } else {
    // A ring round a dot: the drawing convention for a final state.
    g.append(svgEl("circle", { cx: n.x, cy: n.y, r: 10 }), svgEl("circle", { cx: n.x, cy: n.y, r: 5 }, "hero-dot"));
  }
  return g;
}

export function buildHero(svg) {
  if (svg.querySelector("[data-node]")) return;  // already drawn
  svg.setAttribute("viewBox", "40 6 352 276");
  const defs = svgEl("defs");
  const arrow = svgEl("marker", {
    id: "hero-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5,
    markerWidth: 10, markerHeight: 10, markerUnits: "userSpaceOnUse", orient: "auto",
  });
  arrow.append(svgEl("path", { d: "M1 1 L9 5 L1 9" }, "hero-arrowhead"));
  defs.append(arrow);

  const ghosts = svgEl("g", {}, "hero-ghosts");
  const inks = svgEl("g", {}, "hero-inks");
  for (const e of EDGES) {
    const cls = e.dashed ? "hero-edge is-dashed" : "hero-edge";
    ghosts.append(svgEl("path", { d: e.d, "marker-end": "url(#hero-arrow)" }, cls));
    // The ink copy is revealed through a mask whose stroke draws along the
    // edge (stroke-dashoffset), so dashed edges keep their dashes as they ink.
    const mask = svgEl("mask", { id: `hero-m-${e.id}`, maskUnits: "userSpaceOnUse", x: 0, y: 0, width: 400, height: 290 });
    mask.append(svgEl("path", { d: e.d, pathLength: 1, "data-edge": e.id }, "hero-reveal"));
    defs.append(mask);
    inks.append(svgEl("path", { d: e.d, "marker-end": "url(#hero-arrow)", mask: `url(#hero-m-${e.id})` }, cls));
  }
  const label = svgEl("text", { x: 240, y: 151, "text-anchor": "middle" }, "hero-edge-label");
  label.textContent = "tool call?";

  const nodes = svgEl("g", {}, "hero-nodes");
  nodes.append(...NODES.map(drawNode));
  svg.append(defs, ghosts, inks, label, nodes);
}

const reveal = (svg, id) => svg.querySelector(`[data-edge="${id}"]`);
const node = (svg, id) => svg.querySelector(`[data-node="${id}"]`);
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function light(svg, id) {
  for (const n of svg.querySelectorAll(".hero-node.is-active")) n.classList.remove("is-active");
  node(svg, id).classList.add("is-active", "is-seen");
}

function inkIn(path, duration) {
  return path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], {
    duration, easing: "cubic-bezier(.45,0,.25,1)", fill: "forwards",
  }).finished;
}

export async function playHero(svg) {
  if (played) return;
  played = true;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
    light(svg, "agent");
    return;
  }
  svg.dataset.phase = "trace";
  for (const p of svg.querySelectorAll(".hero-reveal")) p.style.strokeDashoffset = "1";
  const taken = new Set();
  light(svg, TRACE[0]);
  await wait(DWELL_MS);
  for (let i = 1; i < TRACE.length; i++) {
    const id = `${TRACE[i - 1]}-${TRACE[i]}`;
    taken.add(id);
    await inkIn(reveal(svg, id), EDGE_MS);
    light(svg, TRACE[i]);
    await wait(DWELL_MS);
  }
  // The run is over: finish the drawing (the branch it didn't take) and rest.
  svg.dataset.phase = "done";
  for (const e of EDGES) if (!taken.has(e.id)) inkIn(reveal(svg, e.id), 600);
}
