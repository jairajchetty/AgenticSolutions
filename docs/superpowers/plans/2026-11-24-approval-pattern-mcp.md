# Approval Pattern + Mock ERP MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the wrong Approval demo with a procurement assistant. Its tools come from a mock ERP MCP server. It may only *propose* a purchase order. A policy or a person approves the exact proposal, and the ERP itself refuses anything unapproved.

**Architecture:**
- **ERP server:** a new MCP server package, `mcp_servers/erp`, holds a SQLite-backed store, the enforcement and the tools. Approval tokens come from a shared library, `common/approval_tokens.py`, so both the Studio and the server can issue and verify them.
- **Approval agent:** a new graph, `agents/approval_agent`. Its nodes are `ask → agent ⇄ tools → policy → approval ⏸ → submit_po`, and they reach the ERP through an injected `ErpClient`.
- **Web app:**
  - It connects one app-scoped `ErpClient`.
  - Its run API accepts either `{"text"}` or `{"resume"}`.
  - Its console renders an approval card.
- **Offline mode:** the scripted model learns to call tools, so the demo runs with a real MCP server and only the model scripted.

**Tech Stack:** Python 3.14, LangGraph 1.2.16, langchain-core 1.8, the official MCP Python SDK 1.x (FastMCP, streamable HTTP, in-memory sessions), FastAPI with SSE, SQLite (`sqlite3`), vanilla ES modules and Node `node:test`.

**Spec:** `docs/superpowers/specs/2026-11-24-approval-pattern-mcp-design.md` (the "Approval spec"). Section references:

| Approval spec section | What it covers |
|---|---|
| §4 | Server tools and enforcement |
| §5 | Graph, registry and UI |
| §6 | Configuration |
| §7 | Tests |
| §9 | Builder-check decisions |

The Guide follows `docs/superpowers/specs/2026-11-24-generic-pattern-guides-design.md`.

