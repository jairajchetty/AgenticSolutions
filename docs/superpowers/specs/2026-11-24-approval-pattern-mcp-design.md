# Approval Pattern (corrected) + Mock ERP MCP Server: Design Spec

- **Date:** 2026-11-24
- **Status:** Draft, builder-checked, awaiting the person's approval
- **Builds on:**
  - The Studio spec: §3 architecture, §5 events, §8 offline mode, §9 sessions, §9b host.
  - The Catalog spec: §3 taxonomy, entry `governance/approval`.
  - The Blueprint redesign spec: UI.
  - The M3 spec: tool calling in the scripted model, tools, and the local Live switch.
  - The Generic Guides spec: the format for the new Guide.
- **Branch:** `feature/approval-mcp`.
- **Order:** this spec is built **after Milestone 3**. It reuses M3's scripted tool calling, its `ToolNode` handling and the Live switch.

## 1. Intent

The Studio's current **Approval** demo is wrong. It runs the interrupt-based chat loop, which pauses to read your next message. It does not gate an action. Specifically:
1. It pauses before input, not before a consequential action.
2. The agent has no tools, so there is nothing to approve.
3. The person sees a prompt, not a proposal.
4. There is no approve, edit or reject decision.
5. Nothing enforces "the agent cannot act without approval".
6. It has neither idempotency on resume nor an audit record.

The person wants a correct Approval demo that uses **tools** and an **MCP server**. The use case is a **procurement assistant on a mock ERP**, which the person chose:

> "Order 12 laptops for the Cape Town office under cost centre CT-OPS." The agent searches the catalogue, checks budget, gets quotes and drafts a requisition. Turning the requisition into a purchase order commits money. **The agent can only propose that. A policy decides whether a person must approve, and the order is placed only after the exact proposal is approved.**

**Why this use case:** it mirrors real ERP approval practice (the person's 20+ years of enterprise integration, and their CV's interest in "agentic AI for ERP optimisation and workflow automation"). It is safe to run in public, since all data is fictional and no money moves. It also shows the whole pattern: policy routing, the human decision, enforcement and audit.

**Goals**
- `governance/approval` gets a correct live demo: the **procurement assistant** (registry id `approval`).
- A mock ERP **MCP server** exposes governed tools, and enforces approval itself as a second line of defence.
- A generic, platform-neutral Approval Guide (Generic Guides spec format).
- Tests that **prove** no purchase order can be placed without approval of the exact proposal.

**Non-goals**
- Integrating any real ERP or real supplier.
- Real payments.
- Multi-level approval chains (one approver level only; a variation the Guide mentions).
- User accounts. The "approver" is the visitor's session.

**Anti-goals**
- Approval enforced only by the prompt or only by the graph.
- An approval that can be replayed for a changed order.
- A resumed run that places a second order.
- A public visitor being able to see or spend another visitor's budget.

## 2. Approaches considered

| | Option | Trade-offs |
|---|---|---|
| **A (chosen)** | **Procurement assistant on a mock ERP** | Enterprise-relevant and tool-rich. It supports policy routing (auto-approve under a threshold) and edits (quantities). Safe and deterministic. |
| B | Customer refund agent | Simple and familiar, but fewer tools and a single yes/no decision. |
| C | Fictional guesthouse booking (after LekkeSlaap) | Relatable, but invites "is this real?" doubts, and has less room for policy. |

**Rejected earlier:** scraping or automating lekkeslaap.co.za. It has no public API, it would likely breach the site's terms, and it risks real bookings and real money.

**Enforcement design:** approval is enforced in **two independent places**.
1. **The agent cannot reach the commit action.** The commit tool is never given to the model. Only a dedicated post-approval step can call it.
2. **The system of record refuses an unapproved commit.** The MCP server requires an approval token bound to the exact proposal.

A single layer was rejected. Prompt-only or graph-only enforcement fails the anti-goals.

## 3. The pattern, generic (content for the new Guide)

The Approval Guide (`agents/approval_agent/explanation.md`) is written in the Generic Guides format. Its generic content must cover the following, platform-neutrally.

