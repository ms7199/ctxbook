"""Vector indexes. Both return cosine similarity so callers never see backend details.

``SqliteVecIndex`` uses the sqlite-vec extension. ``NumpyIndex`` stores vectors as BLOBs and
computes cosine similarity in numpy; it is used when the extension cannot be loaded (for
example, macOS system Python) and is fine for a personal memory of a few thousand facts.
"""

import logging
import sqlite3
from collections.abc import Sequence
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

# sqlite-vec rejects k > 4096 (verified 2026-11-26, see CLAUDE.md section 6).
SQLITE_VEC_MAX_K = 4096


class VectorIndex(Protocol):
    name: str

    def ensure(self, dim: int) -> None: ...
    def add(self, memory_id: int, vector: Sequence[float]) -> None: ...
    def delete(self, memory_id: int) -> None: ...
    def ids(self) -> set[int]: ...
    def search(
        self, vector: Sequence[float], k: int, candidates_sql: str, params: Sequence[object]
    ) -> list[tuple[int, float]]: ...


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute("select 1 from sqlite_master where name = ?", (name,)).fetchone()
    return row is not None


class SqliteVecIndex:
    name = "sqlite-vec"
    _TABLE = "memory_vectors"

    def __init__(self, db: sqlite3.Connection) -> None:
        import sqlite_vec

        self._db = db
        self._serialize = sqlite_vec.serialize_float32

    def ensure(self, dim: int) -> None:
        self._db.execute(
            f"create virtual table if not exists {self._TABLE} "
            f"using vec0(embedding float[{int(dim)}] distance_metric=cosine)"
        )

    def add(self, memory_id: int, vector: Sequence[float]) -> None:
        self._db.execute(f"delete from {self._TABLE} where rowid = ?", (memory_id,))
        self._db.execute(
            f"insert into {self._TABLE}(rowid, embedding) values (?, ?)",
            (memory_id, self._serialize(list(vector))),
        )

    def delete(self, memory_id: int) -> None:
        if _table_exists(self._db, self._TABLE):
            self._db.execute(f"delete from {self._TABLE} where rowid = ?", (memory_id,))

    def ids(self) -> set[int]:
        if not _table_exists(self._db, self._TABLE):
            return set()
        return {row[0] for row in self._db.execute(f"select rowid from {self._TABLE}")}

    def search(
        self, vector: Sequence[float], k: int, candidates_sql: str, params: Sequence[object]
    ) -> list[tuple[int, float]]:
        if not _table_exists(self._db, self._TABLE):
            return []
        rows = self._db.execute(
            f"select rowid, distance from {self._TABLE} "
            f"where embedding match ? and k = ? and rowid in ({candidates_sql}) "
            "order by distance",
            (self._serialize(list(vector)), min(k, SQLITE_VEC_MAX_K), *params),
        ).fetchall()
        return [(int(row[0]), 1.0 - float(row[1])) for row in rows]


class NumpyIndex:
    name = "numpy"
    _TABLE = "memory_vectors_blob"

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def ensure(self, dim: int) -> None:
        self._db.execute(
            f"create table if not exists {self._TABLE} "
            "(id integer primary key, embedding blob not null)"
        )

    def add(self, memory_id: int, vector: Sequence[float]) -> None:
        blob = np.asarray(vector, dtype=np.float32).tobytes()
        self._db.execute(
            f"insert or replace into {self._TABLE}(id, embedding) values (?, ?)",
            (memory_id, blob),
        )

    def delete(self, memory_id: int) -> None:
        if _table_exists(self._db, self._TABLE):
            self._db.execute(f"delete from {self._TABLE} where id = ?", (memory_id,))

    def ids(self) -> set[int]:
        if not _table_exists(self._db, self._TABLE):
            return set()
        return {row[0] for row in self._db.execute(f"select id from {self._TABLE}")}

    def search(
        self, vector: Sequence[float], k: int, candidates_sql: str, params: Sequence[object]
    ) -> list[tuple[int, float]]:
        if not _table_exists(self._db, self._TABLE):
            return []
        rows = self._db.execute(
            f"select id, embedding from {self._TABLE} where id in ({candidates_sql})",
            tuple(params),
        ).fetchall()
        if not rows:
            return []
        ids = np.array([row[0] for row in rows])
        matrix = np.stack([np.frombuffer(row[1], dtype=np.float32) for row in rows])
        query = np.asarray(vector, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
        sims = np.divide(matrix @ query, norms, out=np.zeros(len(rows)), where=norms > 0)
        order = np.argsort(-sims, kind="stable")[:k]
        return [(int(ids[i]), float(sims[i])) for i in order]


def open_vector_index(db: sqlite3.Connection, *, force_numpy: bool = False) -> VectorIndex:
    """Load sqlite-vec if possible; otherwise fall back to numpy with one clear warning."""
    if force_numpy:
        return NumpyIndex(db)
    try:
        import sqlite_vec

        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
    except Exception as exc:  # any failure (missing attribute, DLL, missing module) -> fallback
        log.warning(
            "sqlite-vec could not be loaded (%s: %s). Using the slower pure-Python vector "
            "search instead; this is fine for personal use. Run `ctxbook doctor` for details.",
            type(exc).__name__,
            exc,
        )
        return NumpyIndex(db)
    return SqliteVecIndex(db)
