"""Run the web app: ``python -m agentic_solutions.web``.

One worker only: thread ownership and run slots are kept in memory (spec §3).
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("agentic_solutions.web.app:create_app", factory=True, host="127.0.0.1", port=8000, workers=1)
