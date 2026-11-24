"""Shared offline test helpers, re-exported so tests can `from fakes import ...`."""
from agentic_solutions.agents.approval_agent.erp import ErpUnavailable
from test_secure_chat_graph import FakeEncoder, LIBRARY, make_guard  # noqa: F401


class UnreachableErp:
    """An ERP client for tests that only build graphs: building never connects."""

    async def call(self, tool, args):
        raise ErpUnavailable("no ERP in this test")


def no_token(claims):
    raise AssertionError("this test must not issue approval tokens")
