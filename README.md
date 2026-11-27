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
  web/                   # Patterns Studio web app (FastAPI + static frontend)
    __main__.py          #    `python -m agentic_solutions.web` (uvicorn, 127.0.0.1:8000)
    app.py               #    API: patterns, threads, streamed runs
    registry.py          #    pattern catalog: one spec per runnable pattern
    runner.py            #    LangGraph stream output -> trace events
    threads.py           #    in-memory thread ownership per session
    topology.py          #    compiled graph -> nodes/edges JSON for the browser
    serialize.py         #    JSON-safe messages and state
    config.py            #    settings read from environment variables
    offline/             #    scripted chat model and canned replies (no API calls)
    static/              #    frontend: index.html plus plain JS/CSS, no build step
threatlibrary.json       # (in src/) attack phrases by category, used by the guard
tests/                   # offline tests using a fake LLM (no API calls)
langgraph.json           # registers graphs for `langgraph dev` (LangGraph Studio)
```

`chat_agent` and `secure_chat_agent` use `input()`, so they are CLI-only and are not registered in `langgraph.json` (they would hang in Studio). `interrupt_chat_agent` pauses with `interrupt()` instead, so it is registered and can run in Studio.

Each agent folder also has an `explanation.md`, which the web app shows as that pattern's Guide.

Conventions: one folder per agent under `agents/`, each exporting a compiled `graph`; shared code goes in `common/`; each new agent is registered in `langgraph.json`.

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

A browser UI that runs each pattern and animates its graph, trace timeline and state as it executes.

```bash
python -m agentic_solutions.web   # then open http://localhost:8000
```

This milestone has offline mode only: a scripted model replies, so no API key is needed and nothing costs money. Live mode with Claude arrives in a later milestone. The guardrail pattern still loads the embedding model on first start (see the note under Run).

Optional environment variables (read in `web/config.py`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `OFFLINE_LATENCY_SCALE` | `1.0` | Scales the scripted reply delays; `0` removes them |
| `CHECKPOINT_DB` | `./data/checkpoints.sqlite` | SQLite file for conversation checkpoints |
| `WORKER_THREADS` | `128` | Size of the worker thread pool |
| `SESSION_SECRET` | random per start | Signs session cookies; set it to keep sessions across restarts |

The server runs a single worker because thread ownership is kept in memory. Design and plan: `docs/superpowers/specs/2026-11-22-agentic-patterns-studio-design.md` and `docs/superpowers/plans/2026-11-22-patterns-studio-m1-core.md`.

## Roadmap ideas

2. ~~Chat loop~~ (done: `chat_agent`), ~~`interrupt()` + checkpointer~~ (done: `interrupt_chat_agent`); next, add the guard to the interrupt version
2. Tools + ReAct loop (conditional edges, `ToolNode`)
3. Memory/persistence (checkpointers, threads)
4. Human-in-the-loop (`interrupt`)
5. Multi-agent / supervisor and subgraphs
6. Streaming, LangGraph Studio, tracing with LangSmith
