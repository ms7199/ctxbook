from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ctxbook.storage.sqlite_store import SqliteStore

MODEL = "test-model"
DIM = 3
T0 = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

StoreFactory = Callable[..., SqliteStore]


@pytest.fixture(params=["sqlite-vec", "numpy"])
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
