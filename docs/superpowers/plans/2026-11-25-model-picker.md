# Model Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the header's "Offline (scripted)" badge with a model menu: Offline (scripted), Claude (direct), and open-weight models via OpenRouter. Real models are usable only by the person on their own machine, behind one check that later becomes "admin only".

**Architecture:**
- **Model menu:** a new `web/models.py` holds the menu (built-in entries, or `STUDIO_MODELS`), the one access check `may_choose_model`, and the cross-site guard.
- **Adapters:** `common/llm.py` gains `make_model(entry)` for `anthropic` and `openrouter`. OpenRouter uses `langchain-openai` with routing preferences.
- **Graphs:** compiled lazily per `(pattern, model)` and cached.
- **Threads:** each thread stores its model id.
- **API:** `/api/session`, thread creation and `/state` gain model fields.
- **Runner:** provider errors become safe copy.
- **Front end:** the menu is a `<select>` built by a pure `models.js` helper.

**Tech Stack:** Python 3.14, FastAPI, LangGraph 1.2.16, langchain-core 1.8, `langchain-anthropic` (installed), `langchain-openai` (new, optional `providers` extra), vanilla ES modules, Node `node:test`.

**Spec:** `docs/superpowers/specs/2026-11-25-model-picker-design.md` (the "picker spec"). §3 covers the menu, adapters and check, §4 the API, §5 behaviour, §6 the smoke check, §7 the UI and §8 tests.

**Branch:** `feature/model-picker` (the spec commit is at its head). Work in place.

## Global Constraints

- **Menu entries** are `{id, label, provider, model}`.
  - `offline` is reserved, always first, and the default, with label "Offline (scripted)".
  - `provider` is `anthropic` or `openrouter`.
  - Default entries:
    - `{"id":"claude-haiku","label":"Claude Haiku 5.5","provider":"anthropic","model":"claude-haiku-5-5"}`
    - `{"id":"deepseek","label":"DeepSeek (via OpenRouter)","provider":"openrouter","model":<current DeepSeek slug on OpenRouter that supports tools, confirmed by the implementer>}`
  - `STUDIO_MODELS` (a JSON array) replaces the defaults.
  - Credentials: `ANTHROPIC_API_KEY` for anthropic, `OPENROUTER_API_KEY` for openrouter. An entry without its credential is not listed.
  - Startup fails with a clear message on any of: malformed JSON, a missing field, a duplicate id, the id `offline`, an unknown provider, or a provider package that won't import.
- **The check:** `may_choose_model(request, settings) -> bool` is true only when **all** of these hold:
  - `settings.host` is loopback (`127.0.0.1`, `::1` or `localhost`);
  - `request.client.host` is `127.0.0.1` or `::1`;
  - the `Host` header's hostname is `localhost`, `127.0.0.1` or `[::1]`, with any port;
  - for POSTs, the `Origin` header, when present, has the same scheme and host as the `Host` header.

  It is the **only** gate. Milestone 4 replaces its body with an admin rule.
- **Exact API copy:**
  - 403 `{"detail":"model choice is not available"}`.
  - An unknown model id gives 422 `{"detail":"unknown model"}`.
- **Settings:**
  - `HOST` (default `127.0.0.1`) and `PORT` (default `8000`), also used by `web/__main__.py`;
  - `OPENROUTER_ZDR` (default off);
  - `STUDIO_MODELS` (optional);
  - optional `OPENROUTER_SITE_URL` and `OPENROUTER_APP_TITLE`, which set OpenRouter's `HTTP-Referer` and `X-Title` headers only when set.
- **Adapters:**
  - Both: `max_tokens=4096` and no `temperature`.
  - OpenRouter: base URL `https://openrouter.ai/api/v1`. Every request carries `provider: {"data_collection":"deny","require_parameters":true}`, plus `"zdr": true` when `OPENROUTER_ZDR` is on. Fallbacks are left at OpenRouter's default, so another compliant host for the same model can be used. Confirm the field names against OpenRouter's current docs.
  - The approval graph's `tool_choice={"type":"none"}` must reach OpenRouter as the OpenAI form `"none"`. Translate it inside the adapter; the graph is unchanged.
- **Safe error copy (exact):**

  | Error | Message |
  |---|---|
  | Authentication failure | "The {Provider} API key was rejected." (`Anthropic` / `OpenRouter`) |
  | Rate limit, or OpenRouter's "no compliant provider" | "{label} is busy or unavailable. Try again in a moment." |
  | Connection or timeout | "Couldn't reach {label}." |
  | Anything else | "The run failed." |

  The thread closes, as today. The exception is logged server-side; never log headers or keys.
