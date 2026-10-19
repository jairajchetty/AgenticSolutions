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
tests/                   # offline tests using a fake LLM (no API calls)
langgraph.json           # registers graphs for `langgraph dev` (LangGraph Studio)
```

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
pytest
```

## Roadmap ideas

2. Tools + ReAct loop (conditional edges, `ToolNode`)
3. Memory/persistence (checkpointers, threads)
4. Human-in-the-loop (`interrupt`)
5. Multi-agent / supervisor and subgraphs
6. Streaming, LangGraph Studio, tracing with LangSmith
