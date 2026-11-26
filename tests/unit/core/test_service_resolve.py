import pytest

from ctxbook.core.safety import InvalidInputError
from ctxbook.core.service import MemoryService
from ctxbook.errors import NotFoundError, StaleStateError
from ctxbook.models import Status

PG = "The orders service uses Postgres"
MONGO = "The orders service uses MongoDB"


def _conflict(service: MemoryService) -> tuple[int, int]:
    """Return (existing active id, pending id)."""
    existing = service.save(PG, "shop", "claude-code").memory_id
    pending = service.save(MONGO, "shop", "cursor")
    assert pending.status == "needs_resolution"
    return existing, pending.memory_id


def _status(service: MemoryService, memory_id: int) -> Status:
    return service._store.get(memory_id).status  # type: ignore[union-attr]


def test_new_keeps_both(service: MemoryService) -> None:
    existing, pending = _conflict(service)

    result = service.resolve(pending, "new", None, "cursor")

    assert result.active_id == pending
    assert _status(service, pending) is Status.ACTIVE
    assert _status(service, existing) is Status.ACTIVE


def test_duplicate_drops_pending(service: MemoryService) -> None:
    existing, pending = _conflict(service)

    result = service.resolve(pending, "duplicate", existing, "cursor")

    assert result.active_id == existing
    assert _status(service, pending) is Status.DELETED
    assert _status(service, existing) is Status.ACTIVE


@pytest.mark.parametrize("decision", ["update", "contradiction"])
def test_update_and_contradiction_supersede_target(service: MemoryService, decision: str) -> None:
    existing, pending = _conflict(service)

    result = service.resolve(pending, decision, existing, "cursor")

    assert (result.active_id, result.superseded_id) == (pending, existing)
    assert _status(service, pending) is Status.ACTIVE
    old = service._store.get(existing)
    assert old.status is Status.SUPERSEDED  # type: ignore[union-attr]
    assert old.superseded_by == pending  # type: ignore[union-attr]


def test_update_requires_target(service: MemoryService) -> None:
    _, pending = _conflict(service)

    with pytest.raises(InvalidInputError, match="needs target_id"):
        service.resolve(pending, "update", None, "cursor")
    assert _status(service, pending) is Status.PENDING


def test_unknown_decision(service: MemoryService) -> None:
    _, pending = _conflict(service)

    with pytest.raises(InvalidInputError, match="Unknown decision"):
        service.resolve(pending, "merge", None, "cursor")


def test_resolving_twice_is_refused(service: MemoryService) -> None:
    _, pending = _conflict(service)
    service.resolve(pending, "new", None, "cursor")

    with pytest.raises(StaleStateError, match="already resolved"):
        service.resolve(pending, "new", None, "cursor")


def test_target_already_superseded_rolls_back(service: MemoryService) -> None:
    """Two clients resolve two different pending facts against the same target."""
    existing, first = _conflict(service)
    second = service.save("The orders service uses MySQL", "shop", "claude-desktop").memory_id
    service.resolve(first, "update", existing, "cursor")

    with pytest.raises(StaleStateError, match=f"replaced by memory {first}"):
        service.resolve(second, "update", existing, "claude-desktop")

    assert _status(service, second) is Status.PENDING  # nothing half-applied


def test_target_must_be_in_same_scope(service: MemoryService) -> None:
    other = service.save(PG, "other-repo", "a").memory_id
    _, pending = _conflict(service)

    with pytest.raises(InvalidInputError, match="scope"):
        service.resolve(pending, "update", other, "cursor")


def test_target_cannot_be_the_pending_fact(service: MemoryService) -> None:
    _, pending = _conflict(service)

    with pytest.raises(InvalidInputError, match="different"):
        service.resolve(pending, "update", pending, "cursor")


def test_missing_ids(service: MemoryService) -> None:
    with pytest.raises(NotFoundError):
        service.resolve(999, "new", None, "a")
    _, pending = _conflict(service)
    with pytest.raises(NotFoundError):
        service.resolve(pending, "update", 999, "a")
