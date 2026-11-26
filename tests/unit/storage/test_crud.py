import pytest

from ctxbook.errors import NotFoundError, StaleStateError
from ctxbook.models import EventAction, Status
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0, at


def _add(store: SqliteStore, content: str = "We use Postgres", **kw: object) -> int:
    args: dict[str, object] = {
        "content": content,
        "scope": "orders",
        "source_app": "claude-code",
        "status": Status.ACTIVE,
        "now": T0,
        **kw,
    }
    return store.add(**args).id  # type: ignore[arg-type]


def test_add_returns_stored_memory_and_logs_created(store: SqliteStore) -> None:
    memory = store.add(
        content="We use Postgres",
        scope="orders",
        source_app="claude-code",
        status=Status.ACTIVE,
        now=T0,
    )

    assert memory.content == "We use Postgres"
    assert memory.status is Status.ACTIVE
    assert memory.created_at == memory.updated_at == T0
    [event] = store.events(memory.id)
    assert event.action is EventAction.CREATED
    assert event.new == "We use Postgres"
    assert event.source_app == "claude-code"


def test_get_missing_returns_none(store: SqliteStore) -> None:
    assert store.get(999) is None


def test_get_many(store: SqliteStore) -> None:
    a, b = _add(store, "a"), _add(store, "b")

    found = store.get_many([b, a, b, 999])

    assert set(found) == {a, b}


def test_supersede_links_and_logs(store: SqliteStore) -> None:
    old = _add(store, "We use Postgres")
    new = _add(store, "We use MongoDB")

    result = store.change_status(
        old,
        expected=Status.ACTIVE,
        new=Status.SUPERSEDED,
        superseded_by=new,
        action=EventAction.SUPERSEDED,
        source_app="cursor",
        now=at(5),
    )

    assert result.status is Status.SUPERSEDED
    assert result.superseded_by == new
    assert result.updated_at == at(5)
    assert [p.id for p in store.predecessors(new)] == [old]
    last = store.events(old)[-1]
    assert (last.action, last.old, last.new, last.source_app) == (
        EventAction.SUPERSEDED,
        "active",
        "superseded",
        "cursor",
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (Status.PENDING, Status.ACTIVE),
        (Status.PENDING, Status.DELETED),
        (Status.ACTIVE, Status.SUPERSEDED),
        (Status.ACTIVE, Status.DELETED),
    ],
)
def test_status_transitions(store: SqliteStore, start: Status, end: Status) -> None:
    memory_id = _add(store, status=start)

    result = store.change_status(memory_id, expected=start, new=end, source_app="a", now=at(1))

    assert result.status is end
    assert len(store.events(memory_id)) == 2


def test_wrong_expected_state_raises_and_changes_nothing(store: SqliteStore) -> None:
    old = _add(store)
    new = _add(store, "replacement")
    store.change_status(
        old,
        expected=Status.ACTIVE,
        new=Status.SUPERSEDED,
        superseded_by=new,
        source_app="a",
        now=at(1),
    )

    with pytest.raises(StaleStateError, match=f"replaced by memory {new}"):
        store.change_status(
            old, expected=Status.ACTIVE, new=Status.SUPERSEDED, source_app="b", now=at(2)
        )

    assert len(store.events(old)) == 2
    assert store.get(old).updated_at == at(1)  # type: ignore[union-attr]


def test_change_status_of_missing_id(store: SqliteStore) -> None:
    with pytest.raises(NotFoundError):
        store.change_status(999, expected=Status.ACTIVE, new=Status.DELETED, source_app="a", now=T0)


def test_touch_bumps_updated_at_and_logs(store: SqliteStore) -> None:
    memory_id = _add(store)

    touched = store.touch(memory_id, source_app="cursor", now=at(10))

    assert touched.updated_at == at(10)
    assert touched.created_at == T0
    assert store.events(memory_id)[-1].action is EventAction.DUPLICATE_SEEN


def test_failed_transaction_rolls_back_everything(store: SqliteStore) -> None:
    with pytest.raises(RuntimeError), store.transaction():
        _add(store, "should vanish")
        raise RuntimeError("boom")

    assert store.list_memories() == []


def test_naive_timestamps_are_rejected(store: SqliteStore) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _add(store, now=T0.replace(tzinfo=None))
    assert store.list_memories() == []


def test_list_memories_filters(store: SqliteStore) -> None:
    a = _add(store, "a", now=at(0))
    b = _add(store, "b", now=at(10), status=Status.PENDING)

    assert [m.id for m in store.list_memories()] == [a, b]
    assert [m.id for m in store.list_memories(statuses=[Status.PENDING])] == [b]
    assert [m.id for m in store.list_memories(updated_before=at(5))] == [a]
    assert store.list_memories(statuses=[]) == []


def test_counts(store: SqliteStore) -> None:
    _add(store)
    _add(store, status=Status.PENDING)

    counts = store.counts()

    assert counts[Status.ACTIVE] == 1
    assert counts[Status.PENDING] == 1
    assert counts[Status.DELETED] == 0
