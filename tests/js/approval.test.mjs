// Unit tests for the approval card's pure helpers (Approval spec §5.3, §9.1).
import { test } from "node:test";
import assert from "node:assert/strict";
import { approvalView, errorNotice, formatZar, resumeBody } from "../../src/agentic_solutions/web/static/approval.js";

const EXPIRES = "2026-11-24T10:05:00+00:00";

function payload(overrides = {}) {
  return {
    kind: "approval_request",
    req_id: "REQ-0001",
    version: 2,
    summary: "12 laptops for the Cape Town office",
    cost_centre: "CT-OPS",
    justification: "New starters in the Cape Town office",
    lines: [
      { sku: "LAP-14B", name: "14-inch Business Laptop, 16 GB", quantity: 12, unit_price_zar: 11780,
        line_total_zar: 141360, quote_id: "Q-1", quote_expires_at: EXPIRES },
      { sku: "BAG-01", name: "Laptop bag", quantity: 2, unit_price_zar: 450,
        line_total_zar: 900, quote_id: "Q-2", quote_expires_at: "2026-11-24T10:20:00+00:00" },
    ],
    total_zar: 142260,
    budget_remaining: 180000,
    policy_reason: "Over R5,000 needs approval",
    short_hash: "a1b2c3d4",
    quote_expires_at: EXPIRES,
    requoted: false,
    ...overrides,
  };
}

const hhmm = (iso) => {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

test("formatZar writes whole rands with thousands commas", () => {
  assert.equal(formatZar(12345), "R12,345");
  assert.equal(formatZar(5000), "R5,000");
  assert.equal(formatZar(450), "R450");
  assert.equal(formatZar(1234567.4), "R1,234,567");
  assert.equal(formatZar(-2500), "-R2,500");
});

test("approvalView formats the rows and the total", () => {
  const view = approvalView(payload());
  assert.deepEqual(view.rows, [
    { sku: "LAP-14B", name: "14-inch Business Laptop, 16 GB", qty: 12, unit: "R11,780", lineTotal: "R141,360" },
    { sku: "BAG-01", name: "Laptop bag", qty: 2, unit: "R450", lineTotal: "R900" },
  ]);
  assert.equal(view.total, "R142,260");
  assert.equal(view.costCentre, "CT-OPS");
  assert.equal(view.budgetRemaining, "R180,000");
  assert.equal(view.policyReason, "Over R5,000 needs approval");
  assert.equal(view.shortHash, "a1b2c3d4");
  assert.equal(view.expires, hhmm(EXPIRES));
  assert.match(view.expires, /^\d\d:\d\d$/);
});

test("approvalView sets overBudget only when the total exceeds the remaining budget", () => {
  assert.equal(approvalView(payload()).overBudget, false);
  assert.equal(approvalView(payload({ budget_remaining: 142260 })).overBudget, false);
  assert.equal(approvalView(payload({ budget_remaining: 100000 })).overBudget, true);
});

test("approvalView passes the requoted flag through", () => {
  assert.equal(approvalView(payload()).requoted, false);
  assert.equal(approvalView(payload({ requoted: true })).requoted, true);
});

test("approvalView tolerates a payload with missing parts", () => {
  const view = approvalView({ kind: "approval_request" });
  assert.deepEqual(view.rows, []);
  assert.equal(view.overBudget, false);
  assert.equal(view.requoted, false);
  assert.equal(view.expires, "");
});

const CARD = { version: 2, shortHash: "a1b2c3d4" };
const ID = { version: 2, short_hash: "a1b2c3d4" };

test("approvalView passes the agent's summary and the justification through", () => {
  const view = approvalView(payload());
  assert.equal(view.summary, "12 laptops for the Cape Town office");
  assert.equal(view.justification, "New starters in the Cape Town office");
  assert.equal(approvalView({}).justification, "");
});

test("resumeBody: every decision names the card it was made on", () => {
  for (const decision of ["approve", "edit", "reject"]) {
    const body = resumeBody(decision, { card: approvalView(payload()),
      edits: [{ sku: "LAP-14B", quantity: "10", original: 12 }] });
    assert.equal(body.resume.version, 2, decision);
    assert.equal(body.resume.short_hash, "a1b2c3d4", decision);
  }
});

test("resumeBody: approve sends the decision and the card's identity", () => {
  assert.deepEqual(resumeBody("approve", { card: CARD }), { resume: { decision: "approve", ...ID } });
  assert.deepEqual(resumeBody("approve", { card: CARD, reason: "ignored", edits: [] }),
    { resume: { decision: "approve", ...ID } });
});

test("resumeBody: edit sends only the changed lines, as integers", () => {
  const edits = [
    { sku: "LAP-14B", quantity: "10", original: 12 },
    { sku: "BAG-01", quantity: "2", original: 2 },
  ];
  assert.deepEqual(resumeBody("edit", { card: CARD, edits }), {
    resume: { decision: "edit", ...ID, edits: [{ sku: "LAP-14B", quantity: 10 }] },
  });
  assert.deepEqual(resumeBody("edit", { card: CARD, edits: [{ sku: "BAG-01", quantity: 2, original: 2 }] }),
    { resume: { decision: "edit", ...ID, edits: [] } });
});

test("resumeBody: reject trims the reason, caps it at 500 and drops it when blank", () => {
  assert.deepEqual(resumeBody("reject", { card: CARD, reason: "  Too many laptops  " }),
    { resume: { decision: "reject", ...ID, reason: "Too many laptops" } });
  assert.deepEqual(resumeBody("reject", { card: CARD, reason: "   " }), { resume: { decision: "reject", ...ID } });
  assert.deepEqual(resumeBody("reject", { card: CARD }), { resume: { decision: "reject", ...ID } });
  const long = resumeBody("reject", { card: CARD, reason: ` ${"x".repeat(600)} ` });
  assert.equal(long.resume.reason.length, 500);
});

test("errorNotice gives the next step after a run fails", () => {
  assert.equal(errorNotice("The ERP system is unavailable. Try again shortly."),
    "The ERP system is unavailable. Start a new chat to try again.");
  assert.equal(errorNotice("The run failed."), "This conversation has ended. Start a New chat.");
  assert.equal(errorNotice(undefined), "This conversation has ended. Start a New chat.");
});
