// The trace graph: the pattern's topology drawn with Cytoscape + dagre (spec §6).
//
// Nodes carry one of five states. Each state has its own colour AND its own
// glyph in the label (▶ active, ✓ done, ✕ error, ⏸ paused), so the state can
// be read without colour vision (spec §6, accessibility). Edges flash when
// the runner reports a transition and keep a traversal count in their label.
// Conditional edges (a router picks one of them) are dashed and carry the
// pattern's short label for the condition ("stop", "> R5,000"), or "if" when
// the pattern gives none. Hovering a labelled edge shows the full rule.
//
// A pattern may fix its layout (every node has a position, edges may bend);
// otherwise dagre lays the graph out top to bottom.
//
// Static mode (Catalog spec §4.3) draws a Guide-only pattern's skeleton: the
// same layout and idle styling, conditional edges still dashed and labelled,
// but nothing ever runs on it, so there are no counters or pulses and every
// method except destroy() is a no-op.
//
// Colours come from the Blueprint tokens on :root (one theme, read once per graph).

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
  for (const name of ["navy", "line", "paper", "ink", "amber", "signal-red", "muted-ink", "font-display"]) {
    t[name] = token(`--${name}`);
  }
  return t;
}

// Blueprint line art on the navy frame (Blueprint spec §4.2, §9.3): `--line`
// strokes and labels, the active node amber, an error node `--signal-red`, a
// paused node double-ruled. Fills are the navy itself, lightly tinted by state.
// `still` (reduced motion) drops the colour transitions; states still change.
function stylesheet(t, { still = false } = {}) {
  const onNavy = (c, w) => mix(c, t.navy, w);
  const ease = (ms) => (still ? "0ms" : ms);
  return [
    { selector: "node", style: {
      "shape": "rectangle",
      "width": "data(width)", "height": 34,
      "label": "data(display)",
      "font-family": t["font-display"], "font-size": 17, "font-weight": 600,
      "text-valign": "center", "text-halign": "center",
      "color": t.paper,
      "background-color": t.navy,
      "border-width": 1.5, "border-color": t.line,
      "transition-property": "background-color, border-color, border-width",
      "transition-duration": ease("180ms"),
    } },
    { selector: "node.terminal", style: {
      "shape": "ellipse", "width": 12, "height": 12, "padding": "0px",
      "label": "data(display)",
      "font-size": 15, "font-weight": 500, "color": t.line,
      "text-valign": "bottom", "text-margin-y": 5,
      "background-color": t.line, "border-width": 0,
    } },
    { selector: "node.terminal[kind = 'start']", style: { "text-valign": "top", "text-margin-y": -5 } },
    { selector: "node.terminal.state-done", style: {
      "background-color": t.paper, "border-width": 2, "border-color": t.line, "color": t.paper,
    } },
    { selector: "node.state-active", style: {
      "background-color": onNavy(t.amber, 0.16), "border-color": t.amber, "border-width": 2.5, "color": t.amber,
    } },
    { selector: "node.state-done", style: { "background-color": onNavy(t.line, 0.16), "border-color": t.line } },
    { selector: "node.state-error", style: {
      "background-color": onNavy(t["signal-red"], 0.4), "border-color": t["signal-red"], "border-width": 2.5,
    } },
    { selector: "node.state-paused", style: {
      "background-color": onNavy(t.line, 0.08), "border-color": t.line, "border-style": "double", "border-width": 5,
    } },
    { selector: "node.pulse", style: { "border-width": 5 } },
    { selector: "node.highlight", style: {
      "underlay-color": t.line, "underlay-opacity": 0.28, "underlay-padding": 7, "underlay-shape": "round-rectangle",
    } },
    { selector: "edge", style: {
      "curve-style": "bezier",
      "width": 1.5, "line-color": onNavy(t.line, 0.75),
      "target-arrow-shape": "triangle", "target-arrow-color": onNavy(t.line, 0.75), "arrow-scale": 0.9,
      "label": "data(display)",
      "font-family": t["font-display"], "font-size": 15, "font-weight": 500, "color": t.line,
      "text-background-color": t.navy, "text-background-opacity": 1, "text-background-padding": "3px",
      "transition-property": "line-color, target-arrow-color, width",
      "transition-duration": ease("220ms"),
    } },
    { selector: "edge.conditional", style: { "line-style": "dashed", "line-dash-pattern": [6, 4] } },
    { selector: "edge.loop", style: { "loop-direction": "90deg", "loop-sweep": "-50deg", "control-point-step-size": 60 } },
    { selector: "edge.loop-left", style: { "loop-direction": "-90deg" } },
    { selector: "edge.bent", style: {
      "curve-style": "unbundled-bezier", "control-point-distances": "data(bend)", "control-point-weights": 0.5,
    } },
    { selector: "edge.hover", style: { "line-color": t.paper, "target-arrow-color": t.paper, "width": 2.5, "color": t.paper } },
    { selector: "edge.taken", style: { "line-color": t.line, "target-arrow-color": t.line, "width": 2, "color": t.paper } },
    { selector: "edge.flash", style: { "line-color": t.amber, "target-arrow-color": t.amber, "width": 3.5, "color": t.amber } },
  ];
}