- **Refusal:** the stop reason `refusal` makes the reply "The model declined this request." This goes through `common.llm.declined_or(msg)`, applied at the model call in the four live graphs: `qa_agent`, `chat_agent`, `secure_chat_agent` and `approval_agent`.
- **A conversation keeps its model.**
  - The thread record's `mode` holds the model id.
  - `run_started` carries `mode` (`"offline"` or `"live"`) and `model` (the id).
  - `/state` returns `model: {id, label}`.
- **UI:**
  - The menu shows only when `/api/session.models` has more than one entry. It is labelled "Model", never amber, keyboard-operable, and works at 375 px.
  - "Applies to your next chat." shows after a change until a new chat starts.
  - The badge text is "Offline (scripted)" or "Live · {label}", for the conversation on screen.
  - The choice is kept in `sessionStorage["studio.model"]` (with try/catch) and falls back to Offline when the stored model is no longer listed.
  - DOM APIs only: the single `innerHTML` rule holds.
- **Tests:** no test calls a provider or the network. Live paths use injected fake models. All existing tests keep passing. The one existing assertion that changes by design is the `/api/session` dict; list it in the report.
- **Commits:**
  - Use `git -c user.name="$(git log -1 --format=%an main)" -c user.email="$(git log -1 --format=%ae main)" commit …` with your session's Co-Authored-By trailer.
  - Never stage `.env`, `.superpowers/`, `data/` or `CV_*.pdf`.
  - Never stage `README.md` except as Task 5 describes, because it holds the owner's uncommitted Writing Guidelines.
  - Never kill processes by name, and leave anything on port 8000 alone.
- **Copy** follows the owner's guidelines: written for architects, plain, short and professional.

## Review Focus

1. **Another website in the person's browser starts a paid run.** That could be a cross-site POST, or DNS rebinding, where the page's `Host` is a foreign name pointing at 127.0.0.1. It must get 403, and `/api/session` must list only Offline. Tests in Task 1 (the check) and Task 3 (the endpoints).
2. **A thread started live, then run when the check has become false** (for example, the Host changes). Each run re-checks, so the run gets 403, the thread is not closed, and offline threads are unaffected. Test in Task 3.
3. **The menu changes mid-conversation.** The open thread keeps its model, a reload shows the thread's own model, and a stored choice that is no longer listed falls back to Offline. Tests in Task 3 (API) and Task 4 (JS helper plus browser).
4. **An OpenRouter model with tools.** The approval agent's capped call (`tool_choice` none) must reach OpenRouter as `"none"`, not as `{"type":"none"}`, which OpenAI-format APIs reject. Test in Task 2 on the built request payload.
5. **Provider error text or keys reach the browser.** A fake model raising each provider error gives exactly the safe copy, and the key never appears in events or logs. Test in Task 3.

---

## File structure

```
src/agentic_solutions/web/models.py        CREATE  ModelEntry, load_entries, listed_entries, may_choose_model, label lookup
src/agentic_solutions/web/config.py        MODIFY  host, port, openrouter_zdr, studio_models, openrouter_site_url/app_title
src/agentic_solutions/web/__main__.py      MODIFY  host/port from Settings
src/agentic_solutions/common/llm.py        MODIFY  make_model(entry, settings), declined_or(msg)
src/agentic_solutions/web/registry.py      MODIFY  live_factory(entry, settings)
src/agentic_solutions/web/app.py           MODIFY  lazy (pattern, model) graphs; session/thread/state model fields; checks
src/agentic_solutions/web/runner.py        MODIFY  provider error → safe copy; run_started.model
src/agentic_solutions/agents/{qa,chat,secure_chat,approval}_agent/graph.py  MODIFY  declined_or at the model call
src/agentic_solutions/web/static/models.js  CREATE  pure helpers: menuOptions, rememberedChoice, badgeText
src/agentic_solutions/web/static/{index.html,app.js,styles.css}  MODIFY  the menu
pyproject.toml                              MODIFY  [project.optional-dependencies] providers = ["langchain-openai>=…"]
tests/test_models.py, tests/test_llm_adapters.py, tests/test_model_api.py, tests/js/models.test.mjs  CREATE
README.md                                   MODIFY  (Task 5, staged per the README rule)
```

