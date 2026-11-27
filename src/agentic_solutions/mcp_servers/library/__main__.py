"""Run the library MCP server on its own.

    python -m agentic_solutions.mcp_servers.library           # streamable HTTP, 127.0.0.1:8766/mcp
    python -m agentic_solutions.mcp_servers.library --stdio   # stdio, for MCP Inspector or desktop clients

Settings come from the environment: LIBRARY_DIR, LIBRARY_HOST, LIBRARY_PORT.
The first run builds the index (about a minute, including the model download).
"""
import argparse
import logging

from .config import LibrarySettings, open_index
from .server import build_server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m agentic_solutions.mcp_servers.library",
                                     description="Serve Paradise Lost over MCP.")
    parser.add_argument("--stdio", action="store_true", help="serve over stdio instead of streamable HTTP")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = LibrarySettings()
    index = open_index(settings)
    try:
        build_server(index, host=settings.host, port=settings.port).run(
            transport="stdio" if args.stdio else "streamable-http")
    finally:
        index.close()


if __name__ == "__main__":
    main()
