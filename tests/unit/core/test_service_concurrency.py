"""Step 3.9: two client processes resolve different pending facts against the same target."""

import subprocess
import sys
import time
from pathlib import Path

from ctxbook.core.service import MemoryService
from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore

_RESOLVER = """
import sys, time
from ctxbook.core.service import MemoryService
from ctxbook.errors import StaleStateError
from ctxbook.storage.sqlite_store import SqliteStore
path, pending, target, start = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
service = MemoryService(SqliteStore(path, embed_model=None, embed_dim=None), None)
while time.time() < start:
    time.sleep(0.001)
try:
    service.resolve(pending, "update", target, f"client-{pending}")
    print("won")
except StaleStateError:
    print("stale")
"""


def test_two_processes_update_same_target_exactly_one_wins(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    service = MemoryService(SqliteStore(db, embed_model=None, embed_dim=None), None)
    target = service.save("The orders service uses Postgres", "shop", "x").memory_id
    p1 = service.save("The orders service uses MongoDB", "shop", "y").memory_id
    p2 = service.save("The orders service uses MySQL", "shop", "z").memory_id
    service._store.close()

    start = time.time() + 1.5
    procs = {
        pending: subprocess.Popen(
            [sys.executable, "-c", _RESOLVER, str(db), str(pending), str(target), str(start)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for pending in (p1, p2)
    }
    outcome = {}
    for pending, proc in procs.items():
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err
        outcome[pending] = out.strip()

    assert sorted(outcome.values()) == ["stale", "won"]
    winner = next(p for p, o in outcome.items() if o == "won")
    loser = next(p for p, o in outcome.items() if o == "stale")
    store = SqliteStore(db, embed_model=None, embed_dim=None)
    assert store.get(target).superseded_by == winner  # type: ignore[union-attr]
    assert store.get(winner).status is Status.ACTIVE  # type: ignore[union-attr]
    assert store.get(loser).status is Status.PENDING  # type: ignore[union-attr]
    store.close()
