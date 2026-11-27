// Unit tests for the graph's pure helpers: edge labels, tooltips and the fixed layout.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildElements, edgeDisplay, layoutFor, tooltipText } from "../../src/agentic_solutions/web/static/graph.js";

const node = (id, kind = "node", position = null) => ({ id, label: id, kind, position });
const edge = (source, target, extra = {}) =>
  ({ source, target, conditional: true, label: null, detail: null, bend: null, ...extra });

const AUTO = {
  nodes: [node("__start__", "start"), node("ask"), node("__end__", "end")],
  edges: [edge("ask", "__end__", { label: "stop", detail: "You typed stop." }), edge("ask", "ask")],
};
const FIXED = {
  nodes: [node("__start__", "start", { x: 0, y: 0 }), node("ask", "node", { x: 0, y: 100 }),
          node("__end__", "end", { x: 200, y: 100 })],
  edges: [edge("ask", "__end__", { bend: 30 }), edge("ask", "ask")],
};

test("layoutFor uses dagre unless every node has a position", () => {
  assert.equal(layoutFor(AUTO).name, "dagre");
  assert.equal(layoutFor(FIXED).name, "preset");
  const partial = { ...FIXED, nodes: [...FIXED.nodes.slice(0, 2), node("__end__", "end")] };
  assert.equal(layoutFor(partial).name, "dagre");
});

test("buildElements places nodes only in a fixed layout", () => {
  const fixed = buildElements(FIXED).find((x) => x.data.id === "__end__");
  assert.deepEqual(fixed.position, { x: 200, y: 100 });
  const auto = buildElements(AUTO).find((x) => x.data.id === "__end__");
  assert.equal(auto.position, undefined);
});

test("buildElements bends edges that have a bend", () => {
  const els = buildElements(FIXED);
  const bent = els.find((x) => x.data.id === "ask->__end__");
  assert.equal(bent.data.bend, 30);
  assert.match(bent.classes, /\bbent\b/);
});

test("a loop in a fixed layout turns left, away from the end node", () => {
  assert.match(buildElements(FIXED).find((x) => x.data.id === "ask->ask").classes, /\bloop-left\b/);
  assert.doesNotMatch(buildElements(AUTO).find((x) => x.data.id === "ask->ask").classes, /loop-left/);
});

test("buildElements shows the short label and carries the full rule", () => {
  const e = buildElements(AUTO).find((x) => x.data.id === "ask->__end__");
  assert.equal(e.data.display, "stop");
  assert.equal(e.data.detail, "You typed stop.");
});

test("edgeDisplay falls back to 'if' and appends the traversal count", () => {
  assert.equal(edgeDisplay({ conditional: true, label: null, count: 0 }), "if");
  assert.equal(edgeDisplay({ conditional: true, label: "stop", count: 2 }), "stop ×2");
});

test("tooltipText joins the label and the rule, and is empty without a rule", () => {
  assert.equal(tooltipText({ label: "stop", detail: "You typed stop." }), "stop: You typed stop.");
  assert.equal(tooltipText({ label: "if", detail: null }), "");
});