---

### Task 1: Model menu, settings and the check

**Files:** Create `web/models.py` and `tests/test_models.py`. Modify `web/config.py` and `web/__main__.py`.

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ModelEntry: id: str; label: str; provider: Literal["anthropic","openrouter"]; model: str`.
  - `OFFLINE = ModelEntry("offline", "Offline (scripted)", "offline", "")`. Its provider is the string `"offline"`, and it is never passed to `make_model`.
  - `DEFAULT_ENTRIES: tuple[ModelEntry, ...]`, as in Global Constraints.
  - `load_entries(raw: str | None) -> tuple[ModelEntry, ...]`. It parses `STUDIO_MODELS` or returns the defaults, and raises `ValueError(<clear message>)` per the Global Constraints rules.
  - `credential_set(entry, env: Mapping[str,str]) -> bool`.
  - `listed_entries(entries, env) -> tuple[ModelEntry, ...]`. It returns `OFFLINE` followed by the entries whose credential is set.
  - `may_choose_model(request: Request, settings: Settings) -> bool`, as in Global Constraints.
  - `entry_for(entries, model_id) -> ModelEntry | None`.
  - Copy constants `MODEL_CHOICE_DENIED = "model choice is not available"` and `UNKNOWN_MODEL = "unknown model"`.
  - `Settings` gains:
    - `host: str = "127.0.0.1"`
    - `port: int = 8000`
    - `openrouter_zdr: bool = False`
    - `studio_models: str | None = None`
    - `openrouter_site_url: str | None = None`
    - `openrouter_app_title: str | None = None`

    All are read in `from_env`. `OPENROUTER_ZDR` is true for "1", "true" or "yes", case-insensitive.
  - `__main__` runs uvicorn with `Settings.from_env().host/port`.
- The provider-package import check lives in Task 2's `make_model` path. Task 3 calls it at startup.

- [ ] **Step 1: Write failing tests:**
  - `test_defaults_and_env_override`
  - `test_bad_studio_models_fail_clearly`, parametrized over: bad JSON, a missing field, a duplicate id, `offline` as an id, an unknown provider.
  - `test_listed_only_with_credential`
  - `test_check_true_only_all_loopback`, using a minimal `Request`/scope built for `client`, `headers` and `method`. Parametrized over:
    - bind host `0.0.0.0`
    - client `10.0.0.5`
    - Host `evil.example:8000` (rebinding)
    - POST with Origin `https://evil.example`
    - POST with Origin `http://127.0.0.1:8000`, which is allowed
    - GET with no Origin, which is allowed
    - Host `[::1]:8000`, which is allowed
  - `test_main_uses_settings_host_port`, which monkeypatches `uvicorn.run`.
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Commit:** "Add the model menu, its settings and the access check".

---

### Task 2: Adapters and refusals

**Files:** Modify `common/llm.py`, `pyproject.toml`, and the four live graphs. Create `tests/test_llm_adapters.py`.

**Interfaces:**
- Consumes: `ModelEntry` and `Settings` (Task 1).
- Produces:
  - `make_model(entry: ModelEntry, settings) -> BaseChatModel`:
    - **anthropic:** `ChatAnthropic(model=entry.model, max_tokens=4096)`.
    - **openrouter:** a `ChatOpenAI` subclass, `OpenRouterChat`, in `common/llm.py`:
      - `base_url` is the OpenRouter URL and `api_key` comes from `OPENROUTER_API_KEY`; `max_tokens` is 4096.
      - `extra_body={"provider": {...}}` per Global Constraints.
      - `default_headers` hold the optional site and title.
      - `bind_tools` maps `tool_choice` `{"type":"none"}` (and `"none"`) to `"none"`.
    - An unknown provider raises `ValueError`. A missing `langchain_openai` raises `RuntimeError("Install the providers extra: pip install -e '.[providers]'")`.
  - `check_provider_available(entry) -> None` raises the same `RuntimeError`, for startup.
  - `declined_or(msg: AIMessage) -> AIMessage` returns `AIMessage("The model declined this request.")` when `msg.response_metadata.get("stop_reason") == "refusal"` or `finish_reason == "content_filter"`. Otherwise it returns `msg` unchanged.
  - Apply `declined_or` to the reply at the model call in `qa_agent`, `chat_agent`, `secure_chat_agent` and `approval_agent`. In the approval agent, apply it before the cap override. A declined reply has no tool calls.