const edgeId = (source, target) => `${source}->${target}`;

function nodeDisplay(data, state) {
  if (data.kind !== "node") return data.kind === "start" ? "start" : "end";
  const glyph = GLYPHS[state];
  return glyph ? `${glyph} ${data.label}` : data.label;
}

// Fixed width per node, wide enough for "⏸ label" in the 17px condensed
// display font, so a state change never resizes the node.
const nodeWidth = (label) => Math.max(72, Math.ceil(label.length * 8.2 + 2 * 8.2 + 30));

export function edgeDisplay(data) {
  const parts = [];
  if (data.conditional) parts.push(data.label || "if");
  else if (data.label) parts.push(data.label);
  if (data.count) parts.push(`×${data.count}`);
  return parts.join(" ");
}

// The hover text for an edge: its short label and full rule, or "" without a rule.
export function tooltipText(data) {
  return data.detail ? `${data.label}: ${data.detail}` : "";
}

const isFixed = (topology) => topology.nodes.length > 0 && topology.nodes.every((n) => n.position);

export function layoutFor(topology) {
  return isFixed(topology)
    ? { name: "preset", padding: 24 }
    : { name: "dagre", rankDir: "TB", nodeSep: 60, rankSep: 56, edgeSep: 20, padding: 24 };
}

// Cytoscape elements for a topology, every node idle and every count at zero.
export function buildElements(topology) {
  const fixed = isFixed(topology);
  const elements = [
    ...topology.nodes.map((n) => ({
      group: "nodes",
      data: { id: n.id, label: n.label, kind: n.kind, state: "idle", display: "", width: nodeWidth(n.label) },
      classes: n.kind === "node" ? "" : "terminal",
      ...(fixed ? { position: { x: n.position.x, y: n.position.y } } : {}),
    })),
    ...topology.edges.map((e) => {
      const loop = e.source === e.target;
      const bent = fixed && !loop && e.bend != null && e.bend !== 0;
      return {
        group: "edges",
        data: { id: edgeId(e.source, e.target), source: e.source, target: e.target,
                conditional: e.conditional, label: e.label, detail: e.detail ?? null,
                count: 0, display: "", ...(bent ? { bend: e.bend } : {}) },
        classes: [e.conditional ? "conditional" : "", loop ? "loop" : "", loop && fixed ? "loop-left" : "",
                  bent ? "bent" : ""].filter(Boolean).join(" "),
      };
    }),
  ];
  for (const item of elements) {
    item.data.display = item.group === "nodes" ? nodeDisplay(item.data, "idle") : edgeDisplay(item.data);
  }
  return elements;
}

