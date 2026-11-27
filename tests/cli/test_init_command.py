"""`ctxbook init` end to end through the real CLI, on a fake home folder."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ctxbook.cli.setup.env as setup_env
from ctxbook.cli.main import app


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    user_home = tmp_path / "user"
    (user_home / ".cursor").mkdir(parents=True)
    (user_home / ".gemini").mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))  # Windows
    tools = {"uvx": "/fake/bin/uvx"}
    monkeypatch.setattr(setup_env.shutil, "which", tools.get)
    return user_home


def test_init_then_uninstall(runner: CliRunner, fake_home: Path) -> None:
    result = runner.invoke(
        app, ["init", "--yes", "--no-embeddings", "--source", "git+https://example.com/ctxbook"]
    )

    assert result.exit_code == 0, result.output
    entry = json.loads((fake_home / ".cursor/mcp.json").read_text())["mcpServers"]["ctxbook"]
    assert entry == {
        "command": "/fake/bin/uvx",
        "args": [
            "--managed-python",
            "--python",
            "3.12",
            "--from",
            "git+https://example.com/ctxbook",
            "ctxbook",
            "serve",
            "--no-embeddings",
        ],
    }
    assert "Manual steps:" in result.output  # Cursor user rule to paste
    assert "Restart your AI apps" in result.output

    doctor = runner.invoke(app, ["doctor"])
    assert "AI clients set up by init: Antigravity, Cursor" in doctor.output

    removed = runner.invoke(app, ["init", "--uninstall", "--yes"])
    assert removed.exit_code == 0, removed.output
    assert not (fake_home / ".cursor/mcp.json").exists()
    assert not (fake_home / ".gemini/AGENTS.md").exists()


def test_init_without_uv_explains(
    runner: CliRunner, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(setup_env.shutil, "which", lambda _name: None)

    result = runner.invoke(app, ["init", "--yes", "--no-embeddings"])

    assert result.exit_code == 1
    assert "uvx was not found" in result.output
    assert not (fake_home / ".cursor/mcp.json").exists()


def test_init_default_source_is_this_install(runner: CliRunner, fake_home: Path) -> None:
    runner.invoke(app, ["init", "--yes", "--no-embeddings"])

    args = json.loads((fake_home / ".cursor/mcp.json").read_text())["mcpServers"]["ctxbook"]["args"]
    source = args[args.index("--from") + 1]
    # Tests run from an editable checkout, so the source is this repository folder.
    assert Path(source) == Path(__file__).resolve().parents[2]
