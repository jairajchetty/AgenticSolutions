// Unit tests for the console's pure helpers (model picker final review, finding 5).
import { test } from "node:test";
import assert from "node:assert/strict";
import { settledReply } from "../../src/agentic_solutions/web/static/console.js";

const DECLINED = "The model declined this request.";
const reply = (content) => ({ messages: [{ role: "user", content: "hi" }, { role: "assistant", content }] });

test("settledReply replaces streamed text that a refusal superseded", () => {
  assert.equal(settledReply(`partial ${DECLINED}`, reply(DECLINED)), DECLINED);
});

test("settledReply keeps the bubble when the final reply matches what streamed", () => {
  assert.equal(settledReply("Hello there.", reply("Hello there.")), null);
});

test("settledReply keeps a long bubble that the update only cut short", () => {
  const long = "x".repeat(5000);
  assert.equal(settledReply(long, reply(`${"x".repeat(4096)}…`)), null);
});

test("settledReply keeps the bubble when the update has no assistant text", () => {
  assert.equal(settledReply("Hello", {}), null);
  assert.equal(settledReply("Hello", { messages: [{ role: "assistant", content: "" }] }), null);
});