**Branch:** create `feature/approval-demo` from `feature/approval-mcp` (PR #4 is open on that branch).

## Pre-plan verification (Approval spec §4.4)

**The two libraries:**
- `langchain-mcp-adapters` 0.3.2, the latest, requires `mcp<2.0`.
- `mcp` 2.x has a different API.
- `mcp==1.30.0` provides everything this plan uses:
  - `mcp.server.fastmcp.FastMCP(name, host=, port=, stateless_http=)`
  - `@server.tool(annotations=mcp.types.ToolAnnotations(readOnlyHint=, destructiveHint=, idempotentHint=))`
  - `FastMCP.streamable_http_app()` and `FastMCP.run(transport="stdio" | "streamable-http")`
  - `mcp.client.streamable_http.streamablehttp_client(url)` with `mcp.ClientSession`
  - `mcp.shared.memory.create_connected_server_and_client_session(server._mcp_server)` for in-process sessions

**Rulings recorded here (the person may overturn them):**
1. **No `langchain-mcp-adapters`.** The spec makes the model-facing wrappers custom anyway: tenant is omitted from their schemas and filled from config (§9.2). The adapters would add a dependency for nothing.
2. **Pin `mcp>=1.30,<2`.**
3. **In-process ERP by default.** With `ERP_MCP_URL` unset, the Studio runs the ERP server in-process over the MCP in-memory transport. It is still the real MCP protocol, with a random per-start secret, so one command runs the whole demo.
   - With `ERP_MCP_URL` set, the Studio connects over streamable HTTP, and `ERP_APPROVAL_SECRET` is required. If it is missing, startup fails with a clear message.
   - The spec's random-per-start secret cannot be shared across two processes, which is why this ruling is needed.
4. **Audit tool for Studio decisions.** Add the tool `record_approval_event` to the server, Studio-only and never given to the model. The Studio calls it to audit `approval_requested`, `approved`, `rejected` and `auto_approved`, because the §4.1 tool list has no other way for the server to learn of them.
5. **The server refuses a `"policy"` token for an order over the limit.** This adds defence in depth. The server reads the same `ERP_AUTO_APPROVE_LIMIT_ZAR`.
6. **The approval token is never stored.** `approval` and `policy` store an approval *record* (approver, reason, and the proposal's identity) in state. `submit_po` issues the token at call time. Tokens therefore never reach the checkpoint or the browser's state view.
7. **Offline fallback.** A message that reads like an order ("order|buy N <item> for <cost centre>") is parsed and run as a real order. Any other message gets a text reply listing the samples. This replaces "always draft a small auto-approved order", so "hello" never places an order.

## Global Constraints

**The guarantee:**
- `submit_purchase_order` succeeds only with an `approve` decision for the same `content_hash`, or a policy auto-approval at or under the limit for the same `content_hash`.
- Enforcement lives in two places:
  - The model never receives `submit_purchase_order`, `record_approval_event` or any token.
  - The server verifies everything.

**Server tools (Approval spec §4.1):**
- Names, arguments and annotations are exactly as the spec's table, and every server tool also takes a `tenant: str` argument.
- The model-facing wrappers have identical names and omit `tenant`.

**Enforcement (§4.2):** the server refuses unless all of these hold:
- the HMAC-SHA256 signature is valid under `ERP_APPROVAL_SECRET`;
- the claims match `req_id`, `version`, `content_hash` and `tenant`;
- the token is unexpired (15 min);
- every quote is unexpired (30 min from issue);
- `total_zar ≤ remaining`;
- the requisition has not already been submitted under a different idempotency key;
- `approver != requested_by`;
- the token is not a `"policy"` token for a total over the limit.

Every refusal is audited.

**Token claims (§9.5):**
- `req_id`, `version`, `content_hash`, `tenant`, `approver`, `requested_by`, `reason`, `exp`.
- `approver` is `"visitor:<first 12 hex chars of sha256(session id)>"`, or `"policy"`.
- `requested_by` is `"agent"`.
- `reason` is `"approved"` or `"under limit"`.

**Idempotency:** `submit_po` uses the key `f"{req_id}:{version}"`.

**Configuration (§6, §9.3):**

| Setting | Value |
|---|---|
| `ERP_MCP_URL` | unset means in-process (ruling 3) |
| `ERP_APPROVAL_SECRET` | random per start when in-process; required when the URL is set |
| `ERP_AUTO_APPROVE_LIMIT_ZAR` | default `5000` |
| `ERP_DB` | default `./data/erp.sqlite` |
| `ERP_TENANT_TTL_HOURS` | default `168` |
| HTTP server address | `127.0.0.1:8765`, path `/mcp` |

**Graph node names (pinned):** `ask`, `agent`, `tools`, `policy`, `approval`, `submit_po`.

**Graph edges:**
- `ask → agent | ask | __end__`
- `agent → tools | policy | ask`
- `tools → agent`
- `policy → submit_po | approval | agent`
- `approval → submit_po | policy | agent`
- `submit_po → ask | agent`

**Graph limits:**
- At most **8** agent↔tools rounds per user turn. The 8th model call binds with `tool_choice="none"`.
- At most **3** `propose_order` calls per user turn. After that, the model is bound with `tool_choice="none"`.

**Tenancy:** the tenant is `config["configurable"]["thread_id"]`. The approver comes from `config["configurable"]["approver"]`, which the web app sets per run. The CLI uses `"visitor:cli"`.

**Run API (§5.3, §9.1):**
- `POST /api/threads/{tid}/runs` takes exactly one of `{"text": str}` or `{"resume": {...}}`.
- The resume payload is validated:
  - `decision` is one of `approve`, `edit`, `reject`;
  - `edits` are 1–20 items of `{sku: str, quantity: int 1–999}`, with each SKU among the pending lines;
  - `reason` is 500 characters or fewer.
- A thread paused at `approval` rejects `text` with **409** "Finish the pending approval first". Any other thread rejects `resume` with **409** "Nothing is waiting for approval".

**Errors:**
- Messages are plain and specific.
- An ERP outage inside `policy`, `approval` or `submit_po` becomes the event `error` with "The ERP system is unavailable. Try again shortly."
- Inside a tool call, an outage is returned to the model as the text "The ERP system is unavailable."

**Fixtures:**
- A fictional South African company with about 40 items, 6 suppliers, and the cost centres `CT-OPS`, `JHB-FIN`, `DBN-LOG` and `HQ-IT`, priced in ZAR.
- Quotes are deterministic.
- The three samples must route as follows:
  - "Order 12 laptops for the Cape Town office under CT-OPS" → over the limit → approval → approve → PO placed.
  - "Order 3 keyboards for CT-OPS" → auto-approved → PO placed.
  - "Order 40 monitors for JHB-FIN" → over the limit → approval → approve → **server refuses** (over budget) → the agent explains.

**UI:**
- Blueprint tokens.
- Approve is the only amber control while the card shows.
- The card is keyboard-operable and works at 375 px.
- `innerHTML` is used only through guide.js's DOMPurify path, so the card is built with DOM APIs.

**Existing behaviour:** every existing test keeps passing except the ones this plan migrates off `human_in_loop` (Approval spec §9.7).

**Commits:**
- Use `git -c user.name="$(git log -1 --format=%an main)" -c user.email="$(git log -1 --format=%ae main)" commit …` with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never stage `.env`, `.superpowers/`, `data/` or `CV_*.pdf`.
- Never write a phone number or full email address.
- Never kill processes by name. Leave anything on port 8000 alone.

## Review Focus

1. **Replay or swap: a token issued for one proposal is used for another.** That means an edited version, another tenant's requisition, or a "policy" token on a large order. Tests in Task 2, plus the guarantee fuzz in Task 5.
2. **Two visitors at once.** One visitor's thread id must never reach another's budget or requisitions, and budgets start fresh per tenant. Tests in Task 2 (store isolation) and Task 7 (another session's thread is 404).
3. **The resume re-run of `approval`.** LangGraph re-runs the node from the top on resume, so nothing before `interrupt()` may write to the ERP unless that write ends the pass. Test in Task 5: a resume with unchanged quotes produces no extra `updated` audit event.
4. **The model tries to commit.** A scripted tool call named `submit_purchase_order`, or one carrying a `tenant` argument, must not place an order or switch tenant. Test in Task 5.
5. **A double click or a second tab sends two resumes.** The second gets 409 (a run is already in progress, or nothing is waiting), and exactly one PO exists. Test in Task 7.

---

## File structure

```
pyproject.toml                                        MODIFY  + "mcp>=1.30,<2"
src/agentic_solutions/common/approval_tokens.py       CREATE  issue/verify HMAC tokens (shared)
src/agentic_solutions/mcp_servers/__init__.py         CREATE
src/agentic_solutions/mcp_servers/erp/__init__.py     CREATE
src/agentic_solutions/mcp_servers/erp/fixtures.json   CREATE  catalogue, suppliers, cost centres
src/agentic_solutions/mcp_servers/erp/policy.py       CREATE  needs_person(total, limit) + reason text
src/agentic_solutions/mcp_servers/erp/store.py        CREATE  SQLite per-tenant state, enforcement, audit
src/agentic_solutions/mcp_servers/erp/config.py       CREATE  ErpSettings.from_env()
src/agentic_solutions/mcp_servers/erp/server.py       CREATE  build_server(store, settings) -> FastMCP
src/agentic_solutions/mcp_servers/erp/__main__.py     CREATE  python -m ...erp [--stdio]
src/agentic_solutions/agents/approval_agent/__init__.py   CREATE
src/agentic_solutions/agents/approval_agent/erp.py    CREATE  ErpClient protocol, HttpErpClient, InProcessErpClient, model-facing tools
src/agentic_solutions/agents/approval_agent/graph.py  CREATE  the graph
src/agentic_solutions/agents/approval_agent/__main__.py   CREATE  CLI with terminal approvals
src/agentic_solutions/agents/approval_agent/explanation.md CREATE (Task 9; moved from interrupt_chat_agent)
src/agentic_solutions/web/offline/model.py            MODIFY  bind_tools, tool-call replies, kind rules
src/agentic_solutions/web/offline/scripts.py          MODIFY  APPROVAL script; drop HUMAN_IN_LOOP
src/agentic_solutions/web/registry.py                 MODIFY  approval spec; drop human_in_loop; BuildContext.erp/issue_token
src/agentic_solutions/web/catalog.py                  MODIFY  governance/approval → demo "approval", folder approval_agent
src/agentic_solutions/web/config.py                   MODIFY  ERP settings
src/agentic_solutions/web/runner.py                   MODIFY  UserFacingError → its message in the error event
src/agentic_solutions/web/app.py                      MODIFY  lifespan ErpClient; text|resume; 409 rules; approver in config
src/agentic_solutions/web/static/api.js               MODIFY  streamRun(threadId, body)
src/agentic_solutions/web/static/approval.js          CREATE  pure view-model + resume builders (node-tested)
src/agentic_solutions/web/static/console.js           MODIFY  render the approval card
src/agentic_solutions/web/static/app.js               MODIFY  wire resume sends; restore pending card
src/agentic_solutions/web/static/styles.css           MODIFY  card styles
langgraph.json                                        MODIFY  approval_agent entry
README.md                                             MODIFY  how to run the demo, ERP server, config
tests/...                                             CREATE/MODIFY per task
```

---

### Task 1: Dependency and shared approval tokens

**Files:**
- Modify: `pyproject.toml`
- Create: `src/agentic_solutions/common/approval_tokens.py`, `tests/test_approval_tokens.py`

**Interfaces:**
- Produces, in `approval_tokens.py`:
  - `TOKEN_TTL_S = 900`
  - `class TokenError(Exception)`, whose `str` is the reason
  - `issue(claims: dict, secret: bytes, *, ttl_s: int = TOKEN_TTL_S, now: float | None = None) -> str`
  - `verify(token: str, secret: bytes, *, now: float | None = None) -> dict`
- Token format: `base64url(canonical JSON claims) + "." + base64url(HMAC-SHA256(secret, payload part))`. Canonical JSON means `sort_keys=True, separators=(",", ":")`.
- `issue` adds `exp = now + ttl_s` and requires every claim in the Global Constraints list except `exp`. Otherwise it raises `ValueError`.
- `verify` compares with `hmac.compare_digest`. It raises `TokenError` with one of: "malformed token", "bad signature", "token expired".

- [ ] **Step 1:** Add `"mcp>=1.30,<2"` to `pyproject.toml` dependencies. Run `.venv/bin/pip install "mcp>=1.30,<2"`, then check that `.venv/bin/python -c "import mcp, mcp.server.fastmcp"` succeeds and `pip show mcp` reports 1.30 or later and below 2.
- [ ] **Step 2: Write failing tests:**
  - `test_round_trip_returns_claims_with_exp`
  - `test_tampered_payload_or_signature_is_bad_signature`
  - `test_wrong_secret_is_bad_signature`
  - `test_expired_token`, using `now=` on both calls
  - `test_malformed_token`, for "", "abc" and "a.b.c"
  - `test_issue_requires_all_claims`
- [ ] **Step 3:** Run `pytest tests/test_approval_tokens.py -q` and confirm FAIL. **Step 4:** Implement it. **Step 5:** Run the full suite and confirm PASS.
- [ ] **Step 6: Commit:** "Add the mcp dependency and shared approval tokens".

---

### Task 2: ERP store, policy and fixtures

**Files:**
- Create: `mcp_servers/__init__.py`, `mcp_servers/erp/{__init__,fixtures.json,policy.py,store.py,config.py}`, `tests/test_erp_store.py`

**Interfaces:**
- Consumes: `approval_tokens.verify`, `TokenError` (Task 1).
- Produces:
  - `policy.needs_person(total_zar: float, limit_zar: float) -> bool`, which is true when the total is over the limit.
  - `policy.reason(total_zar, limit_zar) -> str`, which gives "Over R5,000 needs approval" or "Under R5,000: approved by policy". Format rands with a thousands comma and no cents.
  - `config.ErpSettings(db: str, secret: bytes, auto_limit_zar: float, tenant_ttl_hours: float, host: str, port: int)` with `from_env()`.
  - `class ErpError(Exception)`, whose `code` is one of `not_found`, `invalid`, `refused` or `expired`, and whose `str` is a plain message for a person.
  - `class ErpStore(path: str, *, secret: bytes, auto_limit_zar: float, tenant_ttl_hours: float, clock: Callable[[], float] = time.time)`, with methods taking `tenant` first. Each returns plain dicts or lists matching Approval spec §4.1 fields:
    - `search_catalogue(tenant, query, category=None, max_unit_price=None)`
    - `get_supplier(tenant, supplier_id)`
    - `check_budget(tenant, cost_centre)`
    - `get_price_quote(tenant, sku, quantity)`
    - `create_requisition(tenant, cost_centre, lines: list[{"quote_id"}], justification)`
    - `update_requisition(tenant, req_id, lines=None, justification=None)`
    - `get_requisition(tenant, req_id)`
    - `submit_purchase_order(tenant, req_id, version, approval_token, idempotency_key)`
    - `get_audit_trail(tenant, req_id)`
    - `record_approval_event(tenant, req_id, version, event, actor, reason=None)`
- **Persistence:** SQLite via `sqlite3`, in one file with tables for tenants (with a last-seen time), budgets, quotes, requisitions (with versions) and audit.
- **New tenants:** a tenant's first use copies the fixture budgets. Any call purges tenants idle longer than the TTL.
- **Content hash:** `content_hash` is sha256 of the canonical JSON of `{req_id, version, cost_centre, justification, lines:[{sku, quantity, unit_price_zar, quote_id}], total_zar}`.
- **Pricing:**
  - Volume discount: 5% from a quantity of 10, 10% from 50.
  - Prices round to whole rands.
  - Quotes expire 30 minutes after issue.
- **Edits:** `update_requisition` bumps `version`, recomputes the hash, and audits `updated`.
- **Audit events:** `created`, `updated`, `approval_requested`, `approved`, `rejected`, `auto_approved`, `submitted`, `refused`. Each event records `ts`, `event`, `version`, `actor` and `detail`, in insertion order.
- **Submit:** `submit_purchase_order` checks every Global Constraints enforcement rule in a fixed order and raises `ErpError("refused", <plain reason>)` on the first failure, after auditing `refused`.
  - On success it commits the budget, sets the status to `ordered`, assigns `po_number` (`PO-<tenant-local counter, 4 digits>`), and audits `submitted`.
  - The same idempotency key returns the same PO with no second commit.
  - Refusal reasons:
    - "The approval does not match this request (it was changed after approval)."
    - "The approval has expired."
    - "A price quote has expired. Ask for a new quote."
    - "Over budget: R{total} needed, R{remaining} remaining in {cost centre}."
    - "This request was already ordered."
    - "Policy cannot approve orders over R{limit}."
    - "Invalid approval."
- **Fixtures:** must satisfy the three sample routes in Global Constraints.

- [ ] **Step 1: Write failing tests** (`tmp_path` database, a fake clock, a fixed secret):
  - `test_fixtures_cover_samples`: laptops ×12 for CT-OPS is over the limit and within budget. Keyboards ×3 for CT-OPS is within the limit. Monitors ×40 for JHB-FIN is over the limit and over the remaining budget.
  - `test_valid_token_submits_and_commits_budget`
  - Token refusals, parametrized:
    - tampered signature
    - wrong version
    - wrong hash
    - wrong tenant
    - expired token
    - approver equal to requested_by
    - policy token over the limit

    Each refusal is audited.
  - `test_expired_quote_refused`
  - `test_overspend_refused_at_submit`: budget spent by another order after approval.
  - `test_idempotent_submit_same_key_same_po_no_double_commit`
  - `test_second_submit_different_key_refused`
  - `test_edit_voids_prior_approval`: a token for v1 is refused after `update_requisition`.
  - `test_tenant_isolation` (Review Focus 2): tenant B can't read A's requisition (`not_found`), and B's budget is unaffected by A's order.
  - `test_ttl_purges_idle_tenant`
  - `test_audit_trail_complete_and_ordered`
  - `test_state_survives_reopen`: open a new `ErpStore` on the same file.
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Commit:** "Add the mock ERP store with approval enforcement".

---

### Task 3: The MCP server and the Studio-side client

**Files:**
- Create:
  - `mcp_servers/erp/server.py`
  - `mcp_servers/erp/__main__.py`
  - `agents/approval_agent/__init__.py`
  - `agents/approval_agent/erp.py`
  - `tests/test_erp_mcp.py`

**Interfaces:**
- Consumes: `ErpStore`, `ErpError`, `ErpSettings` (Task 2).
- Produces:
  - `server.build_server(store: ErpStore, settings: ErpSettings) -> FastMCP`.
    - It has the ten tools: the nine from §4.1 plus `record_approval_event`. Each takes `tenant: str` first and carries the §4.1 annotations. `record_approval_event` is non-read-only, non-destructive and idempotent=false.
    - Each tool returns the store's dict.
    - An `ErpError` becomes an MCP tool error (`isError`) whose text is `str(err)`.
  - `__main__.py` serves streamable HTTP on `settings.host:settings.port` at `/mcp` by default. With `--stdio` it serves stdio.
  - In `approval_agent/erp.py`:
    - `class ErpUnavailable(Exception)`
    - `class ErpToolError(Exception)`, whose `str` is the server's message
    - `class ErpClient(Protocol)` with `async def call(self, tool: str, args: dict) -> Any`. `call` raises `ErpToolError` on a tool error, and `ErpUnavailable` on a connection failure or timeout (10 s).
    - `HttpErpClient(url)` opens one streamable-HTTP session per call.
    - `InProcessErpClient(server: FastMCP)` is an async context manager holding one in-memory session for its lifetime.
    - `MODEL_TOOL_NAMES`: the eight model-facing names. They are the §4.1 tools minus `submit_purchase_order`, so all read and draft tools.
    - `model_tools(erp: ErpClient) -> list[BaseTool]`: async `StructuredTool`s with the same names and argument schemas minus `tenant`. Each reads the tenant from an injected `config: RunnableConfig` (`["configurable"]["thread_id"]`).
      - An `ErpToolError` returns `"Error: <message>"`.
      - An `ErpUnavailable` returns "The ERP system is unavailable."
      - Results are compact JSON strings.

- [ ] **Step 1: Write failing tests**, using an in-process server over `create_connected_server_and_client_session` and a `tmp_path` store:
  - `test_server_lists_tools_with_schemas_and_annotations`: the ten names; every `inputSchema` has `tenant`; annotations per §4.1, so `submit_purchase_order` has destructiveHint true and idempotentHint true, and the read tools have readOnlyHint true.
  - `test_model_tool_schemas_omit_tenant_and_submit`: `model_tools(...)` names equal `MODEL_TOOL_NAMES`, no schema has `tenant`, and `submit_purchase_order` and `record_approval_event` are absent.
  - `test_model_tool_fills_tenant_from_config`: two thread ids see separate budgets.
  - `test_tool_error_becomes_error_text`, for example an unknown SKU.
  - `test_unavailable_server_becomes_plain_text`: `HttpErpClient("http://127.0.0.1:9/mcp")`.
  - `test_http_transport_round_trip`: start `build_server(...).streamable_http_app()` under uvicorn on a free ephemeral port in a background thread, call `check_budget` through `HttpErpClient`, then shut down.
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Commit:** "Serve the ERP over MCP and add the Studio ERP client".

---

### Task 4: Scripted model calls tools

**Files:**
- Modify: `web/offline/model.py`, `tests/test_offline_model.py`

**Interfaces:**
- Produces:
  - `Rule(match, reply, kind: Literal["text", "tools"] | None = None)`. A rule with `kind="tools"` only matches calls from a model bound with tools; `kind="text"` only matches unbound calls; `None` matches any.
  - `reply` may be a `str`, an `AIMessage`, or a callable `(messages) -> str | AIMessage`. `Script.fallback` may also be any of these.
  - `ScriptedChatModel.bind_tools(tools, *, tool_choice=None, **kw)` returns a bound copy with call kind `"tools"`. With `tool_choice` equal to `"none"` or `{"type": "none"}`, `tool_calls` are stripped from the chosen reply. Its text is kept, or `Script.fallback` text is used if it is empty.
  - Streaming: text replies stream word by word, as today. An `AIMessage` with tool calls is emitted as one `AIMessageChunk` carrying `tool_call_chunks`, so `stream_mode="messages"` and `ainvoke` both yield a final `AIMessage` with the same `tool_calls`.
  - `matched_rule` is unchanged.
- The design mirrors M3 plan Task 2 without structured output (Approval spec §9.6), so M3 can extend it later.

- [ ] **Step 1: Write failing tests:**
  - `test_tool_call_reply_round_trip`, through `ainvoke` and through `astream`.
  - `test_tool_choice_none_strips_tool_calls`
  - `test_callable_rule_sees_whole_history`
  - `test_kind_restricts_rule`
  - `test_unbound_text_streaming_unchanged`
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS. The existing offline tests are unchanged.
- [ ] **Step 5: Commit:** "Teach the scripted model to call tools".

---

### Task 5: The approval graph and CLI

**Files:**
- Create: `agents/approval_agent/graph.py`, `agents/approval_agent/__main__.py`, `tests/test_approval_graph.py`
- Modify: `langgraph.json`

**Interfaces:**
- Consumes:
  - `ErpClient`, `ErpToolError`, `ErpUnavailable` and `model_tools` (Task 3)
  - `approval_tokens.issue` (Task 1)
  - `policy` (Task 2)
  - `ScriptedChatModel`, `Rule`, `Script` (Task 4), in tests
  - `interrupt_chat_agent.graph.ask` and `chat_agent.graph.STOP_WORD`
- Produces:
  - `build_graph(*, erp: ErpClient, issue_token: Callable[[dict], str], auto_limit_zar: float, checkpointer=None, llm_factory=None) -> CompiledStateGraph`
    - The nodes are async except `ask`.
    - `graph` for `langgraph.json` is built lazily against `HttpErpClient(os.environ["ERP_MCP_URL"])`. Building must not connect.
  - Constants: `MAX_TOOL_ROUNDS = 8`, `MAX_PROPOSALS = 3`.
  - `class UserFacingError(Exception)` lives in `agentic_solutions/common/errors.py` (create it), because Task 7's runner reads it.
  - State keys:
    - `messages`
    - `tool_rounds: int`
    - `proposals: int`
    - `pending: dict | None`: the requisition snapshot and the `propose_order` tool-call id
    - `approval: dict | None`: approver, reason, req_id, version, content_hash
    - `audit: list`
- Model-facing tools are `model_tools(erp)` plus the local `propose_order(req_id: str, summary: str)`. This is a tool the agent node routes on and never executes.
  - When `propose_order` is the only call, `agent` routes to `policy`.
  - When it is mixed with other calls, it routes to `tools`, where `propose_order` answers "Error: call propose_order on its own, after the other tools."
  - An unknown tool name, such as `submit_purchase_order`, gets `tools`' normal "not a valid tool" error message.
- **`agent`** binds the tools. It uses `tool_choice="none"` when `tool_rounds >= MAX_TOOL_ROUNDS - 1` or `proposals >= MAX_PROPOSALS`.
- **`policy`** works as follows:
  - It calls `get_requisition` and stores the snapshot in `pending`.
  - At or under the limit, it records `auto_approved` via `record_approval_event`, sets `approval` (approver "policy", reason "under limit"), and goes to `submit_po`.
  - Over the limit, it goes to `approval`.
  - A missing requisition answers the `propose_order` call with "This request has expired. Ask the agent to draft it again." and goes to `agent`.
- **`approval`** runs in this order:
  1. It re-checks quote expiry from `pending`.
  2. If any quote has expired, it re-quotes each line (`get_price_quote`), calls `update_requisition`, and goes to `policy`, with a note in `pending` that prices were re-quoted. All of this happens before any `interrupt`, so the pass ends.
  3. Otherwise it records `approval_requested` (once per version) and calls `interrupt({"kind": "approval_request", ...snapshot, budget_remaining, policy_reason, short_hash: hash[:8], quote_expires_at})`.
  4. On resume:
     - **edit** re-quotes the changed SKUs, calls `update_requisition`, and goes to `policy`.
     - **reject** records `rejected`, answers the `propose_order` call with "The approver rejected this order. Reason: <reason or 'none given'>.", and goes to `agent`.
     - **approve** re-checks quote expiry (as in step 2 if any expired), records `approved`, sets `approval` (approver from config, reason "approved"), and goes to `submit_po`.
- **`submit_po`** issues the token from `approval` with `requested_by="agent"` and calls `submit_purchase_order` with idempotency key `f"{req_id}:{version}"`. Then:
  - On success, it answers the `propose_order` call with the PO details. It also adds a code-written `AIMessage`: "Purchase order {po} placed: {lines} for R{total} on {cost centre}." It sets `audit` from `get_audit_trail` and goes to `ask`.
  - On `ErpToolError`, it answers the call with "The ERP refused the order: <reason>" and goes to `agent`.
- **ERP outages:** `ErpUnavailable` inside `policy`, `approval` or `submit_po` raises `UserFacingError("The ERP system is unavailable. Try again shortly.")`.
- **`ask`** wraps the reused `ask` and resets `tool_rounds` and `proposals` to 0.
- **Routing:** use `Command(goto=...)` with `Literal` return annotations so `get_graph()` draws exactly the Global Constraints edges.
- **`__main__.py`:** an interactive loop using `get_llm()`.
  - By default it builds an in-process server from `ErpSettings.from_env()` with a random secret. With `ERP_MCP_URL` set, it uses HTTP.
  - It prints the approval request as a table and reads `a` (approve), `e` (edit: prompts for SKU and quantity), or `r` (reject: prompts for a reason).
  - `configurable.approver` is `"visitor:cli"`.

- [ ] **Step 1: Write failing tests.** Use a scripted model with callable `kind="tools"` rules that walk search → budget → quote → create → `propose_order` from the tool results in history, `InMemorySaver`, `InProcessErpClient` and a `tmp_path` store:
  - `test_topology_edges`: exactly the Global Constraints node and edge sets.
  - `test_over_limit_pauses_with_snapshot_then_approve_places_one_po`
  - `test_under_limit_auto_approves_without_pause`
  - `test_approved_but_over_budget_is_refused_and_returns_to_agent`, the JHB-FIN case.
  - `test_edit_requires_fresh_decision_and_old_token_refused`: after an edit, the graph pauses again, and a token for the old version is refused by the store.
  - `test_reject_returns_reason_to_agent`
  - `test_resume_rerun_does_no_extra_writes` (Review Focus 3): resume with unchanged quotes produces no extra `updated` audit event.
  - `test_requote_on_expired_quote_routes_to_policy`, with a fake clock moved past 30 minutes.
  - `test_model_cannot_commit` (Review Focus 4): a scripted call to `submit_purchase_order`, and a scripted `check_budget` call with `tenant="other"`. Neither places a PO or reads another tenant: the tenant argument is ignored and comes from config.
  - `test_bound_tools_exclude_submit_and_record`
  - `test_tool_round_cap_ends_turn_with_text`: a tools rule that always calls `check_budget`. After 8 tool rounds the final reply has no `tool_calls`, `next == ("ask",)`, and there are 8 ToolMessages.
  - `test_proposal_cap`: a script that keeps proposing after rejects. The 4th model call is text only.
  - **The guarantee fuzz:** for each sample, and for 30 seeded random decision sequences (approve, edit with random quantities, reject, up to 4 steps), every PO in the store's audit has an `approved` or `auto_approved` event for the same `version`. Its `content_hash` matches the submitted version, and no `submitted` event exists without one.
  - `test_erp_down_raises_user_facing_error`
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement the graph, the CLI and the `langgraph.json` entry `"approval_agent": "./src/agentic_solutions/agents/approval_agent/graph.py:graph"`. **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Commit:** "Add the approval agent graph and CLI".

---

### Task 6: Registry, offline script, catalog, and retiring human_in_loop

**Files:**
- Modify:
  - `web/registry.py`, `web/offline/scripts.py`, `web/catalog.py`, `web/config.py`
  - `tests/test_registry.py`, `tests/test_runner.py`, `tests/test_api.py`, `tests/test_catalog.py`, `tests/test_catalog_api.py`, `tests/test_offline_scripts.py`
  - the JS search fixture if it lists patterns (find it with `grep -rn human_in_loop tests/js`; `router.test.mjs` keeps the legacy redirect)

**Interfaces:**
- Consumes: `build_graph` (Task 5), `InProcessErpClient`, `HttpErpClient` (Task 3), `ErpSettings` (Task 2), `approval_tokens.issue` (Task 1).
- Produces:
  - `BuildContext` gains `erp: ErpClient | None = None`, `issue_token: Callable[[dict], str] | None = None` and `auto_limit_zar: float = 5000`. The approval build raises `RuntimeError("the approval demo needs an ERP client")` when `erp` is None.
  - `PATTERNS["approval"]`:
    - title "Approval: propose, approve, then act"
    - summary "The agent drafts a purchase order; a policy or you approve the exact order before the ERP accepts it."
    - mode `chat`, folder `approval_agent`
    - samples: the three Global Constraints samples
  - `human_in_loop` is removed from `PATTERNS`, and `HUMAN_IN_LOOP` from `SCRIPTS`.
  - `SCRIPTS["approval"]`:
    - **Order rules** (`kind="tools"`): parse the latest human text with `(?:order|buy)\s+(\d+)\s+(.+?)\s+(?:for|under)\s+.*?\b(CT-OPS|JHB-FIN|DBN-LOG|HQ-IT)\b`, case-insensitive. Map the item words to a catalogue search, then walk the tool sequence from the tool results in history.
    - **Follow-up rule** (`kind="text"`): after a `propose_order` ToolMessage (reject or refusal), explain plainly and suggest a next step.
    - **Fallback** (text): explain what to ask, listing the samples (ruling 7).
  - `web/config.Settings` gains `erp_mcp_url: str | None`, `erp_approval_secret: str | None`, `erp_auto_approve_limit_zar: float = 5000`, `erp_db: str = "./data/erp.sqlite"` and `erp_tenant_ttl_hours: float = 168`, all read in `from_env`.
  - Catalog `governance/approval`: `demo="approval"`, `folder="approval_agent"`. Keep the aliases.
- Test migration (Approval spec §9.7): every test that used `human_in_loop` as a generic interrupt chat uses `chat_loop`. `/api/patterns` lists `["qa", "chat_loop", "guardrail", "approval"]`. The registry topology test gains the approval edge set.
- **App startup ERP wiring.** The app's startup builds every registered graph, so this task also adds the ERP to `create_app`:
  - `create_app(settings=None, *, checkpointer=None, guard=None, registry=None, erp=None)`.
  - With `erp` None and `settings.erp_mcp_url` None, the startup code builds an `ErpStore` from settings and a secret: `settings.erp_approval_secret` if set, else `secrets.token_bytes(32)`. It then enters `InProcessErpClient(build_server(...))` for the app's lifetime.
  - With a URL, it uses `HttpErpClient(url)` and requires `erp_approval_secret`. A missing secret raises `RuntimeError("ERP_APPROVAL_SECRET must be set when ERP_MCP_URL is set")` at startup.
  - `issue_token` is `lambda claims: approval_tokens.issue(claims, secret)`, and is passed in through `BuildContext`.
- **Test fixtures.** `conftest.app` sets `erp_db` to a `tmp_path` file and `erp_approval_secret` to a fixed test secret, so every app test runs the in-process ERP.
- **Startup test:** `test_url_without_secret_fails_startup`.

- [ ] **Step 1:** Update the tests listed above and add:
  - `test_approval_registered_and_human_in_loop_gone`
  - `test_catalog_approval_points_at_approval_demo`
  - `test_offline_samples_route_as_specified`: the three samples through the graph with the offline factory. The first pauses; the second places a PO; the third pauses, and approving it gives a refusal followed by a text explanation.
  - `test_fallback_never_orders`: "hello" gives text and no tool calls.

  Run and confirm FAIL.
- [ ] **Step 2:** Implement it. **Step 3:** Run the full suite and confirm PASS.
- [ ] **Step 4: Commit:** "Register the approval demo and retire human_in_loop".

---

### Task 7: API: ERP lifecycle, text or resume, 409 rules

**Files:**
- Modify: `web/app.py`, `web/runner.py`, `tests/conftest.py`, `tests/test_api.py`, `tests/test_runner.py`
- Create: `tests/test_approval_api.py`

**Interfaces:**
- Consumes:
  - `UserFacingError` (Task 5).
  - From Task 6: `create_app(..., erp=)`, the in-process ERP startup wiring, and `BuildContext.erp`/`issue_token`.
- Produces:
  - `RunRequest`: `text: str | None` (1..max_input_chars) and `resume: ResumeRequest | None`. Exactly one is required; otherwise 422.
    - `ResumeRequest`: `decision: Literal["approve", "edit", "reject"]`, `edits: list[Edit] | None` (`max_length=20`, where `Edit` is `{sku: str (1–40), quantity: int 1–999}`), and `reason: str | None` (`max_length=500`).
    - `edit` requires a non-empty `edits` (422 otherwise).
  - Before `begin_run`, read `aget_state`:
    - When paused at `approval`: text gives 409 "Finish the pending approval first", and an edit SKU not in the pending lines gives 422 "Unknown item in edits".
    - When not paused at `approval`: resume gives 409 "Nothing is waiting for approval".
  - Runs use `Command(resume=body.text)` or `Command(resume=body.resume.model_dump(exclude_none=True))`.
  - `_config(thread_id, session_id)` adds `"approver": "visitor:" + sha256(session_id).hexdigest()[:12]`, for priming and runs alike.
  - In the runner, a `UserFacingError` produces `{"type": "error", "message": str(err)}` and then `run_finished{status:"error"}`. Other exceptions are unchanged.
  - `/state.paused` is unchanged: it returns the full `approval_request` payload.

- [ ] **Step 1: Write failing tests** in `test_approval_api.py`:
  - `test_full_approval_over_http_api`: create a thread, send sample 1, and confirm it is paused with `kind == "approval_request"`. Post the approve resume, confirm the stream ends paused at `ask`, and confirm `values.audit` contains `submitted`.
  - `test_text_while_pending_is_409`
  - `test_resume_when_nothing_pending_is_409`, on both an approval thread at `ask` and a `chat_loop` thread.
  - `test_resume_schema_validation`, parametrized:
    - bad decision
    - quantity 0 and 1000
    - 21 edits
    - a reason of 501 characters
    - both text and resume
    - neither
    - an edit with no edits
    - an unknown SKU
  - `test_double_resume_places_one_po` (Review Focus 5): two approve posts, the second sent while the first is streaming and again after it. The second gets 409, and the audit shows one `submitted`.
  - `test_other_session_thread_404`
  - `test_erp_down_event_message`: an `erp` whose `call` raises `ErpUnavailable`, so the stream has the error message from the Global Constraints.
  - `test_pending_card_survives_state_reload`: `/state.paused.payload` holds lines, total and short_hash.
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Commit:** "Accept approval decisions in the run API".

---

### Task 8: The approval card

**Files:**
- Create: `web/static/approval.js`, `tests/js/approval.test.mjs`
- Modify: `web/static/api.js`, `web/static/console.js`, `web/static/app.js`, `web/static/styles.css`

**Interfaces:**
- Consumes: the `approval_request` interrupt payload (Task 5) and the API body shapes (Task 7).
- Produces:
  - In `approval.js` (pure, no DOM):
    - `approvalView(payload) -> {rows: [{sku, name, qty, unit, lineTotal}], total, costCentre, budgetRemaining, overBudget: bool, policyReason, expires, shortHash, requoted: bool}`. Money is formatted as `R12,345`, and `expires` is a local `HH:MM`.
    - `resumeBody(decision, {edits, reason}) -> {resume: {...}}`. It drops unchanged quantities from edits and trims the reason.
  - `api.js`: `streamRun(threadId, body, {signal})`, where `body` is `{text}` or `{resume}`. Update every caller.
  - `console.js`:
    - On an `interrupt` whose payload `kind` is `approval_request`, and in `restore()` when `paused.payload.kind` is `approval_request`, render the card with DOM APIs on a paper sheet. Its contents:
      - lines table
      - total
      - cost centre with budget remaining, plus the over-budget warning "This total is over the remaining budget; the ERP will refuse it."
      - policy reason
      - "Prices were re-quoted" when `requoted`
      - quote expiry
    - **Actions:**
      - **Approve** is the amber primary action.
      - **Edit quantities** toggles number inputs (min 1, max 999) and "Submit changes".
      - **Reject** reveals an optional reason (maxlength 500) and "Reject order".
    - All controls are disabled while busy. The text input is disabled with the hint "Decide on the order first" while a card is pending.
    - The card is removed after a decision is sent. On a 409, the console shows the server's message.
    - The card takes a new `onDecide(body)` callback.
  - `app.js`: `onDecide` sends through the same busy, abort and 404 handling as `send`, without adding a user bubble. Instead it adds a short note: "You approved the order", "You changed quantities" or "You rejected the order".
  - Styles: Blueprint tokens only. The table scrolls inside the card at 375 px. Focus rings use ink. Approve is the only amber.

- [ ] **Step 1: Write failing node tests:**
  - `approvalView` formats totals and rows, sets `overBudget`, and passes the `requoted` flag.
  - `resumeBody` handles approve, edit (only changed lines) and reject (trimmed and capped reason).
- [ ] **Step 2:** Run `pytest tests/test_js.py -q` and confirm FAIL. **Step 3:** Implement it. Run `node.exe --check` on each changed module. The static `innerHTML` rule must still hold.
- [ ] **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Browser check over CDP.** Use your own server on a free port, never 8000, and your own Chrome with a unique `--user-data-dir`. Stop both by PID afterwards. Screenshots go in the scratchpad. Check:
  - (a) sample 1 shows the card with totals, and approving places a PO and shows the audit in the state view;
  - (b) edit then approve;
  - (c) reject with a reason;
  - (d) reload while pending re-renders the card;
  - (e) sample 2 auto-approves with no card;
  - (f) sample 3 approve shows the refusal explanation;
  - (g) the card works by keyboard alone;
  - (h) at 375 px there is no horizontal page scroll;
  - (i) the console is clean.
- [ ] **Step 6: Commit:** "Add the approval card to the console".

---

### Task 9: Guide, docs and the CLI lesson

**Files:**
- Create: `agents/approval_agent/explanation.md`
- Delete: `agents/interrupt_chat_agent/explanation.md`
- Modify:
  - `agents/interrupt_chat_agent/graph.py`: module docstring only.
  - `README.md`.
  - `tests/test_guides.py` and `tests/guide_format.py`, only if a folder list hard-codes `interrupt_chat_agent`.

**Interfaces:**
- Consumes: the graph (Task 5) and the samples (Task 6).
- The Guide follows the Generic Guides format exactly. Sections 1–6 move over from today's `interrupt_chat_agent/explanation.md`: the generic Approval body, including the plain-language "What it is". Section 7 is rewritten for the real demo:
  - **Mapping.** Agent → `agent`. Tools → `tools` (ERP read and draft tools over MCP). Policy → `policy`. Approver → you, at the `approval` pause. Executor → `submit_po`. System of record → the mock ERP MCP server. Audit log → the ERP audit trail shown in the state view after an order. Also covers `ask`.
    - It states the separation-of-duties limitation: you both ask and approve, while a real deployment takes the approver from an identity provider (Approval spec §9.5).
  - **Framework concepts:**
    - `interrupt()` and `Command(resume=...)`
    - re-run on resume, and why nothing before the pause writes
    - the checkpointer as a durable pause
    - the prebuilt tool node
    - `Command(goto)` routing
    - the MCP client, with the tenant filled by the wrapper
  - **Key code:** at most 25 lines from `graph.py`, preferably the `approval` node's decision handling.
  - **Try this:** the three samples, plus "edit the laptop quantity to 2 and see it auto-approve" if that is true with the fixtures (otherwise pick an edit that is).
- `interrupt_chat_agent/graph.py`'s docstring says it is the CLI lesson for `interrupt()` and that the Studio's Approval demo is `approval_agent`.
- **README:** a section "Approval demo and the mock ERP" covering:
  - The one-command run: in-process ERP, with nothing extra to start.
  - Running the ERP separately: `python -m agentic_solutions.mcp_servers.erp`, with `ERP_MCP_URL` and `ERP_APPROVAL_SECRET`.
  - `--stdio` for the MCP Inspector.
  - The config table from the Global Constraints.
  - The CLI.

- [ ] **Step 1:** Write the Guide and delete the old one. Run `pytest tests/test_guides.py tests/test_registry.py tests/test_offline_scripts.py -q` and fix until it passes. The format, denylist, Mapping-names-every-node and Try-this tests apply automatically.
- [ ] **Step 2:** Update the docstring and the README. Run the full suite and confirm PASS.
- [ ] **Step 3:** Commit: "Write the Approval Guide for the real demo and document the ERP server".
