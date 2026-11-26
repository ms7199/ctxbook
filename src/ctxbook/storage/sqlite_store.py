"""SQLite implementation of ``MemoryStore`` (schema v1)."""

import re
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ctxbook.errors import CtxbookError, EmbeddingMismatchError, NotFoundError, StaleStateError
from ctxbook.models import Event, EventAction, Memory, Status
from ctxbook.storage.base import Hit
from ctxbook.storage.vector_index import VectorIndex, open_vector_index

SCHEMA_VERSION = "1"

_SCHEMA = """
create table if not exists meta (
    key   text primary key,
    value text not null
);
create table if not exists memories (
    id            integer primary key,
    content       text not null,
    scope         text not null,
    source_app    text not null,
    status        text not null
                  check (status in ('active', 'pending', 'superseded', 'deleted')),
    superseded_by integer references memories(id),
    created_at    text not null,
    updated_at    text not null
);
create index if not exists memories_scope_status on memories(scope, status);
create index if not exists memories_superseded_by on memories(superseded_by);
create table if not exists memory_events (
    id         integer primary key,
    memory_id  integer not null references memories(id),
    action     text not null,
    old        text,
    new        text,
    source_app text not null,
    created_at text not null
);
create index if not exists memory_events_memory on memory_events(memory_id);
create virtual table if not exists memory_fts using fts5(content);
"""

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _fts_query(text: str) -> str | None:
    """Turn free text into a safe FTS5 query: every word quoted, joined with OR."""
    tokens = list(dict.fromkeys(t.lower() for t in _TOKEN.findall(text)))
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens)


def _placeholders(n: int) -> str:
    return ", ".join("?" * n)


