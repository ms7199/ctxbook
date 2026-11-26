import logging
from pathlib import Path

import pytest
import sqlite_vec

from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0


def test_extension_failure_falls_back_to_numpy_with_one_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_load(_db: object) -> None:
        raise AttributeError("'sqlite3.Connection' object has no attribute 'enable_load_extension'")

    monkeypatch.setattr(sqlite_vec, "load", broken_load)

    with caplog.at_level(logging.WARNING):
        store = SqliteStore(tmp_path / "m.db", embed_model="m", embed_dim=3)

    assert store.vector_backend == "numpy"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "pure-Python vector search" in warnings[0].getMessage()

    memory_id = store.add(
        content="x", scope="s", source_app="a", status=Status.ACTIVE, now=T0, vector=[1, 0, 0]
    ).id
    assert store.vector_search([1, 0, 0], k=1, scopes=["s"], statuses=[Status.ACTIVE]) == [
        (memory_id, pytest.approx(1.0))
    ]
    store.close()


def test_switching_backend_reports_vectors_to_backfill(tmp_path: Path) -> None:
    """A DB written with sqlite-vec and reopened in fallback mode needs re-embedding."""
    path = tmp_path / "m.db"
    first = SqliteStore(path, embed_model="m", embed_dim=3)
    memory_id = first.add(
        content="x", scope="s", source_app="a", status=Status.ACTIVE, now=T0, vector=[1, 0, 0]
    ).id
    first.close()

    second = SqliteStore(path, embed_model="m", embed_dim=3, force_numpy=True)

    assert second.ids_missing_vectors() == [memory_id]
    second.close()
