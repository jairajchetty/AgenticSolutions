"""Run the mock ERP MCP server.

    python -m agentic_solutions.mcp_servers.erp           # streamable HTTP, 127.0.0.1:8765/mcp
    python -m agentic_solutions.mcp_servers.erp --stdio   # stdio, for MCP Inspector or desktop clients

Settings come from the environment (ERP_DB, ERP_APPROVAL_SECRET,
ERP_AUTO_APPROVE_LIMIT_ZAR, ERP_TENANT_TTL_HOURS, ERP_HOST, ERP_PORT). Over HTTP,
ERP_APPROVAL_SECRET is required; over stdio it defaults to a random secret.
"""

import argparse
import logging
import os

from .config import ErpSettings
from .server import build_server
from .store import ErpStore

log = logging.getLogger("agentic_solutions.mcp_servers.erp")
NO_HTTP_SECRET = "ERP_APPROVAL_SECRET must be set to serve over HTTP; the Studio must use the same value."


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m agentic_solutions.mcp_servers.erp",
                                     description="Serve the mock ERP over MCP.")
    parser.add_argument("--stdio", action="store_true",
                        help="serve over stdio instead of streamable HTTP")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Over HTTP the Studio is another process, so it must sign approvals with
    # the same secret: a random one here would refuse every order. Over stdio
    # (MCP Inspector, desktop clients) a random per-start secret is fine.
    if not args.stdio and not os.environ.get("ERP_APPROVAL_SECRET"):
        parser.exit(2, f"{parser.prog}: {NO_HTTP_SECRET}\n")
    settings = ErpSettings.from_env()
    store = ErpStore(settings.db, secret=settings.secret, auto_limit_zar=settings.auto_limit_zar,
                     tenant_ttl_hours=settings.tenant_ttl_hours)
    try:
        server = build_server(store, settings)
        if args.stdio:
            server.run(transport="stdio")
        else:
            log.info("ERP MCP server on http://%s:%s%s", settings.host, settings.port,
                     server.settings.streamable_http_path)
            server.run(transport="streamable-http")
    finally:
        store.close()


if __name__ == "__main__":
    main()
