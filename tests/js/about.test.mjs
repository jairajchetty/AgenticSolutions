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
  assert.ok(ABOUT.record.startsWith("20+ years of integration, solution and enterprise architecture"));
  assert.ok(ABOUT.record.endsWith(ABOUT.builtWith));
  assert.equal(ABOUT.builtWith, "Built this Studio with LangGraph and Claude.");
});

test("bindContact attaches one click listener, once", () => {
  const calls = [];
  const root = { addEventListener: (type, fn) => calls.push([type, fn]) };
  bindContact(root);
  bindContact(root);
  assert.deepEqual(calls.map(([t]) => t), ["click"]);
});

// A stub root whose click handler is captured, and a stub window.location.
function stubbed() {
  const handlers = {};
  const root = { addEventListener: (type, fn) => { handlers[type] = fn; }, querySelector: () => null };
  const location = { href: "http://localhost/#/" };
  globalThis.window = { location };
  bindContact(root);
  return { click: handlers.click, location };
}

function clickOn(target) {
  let prevented = false;
  return { event: { target, preventDefault: () => { prevented = true; } }, prevented: () => prevented };
}

test("a click on a [data-contact] reveals the address and opens the mailto", () => {
  const { click, location } = stubbed();
  const reveal = { textContent: "", hidden: true };
  const trigger = { parentElement: { querySelector: (sel) => (sel === "[data-contact-reveal]" ? reveal : null) } };
  const target = { closest: (sel) => (sel === "[data-contact]" ? trigger : null) };
  const c = clickOn(target);
  click(c.event);
  assert.equal(c.prevented(), true);
  assert.equal(reveal.textContent, `or copy: ${contactAddress()}`);
  assert.equal(reveal.hidden, false);
  assert.equal(location.href, contactHref());
});

test("a click elsewhere does nothing", () => {
  const { click, location } = stubbed();
  const c = clickOn({ closest: () => null });
  click(c.event);
  assert.equal(c.prevented(), false);
  assert.equal(location.href, "http://localhost/#/");
});
