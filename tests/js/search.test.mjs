// Unit tests for the catalog search rule (Catalog spec §4.2, Review Focus 1).
// The fixture is the real `/api/catalog` listing: tests/test_js.py writes it
// to tests/js/.fixture/catalog.json from agentic_solutions.web before it runs
// node, so the searches always see the current taxonomy and descriptions.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { matches } from "../../src/agentic_solutions/web/static/catalog.js";

const FIXTURE = new URL("./.fixture/catalog.json", import.meta.url);
const catalog = JSON.parse(readFileSync(FIXTURE, "utf-8"));
const all = catalog.categories.flatMap((c) => c.patterns.map((p) => ({ p, c })));
const hits = (q) => all.filter(({ p, c }) => matches(q, p, c)).map(({ p }) => p.route);

test("the fixture is the full catalog", () => {
  assert.equal(all.length, 21);
});

test("problem statements find their pattern (Review Focus 1)", () => {
  assert.deepEqual(hits("remember users"), ["memory/episodic"]);
  assert.ok(hits("human sign-off").includes("governance/approval"));
  assert.deepEqual(hits("HITL"), ["governance/approval"]);
  assert.ok(hits("RAG").includes("memory/semantic"));
  // Reflection, plus the composites built on it (through its alias).
  assert.deepEqual(hits("evaluator-optimizer"),
    ["cognitive/reflection", "cognitive/search", "execution/autonomous", "governance/review"]);
});

test("word order does not matter, and every word must match", () => {
  // Autonomous builds on Episodic, so it matches through Episodic's aliases.
  assert.deepEqual(hits("users memory"), ["memory/episodic", "execution/autonomous"]);
  assert.deepEqual(hits("zzz"), []);
  assert.deepEqual(hits("memory zzz"), []);
});

test("an empty or blank query matches everything", () => {
  assert.equal(hits("").length, 21);
  assert.equal(hits("   ").length, 21);
});

test("matching is case-insensitive and splits on punctuation other than -", () => {
  assert.deepEqual(hits("hitl"), ["governance/approval"]);
  assert.deepEqual(hits("remember, users!"), ["memory/episodic"]);
});

test("a trailing s is dropped only as a fallback", () => {
  // "tools" is in ReAct's description as-is; "users" matches Episodic via "user".
  assert.ok(hits("tools").includes("cognitive/react"));
  assert.ok(hits("users").includes("memory/episodic"));
});

// The plain-substring rule with no fallback, built from the same fields.
const plainHits = (word) => all.filter(({ p, c }) =>
  [p.name, p.description, ...(p.aliases ?? []), c.name, c.description,
   ...(p.builds_on ?? []).flatMap((b) => [b.name, ...b.aliases])].join("\n").toLowerCase().includes(word))
  .map(({ p }) => p.route);

test("a word of 4+ characters can match only through the fallback", () => {
  // "users" appears nowhere in the catalog text; "user" is in Episodic's description.
  assert.deepEqual(plainHits("users"), []);
  assert.deepEqual(hits("users"), ["memory/episodic", "execution/autonomous"]);
});

test("short words ending in s get no fallback", () => {
  // Otherwise "is" would match every "i" and "us" every "u".
  assert.deepEqual(hits("is"), plainHits("is"));
  assert.deepEqual(hits("us"), plainHits("us"));
  assert.ok(hits("is").length < hits("i").length);
  assert.ok(hits("us").length < hits("u").length);
});

test("the fallback still finds Episodic for remember users", () => {
  assert.deepEqual(hits("remember users"), ["memory/episodic"]);
});

test("a card matches on the names of the patterns it builds on", () => {
  assert.ok(hits("tool use").includes("governance/approval"));
  assert.ok(hits("tool use").includes("execution/tool-use"));
});

test("a card matches on a building block's alias (Review Focus 5)", () => {
  const found = hits("function calling");
  assert.ok(found.includes("governance/approval") && found.includes("memory/semantic"));
  assert.ok(!found.includes("governance/review"));  // Review builds on Reflection and Single Agent only
});

test("every pattern's own page is linked from the main page (review: Tool Use)", async () => {
  const { cardHref, blockHref } = await import("../../src/agentic_solutions/web/static/catalog.js");
  const linked = new Set();
  for (const { p } of all) {
    if (p.composite) linked.add(cardHref(p));
    else linked.add(blockHref(p));  // the building-blocks strip
    for (const b of p.builds_on) linked.add(blockHref(b));
  }
  assert.deepEqual([...all.map(({ p }) => `#/${p.route}`)].filter((h) => !linked.has(h)), []);
  assert.equal(blockHref(all.find(({ p }) => p.route === "execution/tool-use").p), "#/execution/tool-use");
});
