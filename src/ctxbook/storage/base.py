"""Storage interfaces. ``core`` depends on these, never on SQLite directly."""

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from ctxbook.models import Event, EventAction, Memory, Status

# (memory id, score). For vector search the score is cosine similarity (higher is closer);
# for keyword search it is a relevance score (higher is better).
Hit = tuple[int, float]


class MemoryStore(Protocol):
    """Persistent store of facts, their history, and their search indexes."""

    @property
    def vector_backend(self) -> str:
        """Name of the active vector backend: ``"sqlite-vec"`` or ``"numpy"``."""
        ...

    def transaction(self) -> AbstractContextManager[None]:
        """Group several calls into one atomic write. Re-entrant."""
        ...

    def get_meta(self, key: str) -> str | None: ...

    def set_meta(self, key: str, value: str) -> None: ...

    def add(
        self,
        *,
        content: str,
        scope: str,
        source_app: str,
        status: Status,
        now: datetime,
        vector: Sequence[float] | None = None,
    ) -> Memory:
        """Insert a fact, index it, and log a ``created`` event."""
        ...

    def get(self, memory_id: int) -> Memory | None: ...

    def get_many(self, memory_ids: Iterable[int]) -> dict[int, Memory]: ...

    def change_status(
        self,
        memory_id: int,
        *,
        expected: Status,
        new: Status,
        source_app: str,
        now: datetime,
        action: EventAction = EventAction.STATUS_CHANGED,
        superseded_by: int | None = None,
    ) -> Memory:
        """Move a fact from ``expected`` to ``new`` and log it.

        Raises ``StaleStateError`` if the fact is not in ``expected`` state, so two clients
        can never both apply a change to the same fact. Moving to ``deleted`` also removes
        the fact from the search indexes.
        """
        ...

    def touch(self, memory_id: int, *, source_app: str, now: datetime) -> Memory:
        """Bump ``updated_at`` (a duplicate was seen) and log it."""
        ...

    def set_vector(self, memory_id: int, vector: Sequence[float]) -> None: ...

    def ids_missing_vectors(self) -> list[int]:
        """Active or pending facts with no vector in the active backend (need embedding)."""
        ...

    def vector_search(
        self, vector: Sequence[float], *, k: int, scopes: Sequence[str], statuses: Sequence[Status]
    ) -> list[Hit]: ...

    def keyword_search(
        self, query: str, *, k: int, scopes: Sequence[str], statuses: Sequence[Status]
    ) -> list[Hit]: ...

    def list_memories(
        self,
        *,
        statuses: Sequence[Status] | None = None,
        updated_before: datetime | None = None,
    ) -> list[Memory]: ...

    def predecessors(self, memory_id: int) -> list[Memory]:
        """Facts that were superseded by ``memory_id``."""
        ...

    def events(self, memory_id: int) -> list[Event]: ...

    def counts(self) -> dict[Status, int]: ...

    # ── import support ───────────────────────────────────────────────────

    def insert_raw(self, memory: Memory, events: Sequence[Event]) -> int:
        """Insert a fact with its original timestamps, status and events; returns the new id.

        ``memory.id``, ``memory.superseded_by`` and the events' ids are ignored (ids differ
        between databases); link versions afterwards with ``link_superseded``.
        """
        ...

    def find_exact(
        self, *, content: str, scope: str, source_app: str, created_at: datetime
    ) -> int | None:
        """Id of a fact identical in content, scope, app and creation time, if any."""
        ...

    def link_superseded(self, memory_id: int, superseded_by: int) -> None: ...

    def close(self) -> None: ...