**Roles**
- **Agent**: plans and gathers information, and may only *propose* consequential actions.
- **Tools**: read-only or draft-only capabilities the agent may use freely.
- **Policy**: decides whether a proposal needs a person: amount threshold, budget, risk.
- **Approver**: a person who sees the exact proposal and decides.
- **Executor**: the only component able to perform the consequential action.
- **System of record**: holds the data, and independently refuses unapproved commits.
- **Audit log**: records every proposal and decision.

**Flow**
1. The agent works with read-only and draft tools.
2. The agent proposes an action with exact parameters.
3. Policy either auto-approves (low risk) or pauses the run with the proposal.
4. The approver approves, edits or rejects.
5. **Edit** changes the proposal and returns to policy, so the edited proposal needs its own approval.
6. **Reject** returns to the agent with the reason.
7. **Approve** lets the executor perform exactly the approved proposal.
8. Everything is recorded.

**Design considerations:** the generic "musts"
- **Least privilege:** the agent never holds the commit capability.
- **Bind approval to the exact proposal:** any change invalidates it.
- **Expiry:** approvals and quotes go stale, so re-check at execution time.
- **Re-validate at execution:** check budget and price again.
- **Idempotent execution:** a retry or resume must not act twice.
- **Durable pause:** the run's state survives the wait. Approval may take minutes or days.
- **Separation of duties:** the proposer cannot approve its own proposal.
- **Clear presentation:** show the approver what will happen, to whom, for how much, and why.
- **Audit everything.**
- **Defence in depth:** the system of record checks too.

**Trade-offs**
- Latency and human time.
- Approval fatigue, mitigated by policy thresholds.
- More states to manage: pending, expired or edited proposals.

**Related patterns:** [[governance/guardrails]], [[governance/audit]], [[governance/review]] (the dividing line, in Related patterns), [[cognitive/react]], [[execution/tool-use]].

**Studio section:** maps the roles to this graph's nodes (§5), lists the framework concepts used (interrupt/resume, checkpointing, tool node, the MCP client), shows the key code, and gives "Try this" inputs.

## 4. The mock ERP MCP server

### 4.1 Tools