- `pyproject.toml`: `providers = ["langchain-openai>=1.0"]` under optional dependencies. Install it into `.venv` with `pip install langchain-openai` and report the version.

- [ ] **Step 1: Write failing tests** (no network):
  - `test_anthropic_entry_builds_with_max_tokens_and_no_temperature`, with `ANTHROPIC_API_KEY` monkeypatched to a dummy value.
  - `test_openrouter_payload_has_base_url_routing_and_headers`: build the model and inspect `model._get_request_payload([HumanMessage("hi")])` (or the equivalent in the installed version) for `extra_body.provider` and the `zdr` toggle. Check `model.openai_api_base` and `default_headers`.
  - `test_openrouter_tool_choice_none_is_openai_form` (Review Focus 4): bind a dummy tool with `{"type":"none"}`. The payload's `tool_choice == "none"`.
  - `test_missing_provider_package_message`, by monkeypatching the import to fail.
  - `test_declined_or_maps_refusal_and_passes_others`.
  - `test_live_graph_uses_declined_text`: a fake model returns a refusal in `chat_agent`, and the reply text is the declined copy.
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Commit:** "Add Claude and OpenRouter adapters and refusal handling".

---

### Task 3: Backend: threads carry a model

**Files:** Modify `web/registry.py`, `web/app.py`, `web/runner.py`, and `tests/test_api.py` (the session dict only). Create `tests/test_model_api.py`.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces:
  - `registry.live_factory(entry, settings) -> LLMFactory` returns `lambda: make_model(entry, settings)`.
  - **App startup:**
    - `app.state.model_entries = load_entries(settings.studio_models)`.
    - Call `check_provider_available` for each listed entry.
    - `app.state.graphs` is keyed by `(pattern_id, model_id)`. Offline graphs are built at startup as today.
    - `graph_for(app, pattern_id, model_id)` builds a live graph lazily, with the same saver, guard, ERP client and `issue_token`, and caches it. Use an `asyncio.Lock` so two first requests don't build twice.
    - Topologies still come from the offline graphs.
  - **`GET /api/session`:** returns `{"mode":"offline","models":[{"id","label"}...],"max_input_chars":…}`. Entries beyond Offline are listed only when `may_choose_model` is true (Task 1's `listed_entries`).
  - **`POST /api/patterns/{id}/threads`:** takes an optional body `{"model": str}`.
    - An unknown id gives 422 `UNKNOWN_MODEL`.
    - A non-offline model when the check is false, or whose credential is missing, gives 403 `MODEL_CHOICE_DENIED`.
    - The record stores `mode=model_id`. Priming uses that model's graph.
  - **`POST /runs`:** when `record.mode != "offline"`, re-check `may_choose_model`. A failure gives 403 `MODEL_CHOICE_DENIED` without closing the thread or taking the slot. Do this check before `begin_run`. Use `graph_for(...)`.
  - **`GET /state`:** adds `"model": {"id","label"}`, using `graph_for(...)`.
  - **Runner:**
    - `run_events(..., model: str = "offline", label: str | None = None)` adds `model` to `run_started`, and keeps `mode` as `"offline"` or `"live"`.
    - Provider errors map to the safe copy (Global Constraints). Match by exception class name and module so `anthropic` and `openai` stay optional imports: `AuthenticationError`, `RateLimitError`, `APIConnectionError`/`APITimeoutError`, and OpenRouter's 4xx "no provider" (an `openai.APIStatusError` whose status is 404 or 503 and whose message mentions provider) maps to busy.
    - Log with `log.exception` without request headers.

- [ ] **Step 1: Write failing tests**, using a test helper that injects fake entries: credentials monkeypatched, and `make_model` monkeypatched to return a `ScriptedChatModel`, or a fake that raises.
  - `test_session_lists_only_offline_without_check`
  - `test_session_lists_models_on_loopback_with_keys`. TestClient's client host is `testclient`, so construct the client with `client=("127.0.0.1", 50000)` and `base_url="http://127.0.0.1:8000"`.
  - `test_create_live_thread_runs_full_turn_and_state_reports_model`
  - `test_unknown_model_422`
  - `test_denied_model_403`: a non-loopback client, a foreign Host, a cross-site Origin, and a missing credential.
  - `test_run_rechecks_and_does_not_close` (Review Focus 2)
  - `test_open_thread_keeps_model_after_menu_change` (Review Focus 3)
  - `test_provider_errors_map_to_safe_copy` (Review Focus 5): parametrized over the four classes using fake exception classes named like the providers' own. Assert the exact copy, that the thread is closed, and that a sentinel "sk-secret" never appears in the events or in `caplog`.
  - `test_approval_with_fake_tool_calling_live_model`: one full order through the real graph and ERP with a fake bound model.
  - `test_live_graph_built_once_under_concurrency`
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. **Step 4:** Run the full suite and confirm PASS. List the `/api/session` assertion change in the report.
- [ ] **Step 5: Commit:** "Let a conversation run on a chosen model".

---

### Task 4: The menu in the header

**Files:** Create `web/static/models.js` and `tests/js/models.test.mjs`. Modify `index.html`, `app.js` and `styles.css`.

**Interfaces:**
- Consumes: `/api/session.models`, `/state.model`, `createThread(patternId, {model})`. Update `api.js` `createThread` to send the JSON body when a model is given.
- Produces, in `models.js` (pure):
  - `menuOptions(session) -> [{id,label}]`
  - `rememberedChoice(stored, options) -> id`, which falls back to `"offline"`
  - `badgeText(model) -> "Offline (scripted)" | "Live · {label}"`
- In the UI, per Global Constraints:
  - `<label for="model-select">Model</label><select id="model-select">` in the `#mode-badge` area, shown only when there is more than one option.
  - Otherwise the static badge stays.
  - On change, store the choice and show "Applies to your next chat." until the next new chat or Run.
  - New chats and trigger Runs pass the chosen model.
  - The badge shows the on-screen conversation's model, from `/state.model` on restore and from the creation response on new threads.
  - The trace caption appends the label.

- [ ] **Step 1: Write failing node tests** for the three helpers: options from session, the fallback when the stored value isn't listed, and the badge text.
- [ ] **Step 2:** Run and confirm FAIL. **Step 3:** Implement it. Run `node.exe --check` on each changed module. The `innerHTML` rule must still hold.
- [ ] **Step 4:** Run the full suite and confirm PASS.
- [ ] **Step 5: Browser check over CDP.** Use your own server on a free port, never 8000, started with `ANTHROPIC_API_KEY=dummy` so the menu appears, and your own Chrome with a unique `--user-data-dir`. Stop both by PID afterwards. Screenshots go in the scratchpad. Check:
  - (a) with no keys, the static badge and no menu;
  - (b) with a dummy key, the menu at 1440 and 375 px, operable by keyboard;
  - (c) the note after a change;
  - (d) an open offline chat stays offline after switching, and "Live · Claude Haiku 5.5" appears only on the next new chat. The page shows a run error, because the key is a dummy; confirm the safe copy "The Anthropic API key was rejected." appears;
  - (e) reload restores the thread's own model;
  - (f) a clean console apart from the expected run error.
- [ ] **Step 6: Commit:** "Add the model menu to the header".

---

### Task 5: README and the live smoke check

**Files:** `README.md`, staged per the rule below, and a short "checked models" note.

- [ ] **Step 1: README.** Add a "Choosing a model" section:
  - The menu is local-only today and admin-only later.
  - The keys `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY`.
  - `pip install -e '.[providers]'`.
  - The `STUDIO_MODELS` format, with an example adding a Qwen entry.
  - `OPENROUTER_ZDR`.
  - `HOST` and `PORT`.
  - What OpenRouter is told: deny data collection, require tool support.

  **README rule:** `README.md` holds the owner's uncommitted "## Writing Guidelines" section, which must not be committed.
  - Edit the working tree normally.
  - Stage a blob built from `git show HEAD:README.md` plus only your section: `git hash-object -w <copy>`, then `git update-index --cacheinfo 100644,<blob>,README.md`.
  - Confirm that `git diff --cached README.md` shows only your section.
  - Commit: "Document the model menu".
- [ ] **Step 2: Live smoke check.** This is controller-only and needs the person's explicit go-ahead and their keys in `.env`. It spends a few cents.
  - For each default entry, run:
    - one Session turn;
    - Approval sample 1, which pauses with the approval card;
    - Approval sample 2, which is auto-approved and places a PO.
  - Record screenshots and the token totals.
  - If DeepSeek fails the Approval checks, try a Qwen model, then a Kimi model, on OpenRouter (picker spec §6). Make the first passing one the default open-weight entry and update `DEFAULT_ENTRIES`.
  - The README's checked-models note says which models passed and which failed. Commit the default change and the note.
