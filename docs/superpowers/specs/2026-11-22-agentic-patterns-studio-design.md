# Agentic Patterns Studio — Design Spec

- **Date:** 2026-11-22
- **Status:** Draft, awaiting review
- **Branch:** `feature/patterns-studio`

## 1. Goal

A web app that teaches agentic design patterns by running them live. For the selected pattern the page shows:

1. **Left panel: Execution Trace.** The agent's LangGraph graph, animated as it runs (active node, edges taken), with a step timeline and the state after each step.
2. **Right panel: Agent Console.** A chat window for conversational patterns, or a task box with a **Run** button for one-shot (triggered) patterns.
3. **Below both: Pattern Guide.** An explanation of the pattern: what it is, when to use it, how this graph implements it, the LangGraph concepts involved, and its trade-offs.

The app will later be hosted on an internet-facing machine and shared with other people, so cost control and isolation between visitors are part of the first version, not an afterthought.

**Why:** this repo is a learning repo for agentic AI with LangGraph. The app turns its command-line agents into something other people can watch and try, so each pattern is understood by seeing it run, not by reading code.

**Anti-goals:** an attractive UI whose trace doesn't match what the graph actually did; a public demo that can run up an unbounded model bill; patterns made so complex that they stop teaching.

## 1a. Approaches considered

The person asked for an architecture suitable for later public hosting and chose **A**.

| | Approach | Trade-offs |
|---|---|---|
| **A (chosen)** | One FastAPI container serves the static UI and the API, streams trace events, and runs the graphs in-process with a SQLite checkpointer. Caddy in front handles TLS. | Simplest to build and deploy (one `docker compose up` on a small VM). No Node build. Limited to one instance, which is fine for a demo audience. Switching to a Postgres checkpointer later would allow scaling out. |
| B | The static frontend on a CDN host (Cloudflare or GitHub Pages) plus a separate API container. | Two deployments plus CORS. More moving parts for little gain at this size. |
| C | Self-hosted LangGraph Server as the backend, using the existing `langgraph.json`, with a custom frontend calling `langgraph-sdk`. | Needs Postgres and Redis, and its licensing terms apply when self-hosting. Its event shapes are less suited to teaching traces. |

Rejected earlier: Streamlit or Gradio (live graph animation and a custom three-region layout are awkward), and React/Vite (needs Node inside WSL plus a build step, for no benefit at this size).

Other decisions the person made: patterns = the existing four plus ReAct, Reflection and Plan-and-Execute; the trace depth = graph animation + timeline + state view; offline scripted mode by default, with Live mode unlocked by an access code.

## 2. Scope

### In scope (v1)

Seven patterns. The first four wrap the agents already in this repo; the last three are new:

| # | Id | Pattern | Mode | Source |
|---|----|---------|------|--------|
| 1 | `qa` | Single LLM call | trigger | existing `qa_agent` |
| 2 | `chat_loop` | Loop with conditional routing and memory | chat | existing `chat_agent` |
| 3 | `guardrail` | Input guardrail (embedding threat screen) | chat | existing `secure_chat_agent` |
| 4 | `human_in_loop` | Human-in-the-loop: `interrupt()` + checkpointer | chat | existing `interrupt_chat_agent` |
| 5 | `react` | ReAct tool use | chat | new `react_agent` |
| 6 | `reflection` | Reflection (generate → critique → revise) | trigger | new `reflection_agent` |
| 7 | `plan_execute` | Plan-and-Execute | trigger | new `plan_execute_agent` |

