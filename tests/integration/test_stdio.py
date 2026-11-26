"""Step 4.6: the real stdio transport, with the server in its own process like a real client."""

import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from mcp.types import Implementation

pytestmark = pytest.mark.anyio

_SERVER = """
import sys
from ctxbook.core.service import MemoryService
from ctxbook.server.app import build_server
from ctxbook.storage.sqlite_store import SqliteStore
store = SqliteStore(sys.argv[1], embed_model=None, embed_dim=None)
build_server(MemoryService(store, None)).run()
"""


async def test_save_and_search_over_stdio(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", _SERVER, str(tmp_path / "m.db")],
        env={**os.environ},
    )
    async with Client(params, client_info=Implementation(name="cursor", version="1")) as client:
        saved = await client.call_tool(
            "save_memory", {"content": "Deploys happen on Fridays", "scope": "shop"}
        )
        found = await client.call_tool("search_memory", {"query": "deploys", "scope": "shop"})

    assert saved.structured_content["status"] == "saved"  # type: ignore[index]
    [fact] = found.structured_content["results"]  # type: ignore[index]
    assert (fact["fact"], fact["saved_by"]) == ("Deploys happen on Fridays", "cursor")
