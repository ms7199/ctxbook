from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ctxbook.models import Event, EventAction, Memory, Status

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def test_status_values_match_schema() -> None:
    assert {s.value for s in Status} == {"active", "pending", "superseded", "deleted"}


def test_memory_accepts_string_status_from_db() -> None:
    memory = Memory(
        id=1,
        content="We use Postgres",
        scope="orders",
        source_app="claude-code",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )

    assert memory.status is Status.ACTIVE
    assert memory.superseded_by is None


def test_memory_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        Memory(
            id=1,
            content="x",
            scope="s",
            source_app="a",
            status="archived",
            created_at=NOW,
            updated_at=NOW,
        )


def test_event_roundtrip() -> None:
    event = Event(
        id=1,
        memory_id=2,
        action="superseded",
        old="active",
        new="superseded",
        source_app="cursor",
        created_at=NOW,
    )

    assert event.action is EventAction.SUPERSEDED
    assert Event.model_validate(event.model_dump()) == event
