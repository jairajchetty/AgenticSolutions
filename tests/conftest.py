import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agentic_solutions.web.app import create_app
from agentic_solutions.web.config import Settings
from fakes import FakeEmbedder, make_guard

TEST_ERP_SECRET = "test-erp-approval-secret"


@pytest.fixture(scope="session")
def library_index(tmp_path_factory):
    """The real text, indexed once per session with the fake embedder (no model download)."""
    from agentic_solutions.mcp_servers.library.index import LibraryIndex
    from agentic_solutions.mcp_servers.library.text import TEXT_PATH

    index = LibraryIndex.open(tmp_path_factory.mktemp("library"), TEXT_PATH.read_text(encoding="utf-8"),
                              FakeEmbedder())
    yield index
    index.close()


@pytest.fixture(autouse=True)
def _shared_library(monkeypatch, library_index):
    """Every app in the tests uses the shared index: none builds the real one."""
    import agentic_solutions.web.app as app_module

    monkeypatch.setattr(app_module, "_open_library_index", lambda settings, stack: library_index)


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
