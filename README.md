# AgenticSolutions

A learning repo for building agentic AI with [LangGraph](https://langchain-ai.github.io/langgraph/) and Claude, run locally.

## Writing Guidelines
- The audience are solution architects and enterprise architects
- The writing style should be professional, clear and concise.
- Avoid using jargon, technical detail should be just sufficient to explain the solution.
- Use plain direct language and short sentences
- Example for the Approval pattern "What it is" : "The Approval pattern requires a person to approve an action before it can be executed.

The agent can analyse information and prepare a recommendation, but it cannot perform the action. The workflow pauses until an authorised person approves, modifies, or rejects the proposal.

Only approved actions can be executed. Approval is enforced by the platform, ensuring that people remain accountable for important decisions."

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
- The About text (name, role and record) lives in `src/agentic_solutions/web/static/about.js`; it is the one place to edit to change them (the title block and the footer name are both rendered from it). `index.html` only holds a fallback copy of the footer name for when JavaScript is off, and its `<noscript>` line shows the address without JavaScript; edit both if the name or address changes. The email address is kept in parts and assembled at runtime, so it never appears whole in any served file; "Get in touch" opens a `mailto:` link and also shows the address as selectable text.
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
| Memory | What must it remember? | Session **(live)**, Episodic, Semantic (RAG) **(live)**, Knowledge Graph |
| Execution | How does it act and run? | Tool Use (opens ReAct), Routing, Workflow, Event Driven, Autonomous |
| Governance | How is it kept safe and accountable? | Guardrails **(live)**, Approval **(live)**, Audit, Review |

The taxonomy lives in `web/catalog.yaml`, loaded and checked by `web/catalog.py`. An entry is "live" when its `demo` id is a key of `registry.PATTERNS`; nothing else stores that status.

### The Guide format

Every `agents/<folder>/explanation.md` has the same seven `##` sections, in this order: What it is, When to use it, How it works, Design considerations, Trade-offs, Related patterns, and How this Studio implements it. The first six describe the pattern in general terms and would read the same in any framework. The seventh is specific to this Studio, with four `###` parts: Mapping (which node plays which role), Framework concepts, Key code (one fence of 25 lines or fewer, copied from the folder's `graph.py`) and Try this (inputs that work offline). The page shows that last section collapsed under "How this Studio implements it"; it opens with Enter or Space, and the open state is kept for the browser session across patterns.

The genericity rule: the title and sections 1 to 6 contain no backticks and no framework, protocol or vendor names or code identifiers. Those belong only in section 7. `tests/test_guides.py` enforces this with a denylist, along with the section order, the length (50 to 130 lines), and that Mapping names every node in the pattern's diagram.

### From skeleton to live demo

Each Guide-only pattern has a skeleton folder under `agents/` whose `graph.py` builds the pattern's real topology with empty nodes (`build_skeleton()`), which is what the diagram draws. To make one live:

1. Fill the folder's graph with real node logic, keeping the node names (the Guide and diagram refer to them). Like the live folders, give it a `build_graph(checkpointer=..., llm_factory=...)` and a module-level `graph = build_graph()`.
2. In `web/registry.py`, add a `_build_<id>(c: BuildContext)` factory that calls `build_graph` with `c.checkpointer` and `c.llm_factory`, and add a `_spec(...)` row to `PATTERNS` whose id equals the catalog entry's `demo` (for example `react`, `reflection` or `plan_execute`). Its arguments are the title, the summary, the mode (`"chat"` or `"trigger"`), the factory, the folder (whose `explanation.md` becomes the Guide) and the sample prompts.
3. Add an offline `Script` for the new id to `SCRIPTS` in `web/offline/scripts.py`, so the demo runs without an API key. Give it a rule for every backticked input in the Guide's "Try this" section: `tests/test_offline_scripts.py` sends each one to the script and fails if it falls through to the fallback.
4. Remove the folder's row from `SKELETONS` in `tests/test_skeletons.py`: those tests assert a skeleton has no `graph` export, which the live graph now has.
5. Update the folder's `explanation.md` section 7: drop the "this is a skeleton / placeholders" text, and replace its Key code with lines copied from the live `graph.py` (`tests/test_guides.py` keeps the fence at 25 lines or fewer).

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

## Choosing a model

The Studio runs offline by default. A scripted model replies, so no key is needed and nothing costs money. You can also run a conversation on a real model.

A "Model" menu in the header lists the choices. It appears only when you run the Studio on your own machine. The server must listen on a loopback address (your own machine), and the request must come from that machine. Open the page as `http://localhost:8000` or `http://127.0.0.1:8000`. The menu does not appear on a shared or public server. A later milestone will limit it to administrators.

Never put a proxy or tunnel in front of the Studio while a key is set. This includes a reverse proxy, ngrok, cloudflared and SSH tunnels. The Studio refuses requests that carry forwarding headers. A forwarder that hides itself cannot be detected, so anyone who reaches it could run a paid model. Public use waits for the administrator rule in Milestone 4.

### Keys

| Key | Adds |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude Haiku 5.5 |
| `OPENROUTER_API_KEY` | DeepSeek, through OpenRouter |

An entry appears in the menu only when its key is set. With neither key, the menu is hidden and the Studio stays offline. Put the keys in `.env`.

OpenRouter needs one extra package:

```bash
pip install -e '.[providers]'
```

If an OpenRouter entry is configured and the package is missing, the Studio refuses to start and says so.

### Changing the list

`STUDIO_MODELS` replaces the default entries. It is a JSON array. Each entry has four fields:

| Field | Meaning |
| --- | --- |
| `id` | A short unique name. `offline` is reserved. |
| `label` | The name shown in the menu. |
| `provider` | `anthropic` or `openrouter`. |
| `model` | The provider's model name. |

This example keeps Claude Haiku and adds a Qwen model through OpenRouter. The Qwen model name has not been checked; it shows the format only.

```bash
STUDIO_MODELS='[
  {"id":"claude-haiku","label":"Claude Haiku 5.5","provider":"anthropic","model":"claude-haiku-5-5"},
  {"id":"qwen","label":"Qwen (via OpenRouter)","provider":"openrouter","model":"qwen/qwen3-235b-a22b"}
]'
```

Check the model name on OpenRouter first. The model must support tool calls. The Studio refuses to start if the JSON is malformed, a field is missing, an id is repeated, or the provider is unknown.

### What OpenRouter is told

Every OpenRouter request says two things:

- Do not use hosts that collect or train on the data (`data_collection: deny`).
- Use only hosts that support every parameter in the request, including tools.

OpenRouter may still send the request to any other host that meets both rules. Set `OPENROUTER_ZDR=1` to allow only hosts with a zero data retention policy. With that set, fewer hosts qualify, and a request may fail when none does.

To label your traffic in OpenRouter, set `OPENROUTER_SITE_URL` and `OPENROUTER_APP_TITLE`. They are sent only when set.

### Address and port

| Setting | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | The address the server listens on |
| `PORT` | `8000` | The port the server listens on |

The menu works only when `HOST` is a loopback address (`127.0.0.1`, `::1` or `localhost`). If you set `HOST` to anything else, such as `0.0.0.0`, the menu is off and every conversation runs offline.

### How a choice applies

- A conversation keeps the model it started with.
- A change in the menu applies to your next chat. The page says so.
- Before a chat starts, the badge shows the model the next chat will use. Once it starts, the badge shows that chat's model.
- The choice is remembered for the browser session. If the model is no longer listed, the menu returns to Offline.

### Checked models

Each default model was checked live on 2026-11-25 with one Session turn and both Approval samples. Every run used tool calls and reached the expected result.

| Model | Result |
|---|---|
| Claude Haiku 5.5 (Anthropic) | Passed. It asks which item you mean when the request does not name one, so each Approval sample took two turns. |
| DeepSeek V4.1 Flash (`deepseek/deepseek-v4.1-flash`, via OpenRouter) | Passed. It chose the laptop itself and reached the approval card in one turn; it asked which keyboard. |

Qwen and Kimi were not needed. Check any model you add the same way before relying on it.

## Approval demo and the mock ERP

The Approval demo orders goods from a mock ERP (enterprise resource planning) system for a fictional South African company, priced in rand. The agent can search the catalogue, check budgets, get quotes and draft a requisition. It cannot place the order. Orders of R5,000 or less are approved by policy; larger orders pause for you to approve, edit or reject. The ERP is an MCP server, and it checks every approval itself.

### One-command run

```bash
python -m agentic_solutions.web   # then open http://localhost:8000/#/governance/approval
```

With `ERP_MCP_URL` unset, the Studio runs the ERP inside its own process, with a random approval secret for each start. There is nothing else to start.

### Running the ERP separately

Start the server, then point the Studio at it. Both processes must use the same `ERP_APPROVAL_SECRET`, because the Studio signs each approval and the ERP verifies it. They must also use the same `ERP_AUTO_APPROVE_LIMIT_ZAR`. The Studio's policy approves orders up to its limit, and the ERP refuses a policy approval over its own limit.

```bash
export ERP_APPROVAL_SECRET=<a long random string>
python -m agentic_solutions.mcp_servers.erp        # serves http://127.0.0.1:8765/mcp

# in a second terminal, with the same ERP_APPROVAL_SECRET
export ERP_MCP_URL=http://127.0.0.1:8765/mcp
python -m agentic_solutions.web
```

If `ERP_MCP_URL` is set without `ERP_APPROVAL_SECRET`, the Studio refuses to start. The ERP server also refuses to serve over HTTP without `ERP_APPROVAL_SECRET`.

To browse the server's tools in the MCP Inspector, run it over stdio instead:

```bash
python -m agentic_solutions.mcp_servers.erp --stdio
```

### Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `ERP_MCP_URL` | unset | Unset runs the ERP in-process; set it to use a separate server |
| `ERP_APPROVAL_SECRET` | random per start | Signs approvals; required when `ERP_MCP_URL` is set, and must match the server's |
| `ERP_AUTO_APPROVE_LIMIT_ZAR` | `5000` | Orders at or under this total are approved by policy |
| `ERP_DB` | `./data/erp.sqlite` | SQLite file for the ERP's data |
| `ERP_TENANT_TTL_HOURS` | `168` | How long a visitor's ERP data is kept after their last use |
| Server address | `127.0.0.1:8765`, path `/mcp` | Where `python -m agentic_solutions.mcp_servers.erp` listens |

### Command line

```bash
python -m agentic_solutions.agents.approval_agent
```

The CLI uses Claude, so it needs `ANTHROPIC_API_KEY`. It runs the ERP in-process unless `ERP_MCP_URL` is set, in which case `ERP_APPROVAL_SECRET` is required too. Larger orders stop and ask you to approve, edit or reject. Type "stop" to quit.

In `langgraph.json`, the `approval_agent` graph connects to a separate ERP server, so `langgraph dev` needs `ERP_MCP_URL` and `ERP_APPROVAL_SECRET` set (for example in `.env`).

## Semantic (RAG) demo and the library

The Semantic (RAG) demo answers questions about John Milton's *Paradise Lost* from a vector database. The poem is split into overlapping passages of about 20 lines within each Book and stored in Qdrant (local mode), each with a dense embedding (`BAAI/bge-small-en-v1.5`) and a BM25 keyword vector. Both are computed locally with `fastembed`, so no API key is needed. A `library` MCP server offers two read-only tools, `search_book` (hybrid search) and `read_passage` (lines by position). The agent must search before it answers, answers only from the passages, and cites the Book and lines. Line numbers follow this edition.

### First start

The first start builds the index: about 20 seconds to download the models and 30 to 60 seconds to embed the poem. Later starts reuse it while the text, chunking and models are unchanged; a change to any of them rebuilds it.

| Setting | Default | Purpose |
| --- | --- | --- |
| `LIBRARY_DIR` | `./data/library` | The Qdrant index (`qdrant/`), its fingerprint (`meta.json`) and the embedding models (`models/`) |
| Server address | `127.0.0.1:8766`, path `/mcp` | Where `python -m agentic_solutions.mcp_servers.library` listens (`LIBRARY_HOST`, `LIBRARY_PORT`) |

Qdrant's local mode lets one process use an index folder at a time. To run the standalone library server while the Studio is running, give it its own `LIBRARY_DIR`; it builds its own index there on its first start.

### The text

The committed text is `mcp_servers/library/texts/paradise-lost.txt`: 12 Books, one verse line per line. It was made once from the Planet eBook PDF, which is not committed:

```bash
pip install -e '.[prep]'
python tools/prepare_paradise_lost.py data/books/paradise-lost.pdf
```

## Roadmap ideas

2. ~~Chat loop~~ (done: `chat_agent`), ~~`interrupt()` + checkpointer~~ (done: `interrupt_chat_agent`); next, add the guard to the interrupt version
2. Tools + ReAct loop (conditional edges, `ToolNode`)
3. Memory/persistence (checkpointers, threads)
4. Human-in-the-loop (`interrupt`)
5. Multi-agent / supervisor and subgraphs
6. Streaming, LangGraph Studio, tracing with LangSmith