Every tool carries MCP tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`).

| Tool | Annotations | Behaviour |
|---|---|---|
| `search_catalogue(query, category?, max_unit_price?)` | read-only | Up to 10 items: `sku`, `name`, `unit_price_zar`, `supplier_id`, `category` |
| `get_supplier(supplier_id)` | read-only | Name, lead time (days), rating, preferred flag |
| `check_budget(cost_centre)` | read-only | `allocated`, `committed`, `remaining` (ZAR) |
| `get_price_quote(sku, quantity)` | read-only | `quote_id`, unit price after volume discount, line total, `expires_at` (+30 min) |
| `create_requisition(cost_centre, lines[{quote_id}], justification)` | not read-only, idempotent=false, non-destructive | Draft requisition `req_id`, `version=1`, `total_zar`, `content_hash`, status `draft` |
| `update_requisition(req_id, lines?, justification?)` | not read-only, non-destructive | New version and new hash. Any prior approval for this requisition is void. |
| `get_requisition(req_id)` | read-only | Current version, lines, total, status, hash |
| `submit_purchase_order(req_id, version, approval_token, idempotency_key)` | not read-only, **destructive**, idempotent=true | Validates (§4.2), commits budget, returns `po_number` (status `ordered`). The same `idempotency_key` returns the same PO. |
| `get_audit_trail(req_id)` | read-only | Ordered events: created, updated, approval_requested, approved, rejected, auto_approved, submitted, refused (with reason) |

### 4.2 Enforcement inside the server

`submit_purchase_order` refuses with a clear error unless **all** of the following hold:
- The token's HMAC-SHA256 signature verifies against `ERP_APPROVAL_SECRET`, a shared secret held only by the Studio backend and the server.
- The token's claims match the requisition exactly: `req_id`, `version`, `content_hash`, `tenant`, and an `approver` or `"policy"`.
- The token hasn't expired (15 min).
- Every quote in the requisition is still unexpired.
- `total_zar ≤ remaining` budget at submit time.
- The requisition hasn't already been submitted under a different idempotency key.

Every refusal is audited.

### 4.3 Tenancy and data

- Every call is scoped to a **tenant**: the Studio thread id.
- The Studio's MCP client injects the tenant into every call, using a server-defined header or session parameter. The model never chooses it.
- Each tenant gets a fresh copy of the fixture budgets on first use. Tenants expire after 24 h of inactivity.
- **Fixtures:** a fictional South African company with ~40 catalogue items (laptops, monitors, docking stations, chairs, desks, network gear), 6 suppliers, and 4 cost centres (`CT-OPS`, `JHB-FIN`, `DBN-LOG`, `HQ-IT`) with budgets in ZAR. Quotes are deterministic.
- **Policy threshold:** `ERP_AUTO_APPROVE_LIMIT_ZAR` (default **5000**).

### 4.4 Implementation

- **Package:** `src/agentic_solutions/mcp_servers/erp/`. It holds `server.py` (the MCP app), `store.py` (per-tenant in-memory state), `policy.py`, `tokens.py`, `fixtures.json` and `__main__.py`.
- **SDK:** the official Python MCP SDK (`mcp`).
- **Transports:** **streamable HTTP on loopback** (default `127.0.0.1:8765`) for the Studio, and stdio for local inspection (MCP Inspector or desktop clients).
- **Deployment (M4):** a separate Compose service on the internal network, never exposed publicly. It runs ARM64 on the OCI host.
- **Before planning:** verify the installed `mcp` and `langchain-mcp-adapters` APIs for streamable HTTP, tool annotations and per-call tenant injection. If tenant injection can't be done transparently, the tenant becomes an explicit tool argument filled by a client-side wrapper and never by the model.

## 5. The Studio demo (`approval` / `governance/approval`)

### 5.1 Graph

Node names are fixed, because the catalog and tests pin them:

```
START → ask ─(route)→ agent ─(tool calls?)→ tools → agent
                        │
                        └─(propose_order called)→ policy ─(≤ limit)→ submit_po → ask
                                                    └─(> limit)→ approval ⏸
                                 approval ─approve→ submit_po → ask
                                          ├─edit→ policy
                                          └─reject→ agent
```

- **`agent`** is the model, bound to the read-only and draft MCP tools **plus** a local tool `propose_order(req_id, summary)`. That local tool ends the agent's turn.
- **`tools`** executes MCP tool calls.
- **`policy`** fetches the requisition (`get_requisition`). It auto-approves at or under the limit, issuing a `"policy"` token. Otherwise it routes to `approval`.
- **`approval`** calls the pause with an `approval_request` payload: lines, total, cost centre, budget remaining, policy reason, short hash, quote expiry.
  - Resume value: `{"decision": "approve" | "edit" | "reject", "edits"?: [{sku, quantity}], "reason"?: str}`.
  - **edit** calls `update_requisition` (re-quoting the changed lines) and routes back to `policy`.
  - **reject** appends the reason for the agent.
  - **approve** asks the Studio backend to issue a token (§4.2) bound to the current version and hash, with the approver set to the session.
- **`submit_po`** is the only caller of `submit_purchase_order`. Its idempotency key is `f"{req_id}:{version}"`, so a resume re-run cannot order twice. Its result goes to the conversation.
- **The model never receives** `submit_purchase_order` or any approval token.

### 5.2 Registry and catalog

- New `agents/approval_agent/`: `graph.py`, `explanation.md` (Generic Guides format) and `__main__.py`.
- Registry id `approval`, chat mode, folder `approval_agent`.
- Catalog `governance/approval`: `demo` changes from `human_in_loop` to `approval`.
- The `human_in_loop` registry entry is **removed**. `interrupt_chat_agent` stays in the repo as a CLI lesson.
- The legacy `#human_in_loop` hash still redirects to `#/governance/approval`.
- `langgraph.json` gets an `approval_agent` entry. The MCP server URL comes from env.

### 5.3 UI: the approval card

