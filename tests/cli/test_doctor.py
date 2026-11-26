from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlite_vec
from typer.testing import CliRunner

import ctxbook.cli.doctor as doctor
from ctxbook.cli.main import app
from ctxbook.core.service import MemoryService
from ctxbook.paths import resolve_paths
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0


def _by_name(home: Path, now: datetime = T0) -> dict[str, doctor.Check]:
    return {c.name: c for c in doctor.run_checks(resolve_paths({"CTXBOOK_HOME": str(home)}), now)}


def test_fresh_install_creates_nothing(home: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "not created yet" in result.output
    assert "not downloaded yet" in result.output
    assert not home.exists()  # doctor never creates files


def test_reports_counts_and_backend(home: Path) -> None:
    home.mkdir()
    store = SqliteStore(home / "memory.db", embed_model=None, embed_dim=None)
    service = MemoryService(store, None)
    old = service.save("Orders use Postgres", "shop", "a").memory_id
    service.update(old, "Orders use MongoDB", "a")
    store.close()

    checks = _by_name(home)

    assert "1 active" in checks["Database"].detail
    assert "1 superseded" in checks["Database"].detail
    assert checks["Vector search"].level == "ok"


def test_fallback_mode_is_reported(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_db: object) -> None:
        raise AttributeError("no enable_load_extension")

    monkeypatch.setattr(sqlite_vec, "load", broken)

    check = _by_name(home)["Vector search"]

    assert check.level == "warn"
    assert "pure-Python fallback" in check.detail


def test_missing_embeddings_platform_is_explained(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "fastembed_installed", lambda: False)

    check = _by_name(home)["Embeddings"]

    assert check.level == "warn"
    assert "uvx --python 3.12" in check.detail


def test_old_pending_facts_are_listed(home: Path) -> None:
    home.mkdir()
    store = SqliteStore(home / "memory.db", embed_model=None, embed_dim=None)
    service = MemoryService(store, None, clock=lambda: T0)
    service.save("The orders service uses Postgres", "shop", "a")
    pending = service.save("The orders service uses MongoDB", "shop", "b").memory_id
    store.close()

    fresh = _by_name(home, now=T0 + timedelta(hours=2))
    stale = _by_name(home, now=T0 + timedelta(days=2))

    assert "Unresolved facts" not in fresh
    assert stale["Unresolved facts"].level == "warn"
    assert f"[{pending}]" in stale["Unresolved facts"].detail
