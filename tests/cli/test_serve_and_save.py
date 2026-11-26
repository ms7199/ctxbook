import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from typer.testing import CliRunner

from ctxbook.cli.main import app
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import requires_fastembed


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com"])
def test_http_refuses_non_local_hosts(runner: CliRunner, home: Path, host: str) -> None:
    result = runner.invoke(app, ["serve", "--transport", "http", "--host", host])

    assert result.exit_code == 1
    assert "needs auth, planned for v0.2" in result.output
    assert not (home / "memory.db").exists()  # refused before touching anything


@pytest.mark.anyio
async def test_serve_stdio_end_to_end(home: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ctxbook", "serve", "--no-embeddings"],
        env={**os.environ, "CTXBOOK_HOME": str(home)},
    )
    async with Client(params) as client:
        await client.call_tool("save_memory", {"content": "Deploys on Fridays", "scope": "shop"})
        found = await client.call_tool("search_memory", {"query": "deploys", "scope": "shop"})

    assert found.structured_content["results"][0]["fact"] == "Deploys on Fridays"  # type: ignore[index]
    assert (home / "memory.db").exists()


@requires_fastembed
def test_serve_explains_embedding_mismatch(runner: CliRunner, home: Path) -> None:
    home.mkdir(parents=True)
    SqliteStore(home / "memory.db", embed_model="some-other-model", embed_dim=768).close()

    result = runner.invoke(app, ["save", "x", "--scope", "s"])

    assert result.exit_code == 1
    assert "built with the embedding model some-other-model" in result.output


def test_save_command_outcomes(runner: CliRunner, home: Path) -> None:
    def save(text: str) -> str:
        result = runner.invoke(app, ["save", text, "--scope", "shop", "--no-embeddings"])
        assert result.exit_code == 0, result.output
        return result.output

    assert "Saved as memory 1" in save("The orders service uses Postgres")
    assert "Already stored as memory 1" in save("the orders service uses postgres.")
    conflict = save("The orders service uses MongoDB")
    assert "pending memory 2" in conflict
    assert "[1] The orders service uses Postgres" in conflict


def test_save_rejects_bad_input(runner: CliRunner, home: Path) -> None:
    result = runner.invoke(app, ["save", "   ", "--scope", "shop", "--no-embeddings"])

    assert result.exit_code == 1
    assert "empty" in result.output


def test_source_app_is_cli(runner: CliRunner, home: Path) -> None:
    runner.invoke(app, ["save", "Deploys on Fridays", "--scope", "s", "--no-embeddings"])

    store = SqliteStore(home / "memory.db", embed_model=None, embed_dim=None)
    assert store.get(1).source_app == "cli"  # type: ignore[union-attr]
    store.close()
