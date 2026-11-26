"""Step 4.4: source_app comes from MCP client info, and is "unknown" when absent."""

from types import SimpleNamespace
from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import Implementation

from ctxbook.server.app import client_name

pytestmark = pytest.mark.anyio


def _ctx(client_params: Any) -> Any:
    return SimpleNamespace(session=SimpleNamespace(client_params=client_params))


@pytest.mark.parametrize(
    "params",
    [
        None,  # 2026-07-28 protocol: client info is optional
        SimpleNamespace(client_info=None),
        SimpleNamespace(client_info=SimpleNamespace(name="")),
        SimpleNamespace(client_info=SimpleNamespace(name="   ")),
    ],
)
def test_missing_client_info_is_unknown(params: Any) -> None:
    assert client_name(_ctx(params)) == "unknown"


def test_client_name_is_used_when_present() -> None:
    params = SimpleNamespace(client_info=SimpleNamespace(name="cursor"))
    assert client_name(_ctx(params)) == "cursor"


async def _saved_by(server: MCPServer, client: Client) -> str:
    async with client:
        await client.call_tool("save_memory", {"content": "Deploys on Fridays", "scope": "s"})
        found = await client.call_tool("search_memory", {"query": "deploys", "scope": "s"})
    return found.structured_content["results"][0]["saved_by"]  # type: ignore[index]


async def test_real_client_name_recorded(server: MCPServer) -> None:
    client = Client(server, client_info=Implementation(name="claude-code", version="1"))
    assert await _saved_by(server, client) == "claude-code"


async def test_sdk_default_client_name(server: MCPServer) -> None:
    assert await _saved_by(server, Client(server)) == "mcp"
