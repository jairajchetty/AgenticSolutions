"""Run the web app: ``python -m agentic_solutions.web``.

One worker only: thread ownership and run slots are kept in memory (spec §3).
Proxy headers are off, so no request header can change who the peer seems to
be (model picker access check).
"""
import uvicorn

from .config import Settings

if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run("agentic_solutions.web.app:create_app", factory=True, host=settings.host, port=settings.port, workers=1,
                proxy_headers=False)
