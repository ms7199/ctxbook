from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp.server.mcpserver import MCPServer

from ctxbook.core.service import MemoryService
from ctxbook.server.app import build_server
from ctxbook.storage.sqlite_store import SqliteStore
from tests.fakes import FakeEmbedder


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server(tmp_path: Path) -> Iterator[MCPServer]:
    embedder = FakeEmbedder()
    store = SqliteStore(tmp_path / "m.db", embed_model=embedder.model_name, embed_dim=embedder.dim)
    yield build_server(MemoryService(store, embedder))
    store.close()
