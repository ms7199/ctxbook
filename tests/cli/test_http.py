"""Step 5.2: Streamable HTTP keeps the SDK's DNS-rebinding protection (CLAUDE.md section 5)."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp import Client
from starlette.applications import Starlette
from starlette.testclient import TestClient

from ctxbook.core.service import MemoryService
from ctxbook.server.app import build_server
from ctxbook.storage.sqlite_store import SqliteStore

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"},
    },
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[Starlette]:
    store = SqliteStore(tmp_path / "m.db", embed_model=None, embed_dim=None)
    # Same call `ctxbook serve --transport http` makes internally (host="127.0.0.1").
    yield build_server(MemoryService(store, None)).streamable_http_app(host="127.0.0.1")
    store.close()


def test_bad_host_header_rejected(http_app: Starlette) -> None:
    with TestClient(http_app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/mcp", json=INIT, headers={**HEADERS, "Host": "evil.example"})
    assert response.status_code == 421


def test_bad_origin_rejected(http_app: Starlette) -> None:
    with TestClient(http_app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/mcp", json=INIT, headers={**HEADERS, "Origin": "http://evil.example"}
        )
    assert response.status_code == 403


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.anyio
async def test_real_http_server_round_trip(home: Path) -> None:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "ctxbook", "serve", "--transport", "http", "--port", str(port),
         "--no-embeddings"],
        env={**os.environ, "CTXBOOK_HOME": str(home)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )  # fmt: skip
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        else:
            pytest.fail("HTTP server did not start")

        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            await client.call_tool("save_memory", {"content": "Uses HTTP mode", "scope": "s"})
            found = await client.call_tool("search_memory", {"query": "http mode", "scope": "s"})
        assert found.structured_content["results"][0]["fact"] == "Uses HTTP mode"  # type: ignore[index]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
