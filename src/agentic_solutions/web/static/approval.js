// The approval card's pure helpers (Approval spec §5.3, §9.1): no DOM here.
//
// approvalView turns the `approval_request` interrupt payload into the text
// the card shows; resumeBody builds the run API's `{resume}` body for a
// decision. console.js draws the card from these.

export const REASON_MAX = 500;  // the run API's limit on a reject reason

// Whole rands with a thousands comma, as the ERP writes them: R12,345.
export function formatZar(amount) {
  const n = Math.round(Number(amount) || 0);
  const digits = String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${n < 0 ? "-" : ""}R${digits}`;
}

// An ISO timestamp as the visitor's local HH:MM ("" if absent or unreadable).
function localTime(iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  const pad = (v) => String(v).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// approvalView(payload) -> {rows, total, costCentre, budgetRemaining, overBudget,
//   policyReason, expires, shortHash, requoted, reqId, version, summary}
export function approvalView(payload) {
  const p = payload || {};
  const lines = Array.isArray(p.lines) ? p.lines : [];
  const total = Number(p.total_zar) || 0;
  const remaining = Number(p.budget_remaining);
  return {
    rows: lines.map((line) => ({
      sku: String(line.sku ?? ""),
      name: String(line.name ?? line.sku ?? ""),
      qty: Number(line.quantity) || 0,
      unit: formatZar(line.unit_price_zar),
      lineTotal: formatZar(line.line_total_zar),
    })),
    total: formatZar(total),
    costCentre: String(p.cost_centre ?? ""),
    budgetRemaining: Number.isFinite(remaining) ? formatZar(remaining) : "",
    overBudget: Number.isFinite(remaining) && total > remaining,
    policyReason: String(p.policy_reason ?? ""),
    expires: localTime(p.quote_expires_at),
    shortHash: String(p.short_hash ?? ""),
    requoted: p.requoted === true,
    reqId: String(p.req_id ?? ""),
    version: p.version ?? null,
    summary: String(p.summary ?? ""),
  };
}

// resumeBody(decision, {edits, reason}) -> {resume: {...}}
// `edits` are [{sku, quantity, original}] as read from the card's inputs;
// only lines whose quantity changed are sent. A reject reason is trimmed,
// capped at REASON_MAX and left out when blank.
export function resumeBody(decision, { edits = [], reason = "" } = {}) {
  if (decision === "edit") {
    const changed = (edits || [])
      .map((e) => ({ sku: e.sku, quantity: Number(e.quantity), original: Number(e.original) }))
      .filter((e) => e.quantity !== e.original)
      .map(({ sku, quantity }) => ({ sku, quantity }));
    return { resume: { decision, edits: changed } };
  }
  if (decision === "reject") {
    const text = String(reason ?? "").trim().slice(0, REASON_MAX);
    return { resume: text ? { decision, reason: text } : { decision } };
  }
  return { resume: { decision } };
}