- When a run pauses with an `approval_request`, the console renders an **approval card** (paper sheet, Blueprint tokens). It shows:
  - the lines table (item, qty, unit, line total);
  - the total;
  - the cost centre and budget remaining;
  - the policy reason ("Over R5,000 needs approval");
  - the quote expiry.
- **Actions:**
  - **Approve:** the amber primary action, the only amber in the view at that moment.
  - **Edit quantities:** inline number inputs, then "Submit changes".
  - **Reject:** asks for an optional reason.
- The run API accepts `POST /api/threads/{tid}/runs` with **either** `{"text"}` **or** `{"resume": {...}}`. The resume payload is schema-validated: decision enum, edits with existing SKUs and quantities 1–999, reason ≤ 500 chars.
- A thread not paused at `approval` rejects a `resume` with 409.
- **The card is gone after a decision.** A restored thread re-renders a pending card from `/state`.
- **Audit view:** the state view shows `get_audit_trail` results after `submit_po`.
- The guide's Studio section links the flow to [[governance/audit]].

### 5.4 Offline and Live

- **Offline:**
  - The MCP server and tools are real. Only the model is scripted.
  - Samples:
    - "Order 12 laptops for the Cape Town office under CT-OPS": over the limit, so it goes to approval.
    - "Order 3 keyboards for CT-OPS": auto-approved.
    - "Order 40 monitors for JHB-FIN": over budget, so the submit is refused and explained.
  - The generic fallback drafts a small auto-approved order.
- **Live:** with M3's local Live switch, Claude drives the same tools. The MCP server and approvals behave identically.

## 6. Configuration

| Var | Default | Purpose |
|---|---|---|
| `ERP_MCP_URL` | `http://127.0.0.1:8765/mcp` | Where the Studio reaches the server |
| `ERP_APPROVAL_SECRET` | random per start (dev only) | HMAC key shared by the Studio backend and the server; required in production |
| `ERP_AUTO_APPROVE_LIMIT_ZAR` | `5000` | Policy threshold |
| `ERP_TENANT_TTL_HOURS` | `24` | Tenant expiry |

## 7. Testing

- **Server unit tests:**
  - Token verification: a valid token, a tampered signature, the wrong version, the wrong hash, the wrong tenant, an expired token.
  - An expired quote.
  - Overspend at submit time.
  - Idempotent submit: the same key returns the same PO; a different key after submission is refused.
  - Edits invalidate prior approvals.
  - Tenant isolation.
  - The audit trail is complete and ordered.
- **MCP contract test:** an in-process client lists tools and checks the names, input schemas and annotations from §4.1.
- **Graph tests** (scripted model, real server in-process or on an ephemeral port):
  - **The guarantee:** across every sample and a fuzz of scripted decision sequences, `submit_purchase_order` succeeds only when there was an `approve` decision (or a policy auto-approval) **for the same `content_hash`**.
  - **Edit → re-approval:** the old token is refused.
  - **Reject:** returns to the agent with the reason.
  - **Resume re-run of `submit_po`:** exactly one PO.
  - The model's bound tools never include `submit_purchase_order`.
  - The cap on agent↔tools rounds is the same as ReAct's.
- **API:**
  - Resume schema validation.
  - 409 when the thread is not paused at approval.
  - Another session's thread returns 404.
- **Browser checklist:**
  - The approval card renders with the totals.
  - Approve, edit and reject flows.
  - Reload while pending re-renders the card.
  - Auto-approve under the limit.
  - The audit trail shows.
  - Keyboard operation of the card.
  - Mobile at 375 px.

## 8. Out of scope / left to the builder

- **Out of scope:**
  - Multi-level approvals, delegation, notifications.
  - Real ERP adapters.
  - Exposing the MCP server publicly.
- **Left to the builder:**
  - The fixture contents, within §4.3.
  - The card styling, within Blueprint.
  - Error copy, which must be plain and specific.
  - Whether the server runs in-process for tests or on an ephemeral port.

## 9. Builder-check decisions (builder's calls)

