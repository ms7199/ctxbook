import pytest

from ctxbook.core.safety import InvalidInputError
from ctxbook.core.service import MemoryService, word_overlap
from ctxbook.models import DATA_NOTE, EventAction, Status
from tests.unit.core.conftest import Clock

PG = "The orders service uses Postgres"
MONGO = "The orders service uses MongoDB"


def test_unrelated_fact_is_saved_active(service: MemoryService) -> None:
    service.save(PG, "shop", "claude-code")

    result = service.save("Frontend is written in React", "shop", "cursor")

    assert result.status == "saved"
    assert result.candidates == []
    assert service._store.get(result.memory_id).status is Status.ACTIVE  # type: ignore[union-attr]


def test_same_fact_is_a_duplicate_and_bumps_timestamp(service: MemoryService, clock: Clock) -> None:
    first = service.save(PG, "shop", "claude-code")
    clock.advance(days=1)

    result = service.save("the orders service uses postgres.", "shop", "cursor")

    assert result.status == "duplicate"
    assert result.memory_id == first.memory_id
    stored = service._store.get(first.memory_id)
    assert stored.updated_at == clock.now  # type: ignore[union-attr]
    assert service._store.events(first.memory_id)[-1].action is EventAction.DUPLICATE_SEEN
    assert len(service._store.list_memories()) == 1


def test_changed_fact_needs_resolution(service: MemoryService) -> None:
    first = service.save(PG, "shop", "claude-code")

    result = service.save(MONGO, "shop", "cursor")

    assert result.status == "needs_resolution"
    assert [c.id for c in result.candidates] == [first.memory_id]
    assert result.candidates[0].note == DATA_NOTE
    assert f"pending_id={result.memory_id}" in result.message
    assert service._store.get(result.memory_id).status is Status.PENDING  # type: ignore[union-attr]


def test_conflicts_only_checked_within_scope(service: MemoryService) -> None:
    service.save(PG, "shop", "a")

    assert service.save(MONGO, "other-repo", "a").status == "saved"


def test_scope_is_case_insensitive(service: MemoryService) -> None:
    service.save(PG, "Shop", "a")

    assert service.save(PG, "SHOP", "a").status == "duplicate"


def test_invalid_input_rejected(service: MemoryService) -> None:
    with pytest.raises(InvalidInputError):
        service.save("   ", "shop", "a")
    with pytest.raises(InvalidInputError):
        service.save("x" * 1001, "shop", "a")


def test_keyword_overlap_ignores_common_words() -> None:
    assert word_overlap(PG, MONGO) == pytest.approx(2 / 3)
    assert word_overlap("We use the thing", "They use the other") == 0.0
    assert word_overlap("", "anything") == 0.0