// Static mode's accessible text: the graph's nodes and edges, in words.
function describeStatic(topology) {
  const name = (id) => {
    const n = topology.nodes.find((x) => x.id === id);
    return !n ? id : n.kind === "node" ? n.label : n.kind;  // "start" / "end" for the terminals
  };
  const nodes = topology.nodes.filter((n) => n.kind === "node").map((n) => n.label);
  const edges = topology.edges.map((e) =>
    `${name(e.source)} to ${name(e.target)}${e.conditional ? ` (conditional${e.label ? `: ${e.detail || e.label}` : ""})` : ""}`);
  return `Diagram of the pattern's graph. Nodes: ${nodes.join(", ")}. Edges: ${edges.join("; ")}.`;
}

const noop = () => {};

// createGraph(el, topology, {static}) -> {setNodeState, flashEdge, highlight, reset, destroy}
export function createGraph(el, topology, { static: isStatic = false } = {}) {
  ensureDagre();
  live.get(el)?.destroy();

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const cy = cytoscape({
    container: el,
    elements: buildElements(topology),
    style: stylesheet(palette(), { still: reduceMotion.matches }),
    layout: layoutFor(topology),
    maxZoom: 1.5,  // a two-node graph should not fill the drawing
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

  const rules = topology.edges.filter((e) => e.detail).map((e) => `${e.label}: ${e.detail}`);
  const conditions = rules.length ? ` Conditions: ${rules.join(" ")}` : "";

  function describe() {
    const parts = cy.nodes("[kind = 'node']").map((n) => `${n.data("label")}: ${STATE_WORDS[n.data("state")]}`);
    el.setAttribute("aria-label", `Graph of the selected pattern. ${parts.join(", ")}.${conditions}`);
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

  // The full rule on hover. The tip lives inside the graph's container, which
  // is positioned, so the edge's rendered midpoint is also the tip's offset.
  const tip = document.createElement("div");
  tip.className = "graph-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  el.appendChild(tip);
  cy.on("mouseover", "edge", (evt) => {
    const text = tooltipText(evt.target.data());
    if (!text) return;
    evt.target.addClass("hover");
    const p = evt.target.renderedMidpoint();
    tip.textContent = text;
    tip.hidden = false;
    const x = Math.min(Math.max(p.x + 12, 8), el.clientWidth - tip.offsetWidth - 8);
    const y = p.y - tip.offsetHeight - 12 < 8 ? p.y + 16 : p.y - tip.offsetHeight - 12;
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${y}px`;
  });
  // Leaving the canvas fast skips Cytoscape's mouseout, so the container hides it too.
  const hideTip = () => { cy.edges(".hover").removeClass("hover"); tip.hidden = true; };
  cy.on("mouseout", "edge", hideTip);
  el.addEventListener("mouseleave", hideTip);
  // A fixed layout is drawn at close to full size, so its panel is taller (styles.css).
  el.classList.toggle("is-fixed", isFixed(topology));

  const refit = () => { cy.resize(); cy.fit(undefined, 24); cy.center(); };
  const observer = new ResizeObserver(refit);
  observer.observe(el);

  const methods = isStatic
    ? { setNodeState: noop, flashEdge: noop, highlight: noop, reset: noop }
    : { setNodeState, flashEdge, highlight, reset };
  const api = {
    ...methods,
    destroy() {
      for (const id of [...pulses.keys()]) stopPulse(id);
      for (const handle of flashes.values()) clearTimeout(handle);
      observer.disconnect();
      el.removeEventListener("mouseleave", hideTip);
      el.classList.remove("is-fixed");
      tip.remove();
      cy.destroy();
      live.delete(el);
    },
  };
  live.set(el, api);
  if (isStatic) el.setAttribute("aria-label", describeStatic(topology));
  else describe();
  return api;
}
