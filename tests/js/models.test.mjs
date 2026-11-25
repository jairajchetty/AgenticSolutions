// Unit tests for the model menu helpers (model picker spec §7).
import { test } from "node:test";
import assert from "node:assert/strict";
import { badgeText, menuOptions, rememberedChoice } from "../../src/agentic_solutions/web/static/models.js";

const OFFLINE = { id: "offline", label: "Offline (scripted)" };
const HAIKU = { id: "claude-haiku", label: "Claude Haiku 5.5" };

test("menuOptions lists the session's models with Offline first", () => {
  assert.deepEqual(menuOptions({ models: [HAIKU, OFFLINE] }), [OFFLINE, HAIKU]);
  assert.deepEqual(menuOptions({ models: [OFFLINE] }), [OFFLINE]);
});

test("menuOptions falls back to Offline when the session lists nothing", () => {
  assert.deepEqual(menuOptions({}), [OFFLINE]);
  assert.deepEqual(menuOptions(null), [OFFLINE]);
});

test("rememberedChoice keeps a listed choice", () => {
  assert.equal(rememberedChoice("claude-haiku", [OFFLINE, HAIKU]), "claude-haiku");
});

test("rememberedChoice falls back to offline when the choice is gone or absent", () => {
  assert.equal(rememberedChoice("deepseek", [OFFLINE, HAIKU]), "offline");
  assert.equal(rememberedChoice(null, [OFFLINE, HAIKU]), "offline");
});

test("badgeText names the conversation's model", () => {
  assert.equal(badgeText(OFFLINE), "Offline (scripted)");
  assert.equal(badgeText(null), "Offline (scripted)");
  assert.equal(badgeText(HAIKU), "Live · Claude Haiku 5.5");
});