Also in scope:
- **Offline mode** with scripted LLM responses (the default for anonymous visitors), and **Live mode** with a real model (default **Claude Haiku 5.5**, see §3a), unlocked by an access code.
- Public-hosting safeguards: per-session budgets, per-IP rate limits, input limits, session expiry, and safe tools only.
- A Docker image with Docker Compose and Caddy (TLS) for a single VM with **2 GB of RAM or more** (the person's decision; 2 vCPU / 4 GB recommended, see §9a). The image installs **CPU-only PyTorch** and **bakes `bge-small-en-v1.5` into the image** at build time, so startup needs no Hugging Face download. `guard.py` and its 0.80 threshold are unchanged.

### Out of scope (v1)

User accounts; bring-your-own-key; replaying or stepping through finished runs; running more than one instance; LangSmith tracing; editing graphs in the UI. Section 13 lists these as candidate follow-ups.

## 3. Architecture

```
Browser ──HTTPS──► Caddy (TLS via Let's Encrypt, reverse proxy)
                     └─► app container: FastAPI (uvicorn, 1 worker)
                           ├─ GET  /                      static UI (HTML/CSS/ES modules, no build step)
                           ├─ GET  /api/patterns          catalog
                           ├─ GET  /api/patterns/{id}     topology + explanation + samples
                           ├─ POST /api/patterns/{id}/threads      new conversation
                           ├─ POST /api/threads/{tid}/runs         run/resume → streamed trace events (SSE)
                           ├─ GET  /api/threads/{tid}/state        current state (rehydrate after reload)
                           ├─ GET  /api/session       mode + remaining budget
                           └─ POST /api/session/unlock  access code → Live mode
                         Pattern registry → LangGraph graphs (in-process)
                         SQLite checkpointer (volume)   ← one thread per conversation
                         LLM provider: init_chat_model(LIVE_MODEL) (live) | ScriptedChatModel (offline)
```

Key decisions:
- **One process with in-process graphs.** No LangGraph Server, Redis or Postgres. Uvicorn runs a single worker, because the session store, budgets and rate limiter are in memory and SQLite has one writer.
- **The run endpoint streams its response.** `POST /api/threads/{tid}/runs` returns `text/event-stream`, and the browser reads it with `fetch()` plus a stream reader. `EventSource` can't send POST bodies. One request carries both the user's input and its trace.
- **Topology comes from the compiled graph** (`graph.get_graph()`), never written by hand, so the picture can't drift from the code.
- **The frontend uses no build step.** Libraries load from cdnjs/jsDelivr at pinned versions: Cytoscape.js with the dagre layout for the graph, marked + DOMPurify for Markdown. This keeps the repo Python-only; Node isn't needed.
- **The LLM is injected.** Each graph gets its model through a factory, so the same graph runs against the Live model (Claude by default), the offline script, or a test fake.

## 3a. Model selection

**Default Live model: Claude Haiku 5.5 (`claude-haiku-5-5`).** It costs $0.10 input and $0.50 output per million tokens, about 20× less than Sonnet 5.5. A typical demo run (about 3k tokens in, 500 out) costs well under a tenth of a cent, and the 2M-token daily cap costs at most about $1 a day. Haiku 5.5 supports the tool calling and structured output that patterns 5–7 need. Switch to Sonnet 5.5 by setting `LIVE_MODEL=anthropic:claude-sonnet-5-5`, with no code changes. The prices come from Anthropic's list and should be re-checked when deploying.

**Provider-neutral configuration.** The web app creates its Live model with LangChain's `init_chat_model`, through `common/llm.py`:

```python
def make_chat_model(model: str, **kwargs) -> BaseChatModel:
    """'anthropic:claude-haiku-5-5', 'ollama:qwen3', ... -> a LangChain chat model."""
    return init_chat_model(model, **kwargs)
```

- Agents get their model only through the injected `LLMFactory`, so no graph code names a provider.
- **Provider packages are optional extras:** `langchain-anthropic` stays a core dependency, and other integrations (for example `langchain-ollama`) are installed only when wanted, through a `providers` extra or manually. Selecting a provider whose package is missing fails at startup with a clear message, not on the first visitor's request.
- **Provider-neutral pieces:** budgets read the standard `usage_metadata` on LangChain `AIMessage`s. Tool calls use `bind_tools`, and structured output uses `with_structured_output`. A model whose integration doesn't report `usage_metadata` is counted conservatively: each call is charged `LIVE_SESSION_TOKENS / LIVE_SESSION_CALLS` tokens.
- **Quality bar for non-Claude models (builder's note):** small open models are often unreliable at tool calling and structured output, which patterns 5–7 depend on. The README documents this, and the app makes no attempt to repair malformed tool calls. A failure shows up as an `error` event in the trace.
- **Not in v1:** per-pattern model overrides, letting visitors pick a model, and a provider-specific rate-limit mapping for anything other than Anthropic.
- The existing CLIs keep using `get_llm()` and `CLAUDE_MODEL` unchanged.

## 4. Pattern catalog

Every pattern lives in its own folder under `agents/` and exports `build_graph(...)`, following the repo's conventions. It also gains an `explanation.md` that the Pattern Guide renders. The web layer describes each pattern with a `PatternSpec` record:

```python
@dataclass(frozen=True)
class PatternSpec:
    id: str
    title: str
    summary: str                 # one line for the catalog
    mode: Literal["chat", "trigger"]
    build: Callable[[LLMFactory, Checkpointer], CompiledGraph]
    make_input: Callable[[str], Any]   # user text -> graph input (or Command(resume=...))
    explanation_path: Path
    samples: list[str]           # clickable example inputs
    offline_script: Script       # scripted responses for offline mode
```

### 4.1 Modes

- **chat:** a multi-turn conversation on one thread. Patterns 2–5 pause at an `ask` node through `interrupt()`. Each user message resumes the graph with `Command(resume=text)` and the graph runs until it pauses again. **New chat** starts a new thread.
- **trigger:** one task in, one result out. Every **Run** starts a new thread, so runs don't share memory. The result appears as a card in the console, and intermediate artifacts (plan, drafts, critiques) appear in the trace's state view.

### 4.2 Changes to the existing agents

`chat_agent` and `secure_chat_agent` wait with `input()`, which blocks and can't work on a server. Both `build_graph` functions gain optional parameters, and the defaults keep the CLI and existing tests unchanged:

```python
def build_graph(ask_node=ask, checkpointer=None, llm_factory=get_llm): ...
```

The web layer passes the `interrupt()`-based `ask` from `interrupt_chat_agent`. The explanations for patterns 2 and 3 say so: "In the web demo the `ask` node waits with `interrupt()` (see pattern 4); in the CLI it uses `input()`." `qa_agent` and `interrupt_chat_agent` also gain `llm_factory`. Every agent today calls the module-level `get_llm()`, and tests monkeypatch it. The new parameter allows injection without monkeypatching, and the old route keeps working.

### 4.3 Pattern 1: Single LLM call (`qa`, trigger)
`START → answer → END`. This is the baseline the other patterns build on: one call, no loop, no memory. The Guide stresses that it's often the right choice ("start simple").

### 4.4 Pattern 2: Chat loop (`chat_loop`, chat)
`START → ask → (route) → answer → ask …`, with `stop` going to END. Teaches cycles, conditional edges, and the `add_messages` reducer as memory.

### 4.5 Pattern 3: Input guardrail (`guardrail`, chat)
`ask → guard → (answer | refuse) → ask`. The guard embeds the prompt with `bge-small-en-v1.5` and compares it with `threatlibrary.json`. The trace's state view shows `threat` (category and score), and a refused prompt highlights the `refuse` node in red. The guard runs locally in both modes and costs nothing, so offline visitors see the real guard working. The embedding model is loaded once, at app startup.

### 4.6 Pattern 4: Human-in-the-loop (`human_in_loop`, chat)
The same loop as pattern 2, but this Guide is about pausing: the trace shows a **⏸ paused at `ask`** badge, the `thread_id`, and the checkpoint count. The console shows the interrupt's payload (`QUESTION_PROMPT`) as the agent's prompt.

### 4.7 Pattern 5: ReAct tool use (`react`, chat) — new
```
START → ask → (route) → agent ─(tool_calls?)→ tools ─→ agent
                  ↑                └─(no)────────────→ ask
```
- `agent` calls the model with the tools bound (`bind_tools`). `tools` is LangGraph's prebuilt `ToolNode`. The route after `agent` is a custom `Literal["tools", "ask"]` router (it works like `tools_condition`, but returns to `ask` and enforces the cap below).
- Tools are safe, deterministic and free of side effects:
  - `calculator(expression)`: arithmetic evaluated by an AST whitelist (no `eval`).
  - `current_time(timezone)`: uses `zoneinfo`.
  - `unit_convert(value, from_unit, to_unit)`: a small table of length, mass and temperature units.
  - `pattern_glossary(term)`: looks up a canned glossary of agent terms.
- The console shows each tool call as a chip (`🔧 calculator("17*23") → 391`).
- **Tool-loop cap (builder's call):** a counter in state, `tool_rounds`, is reset by `ask` on each user turn and incremented by `agent`. The router after `agent` is `Literal["tools", "ask"]`. Once `tool_rounds` reaches 8, `agent` is called one last time without tools bound, so it must answer in text, and the route returns to `ask`. That keeps the thread paused at an interrupt and resumable. The cap is counted per user turn. `recursion_limit` (set to 60) is only a backstop, and the runner reports hitting it as an `error` event.

### 4.8 Pattern 6: Reflection (`reflection`, trigger) — new
```
START → generate → critique ─(score ≥ 8 or iteration = 3)→ END
                       └─(otherwise)→ revise → critique
```
- State: `task`, `draft`, `critique` (`score: int 1–10`, `feedback: str`), `iteration`, `history` (all drafts and critiques).
- `critique` returns structured output (`with_structured_output(Critique)`). `revise` rewrites the draft using the feedback.
- The result card shows the final draft. The state view shows each draft and its score, so the improvement is visible.
- Samples: "Write a haiku about distributed systems", "Explain recursion to a 10-year-old in 3 sentences", "Write a product tagline for a solar backpack".

### 4.9 Pattern 7: Plan-and-Execute (`plan_execute`, trigger) — new
```
START → planner → executor ─(tool_calls?)→ tools → executor
                      ├─(step done, steps left)→ executor
                      └─(all steps done)→ synthesizer → END
```
- `planner` returns structured output with 2–5 steps (`Plan(steps: list[str])`). `executor` works on the current step, with the goal and previous results as context. `synthesizer` writes the final answer.
- **Tools are real graph nodes (builder's call),** so the trace shows them, as the anti-goal requires. `executor` uses the same tools as ReAct, and `tools` is a `ToolNode`. The router after `executor` is `Literal["tools", "executor", "synthesizer"]`:
  - `tool_calls` present and `step_tool_rounds < 2` → `tools`.
  - Otherwise the step is done: its text is appended to `results`, `current_step` advances, `step_tool_rounds` resets, and the route goes to `executor` if steps remain or to `synthesizer` if not.
  - On the last allowed round, `executor` is called without tools, so it must finish the step in text. Messages for each step are kept in a `step_messages` channel that is cleared when the step advances.
- The state view shows the plan as a checklist that ticks off as steps finish. The Guide covers replanning as a variation that v1 doesn't implement.

## 5. Trace event protocol

The run endpoint streams Server-Sent Events. Each `data:` line is a JSON object with a `type`:

| type | fields | emitted when |
|---|---|---|
| `run_started` | `run_id`, `thread_id`, `mode` (`live`/`offline`) | before the first step |
| `node_started` | `step`, `node`, `ts` | a node begins |
| `token` | `node`, `text` | an LLM token streams from a node, chat answers only |
| `tool_call` | `node`, `name`, `args`, `id` | an AI message requests a tool |
| `tool_result` | `name`, `content`, `id` | `ToolNode` returns |
| `node_finished` | `step`, `node`, `ts`, `duration_ms`, `update` | a node returns; `update` is a JSON-safe summary of its state update |
| `edge` | `source`, `target`, `step` | the runner sees the transition from one node to the next |
| `interrupt` | `node`, `payload` | the graph pauses |
| `run_finished` | `status` (`completed`/`paused`/`error`/`budget_exhausted`), `output?`, `usage` | the stream ends |
| `error` | `message` (safe text, never a stack trace) | on failure |

Implementation: `graph.astream(input, config, stream_mode=["tasks", "messages"])`, checked against the installed langgraph 1.2:
- A `tasks` event with `input` and `triggers` means a node started. A `tasks` event with `result`, `interrupts` and `error` means it finished. A non-empty `interrupts` list becomes an `interrupt` event.
- `messages` events (`AIMessageChunk`, metadata) become `token` events, tagged with `metadata["langgraph_node"]`.
- **Edges:** the first node of a fresh run gets an edge from `__start__`. Each later node gets an edge from the node that finished before it. A run that completes adds an edge from the last node to `__end__`. On a **resume**, the paused node starts again, because LangGraph re-runs it from its first line. It gets no incoming edge and is marked "resumed", which the HITL Guide points out.
- Messages are converted to JSON as `{role, content, tool_calls?, name?}`. Long strings are cut to 4 KB for display only.

**Topology rule:** `get_graph()` can only draw a conditional edge's targets when the router declares them, so every router must annotate its return as `Literal[...]`. Otherwise LangGraph draws edges to every node. The existing routers already do this, and a topology test enforces it for every pattern.

## 6. UI

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Agentic Patterns Studio   [pattern tabs: 1 2 3 4 5 6 7]   ● Offline [🔑] │
├────────────────────────────────────┬─────────────────────────────────────┤
│ EXECUTION TRACE                    │ AGENT CONSOLE                       │
│  ┌──────────────────────────────┐  │  chat bubbles / result cards        │
│  │  graph (Cytoscape + dagre)   │  │  tool-call chips, refusals,         │
│  │  active node pulses,         │  │  interrupt prompts                  │
│  │  traversed edges animate     │  │                                     │
│  └──────────────────────────────┘  │  [sample chips]                     │
│  Timeline: 1 ask 2 guard 3 answer… │  [ input ........... ] [Send/Run]  │
│  State @ step n (collapsible JSON) │  [New chat]                         │
├────────────────────────────────────┴─────────────────────────────────────┤
│ PATTERN GUIDE: What · When to use · How this graph works · Concepts ·   │
│               Trade-offs · Key code                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Graph styling:** each node has a state: idle, active (pulsing accent), done (filled), error (red) or paused (amber ⏸). Edges flash when taken and keep a count of how often they were traversed. Conditional edges are dashed and labelled. `__start__` and `__end__` are small terminal dots.
- **Timeline:** one row per step (`#n node · duration`). Clicking a row selects that step: its node is highlighted and the state view shows the state up to that step. That is inspection only, not replay.
- **Pacing:** offline mode adds simulated latency (300–900 ms per LLM call, tokens streamed at about 40 per second) so the animation is easy to follow. Live mode shows real timing.
- **Mode badge:** shows `Offline (scripted)` or `Live · <model display name>` (e.g. `Live · Claude Haiku 5.5`), plus the remaining budget. 🔑 opens the unlock dialog.
- **Responsive:** below 900 px the panels stack in the order Console, Trace, Guide. Light and dark themes follow `prefers-color-scheme`.
- **Accessibility:** a node's state is shown by both colour and an icon or label. The timeline and console announce changes through an `aria-live` region.
- The URL hash (`#react`) selects the pattern, so links can point straight at one.

## 7. Pattern Guide content

`explanation.md` in each agent folder has fixed sections, which the page renders as labelled blocks:

1. **What it is:** two or three sentences.
2. **When to use / when not to.**
3. **How this graph works:** one bullet per node and router, using the same names as the trace.
4. **LangGraph concepts:** for example `interrupt`, `Command`, `ToolNode`, structured output.
5. **Trade-offs:** cost, latency, failure modes.
6. **Key code:** a short excerpt (at most 25 lines) from the agent's `graph.py`.
7. **Try this:** suggested inputs that exercise each branch, such as an attack phrase for the guardrail.

## 8. Offline mode

- `ScriptedChatModel` is a `BaseChatModel` subclass. It supports `invoke`, streaming, `bind_tools` and `with_structured_output`. Each pattern supplies a **Script**: an ordered list of rules (`match` on the latest human text, or on the node or call kind) mapped to responses (text, an `AIMessage` with `tool_calls`, or a structured object). A default rule answers any unmatched input with something like: "(Offline demo) I'd normally ask the model here. Unlock Live mode to try your own input."
- The scripts cover every sample input and exercise every branch: ReAct runs at least one tool loop, Reflection goes through one revise round before passing, and Plan-and-Execute runs a three-step plan.
- The guardrail always uses the real embedding guard (it is local and free).
- **Free text in offline mode (builder's call):** the input box stays enabled in every pattern. Each pattern's script has a **generic fallback** that still runs every branch: ReAct does one calculator round, Reflection has a generic critique scoring 6 then 9 so it revises once, and Plan-and-Execute uses a generic three-step plan. Fallback replies say they're scripted, e.g. "(Offline demo: scripted response. Unlock Live mode for real answers.)". The test rule becomes: every sample input matches a *specific* rule, and any free text runs to `completed` or `paused` through the fallback.
- The same scripted models back the automated tests, so the offline demo can't silently break.

## 9. Sessions, access and safeguards

- **Session:** a signed, HTTP-only, `SameSite=Lax` cookie (Starlette `SessionMiddleware`, key from `SESSION_SECRET`) holding a random session id. Server-side session data (mode, budget counters, owned thread ids) lives in memory and expires after 2 hours of inactivity.
- **Thread ownership:** a thread id is a server-generated UUID, recorded in the session that created it. Reaching a thread from another session returns 404.
- **Unlock:** `POST /api/session/unlock {code}` compares the code with the SHA-256 hashes in `ACCESS_CODE_HASHES` using a constant-time comparison. Success turns on Live mode for that session. Each IP gets 5 attempts per 15 minutes.
- **Live budget per session** (configurable): 40 LLM calls and 60k total tokens, counted from the response usage metadata. When the budget runs out, the run ends with `budget_exhausted` and the session drops back to offline mode.
- **Mode is fixed per thread (builder's call).** A thread records `live` or `offline` when it is created. Graphs are compiled once per pattern and mode at startup, sharing the checkpointer, and a thread always runs on its own mode's graph.
  - Unlocking Live mid-chat doesn't change the open thread. The console shows "Live unlocked. Start a New chat to use the live model."
  - The budget is checked before every LLM call by a wrapper around the live model. If it runs out mid-run, the wrapper raises `BudgetExhausted`, and the runner catches it and emits `run_finished{status:"budget_exhausted"}`. The thread is then marked **closed**: its trace and messages stay visible, and the console offers New chat, which starts an offline thread. A closed thread rejects further runs with 409.
  - Any other run error closes the thread in the same way.
- **Global daily cap:** `LIVE_DAILY_TOKEN_CAP` (default 2M tokens). When it's reached, Live mode is unavailable to everyone until midnight UTC.
- **Rate limits:** 20 runs per minute per IP (an in-memory token bucket keyed on the `X-Forwarded-For` value set by Caddy, trusted only from the proxy), and one active run per session at a time (409 otherwise).
- **Input limits:** messages up to 2,000 characters; runs time out after 90 s; ReAct and Plan-and-Execute recursion limits are set as in §4.
- **Tools** have no network, filesystem or shell access (§4.7).
- **Secrets:** the API key exists only in the server's environment. It never reaches the browser, logs or error events.
- **Headers:** Caddy sets HSTS. The app sets a CSP that allows its own origin and the two pinned CDN hosts, plus `X-Content-Type-Options`.
- **Persistence:** the SQLite checkpointer file lives on a volume, and a background task deletes threads idle for more than 24 h. Sessions are in memory, so a restart sends every visitor back to offline mode. That is acceptable for a demo.

## 9a. Capacity

**Target:** 100–200 visitors at once, which means roughly 20–50 runs in progress at any moment, on one VM with **2 vCPU and 4 GB of RAM** (2 GB is the minimum). The work is mostly I/O-bound: runs spend their time waiting on the model API or on the simulated delay.

Requirements:
- **A large thread pool for sync nodes.** The graph nodes stay synchronous, so the existing agents and their CLIs (`graph.stream`) keep working. LangGraph runs sync nodes in the event loop's default executor. At startup the app installs a `ThreadPoolExecutor(max_workers=WORKER_THREADS)` (default 128) as that executor. The plan's first task verifies that `astream` really dispatches sync nodes there.
- **No blocking sleeps.** The offline `ScriptedChatModel` simulates latency with `asyncio.sleep` in its async path (`_agenerate`/`_astream`). If it's called synchronously from inside a node, it must not hold a worker thread longer than the simulated latency. The plan's spike picks the mechanism.
- **The guard runs off the event loop.** Embedding is CPU work, about 10–30 ms per prompt. It runs inside a sync node and so in the thread pool, and PyTorch releases the GIL. Torch's intra-op threads are capped (`torch.set_num_threads(2)`) so that guard calls running at the same time can't oversubscribe the CPUs.
- **SQLite tuned for concurrent writes:** `journal_mode=WAL`, `synchronous=NORMAL`, and one shared async connection. The 24-hour cleanup bounds the file's growth.
- **Provider limits:** a rate-limit error from the provider (`anthropic.RateLimitError` for Anthropic; any error a provider adapter maps to rate limiting) becomes a friendly "The model is busy, try again in a moment" `error` event. Retries stay as the SDK's defaults (2). The access codes and the daily cap keep Live traffic well below the account's rate limits.
- **SSE through Caddy:** `flush_interval -1` on the reverse proxy, plus a heartbeat comment (`: ping`) every 15 s so idle streams aren't dropped.

**Not covered:** high availability. One process on one VM means a restart interrupts the runs in progress and resets sessions. Scaling beyond about 1,000 visitors, or surviving a server failure, means a Postgres checkpointer, Redis for sessions and rate limits, and several workers. Sessions, the limiter and the checkpointer each sit behind a small interface so they can be swapped later, but that move isn't built in v1.

**Load test (acceptance criterion for milestone 3):** a Locust script in `loadtest/` simulates 200 users in offline mode. Each user opens a pattern, creates a thread and sends a message every 5–15 s, across all 7 patterns. Run for 5 minutes against the production container on the target VM size, it must show:
- 0 errors.
- p95 time from POST to first SSE event < 1 s.
- p95 time from POST to `run_finished` < the scripted latency + 2 s.
- App container RSS < 1.5 GB.

## 9b. Target host (decided 2026-11-23)

The person chose **Oracle Cloud Infrastructure (OCI) Always Free, Ampere A1**: up to **2 OCPUs and 12 GB RAM** for this instance. On A1, one OCPU is one physical Arm core, so this is 2 cores. It exceeds the §9a recommendation (2 vCPU / 4 GB), and the load test in §9a runs on this machine. Prefer the Johannesburg region (`af-johannesburg-1`) when A1 capacity is available there.

Deployment requirements that follow from this host (Milestone 4, "hardening + deploy"):
- **ARM64 images:**
  - Build the image for `linux/arm64`, either on the VM itself or with `docker buildx build --platform linux/arm64`.
  - The base images (`python:3.x-slim`, `caddy`) are multi-architecture.
  - All Python dependencies have aarch64 wheels: torch, sentence-transformers, langgraph, fastapi, uvicorn and aiosqlite.
  - The default PyPI `torch` wheel on aarch64 is already CPU-only, so the "CPU-only PyTorch" step needs no special index there. Keep the x86 path working for local builds.
- **Ports open twice:**
  - Allow TCP 80 and 443 in the VCN security list or network security group.
  - Also allow them in the VM's own firewall: OCI's Ubuntu and Oracle Linux images block inbound ports by default.
  - Document both steps, plus SSH (22) restricted to the person's IP.
- **Idle reclamation:**
  - Oracle's published policy lets it reclaim Always Free compute that stays idle over 7 days. The low-utilisation thresholds cover CPU, network and, for A1, memory.
  - A quiet demo can look idle, so the deploy guide recommends upgrading the tenancy to Pay-As-You-Go. Always Free resources stay free, and the reclamation no longer applies.
  - Re-check the current thresholds in Oracle's docs at deploy time.
- **Capacity errors:** A1 launches can fail with "out of host capacity" in busy regions. The deploy guide says to retry, or to try another availability domain or region.
- **Account limits:** the Always Free A1 allowance is 4 OCPUs / 24 GB across the tenancy. This instance uses about half of it.
- **Persistence:**
  - The SQLite checkpoint file and Caddy's certificate store live on named Docker volumes on the boot volume.
  - Note that a reclaimed or terminated instance loses them, which is acceptable for a demo.

## 10. Configuration (environment)

| Var | Default | Purpose |
|---|---|---|
| `LIVE_MODEL` | `anthropic:claude-haiku-5-5` | the web app's Live model, as a `provider:model` string for `init_chat_model` (§3a) |
| `ANTHROPIC_API_KEY` | none | the credential for `anthropic:` models. Live is disabled when the selected provider's credential is missing. Other providers use their own variables. |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | existing CLI setting, unchanged; used by `get_llm()` when no model string is given |
| `SESSION_SECRET` | random per start (dev only) | cookie signing; required in production |
| `ACCESS_CODE_HASHES` | empty | comma-separated SHA-256 hex digests |
| `LIVE_SESSION_CALLS` / `LIVE_SESSION_TOKENS` | 40 / 60000 | per-session budget |
| `LIVE_DAILY_TOKEN_CAP` | 2000000 | global cap |
| `CHECKPOINT_DB` | `./data/checkpoints.sqlite` | checkpointer path |
| `TRUST_PROXY` | `false` | read the client IP from `X-Forwarded-For` |
| `WORKER_THREADS` | `128` | size of the executor that runs sync graph nodes |

## 11. Code layout

```
src/agentic_solutions/
  common/llm.py                 # get_llm (unchanged API) + make_chat_model(model_string) + LLMFactory type
  agents/
    qa_agent/ chat_agent/ secure_chat_agent/ interrupt_chat_agent/   # + explanation.md each
    react_agent/        graph.py tools.py explanation.md __main__.py
    reflection_agent/   graph.py explanation.md __main__.py
    plan_execute_agent/ graph.py explanation.md __main__.py
  web/
    app.py              # create_app(): routes, middleware, static mount
    registry.py         # PatternSpec list
    runner.py           # astream -> trace events
    topology.py         # compiled graph -> {nodes, edges}
    serialize.py        # state/messages -> JSON-safe
    sessions.py         # session store, unlock, budgets
    limits.py           # rate limiter, daily cap
    offline.py          # ScriptedChatModel + per-pattern scripts
    static/             # index.html, app.js, graph.js, console.js, guide.js, styles.css
    __main__.py         # `python -m agentic_solutions.web` → uvicorn
Dockerfile
deploy/docker-compose.yml
deploy/Caddyfile
tests/  test_topology.py test_runner.py test_sessions.py test_api.py
        test_react_graph.py test_reflection_graph.py test_plan_execute_graph.py
        test_offline_scripts.py
```

New dependencies: `fastapi`, `uvicorn[standard]`, `langgraph-checkpoint-sqlite`, `aiosqlite`, `itsdangerous`; `httpx` (dev, for `TestClient`); `locust` (optional extra `load`). New agents are also registered in `langgraph.json` without a checkpointer, as the repo's convention requires.

## 12. Testing

Tests are written first (TDD) and run offline, with no network or API calls:

- **Agents:** for each new graph, routing tests for every branch with the scripted or fake models: the tool loop and its round-trip cap, Reflection stopping on score and on the iteration cap, Plan-and-Execute running each step once and then synthesizing. Calculator safety tests reject `__import__`, attribute access and huge exponents.
- **Topology:** the JSON for each registered pattern matches the graph's nodes and edges, with conditional edges flagged.
- **Runner:** the event sequence for a scripted run (`run_started` → `node_started`/`node_finished` pairs → `edge`s → `interrupt` or `run_finished`); serialization of messages and tool calls; a budget running out mid-run.
- **Model config:** `make_chat_model` parses provider strings; a missing provider package fails at startup; usage is counted from `usage_metadata`, with the conservative charge used when it's absent.
- **API:** catalog and detail endpoints; thread ownership (another session gets 404); unlock success, failure and lockout; the 409 for concurrent runs; the 413 or 422 for oversized input; the rate-limit 429; and that no secrets appear in responses.
- **Offline scripts:** every sample input of every pattern runs to `completed` or `paused` without reaching the default rule.
- **Load:** the Locust test and pass criteria in §9a (milestone 3, run manually against the container, not in `pytest`).
- **Frontend:** a manual checklist in the plan (all 7 patterns, both themes, mobile width). An automated browser smoke test can come later.

The existing tests must still pass unchanged.

## 13. Delivery milestones

1. **Core:** LLM injection in the existing agents, topology, runner, registry for patterns 1–4, the API, offline scripts, and the UI shell with trace, console and guide.
2. **New patterns:** ReAct, Reflection, Plan-and-Execute, with their explanations and scripts.
3. **Public hardening and deploy:** sessions, unlock, budgets, rate limits, CSP, Dockerfile, Compose and Caddy, the load test passing the §9a criteria, and a README section.

Follow-ups after v1: replaying runs from checkpoints, Router, Supervisor (multi-agent), parallel fan-out, guardrail + HITL combined, bring-your-own-key, LangSmith links.

## 14. Open questions

- The domain name for deployment, which Caddy needs. The host is decided (§9b). Needed in Milestone 4.
- The budget and cap defaults above are guesses, to tune after watching real usage.
