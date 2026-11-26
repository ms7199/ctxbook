import pytest

from ctxbook.core.service import MemoryService
from ctxbook.errors import NotFoundError
from ctxbook.models import EventAction, Status
from tests.unit.core.conftest import Clock


def test_history_of_three_versions_from_any_version(service: MemoryService, clock: Clock) -> None:
    v1 = service.save("Orders use Postgres", "shop", "claude-code").memory_id
    clock.advance(days=1)
    v2 = service.update(v1, "Orders use MongoDB", "cursor").memory_id
    clock.advance(days=1)
    v3 = service.update(v2, "Orders use DynamoDB", "claude-desktop").memory_id

    for start in (v1, v2, v3):
        history = service.history(start)
        assert [v.id for v in history.versions] == [v1, v2, v3]
        assert [v.status for v in history.versions] == [
            Status.SUPERSEDED,
            Status.SUPERSEDED,
            Status.ACTIVE,
        ]
        assert history.current_id == v3

    events = service.history(v1).events
    assert [e.at for e in events] == sorted(e.at for e in events)
    assert {e.by for e in events} == {"claude-code", "cursor", "claude-desktop"}
    assert [e.action for e in events].count(EventAction.SUPERSEDED) == 2


def test_history_via_resolve(service: MemoryService) -> None:
    old = service.save("The orders service uses Postgres", "shop", "a").memory_id
    pending = service.save("The orders service uses MongoDB", "shop", "b").memory_id
    service.resolve(pending, "contradiction", old, "b")

    history = service.history(old)

    assert [v.id for v in history.versions] == [old, pending]
    assert history.current_id == pending


def test_history_of_forgotten_fact_has_no_current(service: MemoryService) -> None:
    memory_id = service.save("x fact", "shop", "a").memory_id
    service.forget(memory_id, "a")

    history = service.history(memory_id)

    assert history.current_id is None
    assert history.events[-1].action is EventAction.DELETED


def test_history_missing(service: MemoryService) -> None:
    with pytest.raises(NotFoundError):
        service.history(5)
