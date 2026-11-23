// Unit tests for the About content and obfuscated contact (Blueprint spec §4.1, §5).
import { test } from "node:test";
import assert from "node:assert/strict";
import { ABOUT, bindContact, contactAddress, contactHref } from "../../src/agentic_solutions/web/static/about.js";

test("contactHref builds the mailto with the encoded subject", () => {
  assert.equal(contactHref(), "mailto:" + ["jairajchetty", "gmail.com"].join("@") + "?subject=Agentic%20Patterns%20Studio");
});

test("contactAddress joins the parts", () => {
  assert.equal(contactAddress(), ["jairajchetty", "gmail.com"].join("@"));
});

test("ABOUT holds the exact spec copy", () => {
  assert.equal(ABOUT.name, "Jairaj Chetty");
  assert.equal(ABOUT.role, "Solution architect, enterprise integration and agentic AI");
  assert.ok(ABOUT.record.startsWith("20+ years of integration architecture"));
  assert.ok(ABOUT.record.includes("120+ integrations for MTN's group-wide Oracle Fusion ERP."));
  assert.ok(ABOUT.record.endsWith(ABOUT.builtWith));
  assert.equal(ABOUT.builtWith, "Built this Studio with LangGraph and Claude.");
});

test("bindContact attaches one click and one keydown listener, once", () => {
  const calls = [];
  const root = { addEventListener: (type, fn) => calls.push([type, fn]) };
  bindContact(root);
  bindContact(root);
  assert.deepEqual(calls.map(([t]) => t).sort(), ["click", "keydown"]);
});
