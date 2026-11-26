"""Several AI clients each start their own ctxbook process on one DB file."""

import subprocess
import sys
import time
from pathlib import Path

from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0

_PRELUDE = """
import sys, time
from datetime import UTC, datetime
from ctxbook.models import Status
from ctxbook.errors import StaleStateError
from ctxbook.storage.sqlite_store import SqliteStore
path, name, start = sys.argv[1], sys.argv[2], float(sys.argv[3])
store = SqliteStore(path, embed_model="m", embed_dim=3)
while time.time() < start:
    time.sleep(0.001)
"""

_WRITER = (
    _PRELUDE
    + """
for i in range(100):
    store.add(content=f"{name} fact {i}", scope="s", source_app=name,
              status=Status.ACTIVE, now=datetime.now(UTC), vector=[1.0, float(i), 0.0])
print("done")
"""
)

_SUPERSEDER = (
    _PRELUDE
    + """
try:
    store.change_status(1, expected=Status.ACTIVE, new=Status.SUPERSEDED,
                        source_app=name, now=datetime.now(UTC))
    print("won")
except StaleStateError:
    print("stale")
"""
)


def _run_pair(script: str, db: Path) -> list[str]:
    start = time.time() + 1.5  # both processes begin at the same moment
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(db), name, str(start)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for name in ("client-a", "client-b")
    ]
    outputs = []
    for proc in procs:
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err
        outputs.append(out.strip())
    return outputs


def _init_db(db: Path) -> SqliteStore:
    return SqliteStore(db, embed_model="m", embed_dim=3)


def test_two_processes_write_at_once(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _init_db(db).close()

    assert _run_pair(_WRITER, db) == ["done", "done"]

    store = _init_db(db)
    memories = store.list_memories()
    assert len(memories) == 200
    assert {m.source_app for m in memories} == {"client-a", "client-b"}
    assert store.ids_missing_vectors() == []
    assert len(store.events(memories[0].id)) == 1
    store.close()


def test_two_processes_superseding_one_fact_exactly_one_wins(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    store = _init_db(db)
    store.add(content="We use Postgres", scope="s", source_app="x", status=Status.ACTIVE, now=T0)
    store.close()

    assert sorted(_run_pair(_SUPERSEDER, db)) == ["stale", "won"]

    store = _init_db(db)
    assert store.get(1).status is Status.SUPERSEDED  # type: ignore[union-attr]
    assert len(store.events(1)) == 2  # created + exactly one change
    store.close()
