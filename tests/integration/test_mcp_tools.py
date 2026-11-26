from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import Implementation

from ctxbook.config import Settings
from ctxbook.core.service import MemoryService
from ctxbook.models import DATA_NOTE
from ctxbook.rules import MEMORY_RULE
from ctxbook.server.app import build_server
from ctxbook.storage.sqlite_store import SqliteStore

pytestmark = pytest.mark.anyio

TOOLS = {
    "save_memory",
    "search_memory",
    "resolve_memory",
    "update_memory",
    "forget_memory",
    "get_fact_history",
}
CLAUDE_CODE = Implementation(name="claude-code", version="1.0")


async def _call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
    result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    assert result.structured_content is not None, f"{tool} returned no structured content"
    return result.structured_content


async def test_exactly_six_tools_with_prompt_style_descriptions(server: MCPServer) -> None:
    async with Client(server) as client:
        tools = (await client.list_tools()).tools

    assert {t.name for t in tools} == TOOLS
    for tool in tools:
        assert "Do NOT" in (tool.description or ""), tool.name
        assert tool.output_schema is not None, tool.name
        props = tool.input_schema["properties"]
        assert "ctx" not in props, tool.name
        assert all("description" in p for p in props.values()), tool.name


async def test_read_only_and_destructive_hints(server: MCPServer) -> None:
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert tools["search_memory"].annotations.read_only_hint is True  # type: ignore[union-attr]
    assert tools["get_fact_history"].annotations.read_only_hint is True  # type: ignore[union-attr]
    assert tools["forget_memory"].annotations.destructive_hint is True  # type: ignore[union-attr]


async def test_server_sends_memory_rule_as_instructions(server: MCPServer) -> None:
    async with Client(server) as client:
        assert client.instructions == MEMORY_RULE


async def test_full_lifecycle_through_mcp(server: MCPServer) -> None:
    async with Client(server, client_info=CLAUDE_CODE) as client:
        first = await _call(
            client, "save_memory", content="The orders service uses Postgres", scope="shop"
        )
        assert first["status"] == "saved"

        conflict = await _call(
            client, "save_memory", content="The orders service uses MongoDB", scope="shop"
        )
        assert conflict["status"] == "needs_resolution"
        assert conflict["candidates"][0]["id"] == first["memory_id"]

        resolved = await _call(
            client,
            "resolve_memory",
            pending_id=conflict["memory_id"],
            decision="update",
            target_id=first["memory_id"],
        )
        assert resolved["superseded_id"] == first["memory_id"]

        found = await _call(client, "search_memory", query="orders database", scope="shop")
        assert [r["fact"] for r in found["results"]] == ["The orders service uses MongoDB"]
        assert found["results"][0]["saved_by"] == "claude-code"
        assert found["results"][0]["note"] == DATA_NOTE

        updated = await _call(
            client,
            "update_memory",
            memory_id=conflict["memory_id"],
            new_content="The orders service uses DynamoDB",
        )
        history = await _call(client, "get_fact_history", memory_id=first["memory_id"])
        assert [v["fact"] for v in history["versions"]] == [
            "The orders service uses Postgres",
            "The orders service uses MongoDB",
            "The orders service uses DynamoDB",
        ]
        assert history["current_id"] == updated["memory_id"]

        await _call(client, "forget_memory", memory_id=updated["memory_id"])
        empty = await _call(client, "search_memory", query="orders database", scope="shop")
        assert empty["results"] == []


async def test_service_errors_reach_the_ai_with_their_message(server: MCPServer) -> None:
    async with Client(server) as client:
        missing = await client.call_tool("get_fact_history", {"memory_id": 404})
        too_long = await client.call_tool("save_memory", {"content": "x" * 5000, "scope": "s"})
        bad_decision = await client.call_tool(
            "resolve_memory", {"pending_id": 1, "decision": "merge"}
        )

    assert missing.is_error
    assert "No memory with id 404" in missing.content[0].text  # type: ignore[union-attr]
    assert too_long.is_error
    assert "limit is 1000" in too_long.content[0].text  # type: ignore[union-attr]
    assert bad_decision.is_error  # rejected by the input schema before reaching the service


async def test_huge_limit_is_capped_not_rejected(tmp_path: Path) -> None:
    # Keyword-only: facts sharing 1 of 4 meaningful words are deterministically "different".
    store = SqliteStore(tmp_path / "k.db", embed_model=None, embed_dim=None)
    server = build_server(MemoryService(store, None, Settings(token_budget=100_000)))
    async with Client(server) as client:
        statuses = [
            (
                await _call(
                    client, "save_memory", content=f"alpha{i} beta{i} gamma{i} database", scope="s"
                )
            )["status"]
            for i in range(25)
        ]
        found = await _call(client, "search_memory", query="database", scope="s", limit=500)
    store.close()

    assert statuses.count("saved") == 25
    assert len(found["results"]) == 20