1. **Two kinds of pause.** A thread can be paused at `ask` (it wants text) or at `approval` (it wants a decision).
   - `POST /runs` accepts `{"text"}` only when the thread is paused at `ask`, and `{"resume"}` only when it is paused at `approval`. Anything else returns **409**, with "Finish the pending approval first" or "Nothing is waiting for approval".
   - `/state.paused` returns `{node, payload}`. The `approval_request` payload carries a full snapshot of the requisition (lines, totals, budget, expiry, hash), so the card can be rebuilt after any restart from the checkpoint alone.
   - The runner's `resumed` flag is unchanged: every run on a paused thread is a resume.
2. **MCP client and tenant.**
   - The Studio opens one app-scoped MCP client in the lifespan and injects it into the build through the BuildContext. The approval agent's nodes are **async**.
   - The tenant is read from `config["configurable"]["thread_id"]` inside each node.
   - **Canonical tenant mechanism:** the server's tools take an explicit `tenant` argument. The Studio wraps them as **model-facing tools whose schemas omit `tenant`**, and the wrapper fills it from the config. The contract test checks both: the server schemas include `tenant`, and the model-facing schemas don't.
   - If the ERP server is down, startup still succeeds. Tool calls return an error the model can read ("The ERP system is unavailable"), and `policy`, `approval` and `submit_po` failures become the safe `error` event "The ERP system is unavailable. Try again shortly."
3. **ERP persistence.**
   - The ERP store persists to SQLite (`ERP_DB`, default `./data/erp.sqlite`), so tenants, requisitions and the audit log survive restarts of either process. `ERP_TENANT_TTL_HOURS` defaults to **168** (7 days).
   - If a paused thread's requisition no longer exists, the card shows "This request has expired. Ask the agent to draft it again." and the graph routes back to `agent` with that note.
4. **Expiry and refusals.**
   - The token is issued at approve time, and `submit_po` runs immediately after, so token expiry only covers retries.
   - **Quote expiry is checked when the card is shown and again on approve.** If any quote has expired, `approval` re-quotes through `update_requisition`: a new version and a new hash. It then routes to `policy`, which needs a fresh decision. The card says "Prices were re-quoted".
   - **Submit refusals** (over budget, expired, stale) go back to `agent` as a tool-style message with the server's reason, so the agent explains or proposes an alternative. That adds the edge `submit_po → agent` on refusal; success goes `submit_po → ask`.
   - At most **3 proposals per user turn** (`proposals` counter, reset by `ask`). After that, the agent must answer in text.
   - The §5.1 diagram and the topology tests include these edges.
5. **Token boundary and identity.**
   - `src/agentic_solutions/common/approval_tokens.py` is a small shared library used by both the server and the Studio: it issues and verifies tokens. The approval agent gets an injected `issue_token(claims)` callable, so the graph module never reads the secret directly.
   - Claims: `req_id`, `version`, `content_hash`, `tenant`, `approver`, `requested_by`, `reason`, `exp`.
     - `approver` is `"visitor:<session id hash>"` for a human approval and `"policy"` for auto-approval.
     - `requested_by` is `"agent"`.
     - `reason` is `"approved"` or `"under limit"`.
   - **Separation of duties is a stated demo limitation.** The visitor both asks the agent and approves, and the Guide's Studio section says so. In a real deployment the approver comes from an identity provider and must differ from the requester. The server enforces `approver != requested_by`, which holds trivially here.
6. **Ordering with M3.** M3 is built and merged before this plan starts, and this plan targets M3's code as built. Any extra scripted-model capability needed for multi-call scripts goes into this plan. The model-facing MCP wrappers are standard tool objects, so M3's scripted `bind_tools` works with them.
7. **`human_in_loop` removal.**
   - Existing tests that use `human_in_loop` as the generic interrupt-chat pattern move to `chat_loop`, which has the same mechanics.
   - `/api/patterns` now lists `approval` and drops `human_in_loop`. The JS search fixture regenerates.
   - `interrupt_chat_agent` loses its registry entry, offline script and `explanation.md`. It stays a CLI lesson, and its module docstring explains it.
