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
- **Offline mode** with scripted LLM responses (the default for anonymous visitors), and **Live mode** with real Claude, unlocked by an access code.
- Public-hosting safeguards: per-session budgets, per-IP rate limits, input limits, session expiry, and safe tools only.
- A Docker image with Docker Compose and Caddy (TLS) for a single VM.

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
                         LLM provider: ChatAnthropic (live) | ScriptedChatModel (offline)
```

Key decisions:
- **One process with in-process graphs.** No LangGraph Server, Redis or Postgres. Uvicorn runs a single worker, because the session store, budgets and rate limiter are in memory and SQLite has one writer.
- **The run endpoint streams its response.** `POST /api/threads/{tid}/runs` returns `text/event-stream`, and the browser reads it with `fetch()` plus a stream reader. `EventSource` can't send POST bodies. One request carries both the user's input and its trace.
- **Topology comes from the compiled graph** (`graph.get_graph()`), never written by hand, so the picture can't drift from the code.
- **The frontend uses no build step.** Libraries load from cdnjs/jsDelivr at pinned versions: Cytoscape.js with the dagre layout for the graph, marked + DOMPurify for Markdown. This keeps the repo Python-only; Node isn't needed.
- **The LLM is injected.** Each graph gets its model through a factory, so the same graph runs against Claude, the offline script, or a test fake.

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
- `agent` calls Claude with the tools bound (`bind_tools`). `tools` is LangGraph's prebuilt `ToolNode`, and the route after `agent` is `tools_condition`, re-labeled to return to `ask`.
- Tools are safe, deterministic and free of side effects:
  - `calculator(expression)`: arithmetic evaluated by an AST whitelist (no `eval`).
  - `current_time(timezone)`: uses `zoneinfo`.
  - `unit_convert(value, from_unit, to_unit)`: a small table of length, mass and temperature units.
  - `pattern_glossary(term)`: looks up a canned glossary of agent terms.
- The console shows each tool call as a chip (`🔧 calculator("17*23") → 391`).
- Each run is capped at 8 agent↔tools round trips (enforced with `recursion_limit`); hitting the cap ends the turn with a short message.

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
START → planner → executor ─(steps left?)→ executor
                      └─(done)→ synthesizer → END
```
- `planner` returns structured output with 2–5 steps (`Plan(steps: list[str])`). `executor` runs one step per visit, with the goal and previous results as context, and appends to `results`. `synthesizer` writes the final answer.
- The executor has the same tools as ReAct (one bounded tool round per step), so plans like "compute X, then compare Y" can use the calculator and unit converter.
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
- **Mode badge:** shows `Offline (scripted)` or `Live · Claude`, plus the remaining budget. 🔑 opens the unlock dialog.
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

- `ScriptedChatModel` is a `BaseChatModel` subclass. It supports `invoke`, streaming, `bind_tools` and `with_structured_output`. Each pattern supplies a **Script**: an ordered list of rules (`match` on the latest human text, or on the node or call kind) mapped to responses (text, an `AIMessage` with `tool_calls`, or a structured object). A default rule answers any unmatched input with something like: "(Offline demo) I'd normally ask Claude here. Unlock Live mode to try your own input."
- The scripts cover every sample input and exercise every branch: ReAct runs at least one tool loop, Reflection goes through one revise round before passing, and Plan-and-Execute runs a three-step plan.
- The guardrail always uses the real embedding guard (it is local and free).
- The same scripted models back the automated tests, so the offline demo can't silently break.

## 9. Sessions, access and safeguards

