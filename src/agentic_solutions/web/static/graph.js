// The trace graph: the pattern's topology drawn with Cytoscape + dagre (spec §6).
//
// Nodes carry one of five states. Each state has its own colour AND its own
// glyph in the label (▶ active, ✓ done, ✕ error, ⏸ paused), so the state can
// be read without colour vision (spec §6, accessibility). Edges flash when
// the runner reports a transition and keep a traversal count in their label.
// Conditional edges (a router picks one of them) are dashed and labelled "if".
//
// Colours come from the CSS tokens on :root, re-read when the colour scheme
// changes, so the graph follows the light and dark themes.

const GLYPHS = { idle: "", active: "▶", done: "✓", error: "✕", paused: "⏸" };
const STATE_WORDS = { idle: "idle", active: "running", done: "done", error: "error", paused: "paused" };
const FLASH_MS = 750;
const PULSE_MS = 650;

const live = new WeakMap();  // container -> current graph, so a rebuild tears the old one down

let registered = false;
function ensureDagre() {
  if (registered) return;
  // cytoscape-dagre registers itself when it finds the global; using it twice is harmless.
  if (typeof cytoscapeDagre === "function") cytoscape.use(cytoscapeDagre);
  registered = true;
}

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Mix two #rrggbb colours (Cytoscape has no color-mix()).
function mix(a, b, weight) {
  const parse = (hex) => {
    const h = hex.replace("#", "");
    const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  };
  try {
    const [x, y] = [parse(a), parse(b)];
    if ([...x, ...y].some(Number.isNaN)) return a;
    const out = x.map((v, i) => Math.round(v * weight + y[i] * (1 - weight)));
    return `#${out.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  } catch {
    return a;
  }
}

function palette() {
  const t = {};
  for (const name of ["panel", "panel-sunk", "ink", "muted", "rule", "signal", "signal-soft",
                      "paused", "error", "done", "font-code"]) {
    t[name] = token(`--${name}`);
  }
  return t;
}

function stylesheet(t) {
  const tint = (c) => mix(c, t.panel, 0.2);
  return [
    { selector: "node", style: {
      "shape": "round-rectangle",
      "width": "data(width)", "height": 34,
      "label": "data(display)",
      "font-family": t["font-code"], "font-size": 13, "font-weight": 600,
      "text-valign": "center", "text-halign": "center",
      "color": t.ink,
      "background-color": t.panel,
      "border-width": 1.5, "border-color": t.muted,
      "transition-property": "background-color, border-color, border-width",
      "transition-duration": "180ms",
    } },
    { selector: "node.terminal", style: {
      "shape": "ellipse", "width": 14, "height": 14, "padding": "0px",
      "label": "data(display)",
      "font-size": 11, "font-weight": 400, "color": t.muted,
      "text-valign": "bottom", "text-margin-y": 5,
      "background-color": t.muted, "border-width": 0,
    } },
    { selector: "node.terminal[kind = 'start']", style: { "text-valign": "top", "text-margin-y": -5 } },
    { selector: "node.terminal.state-done", style: { "background-color": t.done } },
    { selector: "node.state-active", style: {
      "background-color": t["signal-soft"], "border-color": t.signal, "border-width": 2.5, "color": t.ink,
    } },
    { selector: "node.state-done", style: { "background-color": tint(t.done), "border-color": t.done } },
    { selector: "node.state-error", style: { "background-color": tint(t.error), "border-color": t.error, "border-width": 2.5 } },
    { selector: "node.state-paused", style: {
      "background-color": tint(t.paused), "border-color": t.paused, "border-style": "double", "border-width": 4,
    } },
    { selector: "node.pulse", style: { "border-width": 5 } },
    { selector: "node.highlight", style: {
      "underlay-color": t.signal, "underlay-opacity": 0.22, "underlay-padding": 7, "underlay-shape": "round-rectangle",
    } },
    { selector: "edge", style: {
      "curve-style": "bezier",
      "width": 1.5, "line-color": t.muted,
      "target-arrow-shape": "triangle", "target-arrow-color": t.muted, "arrow-scale": 0.9,
      "label": "data(display)",
      "font-family": t["font-code"], "font-size": 11, "color": t.muted,
      "text-background-color": t["panel-sunk"], "text-background-opacity": 1, "text-background-padding": "2px",
      "transition-property": "line-color, target-arrow-color, width",
      "transition-duration": "220ms",
    } },
    { selector: "edge.conditional", style: { "line-style": "dashed", "line-dash-pattern": [6, 4] } },
    { selector: "edge.loop", style: { "loop-direction": "90deg", "loop-sweep": "-50deg", "control-point-step-size": 60 } },
    { selector: "edge.taken", style: { "line-color": mix(t.signal, t.muted, 0.55), "target-arrow-color": mix(t.signal, t.muted, 0.55), "color": t.ink } },
    { selector: "edge.flash", style: { "line-color": t.signal, "target-arrow-color": t.signal, "width": 4, "color": t.signal } },
  ];
}

const edgeId = (source, target) => `${source}->${target}`;

function nodeDisplay(data, state) {
  if (data.kind !== "node") return data.kind === "start" ? "start" : "end";
  const glyph = GLYPHS[state];
  return glyph ? `${glyph} ${data.label}` : data.label;
}

// Fixed width per node, wide enough for "⏸ label" in the 13px code font, so
// a state change never resizes the node.
const nodeWidth = (label) => Math.max(72, Math.ceil(label.length * 8.2 + 2 * 8.2 + 30));

function edgeDisplay(data) {
  const parts = [];
  if (data.conditional) parts.push(data.label || "if");
  else if (data.label) parts.push(data.label);
  if (data.count) parts.push(`×${data.count}`);
  return parts.join(" ");
}

// createGraph(el, topology) -> {setNodeState, flashEdge, highlight, reset}
export function createGraph(el, topology) {
  ensureDagre();
  live.get(el)?.destroy();

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const elements = [
    ...topology.nodes.map((n) => ({
      group: "nodes",
      data: { id: n.id, label: n.label, kind: n.kind, state: "idle", display: "", width: nodeWidth(n.label) },
      classes: n.kind === "node" ? "" : "terminal",
    })),
    ...topology.edges.map((e) => ({
      group: "edges",
      data: { id: edgeId(e.source, e.target), source: e.source, target: e.target,
              conditional: e.conditional, label: e.label, count: 0, display: "" },
      classes: [e.conditional ? "conditional" : "", e.source === e.target ? "loop" : ""].join(" ").trim(),
    })),
  ];
  for (const item of elements) {
    item.data.display = item.group === "nodes" ? nodeDisplay(item.data, "idle") : edgeDisplay(item.data);
  }

  const cy = cytoscape({
    container: el,
    elements,
    style: stylesheet(palette()),
    layout: { name: "dagre", rankDir: "TB", nodeSep: 60, rankSep: 56, edgeSep: 20, padding: 24 },
    maxZoom: 1.25,  // a two-node graph should not fill the panel
    userZoomingEnabled: false,
    userPanningEnabled: false,
    boxSelectionEnabled: false,
    autoungrabify: true,
    autounselectify: true,
  });

  const pulses = new Map();  // node id -> interval handle
  const flashes = new Map();  // edge id -> timeout handle

  function stopPulse(id) {
    clearInterval(pulses.get(id));
    pulses.delete(id);
    cy.getElementById(id).removeClass("pulse");
  }

  function describe() {
    const parts = cy.nodes("[kind = 'node']").map((n) => `${n.data("label")}: ${STATE_WORDS[n.data("state")]}`);
    el.setAttribute("aria-label", `Graph of the selected pattern. ${parts.join(", ")}.`);
  }

  function setNodeState(id, state) {
    const node = cy.getElementById(id);
    if (node.empty() || !(state in GLYPHS)) return;
    stopPulse(id);
    node.removeClass(Object.keys(GLYPHS).map((s) => `state-${s}`).join(" "));
    if (state !== "idle") node.addClass(`state-${state}`);
    node.data({ state, display: nodeDisplay(node.data(), state) });
    if (state === "active" && !reduceMotion.matches) {
      pulses.set(id, setInterval(() => node.toggleClass("pulse"), PULSE_MS));
    }
    describe();
  }

  function flashEdge(source, target) {
    const edge = cy.getElementById(edgeId(source, target));
    if (edge.empty()) return;
    edge.data("count", edge.data("count") + 1);
    edge.data("display", edgeDisplay(edge.data()));
    edge.addClass("taken flash");
    clearTimeout(flashes.get(edge.id()));
    flashes.set(edge.id(), setTimeout(() => edge.removeClass("flash"), FLASH_MS));
    if (target === "__end__") setNodeState("__end__", "done");
  }

  function highlight(id) {
    cy.nodes().removeClass("highlight");
    if (id) cy.getElementById(id).addClass("highlight");
  }

  function reset() {
    for (const id of [...pulses.keys()]) stopPulse(id);
    for (const handle of flashes.values()) clearTimeout(handle);
    flashes.clear();
    cy.nodes().forEach((n) => setNodeState(n.id(), "idle"));
    cy.edges().forEach((e) => {
      e.removeClass("taken flash");
      e.data("count", 0);
      e.data("display", edgeDisplay(e.data()));
    });
    highlight(null);
  }

  const refit = () => { cy.resize(); cy.fit(undefined, 24); cy.center(); };
  const observer = new ResizeObserver(refit);
  observer.observe(el);
  const scheme = matchMedia("(prefers-color-scheme: dark)");
  const restyle = () => cy.style(stylesheet(palette()));
  scheme.addEventListener("change", restyle);

  const api = {
    setNodeState, flashEdge, highlight, reset,
    destroy() {
      for (const id of [...pulses.keys()]) stopPulse(id);
      for (const handle of flashes.values()) clearTimeout(handle);
      observer.disconnect();
      scheme.removeEventListener("change", restyle);
      cy.destroy();
      live.delete(el);
    },
  };
  live.set(el, api);
  describe();
  return api;
}
