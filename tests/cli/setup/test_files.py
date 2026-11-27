import json
from pathlib import Path

import pytest

from ctxbook.cli.setup.files import (
    END,
    START,
    ConfigFileError,
    backup,
    json_is_empty_shell,
    json_with_entry,
    json_with_list_item,
    json_without_entry,
    json_without_list_item,
    text_with_block,
    text_without_block,
    write_atomic,
)

KEYS = ("mcpServers", "ctxbook")
ENTRY = {"command": "/bin/uvx", "args": ["ctxbook", "serve"]}


def test_merge_keeps_other_servers_and_settings(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))

    new = json_with_entry(config, KEYS, ENTRY)

    data = json.loads(new)  # type: ignore[arg-type]
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["ctxbook"] == ENTRY


def test_merge_into_missing_or_empty_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    empty = tmp_path / "empty.json"
    empty.write_text("  \n")

    for path in (missing, empty):
        assert json.loads(json_with_entry(path, KEYS, ENTRY)) == {"mcpServers": {"ctxbook": ENTRY}}  # type: ignore[arg-type]


def test_merge_is_idempotent(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    write_atomic(config, json_with_entry(config, KEYS, ENTRY))  # type: ignore[arg-type]

    assert json_with_entry(config, KEYS, ENTRY) is None


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"mcpServers": ["list"]}'])
def test_malformed_config_is_refused(tmp_path: Path, content: str) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(content)

    with pytest.raises(ConfigFileError, match="not changed"):
        json_with_entry(config, KEYS, ENTRY)
    assert config.read_text() == content


def test_remove_entry_only_ours(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"other": {}, "ctxbook": ENTRY}}))

    remaining = json.loads(json_without_entry(config, KEYS))  # type: ignore[arg-type]

    assert remaining == {"mcpServers": {"other": {}}}
    assert json_without_entry(tmp_path / "none.json", KEYS) is None


def test_list_item_add_and_remove(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}))
    keys = ("permissions", "allow")

    write_atomic(settings, json_with_list_item(settings, keys, "mcp__ctxbook__*"))  # type: ignore[arg-type]
    allowed = json.loads(settings.read_text())["permissions"]["allow"]
    assert allowed == ["Bash(ls)", "mcp__ctxbook__*"]
    assert json_with_list_item(settings, keys, "mcp__ctxbook__*") is None

    write_atomic(settings, json_without_list_item(settings, keys, "mcp__ctxbook__*"))  # type: ignore[arg-type]
    assert json.loads(settings.read_text())["permissions"]["allow"] == ["Bash(ls)"]


def test_empty_shell_detection() -> None:
    assert json_is_empty_shell('{"mcpServers": {}}')
    assert not json_is_empty_shell('{"mcpServers": {"x": {}}}')
    assert not json_is_empty_shell('{"theme": "dark"}')


def test_rule_block_appended_refreshed_and_removed(tmp_path: Path) -> None:
    rules = tmp_path / "CLAUDE.md"
    original = "# My rules\n- be brief\n"
    rules.write_text(original)

    write_atomic(rules, text_with_block(rules, "RULE v1"))  # type: ignore[arg-type]
    assert rules.read_text() == f"{original}\n{START}\nRULE v1\n{END}\n"
    assert text_with_block(rules, "RULE v1") is None  # idempotent

    write_atomic(rules, text_with_block(rules, "RULE v2"))  # type: ignore[arg-type]
    assert rules.read_text().count(START) == 1
    assert "RULE v2" in rules.read_text()

    write_atomic(rules, text_without_block(rules))  # type: ignore[arg-type]
    assert rules.read_text() == original


def test_rule_block_in_new_file(tmp_path: Path) -> None:
    rules = tmp_path / "AGENTS.md"

    assert text_with_block(rules, "RULE") == f"{START}\nRULE\n{END}\n"
    assert text_without_block(rules) is None


def test_backup_copies_exactly(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_bytes(b'{"a": 1}\r\n')

    copy = backup(config)

    assert copy.read_bytes() == b'{"a": 1}\r\n'
    assert ".ctxbook-backup-" in copy.name
    assert copy.parent == config.parent
