// Unit tests for the catalog search rule (Catalog spec §4.2, Review Focus 1).
// The fixture is the real `/api/catalog` listing: tests/test_js.py writes it
// to tests/js/.fixture/catalog.json from agentic_solutions.web before it runs
// node, so the searches always see the current taxonomy and hints.
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
  assert.deepEqual(hits("evaluator-optimizer"), ["cognitive/reflection"]);
});

test("word order does not matter, and every word must match", () => {
  assert.deepEqual(hits("users memory"), ["memory/episodic"]);
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
  // "tools" is in ReAct's hint as-is; "users" matches Episodic via "user".
  assert.ok(hits("tools").includes("cognitive/react"));
  assert.ok(hits("users").includes("memory/episodic"));
});
