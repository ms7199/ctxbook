import pytest

from ctxbook.core.service import MemoryService
from ctxbook.errors import StaleStateError
from ctxbook.models import EventAction, Status
from tests.unit.core.conftest import Clock


def _pending(service: MemoryService) -> int:
    service.save("The orders service uses Postgres", "shop", "a")
    result = service.save("The orders service uses MongoDB", "shop", "b")
    assert result.status == "needs_resolution"
    return result.memory_id


def test_pending_not_expired_before_deadline(service: MemoryService, clock: Clock) -> None:
    pending = _pending(service)
    clock.advance(days=6, hours=23)

    assert service.expire_pending() == 0
    assert service._store.get(pending).status is Status.PENDING  # type: ignore[union-attr]


def test_pending_auto_accepted_after_seven_days(service: MemoryService, clock: Clock) -> None:
    pending = _pending(service)
    clock.advance(days=7, minutes=1)

    service.search("anything", "shop")  # any operation triggers expiry

    memory = service._store.get(pending)
    assert memory.status is Status.ACTIVE  # type: ignore[union-attr]
    last = service._store.events(pending)[-1]
    assert (last.action, last.source_app) == (EventAction.EXPIRED_AUTO_ACCEPT, "ctxbook")


def test_resolving_an_expired_pending_explains_why(service: MemoryService, clock: Clock) -> None:
    pending = _pending(service)
    clock.advance(days=8)

    with pytest.raises(StaleStateError, match="expired and was accepted automatically"):
        service.resolve(pending, "new", None, "b")