class SqliteStore:
    """Facts, history and search indexes in one SQLite file.

    ``embed_model``/``embed_dim`` describe the active embedder; pass ``None`` for keyword-only
    mode. A database built with one model refuses to open with another.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        embed_model: str | None,
        embed_dim: int | None,
        force_numpy: bool = False,
        busy_timeout_ms: int = 5000,
    ) -> None:
        if (embed_model is None) != (embed_dim is None):
            raise ValueError("embed_model and embed_dim must both be set or both be None")
        self.path = str(path)
        # The MCP server calls the store from worker threads, one call at a time (it holds a
        # lock), so the connection may move between threads but is never used concurrently.
        self._db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._depth = 0
        self._db.execute(f"pragma busy_timeout = {int(busy_timeout_ms)}")
        self._db.execute("pragma journal_mode = wal")
        self._db.execute("pragma synchronous = normal")
        self._db.execute("pragma foreign_keys = on")
        self._index: VectorIndex = open_vector_index(self._db, force_numpy=force_numpy)
        with self.transaction():
            for statement in _SCHEMA.split(";"):
                if statement.strip():
                    self._db.execute(statement)
            self._check_schema_version()
            self._dim = self._check_embedding(embed_model, embed_dim)

    # ── setup ────────────────────────────────────────────────────────────

    def _check_schema_version(self) -> None:
        stored = self.get_meta("schema_version")
        if stored is None:
            self.set_meta("schema_version", SCHEMA_VERSION)
        elif stored != SCHEMA_VERSION:
            raise CtxbookError(
                f"This memory database uses schema version {stored}, but this ctxbook "
                f"understands version {SCHEMA_VERSION}. Please upgrade ctxbook."
            )

    def _check_embedding(self, model: str | None, dim: int | None) -> int | None:
        stored_model = self.get_meta("embed_model")
        stored_dim = self.get_meta("embed_dim")
        if model is None or dim is None:
            return None
        if stored_model is None:
            self.set_meta("embed_model", model)
            self.set_meta("embed_dim", str(dim))
        elif stored_model != model or stored_dim != str(dim):
            raise EmbeddingMismatchError(
                f"This memory database was built with the embedding model {stored_model} "
                f"({stored_dim} dimensions), but ctxbook is now using {model} ({dim} "
                "dimensions). Mixing them would give wrong search results. Switch back to "
                "the original model, or run with --no-embeddings."
            )
        self._index.ensure(dim)
        return dim

    # ── transactions and meta ────────────────────────────────────────────

    @property
    def vector_backend(self) -> str:
        return self._index.name

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._depth == 0:
            self._db.execute("begin immediate")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._db.execute("rollback")
            raise
        self._depth -= 1
        if self._depth == 0:
            self._db.execute("commit")

    def get_meta(self, key: str) -> str | None:
        row = self._db.execute("select value from meta where key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            "insert into meta(key, value) values (?, ?) "
            "on conflict(key) do update set value = excluded.value",
            (key, value),
        )

    # ── writes ───────────────────────────────────────────────────────────

    def _log(
        self,
        memory_id: int,
        action: EventAction,
        *,
        source_app: str,
        now: datetime,
        old: str | None = None,
        new: str | None = None,
    ) -> None:
        self._db.execute(
            "insert into memory_events(memory_id, action, old, new, source_app, created_at) "
            "values (?, ?, ?, ?, ?, ?)",
            (memory_id, action.value, old, new, source_app, _ts(now)),
        )

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
        with self.transaction():
            cursor = self._db.execute(
                "insert into memories(content, scope, source_app, status, created_at, "
                "updated_at) values (?, ?, ?, ?, ?, ?)",
                (content, scope, source_app, status.value, _ts(now), _ts(now)),
            )
            memory_id = int(cursor.lastrowid or 0)
            self._db.execute(
                "insert into memory_fts(rowid, content) values (?, ?)", (memory_id, content)
            )
            if vector is not None:
                self.set_vector(memory_id, vector)
            self._log(memory_id, EventAction.CREATED, source_app=source_app, now=now, new=content)
        return self._require(memory_id)

    def set_vector(self, memory_id: int, vector: Sequence[float]) -> None:
        if self._dim is None:
            raise ValueError("this store was opened without an embedding model")
        if len(vector) != self._dim:
            raise EmbeddingMismatchError(
                f"vector has {len(vector)} dimensions, the database expects {self._dim}"
            )
        self._index.add(memory_id, vector)

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
        with self.transaction():
            cursor = self._db.execute(
                "update memories set status = ?, superseded_by = coalesce(?, superseded_by), "
                "updated_at = ? where id = ? and status = ?",
                (new.value, superseded_by, _ts(now), memory_id, expected.value),
            )
            if cursor.rowcount == 0:
                current = self.get(memory_id)
                if current is None:
                    raise NotFoundError(f"No memory with id {memory_id}.")
                detail = (
                    f" It was replaced by memory {current.superseded_by}."
                    if current.superseded_by
                    else ""
                )
                raise StaleStateError(
                    f"Memory {memory_id} is {current.status.value}, not {expected.value}; "
                    f"another client probably changed it first.{detail}"
                )
            if new is Status.DELETED:
                self._db.execute("delete from memory_fts where rowid = ?", (memory_id,))
                self._index.delete(memory_id)
            self._log(
                memory_id, action, source_app=source_app, now=now, old=expected.value, new=new.value
            )
        return self._require(memory_id)

    def touch(self, memory_id: int, *, source_app: str, now: datetime) -> Memory:
        with self.transaction():
            cursor = self._db.execute(
                "update memories set updated_at = ? where id = ?", (_ts(now), memory_id)
            )
            if cursor.rowcount == 0:
                raise NotFoundError(f"No memory with id {memory_id}.")
            self._log(memory_id, EventAction.DUPLICATE_SEEN, source_app=source_app, now=now)
        return self._require(memory_id)

    # ── reads ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_memory(row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            content=row["content"],
            scope=row["scope"],
            source_app=row["source_app"],
            status=row["status"],
            superseded_by=row["superseded_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get(self, memory_id: int) -> Memory | None:
        row = self._db.execute("select * from memories where id = ?", (memory_id,)).fetchone()
        return None if row is None else self._to_memory(row)

    def _require(self, memory_id: int) -> Memory:
        memory = self.get(memory_id)
        if memory is None:
            raise NotFoundError(f"No memory with id {memory_id}.")
        return memory

    def get_many(self, memory_ids: Iterable[int]) -> dict[int, Memory]:
        ids = list(dict.fromkeys(memory_ids))
        if not ids:
            return {}
        rows = self._db.execute(
            f"select * from memories where id in ({_placeholders(len(ids))})", ids
        ).fetchall()
        return {row["id"]: self._to_memory(row) for row in rows}

    def ids_missing_vectors(self) -> list[int]:
        rows = self._db.execute(
            "select id from memories where status in ('active', 'pending') order by id"
        ).fetchall()
        have = self._index.ids()
        return [row[0] for row in rows if row[0] not in have]

    def _candidates(
        self, scopes: Sequence[str], statuses: Sequence[Status]
    ) -> tuple[str, list[object]]:
        sql = (
            f"select id from memories where scope in ({_placeholders(len(scopes))}) "
            f"and status in ({_placeholders(len(statuses))})"
        )
        return sql, [*scopes, *(s.value for s in statuses)]

    def vector_search(
        self, vector: Sequence[float], *, k: int, scopes: Sequence[str], statuses: Sequence[Status]
    ) -> list[Hit]:
        if self._dim is None or not scopes or not statuses or k <= 0:
            return []
        sql, params = self._candidates(scopes, statuses)
        return self._index.search(vector, k, sql, params)

    def keyword_search(
        self, query: str, *, k: int, scopes: Sequence[str], statuses: Sequence[Status]
    ) -> list[Hit]:
        match = _fts_query(query)
        if match is None or not scopes or not statuses or k <= 0:
            return []
        rows = self._db.execute(
            "select memory_fts.rowid as id, bm25(memory_fts) as score from memory_fts "
            "join memories on memories.id = memory_fts.rowid "
            f"where memory_fts match ? and memories.scope in ({_placeholders(len(scopes))}) "
            f"and memories.status in ({_placeholders(len(statuses))}) "
            "order by score limit ?",
            (match, *scopes, *(s.value for s in statuses), k),
        ).fetchall()
        # bm25() is lower-is-better (negative); flip so higher is better like vector search.
        return [(int(row["id"]), -float(row["score"])) for row in rows]

    def list_memories(
        self,
        *,
        statuses: Sequence[Status] | None = None,
        updated_before: datetime | None = None,
    ) -> list[Memory]:
        clauses: list[str] = []
        params: list[object] = []
        if statuses is not None:
            if not statuses:
                return []
            clauses.append(f"status in ({_placeholders(len(statuses))})")
            params.extend(s.value for s in statuses)
        if updated_before is not None:
            clauses.append("updated_at < ?")
            params.append(_ts(updated_before))
        where = f" where {' and '.join(clauses)}" if clauses else ""
        rows = self._db.execute(f"select * from memories{where} order by id", params).fetchall()
        return [self._to_memory(row) for row in rows]

    def predecessors(self, memory_id: int) -> list[Memory]:
        rows = self._db.execute(
            "select * from memories where superseded_by = ? order by id", (memory_id,)
        ).fetchall()
        return [self._to_memory(row) for row in rows]

    def events(self, memory_id: int) -> list[Event]:
        rows = self._db.execute(
            "select * from memory_events where memory_id = ? order by id", (memory_id,)
        ).fetchall()
        return [
            Event(
                id=row["id"],
                memory_id=row["memory_id"],
                action=row["action"],
                old=row["old"],
                new=row["new"],
                source_app=row["source_app"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def counts(self) -> dict[Status, int]:
        result = dict.fromkeys(Status, 0)
        for row in self._db.execute("select status, count(*) from memories group by status"):
            result[Status(row[0])] = int(row[1])
        return result

    def close(self) -> None:
        self._db.close()