- **Session:** a signed, HTTP-only, `SameSite=Lax` cookie (Starlette `SessionMiddleware`, key from `SESSION_SECRET`) holding a random session id. Server-side session data (mode, budget counters, owned thread ids) lives in memory and expires after 2 hours of inactivity.
- **Thread ownership:** a thread id is a server-generated UUID, recorded in the session that created it. Reaching a thread from another session returns 404.
- **Unlock:** `POST /api/session/unlock {code}` compares the code with the SHA-256 hashes in `ACCESS_CODE_HASHES` using a constant-time comparison. Success turns on Live mode for that session. Each IP gets 5 attempts per 15 minutes.
- **Live budget per session** (configurable): 40 LLM calls and 60k total tokens, counted from the response usage metadata. When the budget runs out, the run ends with `budget_exhausted` and the session drops back to offline mode.
- **Global daily cap:** `LIVE_DAILY_TOKEN_CAP` (default 2M tokens). When it's reached, Live mode is unavailable to everyone until midnight UTC.
- **Rate limits:** 20 runs per minute per IP (an in-memory token bucket keyed on the `X-Forwarded-For` value set by Caddy, trusted only from the proxy), and one active run per session at a time (409 otherwise).
- **Input limits:** messages up to 2,000 characters; runs time out after 90 s; ReAct and Plan-and-Execute recursion limits are set as in §4.
- **Tools** have no network, filesystem or shell access (§4.7).
- **Secrets:** the API key exists only in the server's environment. It never reaches the browser, logs or error events.
- **Headers:** Caddy sets HSTS. The app sets a CSP that allows its own origin and the two pinned CDN hosts, plus `X-Content-Type-Options`.
- **Persistence:** the SQLite checkpointer file lives on a volume, and a background task deletes threads idle for more than 24 h. Sessions are in memory, so a restart sends every visitor back to offline mode. That is acceptable for a demo.

## 10. Configuration (environment)

| Var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Live mode (absent → Live disabled) |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | existing setting, unchanged |
| `SESSION_SECRET` | random per start (dev only) | cookie signing; required in production |
| `ACCESS_CODE_HASHES` | empty | comma-separated SHA-256 hex digests |
| `LIVE_SESSION_CALLS` / `LIVE_SESSION_TOKENS` | 40 / 60000 | per-session budget |
| `LIVE_DAILY_TOKEN_CAP` | 2000000 | global cap |
| `CHECKPOINT_DB` | `./data/checkpoints.sqlite` | checkpointer path |
| `TRUST_PROXY` | `false` | read the client IP from `X-Forwarded-For` |

## 11. Code layout

```
src/agentic_solutions/
  common/llm.py                 # get_llm (unchanged API) + LLMFactory type
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

New dependencies: `fastapi`, `uvicorn[standard]`, `langgraph-checkpoint-sqlite`, `aiosqlite`, `itsdangerous`; `httpx` (dev, for `TestClient`). New agents are also registered in `langgraph.json` without a checkpointer, as the repo's convention requires.

## 12. Testing

Tests are written first (TDD) and run offline, with no network or API calls:

- **Agents:** for each new graph, routing tests for every branch with the scripted or fake models: the tool loop and its round-trip cap, Reflection stopping on score and on the iteration cap, Plan-and-Execute running each step once and then synthesizing. Calculator safety tests reject `__import__`, attribute access and huge exponents.
- **Topology:** the JSON for each registered pattern matches the graph's nodes and edges, with conditional edges flagged.
- **Runner:** the event sequence for a scripted run (`run_started` → `node_started`/`node_finished` pairs → `edge`s → `interrupt` or `run_finished`); serialization of messages and tool calls; a budget running out mid-run.
- **API:** catalog and detail endpoints; thread ownership (another session gets 404); unlock success, failure and lockout; the 409 for concurrent runs; the 413 or 422 for oversized input; the rate-limit 429; and that no secrets appear in responses.
- **Offline scripts:** every sample input of every pattern runs to `completed` or `paused` without reaching the default rule.
- **Frontend:** a manual checklist in the plan (all 7 patterns, both themes, mobile width). An automated browser smoke test can come later.

The existing tests must still pass unchanged.

## 13. Delivery milestones

1. **Core:** LLM injection in the existing agents, topology, runner, registry for patterns 1–4, the API, offline scripts, and the UI shell with trace, console and guide.
2. **New patterns:** ReAct, Reflection, Plan-and-Execute, with their explanations and scripts.
3. **Public hardening and deploy:** sessions, unlock, budgets, rate limits, CSP, Dockerfile, Compose and Caddy, and a README section.

Follow-ups after v1: replaying runs from checkpoints, Router, Supervisor (multi-agent), parallel fan-out, guardrail + HITL combined, bring-your-own-key, LangSmith links.

## 14. Open questions

- The domain and host for deployment. They aren't needed until milestone 3, and Caddy needs only a domain name.
- The budget and cap defaults above are guesses, to tune after watching real usage.
