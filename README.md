# AgenticSolutions

A learning repo for building agentic AI with [LangGraph](https://langchain-ai.github.io/langgraph/) and Claude, run locally.

## Architecture

```
src/agentic_solutions/
  common/llm.py          # shared Claude factory (model, temperature, env)
  agents/
    qa_agent/            # 1. simplest graph: START -> answer -> END
      graph.py           #    State, node, edges, compile  (exports `graph`)
      __main__.py        #    CLI entrypoint
    chat_agent/          # 2. loop: ask -> answer -> ask ... until "stop"
      graph.py           #    cycle, conditional edge, message memory
      __main__.py        #    interactive CLI
    secure_chat_agent/   # 3. chat_agent + prompt-injection guard
      guard.py           #    embeds threatlibrary.json, cosine-similarity check
      graph.py           #    ask -> guard -> answer | refuse
      __main__.py        #    interactive CLI
    interrupt_chat_agent/ # 4. chat_agent again, but pauses with interrupt() + checkpointer
      graph.py           #    interrupt(), Command(resume=...), thread_id
      __main__.py        #    caller loop: run -> pause -> ask human -> resume
    <16 skeleton folders>/ # react, reflection, plan_execute, search, supervisor, swarm, hierarchy,
                         #   episodic_memory, semantic_memory, knowledge_graph, routing, workflow,
                         #   event_driven, autonomous, audit, review (each as `<name>_agent`):
                         #   graph.py (`build_skeleton()`: real topology, empty nodes) + explanation.md
  web/                   # Patterns Studio web app (FastAPI + static frontend)
    __main__.py          #    `python -m agentic_solutions.web` (uvicorn, 127.0.0.1:8000)
    app.py               #    API: patterns, threads, streamed runs
    registry.py          #    registry of runnable (live) patterns: one spec per demo
    catalog.py           #    the 21-pattern taxonomy; live/guide status derived from the registry
    runner.py            #    LangGraph stream output -> trace events
    threads.py           #    in-memory thread ownership per session
    topology.py          #    compiled graph -> nodes/edges JSON for the browser
    serialize.py         #    JSON-safe messages and state
    config.py            #    settings read from environment variables
    offline/             #    scripted chat model and canned replies (no API calls)
    static/              #    frontend: index.html plus plain JS/CSS, no build step
                         #    (router.js: hash routes; catalog.js: home and search)
threatlibrary.json       # (in src/) attack phrases by category, used by the guard
tests/                   # offline tests using a fake LLM (no API calls)
  js/                    #   Node unit tests for router.js and the catalog search (run by test_js.py)
langgraph.json           # registers graphs for `langgraph dev` (LangGraph Studio)
```

`chat_agent` and `secure_chat_agent` use `input()`, so they are CLI-only and are not registered in `langgraph.json` (they would hang in Studio). `interrupt_chat_agent` pauses with `interrupt()` instead, so it is registered and can run in Studio.

Each agent folder also has an `explanation.md`, which the web app shows as that pattern's Guide.

Conventions: one folder per agent under `agents/`, each exporting a compiled `graph` (the skeleton folders instead export `build_skeleton()` and are not registered in `langgraph.json`); shared code goes in `common/`; each new agent is registered in `langgraph.json`.

## Setup (WSL / Linux)

Keep the repo inside the WSL filesystem (e.g. `~/AgenticSolutions`), not under `/mnt/c/`, which is much slower for Python.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add your ANTHROPIC_API_KEY
```

Run `source .venv/bin/activate` again in each new terminal.

## Run

```bash
python -m agentic_solutions.agents.qa_agent "What is LangGraph?"
python -m agentic_solutions.agents.chat_agent   # interactive; type "stop" to quit
python -m agentic_solutions.agents.secure_chat_agent   # same, with the threat guard
python -m agentic_solutions.agents.interrupt_chat_agent # same loop, pauses via interrupt()
pytest
```

The first `secure_chat_agent` run downloads the `bge-small-en-v1.5` embedding model.

### LangGraph Studio

```bash
pip install "langgraph-cli[inmem]"
langgraph dev
```

`langgraph dev` prints a Studio URL; open it in your Windows browser (WSL forwards `localhost`).

## Patterns Studio (web app)

A browser UI with a catalog of 21 agentic patterns. The four that have a live demo run in a workbench that animates the graph, trace timeline and state as it executes; the rest show their graph and a written Guide until their demo is built.

```bash
python -m agentic_solutions.web   # then open http://localhost:8000
```

### Design

The interface uses the Blueprint design system (`docs/superpowers/specs/2026-11-23-blueprint-redesign-design.md`): navy drafting-grid pages, paper-coloured sheets, an amber accent for the active node, the current step and the one primary action, and a single theme with no dark-mode variant.

- Colour tokens, type and spacing are CSS custom properties in the `:root` block of `src/agentic_solutions/web/static/styles.css`.
- The About text (name, role and record) lives in `src/agentic_solutions/web/static/about.js`; it is the one place to edit to change them (the title block and the footer name are both rendered from it). The one other place is the `<noscript>` line in `index.html`, which shows the address without JavaScript and must be edited too if the address changes. The email address is kept in parts and assembled at runtime, so it never appears whole in any served file; "Get in touch" opens a `mailto:` link and also shows the address as selectable text.
- Fonts (Barlow Condensed and Public Sans) load from Google Fonts, so the page needs network access for them and falls back to system fonts without it.

### Catalog and routes

- `#/` is the catalog home: a hero with a search box ("remember users", "human sign-off", "HITL", "RAG" all find a pattern) above one catalog sheet of the five categories, plus a title block about the architect.
- `#/<category>/<pattern>` opens a pattern, e.g. `#/governance/approval`, with a breadcrumb and ←/→ buttons that step through that category (wrapping at the ends).
- A pattern with a live demo opens the purpose sheet, then the workbench (graph, timeline, state, console), then the rest of the guide. Any other pattern is Guide-only: the purpose sheet, then its static graph diagram, then the rest of the guide. Guide-only pages create no thread and make no `/runs` call.
- `Tool Use` is listed under Execution but opens the ReAct page; its status follows ReAct's.
- Old links still work: `#qa`, `#chat_loop`, `#guardrail` and `#human_in_loop` redirect to their new routes (a remembered conversation restores). An unknown route shows the catalog with a "That pattern wasn't found" notice.
- The catalog is served read-only at `GET /api/catalog` and `GET /api/catalog/<category>/<pattern>`.

### The 21 patterns

| Category | Question | Patterns |
| --- | --- | --- |
| Cognitive | How should the agent think? | ReAct, Reflection, Planning, Search |
| Collaboration | How many agents, and who leads? | Single Agent **(live)**, Supervisor, Swarm, Hierarchy |
| Memory | What must it remember? | Session **(live)**, Episodic, Semantic, Knowledge Graph |
| Execution | How does it act and run? | Tool Use (opens ReAct), Routing, Workflow, Event Driven, Autonomous |
| Governance | How is it kept safe and accountable? | Guardrails **(live)**, Approval **(live)**, Audit, Review |

The taxonomy lives in `web/catalog.py`. An entry is "live" when its `demo` id is a key of `registry.PATTERNS`; nothing else stores that status.

### From skeleton to live demo

Each Guide-only pattern has a skeleton folder under `agents/` whose `graph.py` builds the pattern's real topology with empty nodes (`build_skeleton()`), which is what the diagram draws. To make one live:

1. Fill the folder's graph with real node logic, keeping the node names (the Guide and diagram refer to them). Like the live folders, give it a `build_graph(checkpointer=..., llm_factory=...)` and a module-level `graph = build_graph()`.
2. In `web/registry.py`, add a `_build_<id>(c: BuildContext)` factory that calls `build_graph` with `c.checkpointer` and `c.llm_factory`, and add a `_spec(...)` row to `PATTERNS` whose id equals the catalog entry's `demo` (for example `react`, `reflection` or `plan_execute`). Its arguments are the title, the summary, the mode (`"chat"` or `"trigger"`), the factory, the folder (whose `explanation.md` becomes the Guide) and the sample prompts.
3. Add an offline `Script` for the new id to `SCRIPTS` in `web/offline/scripts.py`, so the demo runs without an API key. Give it a rule for every backticked input in the Guide's "Try this" section: `tests/test_offline_scripts.py` sends each one to the script and fails if it falls through to the fallback.
4. Remove the folder's row from `SKELETONS` in `tests/test_skeletons.py`: those tests assert a skeleton has no `graph` export, which the live graph now has.
5. Rewrite the folder's `explanation.md`: drop the "this is a skeleton / placeholders" text, and replace its Key code with lines copied from the live `graph.py` (`tests/test_guides.py` keeps the fence at 25 lines or fewer).

No edit to `catalog.py` is needed: the entry turns live and the page switches from Guide-only to the workbench.

### Running and configuring

This milestone has offline mode only: a scripted model replies, so no API key is needed and nothing costs money. Live mode with Claude arrives in a later milestone. The guardrail pattern still loads the embedding model on first start (see the note under Run).

Optional environment variables (read in `web/config.py`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `OFFLINE_LATENCY_SCALE` | `1.0` | Scales the scripted reply delays; `0` removes them |
| `CHECKPOINT_DB` | `./data/checkpoints.sqlite` | SQLite file for conversation checkpoints |
| `WORKER_THREADS` | `128` | Size of the worker thread pool |
| `SESSION_SECRET` | random per start | Signs session cookies; set it to keep sessions across restarts |

The server runs a single worker because thread ownership is kept in memory. Design and plan: `docs/superpowers/specs/2026-11-22-agentic-patterns-studio-design.md` and `docs/superpowers/plans/2026-11-22-patterns-studio-m1-core.md`; the catalog design is `docs/superpowers/specs/2026-11-22-pattern-catalog-menu-design.md`.

The frontend's pure logic (hash routing, catalog search) has Node unit tests in `tests/js`, run by `tests/test_js.py` as part of `pytest`. They need Node 21 or newer; with none found the test is skipped (set `NODE_BIN` to point at a specific binary).

## Roadmap ideas

2. ~~Chat loop~~ (done: `chat_agent`), ~~`interrupt()` + checkpointer~~ (done: `interrupt_chat_agent`); next, add the guard to the interrupt version
2. Tools + ReAct loop (conditional edges, `ToolNode`)
3. Memory/persistence (checkpointers, threads)
4. Human-in-the-loop (`interrupt`)
5. Multi-agent / supervisor and subgraphs
6. Streaming, LangGraph Studio, tracing with LangSmith
