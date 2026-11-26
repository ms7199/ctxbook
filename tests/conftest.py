import importlib.util
import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ctxbook.storage.sqlite_store import SqliteStore


def _sqlite_vec_loads() -> bool:
    """Some Pythons (macOS system / python.org / GitHub runner builds) can't load extensions."""
    try:
        import sqlite_vec

        db = sqlite3.connect(":memory:")
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.close()
    except Exception:
        return False
    return True


FASTEMBED_INSTALLED = importlib.util.find_spec("fastembed") is not None
requires_fastembed = pytest.mark.skipif(
    not FASTEMBED_INSTALLED,
    reason="fastembed is not installable here (Intel Mac + Python 3.14+, decision D17)",
)

SQLITE_VEC_AVAILABLE = _sqlite_vec_loads()
requires_sqlite_vec = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE,
    reason="this Python cannot load SQLite extensions (ctxbook uses the numpy fallback)",
)

MODEL = "test-model"
DIM = 3
T0 = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

StoreFactory = Callable[..., SqliteStore]


@pytest.fixture(params=[pytest.param("sqlite-vec", marks=requires_sqlite_vec), "numpy"])
def backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def make_store(tmp_path: Path, backend: str) -> Iterator[StoreFactory]:
    """Open stores on one temp DB file, with the parametrised vector backend."""
    opened: list[SqliteStore] = []

    def factory(model: str | None = MODEL, dim: int | None = DIM) -> SqliteStore:
        store = SqliteStore(
            tmp_path / "memory.db",
            embed_model=model,
            embed_dim=dim,
            force_numpy=backend == "numpy",
        )
        opened.append(store)
        return store

    yield factory
    for store in opened:
        store.close()


@pytest.fixture
def store(make_store: StoreFactory) -> SqliteStore:
    return make_store()


def at(minutes: int) -> datetime:
    """A fixed timestamp ``minutes`` after T0."""
    return T0 + timedelta(minutes=minutes)
