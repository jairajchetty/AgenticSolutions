// Unit tests for the purpose-first Guide split (Blueprint spec §4.2, §9.4).
import { test } from "node:test";
import assert from "node:assert/strict";
import { splitPurpose } from "../../src/agentic_solutions/web/static/guide.js";

const SECTIONS = {
  what: "## What it is\nA graph.\n",
  when: "## When to use it\nWhen you branch.\n",
  how: "## How this graph works\nSteps.\n",
  concepts: "## LangGraph concepts\nNodes.\n",
  trade: "## Trade-offs\nCost.\n",
  code: "## Key code\n```python\nx = 1\n```\n",
  try: "## Try this\nRun it.\n",
};
const headings = (md) => [...md.matchAll(/^## (.+)$/gm)].map((m) => m[1]);
const sample = (order) => "# Routing\n\n" + order.map((k) => SECTIONS[k]).join("\n");

test("splits the purpose sections from the rest, H1 excluded", () => {
  const { purpose, rest } = splitPurpose(sample(["what", "when", "how", "concepts", "trade", "code", "try"]));
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.deepEqual(headings(rest), ["How this graph works", "LangGraph concepts", "Trade-offs", "Key code", "Try this"]);
  assert.ok(!/^# /m.test(rest));
  assert.ok(purpose.includes("A graph.") && purpose.includes("When you branch."));
});

test("matches by name when sections are in a different order", () => {
  const { purpose, rest } = splitPurpose(sample(["how", "when", "trade", "what", "code"]));
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.deepEqual(headings(rest), ["How this graph works", "Trade-offs", "Key code"]);
});

test("missing purpose heading: purpose empty, rest is input minus the H1", () => {
  const input = sample(["what", "how", "trade"]);
  const { purpose, rest } = splitPurpose(input);
  assert.equal(purpose, "");
  assert.equal(rest, input.replace(/^# Routing\n/, ""));
});

test("headings inside code fences are ignored", () => {
  const md = "# T\n\n## How\n```md\n## What it is\nfake\n## When to use it\n```\n\n" + SECTIONS.what + "\n" + SECTIONS.when;
  const { purpose, rest } = splitPurpose(md);
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.ok(!purpose.includes("fake"));
  assert.ok(rest.includes("fake"));
});

test("no H1 and empty input are handled", () => {
  assert.deepEqual(splitPurpose(""), { purpose: "", rest: "" });
  assert.equal(splitPurpose(SECTIONS.how).rest, SECTIONS.how);
});
