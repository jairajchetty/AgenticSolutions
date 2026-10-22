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
threatlibrary.json       # (in src/) attack phrases by category, used by the guard
tests/                   # offline tests using a fake LLM (no API calls)
langgraph.json           # registers graphs for `langgraph dev` (LangGraph Studio)
```

`chat_agent` uses `input()`, so it is CLI-only and is not registered in `langgraph.json` (it would hang in Studio until it moves to `interrupt()`).

Conventions: one folder per agent under `agents/`, each exporting a compiled `graph`; shared code goes in `common/`; each new agent is registered in `langgraph.json`.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # then add your ANTHROPIC_API_KEY
```

## Run

```powershell
python -m agentic_solutions.agents.qa_agent "What is LangGraph?"
python -m agentic_solutions.agents.chat_agent   # interactive; type "stop" to quit
python -m agentic_solutions.agents.secure_chat_agent   # same, with the threat guard
pytest
```

## Roadmap ideas

2. ~~Chat loop~~ (done: `chat_agent`); next, swap `input()` for `interrupt()` + a checkpointer
2. Tools + ReAct loop (conditional edges, `ToolNode`)
3. Memory/persistence (checkpointers, threads)
4. Human-in-the-loop (`interrupt`)
5. Multi-agent / supervisor and subgraphs
6. Streaming, LangGraph Studio, tracing with LangSmith
