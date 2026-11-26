import pytest

from ctxbook.core.service import MemoryService
from ctxbook.errors import NotFoundError, StaleStateError
from ctxbook.models import Status

PG = "The orders service uses Postgres"


def test_update_creates_new_version_and_supersedes_old(service: MemoryService) -> None:
    old = service.save(PG, "shop", "claude-code").memory_id

    result = service.update(old, "The orders service uses MongoDB", "cursor")

    assert result.status == "updated"
    assert result.superseded_id == old
    new = service._store.get(result.memory_id)
    assert new.status is Status.ACTIVE  # type: ignore[union-attr]
    assert new.scope == "shop"  # type: ignore[union-attr]
    assert new.source_app == "cursor"  # type: ignore[union-attr]
    assert service._store.get(old).superseded_by == result.memory_id  # type: ignore[union-attr]


def test_update_with_same_text_changes_nothing(service: MemoryService) -> None:
    old = service.save(PG, "shop", "a").memory_id

    result = service.update(old, "the orders service uses postgres!", "a")

    assert (result.status, result.memory_id) == ("unchanged", old)
    assert len(service._store.list_memories()) == 1


def test_update_of_superseded_fact_points_to_current(service: MemoryService) -> None:
    old = service.save(PG, "shop", "a").memory_id
    current = service.update(old, "Orders moved to MongoDB", "a").memory_id

    with pytest.raises(StaleStateError, match=f"current version is memory {current}"):
        service.update(old, "Orders moved to MySQL", "b")


def test_update_missing(service: MemoryService) -> None:
    with pytest.raises(NotFoundError):
        service.update(42, "x", "a")


def test_forget_hides_fact_from_search(service: MemoryService) -> None:
    memory_id = service.save(PG, "shop", "a").memory_id

    result = service.forget(memory_id, "a")

    assert result.memory_id == memory_id
    assert service.search("postgres orders", "shop").results == []
    assert service._store.get(memory_id).status is Status.DELETED  # type: ignore[union-attr]


def test_forget_twice_and_missing(service: MemoryService) -> None:
    memory_id = service.save(PG, "shop", "a").memory_id
    service.forget(memory_id, "a")

    with pytest.raises(StaleStateError, match="already forgotten"):
        service.forget(memory_id, "a")
    with pytest.raises(NotFoundError):
        service.forget(999, "a")


def test_forget_pending_fact(service: MemoryService) -> None:
    service.save(PG, "shop", "a")
    pending = service.save("The orders service uses MongoDB", "shop", "a").memory_id

    service.forget(pending, "a")

    assert service._store.get(pending).status is Status.DELETED  # type: ignore[union-attr]
