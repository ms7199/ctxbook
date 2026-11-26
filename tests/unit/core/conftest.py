from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ctxbook.config import Settings
from ctxbook.core.service import MemoryService
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0
from tests.fakes import FakeEmbedder


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock() -> Clock:
    return Clock()


ServiceFactory = Callable[..., MemoryService]


@pytest.fixture
def make_service(tmp_path: Path, clock: Clock) -> Iterator[ServiceFactory]:
    stores: list[SqliteStore] = []

    def factory(mode: str = "hybrid", settings: Settings | None = None) -> MemoryService:
        embedder = FakeEmbedder() if mode == "hybrid" else None
        store = SqliteStore(
            tmp_path / "m.db",
            embed_model=embedder.model_name if embedder else None,
            embed_dim=embedder.dim if embedder else None,
        )
        stores.append(store)
        return MemoryService(store, embedder, settings=settings, clock=clock)

    yield factory
    for store in stores:
        store.close()


@pytest.fixture(params=["hybrid", "keyword"])
def mode(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def service(make_service: ServiceFactory, mode: str) -> MemoryService:
    return make_service(mode)
