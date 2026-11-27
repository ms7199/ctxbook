"""Steps 6.2-6.7: client adapters, the init flow, and an exact uninstall."""

import json
from pathlib import Path

import pytest

from ctxbook.cli.setup.env import CommandResult
from ctxbook.cli.setup.files import END, START, ConfigFileError
from ctxbook.cli.setup.run import load_manifest, run_init, run_uninstall
from ctxbook.rules import MEMORY_RULE
from tests.cli.setup.conftest import CLAUDE, UVX, FakeMachine

COMMAND = [UVX, "--managed-python", "--python", "3.12", "--from", "ctxbook", "ctxbook", "serve"]
ENTRY = {"command": UVX, "args": COMMAND[1:]}


def _init(machine: FakeMachine, data_dir: Path, **kw: object) -> tuple[list[object], list[str]]:
    out: list[str] = []
    args = {"allow_tools": False, "yes": True, "confirm": lambda _q: True, "echo": out.append}
    args.update(kw)
    plans = run_init(machine.env, data_dir, COMMAND, **args)  # type: ignore[arg-type]
    return plans, out


def _uninstall(machine: FakeMachine, data_dir: Path) -> list[str]:
    out: list[str] = []
    run_uninstall(machine.env, data_dir, yes=True, confirm=lambda _q: True, echo=out.append)
    return out


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


# ── 6.2 Claude Code ──────────────────────────────────────────────────────────


