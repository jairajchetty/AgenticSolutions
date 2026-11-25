# Model Picker (Offline · Claude · Open-weight via OpenRouter): Design Spec

- **Date:** 2026-11-25
- **Status:** Builder-checked, awaiting the person's approval
- **Builds on:**
  - The Studio spec (`2026-11-22-agentic-patterns-studio-design.md`): §3a covers the provider-neutral model and `init_chat_model`, §9 says a conversation keeps its mode, and §10 is configuration.
  - The Approval spec (`2026-11-24-approval-pattern-mcp-design.md`): the Approval demo is tool-calling.
- **Supersedes:** the local Live switch in the M3 spec (`2026-11-23-live-cognitive-patterns-design.md` §3, and the Live parts of §9). That content now lives here, generalised from one Live model to a menu of models. M3 keeps only the three cognitive patterns.
- **Branch:** `feature/model-picker`, from `feature/approval-demo` (PR #5). It is isolated from Milestone 3.

## 1. Intent

The person wants a **model picker** in the Studio header, where the "Offline (scripted)" badge is now. The menu holds Offline (scripted), Claude and DeepSeek, and is easy to extend with other open-weight models. This lets the person compare a pattern's behaviour across a scripted run, a frontier model and an open-weight model.

**Who may use it:**
- **Now:** only the person, on their own machine.
- **Later, once public:** only an **admin user**. Everyone else always runs Offline.

The design therefore puts "may this visitor choose a model?" behind **one check**. Going public swaps that check's local-machine rule for an admin rule and changes nothing else.

**Goals**
- A header drop-down. Offline is the default, and an entry is listed only when its credential is set.
- Claude runs through Anthropic's API directly. DeepSeek, and any open-weight model added later, run through **OpenRouter**, configured to avoid providers that retain or train on prompts. Adding a model is one config entry.
- A conversation keeps the model it started with. The trace and the console show which model answered.
- Every live demo (Single Agent, Session, Guardrails, Approval) works with every listed model, including Approval's tool calling.

**Non-goals**
- Admin accounts, an access code, budgets, rate limits and deployment. These are Milestone 4; only the check's seam is built here.
- Live versions of the Guide-only patterns.
- Per-message model switching, or comparing two models side by side in one view.

**Anti-goals**
- A visitor other than the person (today) or an admin (later) seeing or using a real model.
- An offline run that looks like real reasoning. Scripted output stays labelled.
- A model in the menu that can't do tool calling, which would break the Approval demo.
- Keys or provider error details reaching the browser or the logs.

## 2. Approaches considered

The person chose **A**.

| | Approach | Trade-offs |
|---|---|---|
| **A (chosen)** | **Claude direct, plus open-weight models through OpenRouter.** A small config list drives the menu. | One new adapter covers every open-weight model, and OpenRouter's routing controls keep prompts away from retaining providers. Two keys. |
| B | Claude direct, plus DeepSeek's own API | Cheapest for DeepSeek, but every further model needs another vendor. Prompts go to DeepSeek's own hosts. |
| C | Everything through OpenRouter, Claude included | One key, but Claude goes through a middleman with a fee, and Anthropic-specific features are harder to reach. |

**Integration advice (recorded for the person):**
- DeepSeek's own API is OpenAI-compatible and supports tool calls, so B stays possible.
- OpenRouter's provider routing can deny data collection and restrict routing to zero-data-retention endpoints. It can also require that the chosen host supports every parameter sent, which matters for tools.
- Tool-calling quality varies by model and host. That is why each menu entry is checked before it is listed (§6).

## 3. The model menu

### 3.1 Configuration

The menu is a list of **model entries**. Each entry has:

| Field | Meaning |
|---|---|
| `id` | A stable short id used by the API and the UI, e.g. `claude-haiku`, `deepseek`. `offline` is reserved. |
| `label` | The menu text, e.g. "Claude Haiku 5.5", "DeepSeek V4 Flash (via OpenRouter)" |
| `provider` | `anthropic` or `openrouter` |
| `model` | The provider's model name, e.g. `claude-haiku-5-5`, or an OpenRouter slug such as `deepseek/…` |

- **Defaults:** two built-in entries, Claude Haiku 5.5 and DeepSeek through OpenRouter. The builder confirms the current DeepSeek slug on OpenRouter (and that it supports tool calling) at build time.
- **Override:** the environment variable `STUDIO_MODELS` replaces the list with a JSON array of entries, so the person can add Qwen, Llama, Kimi and others without a code change.
- **Credentials:**
  - `anthropic` needs `ANTHROPIC_API_KEY`.
  - `openrouter` needs `OPENROUTER_API_KEY`.
  - An entry whose credential is missing is **not listed**.
- **Startup checks:**
  - A malformed `STUDIO_MODELS` fails startup with a clear message.
  - So does an unknown `provider`, or a provider whose package won't import.
- **Offline** is always the first entry and the default. It never needs a credential.

### 3.2 The adapters

All entries are built through one factory: `make_model(entry) -> BaseChatModel`, in `common/llm.py`, called **per model call** like the offline factory, so no state is shared between runs.

**`anthropic`:**
- Builds the existing Claude client (`langchain-anthropic`).
- No `temperature` is set.
- `max_tokens` is 4096.

**`openrouter`:**
- Builds an OpenAI-compatible chat model (`langchain-openai`, a new optional dependency) with `base_url=https://openrouter.ai/api/v1` and `max_tokens` 4096.
- It sends OpenRouter's routing preferences on every request:
  - **Deny data collection.** Do not route to providers that store or train on prompts.
  - **Require parameter support.** Route only to hosts that support every parameter sent, including tools.
  - **Fallbacks only among compliant hosts.** OpenRouter may move to another host serving the same model if that host also meets both rules above. It never moves to a different model. If no compliant host is free, the request fails cleanly. *(Builder's call: `allow_fallbacks` stays on; the two rules above already exclude non-compliant hosts.)*
  - **Zero data retention: optional.** `OPENROUTER_ZDR` (default off) adds the stricter "zero-data-retention endpoints only" rule. *(Builder's call: off by default, because ZDR may leave no host that serves DeepSeek with tools; deny-data-collection is always on.)*
- It sends OpenRouter's optional app identification headers (site URL and title) only if set in config. No personal details are sent.
- The builder checks the exact request fields against OpenRouter's current docs.

**Shared behaviour:**
- Usage tokens are read from LangChain's standard `usage_metadata`. A model that reports none shows no token note.
- Reasoning or thinking content is never shown in v1. Only text reaches chat bubbles, and tokens stream from text only.

### 3.3 Who may choose (the one check)

`may_choose_model(request) -> bool` is the only gate. **Now** it returns true when **both** hold:
1. The server's bind host is loopback: `HOST` (default `127.0.0.1`), which `web/__main__.py` also uses with `PORT` (default `8000`).
2. The requesting client is loopback (`request.client.host` in `127.0.0.1` / `::1`). This holds even if the app is started another way, e.g. `uvicorn --host 0.0.0.0` behind Docker.

**Later (Milestone 4):** the body becomes "the session belongs to an admin". Every caller is unchanged.

**Cross-site protection (builder's call).** Because the check trusts the local browser, another website open in that browser must not be able to use it. Every request that can start a real-model run checks two things. Otherwise it returns 403, and so does `/api/session`'s model list:
- The `Host` header is one of `localhost`, `127.0.0.1` or `[::1]`, with any port. This defeats DNS rebinding.
- On POSTs, the `Origin` header, when present, matches the Host. This defeats cross-site form posts.

Tests cover both. When the check becomes the admin rule, these two checks stay.

When the check is false:
- `/api/session` lists only Offline.
- The header shows the plain "Offline (scripted)" badge, with no menu.
- Asking for any other model returns **403** `{"detail": "model choice is not available"}`.

## 4. API (additive)

- `GET /api/session` returns `{mode: "offline", models: [{id, label}], max_input_chars}`.
  - `models` always starts with `{id: "offline", label: "Offline (scripted)"}`.
  - Other entries appear only when `may_choose_model` is true and their credential is set.
  - `mode` stays the session default, `offline`.
- `POST /api/patterns/{id}/threads` accepts an optional body `{"model": "<id>"}`. The default is `"offline"`.
  - An unknown id gives **422**.
  - An id that isn't allowed for this request gives **403**.
  - The thread record stores the model id. Every run on the thread uses that model, and the check is repeated on each run.
- `GET /api/threads/{tid}/state` adds `model: {id, label}`.
- **Graphs:**
  - The offline graphs are compiled at startup, as today.
  - The graph for a `(pattern, model)` pair is compiled **lazily** on first use and cached. The Guardrails embedding guard and the Approval ERP client are shared across models.
- **Events:** `run_started` adds `model` (the id), so the trace can label the run.

## 5. Behaviour with a real model

**Error mapping.** Provider errors become safe `error` events. The real exception is logged server-side, never its headers or key. The thread then closes, as today.

| Error | Message shown |
|---|---|
| Authentication failure | "The {provider} API key was rejected." |
| Rate limit, or OpenRouter "no compliant provider" | "{label} is busy or unavailable. Try again in a moment." |
| Connection error or timeout | "Couldn't reach {label}." |
| Anything else | "The run failed." |

**Refusals.** A response whose stop reason says the model refused becomes the reply "The model declined this request.", and the run continues.

**Approval with a real model:**
- The agent node is unchanged. It binds the read and draft tools plus `propose_order`, and the per-turn caps and the code-level override still hold.
- `tool_choice="none"` is sent in each provider's accepted form. The builder confirms the OpenAI-compatible form for OpenRouter.
- The server-side guarantee (the ERP refuses anything unapproved) is unchanged, whatever the model does.

**No budgets locally.** These are the person's own keys. `run_finished.usage` is shown as a small "N tokens" note after a live run.

**Run timeout.** The existing 90 s run timeout applies to live runs.

## 6. The tool-calling check

Before a default entry ships, the builder runs one live **smoke check** per entry. This needs the person's go-ahead and keys, and spends a few cents. It covers:
- one Session turn;
- one Approval sample that pauses with an approval card;
- the auto-approved keyboards sample, which places a PO.

Screenshots and token totals are recorded.

If DeepSeek fails the Approval checks, the builder tries a Qwen model, then a Kimi model, through OpenRouter, and ships the first open-weight model that passes as the default open-weight entry (the person's decision). An entry that fails is not shipped as a default, and the README says which models were checked and how they did. Automated tests never call a provider (§8).

## 7. UI

**The menu.**
- When `models` has more than one entry, the header badge becomes a labelled `<select>`: "Model: Offline (scripted) ▾", with options in config order.
- It uses Blueprint tokens and is keyboard-operable. It is never amber, because amber is reserved for the active node and the one primary action.
- With only Offline, the header shows today's static badge.

**When a choice applies.**
- Changing the model does **not** change the open conversation.
- It applies to the next New chat for chat patterns, and to the next Run for trigger patterns, which create a thread per run anyway.
- A one-line note under the menu says "Applies to your next chat." until a new chat starts.

**Showing the model.**
- The badge text shows the model of the **conversation on screen**: "Offline (scripted)", or "Live · Claude Haiku 5.5".
- The trace caption adds the model label.
- A restored thread shows its own model, taken from `/state`.

**Remembering the choice.** The menu choice is remembered per browser in `sessionStorage`, wrapped in try/catch. If the remembered model is no longer listed, the menu falls back to Offline.

**Copy.** Plain and short, for architects, per the owner's writing guidelines.

## 8. Testing

**No test calls a provider.** Live paths use injected fake chat models.

**Menu:**
- Entries appear only with their credential.
- `STUDIO_MODELS` parsing and its errors.
- An unknown provider or a missing package fails startup with the message.

**The check:**
- true only with a loopback bind host and a loopback client;
- a non-loopback client sees only Offline and gets 403 on create;
- run-time re-checks;
- a foreign `Host` header (DNS rebinding) or a mismatched `Origin` on a POST gets 403 and an Offline-only model list.

**Threads:**
- A thread created with a fake `claude-haiku` model runs a full turn, and `/state.model` reports it.
- Switching the menu mid-chat leaves the open thread unchanged.
- Restore shows the thread's own model.

**Adapters:**
- The OpenRouter factory sets the base URL and the routing preferences (deny data collection, require parameters, and ZDR only when `OPENROUTER_ZDR` is on), checked on the built model's request payload without network.
- Anthropic keeps `max_tokens` 4096 and no temperature.

**Errors:** fake models raise the providers' authentication, rate-limit and connection errors, giving the exact copy, and the thread closes. A refusal maps to the declined text.

**Approval with a fake live model:** one tool-calling fake drives a full order through the real graph and ERP, unchanged.

**JS:** a node test for the pure menu helpers: options from `/api/session`, the remembered-choice fallback, and the badge text.

**Browser checklist:**
- The menu is absent with no keys.
- With a fake key, the menu is present, keyboard-operable and works at 375 px.
- The note appears after a change.
- The badge and trace label match the conversation.

**Live smoke check** per §6, with the person's go-ahead.

## 9. Changes to the M3 spec and plan

- **M3 spec:**
  - The title becomes "Live Cognitive Patterns (Milestone 3)".
  - §1's Live sentence and goal, §2 (approaches for the switch), §3 (Local Live mode) and the Live bullets in §9 are removed. A pointer to this spec replaces them.
  - M3's three patterns then rely on the picker for live runs.
- **M3 plan:**
  - Task 8 (local Live backend) and the Live parts of Tasks 10 and 12 are marked as superseded by this spec.
  - Task 1's "map live API errors" moves here (§5).

## 10. Out of scope / left to the builder

- **Out of scope:**
  - The admin rule itself, access codes, budgets, rate limits and deployment (Milestone 4).
  - Showing reasoning or thinking.
  - Per-pattern model overrides.
  - Any model host other than Anthropic and OpenRouter. DeepSeek's own API remains a later option, and would be one more `provider` value.
- **Left to the builder:**
  - The menu styling within Blueprint.
  - The exact OpenRouter request fields and current DeepSeek slug, which must be confirmed against current docs.
  - The module layout, e.g. `web/models.py` for the menu and the check.
