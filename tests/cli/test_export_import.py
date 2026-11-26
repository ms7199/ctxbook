import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ctxbook.cli.main import app
from ctxbook.core.service import MemoryService
from ctxbook.core.transfer import import_lines
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0


def _seed(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(home / "memory.db", embed_model=None, embed_dim=None)
    service = MemoryService(store, None)
    old = service.save("Orders use Postgres", "shop", "claude-code").memory_id
    service.update(old, "Orders use MongoDB", "cursor")
    gone = service.save("Temporary note to forget", "shop", "cursor").memory_id
    service.forget(gone, "cursor")
    service.save("User prefers short answers", "global", "claude-desktop")
    store.close()


def _snapshot(home: Path) -> list[tuple[object, ...]]:
    """Everything that must survive a round trip (ids may differ, so compare by content)."""
    store = SqliteStore(home / "memory.db", embed_model=None, embed_dim=None)
    by_id = {m.id: m for m in store.list_memories()}
    rows = []
    for m in by_id.values():
        successor = by_id[m.superseded_by].content if m.superseded_by else None
        events = [(e.action, e.old, e.new, e.source_app, e.created_at) for e in store.events(m.id)]
        kept_events = [e for e in events if e[0] != "imported"]
        rows.append(
            (
                m.content,
                m.scope,
                m.source_app,
                m.status,
                m.created_at,
                m.updated_at,
                successor,
                kept_events,
            )
        )
    store.close()
    return sorted(rows, key=repr)


def test_round_trip_preserves_everything(
    runner: CliRunner, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(home)
    export_file = tmp_path / "backup.jsonl"

    result = runner.invoke(app, ["export", str(export_file)])
    assert result.exit_code == 0, result.output

    other_home = tmp_path / "restored"
    monkeypatch.setenv("CTXBOOK_HOME", str(other_home))
    result = runner.invoke(app, ["import", str(export_file)])
    assert result.exit_code == 0, result.output
    assert "Imported 4 memories (0 already present)" in result.output

    assert _snapshot(other_home) == _snapshot(home)


def test_import_twice_adds_nothing(runner: CliRunner, home: Path, tmp_path: Path) -> None:
    _seed(home)
    export_file = tmp_path / "backup.jsonl"
    runner.invoke(app, ["export", str(export_file)])

    result = runner.invoke(app, ["import", str(export_file)])  # into the same DB

    assert "Imported 0 memories (4 already present)" in result.output


def test_restored_facts_are_searchable(runner: CliRunner, home: Path, tmp_path: Path) -> None:
    _seed(home)
    export_file = tmp_path / "backup.jsonl"
    runner.invoke(app, ["export", str(export_file)])
    restored = tmp_path / "restored"
    restored.mkdir()
    store = SqliteStore(restored / "memory.db", embed_model=None, embed_dim=None)

    import_lines(store, export_file.read_text().splitlines(), now=T0)
    found = MemoryService(store, None).search("orders", "shop").results
    store.close()

    assert [f.fact for f in found] == ["Orders use MongoDB"]


def test_export_to_stdout_has_header_and_records(runner: CliRunner, home: Path) -> None:
    _seed(home)

    result = runner.invoke(app, ["export"])

    lines = result.output.strip().splitlines()
    header = json.loads(lines[0])
    assert header["format"] == "ctxbook-export"
    assert header["schema_version"] == "1"
    assert len(lines) == 5
    assert json.loads(lines[1])["events"][0]["action"] == "created"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ('{"some": "json"}\n', "not a ctxbook export"),
        ('{"format": "ctxbook-export", "export_version": 99}\n', "not supported"),
        ('{"format": "ctxbook-export", "export_version": 1}\n{"id": "x"}\n', "Line 2"),
    ],
)
def test_bad_import_files_are_explained(
    runner: CliRunner, home: Path, tmp_path: Path, content: str, message: str
) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(content)

    result = runner.invoke(app, ["import", str(bad)])

    assert result.exit_code == 1
    assert message in result.output