def test_claude_code_with_cli_runs_claude_mcp_add(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("claude-code")
    machine.on_path["claude"] = CLAUDE

    _init(machine, data_dir)

    assert machine.ran == [[CLAUDE, "mcp", "add", "--scope", "user", "ctxbook", "--", *COMMAND]]
    rules = (machine.home / ".claude" / "CLAUDE.md").read_text()
    assert rules == f"{START}\n{MEMORY_RULE.rstrip()}\n{END}\n"
    assert not (machine.home / ".claude.json").exists()  # never hand-edited


def test_claude_code_already_registered_is_fine(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("claude-code")
    machine.on_path["claude"] = CLAUDE
    duplicate = "MCP server ctxbook already exists in user config"
    machine.reply = lambda _argv: CommandResult(1, duplicate)

    _init(machine, data_dir)  # does not raise

    assert all(c.kind != "command" for c in load_manifest(data_dir).changes)


def test_claude_code_without_cli_prints_the_command(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("claude-code")

    plans, _ = _init(machine, data_dir)

    assert machine.ran == []
    [note] = plans[0].notes  # type: ignore[attr-defined]
    assert "claude mcp add --scope user ctxbook -- /opt/uv/bin/uvx --managed-python" in note
    assert (machine.home / ".claude" / "CLAUDE.md").exists()  # rule still written


def test_claude_code_allow_tools(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("claude-code")
    settings = machine.home / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "model": "opus"}))

    _init(machine, data_dir, allow_tools=True)

    data = _json(settings)
    assert data["permissions"] == {"allow": ["Bash(ls)", "mcp__ctxbook__*"]}
    assert data["model"] == "opus"


# ── 6.3 Claude Desktop ───────────────────────────────────────────────────────


def test_claude_desktop_macos_merges_config(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("claude-desktop")
    config = machine.home / "Library/Application Support/Claude/claude_desktop_config.json"
    config.write_text(json.dumps({"mcpServers": {"github": {"command": "gh"}}}))

    plans, _ = _init(machine, data_dir)

    assert _json(config)["mcpServers"] == {"github": {"command": "gh"}, "ctxbook": ENTRY}
    assert "restart" in plans[0].notes[0]  # type: ignore[attr-defined]


def test_claude_desktop_windows_uses_appdata(machine: FakeMachine, data_dir: Path) -> None:
    machine.system = "Windows"
    machine.install("claude-desktop-win")

    _init(machine, data_dir)

    config = machine.home / "AppData/Roaming/Claude/claude_desktop_config.json"
    assert _json(config) == {"mcpServers": {"ctxbook": ENTRY}}


def test_claude_desktop_not_on_linux(machine: FakeMachine, data_dir: Path) -> None:
    machine.system = "Linux"
    machine.install("claude-desktop")  # even if a folder with that name exists

    plans, out = _init(machine, data_dir)

    assert plans == []
    assert any("No supported AI client found" in line for line in out)


# ── 6.4 Cursor and 6.5 Antigravity ───────────────────────────────────────────


def test_cursor_registers_server_and_prints_rule(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("cursor")

    plans, _ = _init(machine, data_dir)

    assert _json(machine.home / ".cursor/mcp.json") == {"mcpServers": {"ctxbook": ENTRY}}
    assert MEMORY_RULE in plans[0].notes[0]  # type: ignore[attr-defined]
    assert not (machine.home / ".cursor/rules").exists()  # no project files touched


def test_antigravity_config_and_agents_md(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("antigravity")
    agents = machine.home / ".gemini/AGENTS.md"
    agents.write_text("# My agent rules\n")

    _init(machine, data_dir)

    assert _json(machine.home / ".gemini/config/mcp_config.json") == {
        "mcpServers": {"ctxbook": ENTRY}
    }
    text = agents.read_text()
    assert text.startswith("# My agent rules\n")
    assert START in text and MEMORY_RULE.splitlines()[0] in text


# ── 6.6 the flow ─────────────────────────────────────────────────────────────


def test_declining_changes_nothing(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("cursor", "antigravity")

    plans, out = _init(machine, data_dir, yes=False, confirm=lambda _q: False)

    assert plans == []
    assert "Nothing was changed." in out
    assert not (machine.home / ".cursor/mcp.json").exists()
    assert not (machine.home / ".gemini/AGENTS.md").exists()
    assert not data_dir.exists()


def test_preview_lists_every_change_before_asking(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("cursor", "antigravity")
    asked: list[str] = []

    def confirm(question: str) -> bool:
        asked.append(question)
        return False

    _, out = _init(machine, data_dir, yes=False, confirm=confirm)

    text = "\n".join(out)
    assert "register the server in ~/.cursor/mcp.json" in text
    assert "add the memory rule in ~/.gemini/AGENTS.md" in text
    assert "Not found: Claude Code, Claude Desktop" in text
    assert asked == ["Apply these changes?"]


def test_running_twice_changes_nothing_and_keeps_first_backup(
    machine: FakeMachine, data_dir: Path
) -> None:
    machine.install("cursor")
    config = machine.home / ".cursor/mcp.json"
    config.write_text('{"mcpServers": {}, "x": 1}')
    _init(machine, data_dir)
    first = load_manifest(data_dir).changes[0]
    after_first = config.read_bytes()

    _, out = _init(machine, data_dir)

    assert "Everything is already set up; nothing to change." in "\n".join(out)
    assert config.read_bytes() == after_first
    assert load_manifest(data_dir).changes == [first]
    assert Path(first.backup).read_text() == '{"mcpServers": {}, "x": 1}'  # type: ignore[arg-type]


def test_malformed_config_is_left_untouched(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("cursor")
    config = machine.home / ".cursor/mcp.json"
    config.write_text('{"mcpServers": {,}')

    with pytest.raises(ConfigFileError, match="not valid JSON"):
        _init(machine, data_dir)

    assert config.read_text() == '{"mcpServers": {,}'
    assert list(config.parent.glob("*.ctxbook-backup-*")) == []


# ── 6.7 uninstall ────────────────────────────────────────────────────────────


def test_uninstall_restores_every_file_byte_for_byte(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("claude-code", "claude-desktop", "cursor", "antigravity")
    machine.on_path["claude"] = CLAUDE
    originals = {
        machine.home / ".claude/CLAUDE.md": b"# Mine\r\n- tabs\r\n",
        machine.home / "Library/Application Support/Claude/claude_desktop_config.json": (
            b'{\n    "mcpServers": {"a": {"command": "a"}},\n    "x": [1,2]\n}'
        ),
        machine.home / ".gemini/AGENTS.md": b"keep me",
    }
    for path, content in originals.items():
        path.write_bytes(content)
    created = [machine.home / ".cursor/mcp.json", machine.home / ".gemini/config/mcp_config.json"]

    _init(machine, data_dir)
    assert all(p.exists() for p in created)
    out = _uninstall(machine, data_dir)

    for path, content in originals.items():
        assert path.read_bytes() == content, path
    assert not any(p.exists() for p in created)
    assert machine.ran[-1] == [CLAUDE, "mcp", "remove", "ctxbook", "--scope", "user"]
    assert not (data_dir / "init-manifest.json").exists()
    assert "Done." in out


def test_uninstall_keeps_edits_made_after_init(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("cursor", "claude-code")
    config = machine.home / ".cursor/mcp.json"
    rules = machine.home / ".claude/CLAUDE.md"
    _init(machine, data_dir)
    data = _json(config)
    data["mcpServers"]["mine"] = {"command": "x"}  # type: ignore[index]
    config.write_text(json.dumps(data))
    rules.write_text(rules.read_text() + "\n- my new rule\n")

    _uninstall(machine, data_dir)

    assert _json(config) == {"mcpServers": {"mine": {"command": "x"}}}
    assert START not in rules.read_text()
    assert "- my new rule" in rules.read_text()


def test_uninstall_without_manifest_still_removes_our_parts(
    machine: FakeMachine, data_dir: Path
) -> None:
    machine.install("antigravity")
    _init(machine, data_dir)
    (data_dir / "init-manifest.json").unlink()

    _uninstall(machine, data_dir)

    assert _json(machine.home / ".gemini/config/mcp_config.json") == {"mcpServers": {}}
    assert START not in (machine.home / ".gemini/AGENTS.md").read_text()


def test_uninstall_when_nothing_was_set_up(machine: FakeMachine, data_dir: Path) -> None:
    machine.install("cursor")

    out = _uninstall(machine, data_dir)

    assert "Nothing to remove" in out[-1]
