// Unit tests for the Studio's hash router (Catalog spec §4.1). Run with
// `node --test tests/js/` (tests/test_js.py does this under pytest).
import { test } from "node:test";
import assert from "node:assert/strict";
import { LEGACY, formatHash, parseHash } from "../../src/agentic_solutions/web/static/router.js";

test("empty, bare and root hashes are the catalog home", () => {
  for (const hash of ["", "#", "#/"]) assert.deepEqual(parseHash(hash), { view: "home" }, hash);
});

test("a category/pattern hash is a pattern page", () => {
  assert.deepEqual(parseHash("#/governance/approval"), { view: "pattern", route: "governance/approval" });
  assert.deepEqual(parseHash("#/execution/tool-use"), { view: "pattern", route: "execution/tool-use" });
});

test("M1 hashes are legacy redirects to their new routes", () => {
  assert.deepEqual(parseHash("#guardrail"), { view: "legacy", route: "governance/guardrails" });
  for (const [id, route] of Object.entries(LEGACY)) {
    assert.deepEqual(parseHash(`#${id}`), { view: "legacy", route }, id);
  }
});

test("the legacy map is exactly the four M1 patterns", () => {
  assert.deepEqual({ ...LEGACY }, {
    qa: "collaboration/single-agent",
    chat_loop: "memory/session",
    guardrail: "governance/guardrails",
    human_in_loop: "governance/approval",
  });
});

test("anything else is unknown", () => {
  for (const hash of ["#/x", "#%E0", "#/a/b/c", "#nope", "#constructor", "#/governance/", "#/Gov/approval"]) {
    assert.deepEqual(parseHash(hash), { view: "unknown" }, hash);
  }
});

test("formatHash round-trips through parseHash", () => {
  assert.equal(formatHash("governance/approval"), "#/governance/approval");
  assert.equal(formatHash(), "#/");
  assert.deepEqual(parseHash(formatHash()), { view: "home" });
  for (const route of [...Object.values(LEGACY), "execution/tool-use"]) {
    assert.deepEqual(parseHash(formatHash(route)), { view: "pattern", route }, route);
  }
});
