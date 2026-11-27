import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agentic_solutions.web.app import create_app
from agentic_solutions.web.config import Settings
from fakes import make_guard

TEST_ERP_SECRET = "test-erp-approval-secret"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def app(tmp_path):
    # Every app test runs the in-process ERP, on its own database file.
    settings = Settings(session_secret="test-secret", offline_latency_scale=0, checkpoint_db=":memory:",
                        erp_db=str(tmp_path / "erp.sqlite"), erp_approval_secret=TEST_ERP_SECRET)
    return create_app(settings, checkpointer=InMemorySaver(), guard=make_guard())


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
