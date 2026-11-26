"""`ctxbook doctor`: report the environment without changing anything.

Never creates the database and never downloads the embedding model.
"""

import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from ctxbook import __version__
from ctxbook.cli.runtime import fastembed_installed
from ctxbook.embeddings.fastembed_embedder import DEFAULT_MODEL, FastembedEmbedder
from ctxbook.errors import CtxbookError
from ctxbook.models import Status
from ctxbook.paths import Paths, resolve_paths
from ctxbook.storage.sqlite_store import SqliteStore

Level = Literal["ok", "warn", "info"]
STALE_PENDING = timedelta(days=1)


@dataclass(frozen=True)
class Check:
    level: Level
    name: str
    detail: str


def run_checks(paths: Paths | None = None, now: datetime | None = None) -> list[Check]:
    paths = paths or resolve_paths()
    now = now or datetime.now(UTC)
    python = f"{sys.version.split()[0]} ({platform.system()} {platform.machine()})"
    checks = [Check("info", "ctxbook", __version__), Check("info", "Python", python)]
    checks += _storage_checks(paths, now)
    checks += _embedding_checks(paths)
    return checks


def _storage_checks(paths: Paths, now: datetime) -> list[Check]:
    db_exists = paths.db_path.exists()
    try:
        store = SqliteStore(
            paths.db_path if db_exists else ":memory:", embed_model=None, embed_dim=None
        )
    except CtxbookError as exc:
        return [Check("warn", "Database", f"{paths.db_path}: {exc}")]
    try:
        checks = [Check("info", "SQLite", store.sqlite_version)]
        if store.vector_backend == "sqlite-vec":
            checks.append(Check("ok", "Vector search", "sqlite-vec extension loaded"))
        else:
            checks.append(
                Check(
                    "warn",
                    "Vector search",
                    "sqlite-vec could not be loaded; using the slower pure-Python fallback "
                    "(fine for personal use). Python from uv or Homebrew usually avoids this.",
                )
            )
        if not db_exists:
            checks.append(
                Check("info", "Database", f"{paths.db_path} (not created yet: no memories)")
            )
            return checks
        counts = store.counts()
        summary = ", ".join(f"{counts[s]} {s.value}" for s in Status)
        checks.append(Check("ok", "Database", f"{paths.db_path} ({summary})"))
        model = store.get_meta("embed_model")
        if model:
            checks.append(Check("info", "Embedding model in database", model))
        if missing := store.ids_missing_vectors():
            checks.append(
                Check("info", "Vectors", f"{len(missing)} facts will be embedded on next use")
            )
        stale = [
            m
            for m in store.list_memories(statuses=[Status.PENDING])
            if now - m.updated_at > STALE_PENDING
        ]
        if stale:
            lines = "; ".join(f"[{m.id}] {m.content[:60]}" for m in stale[:5])
            checks.append(
                Check(
                    "warn",
                    "Unresolved facts",
                    f"{len(stale)} pending for over a day (accepted automatically after 7 "
                    f"days): {lines}",
                )
            )
        return checks
    finally:
        store.close()


def _embedding_checks(paths: Paths) -> list[Check]:
    if not fastembed_installed():
        return [
            Check(
                "warn",
                "Embeddings",
                "not available on this platform (no onnxruntime build, e.g. Intel Mac with "
                "Python 3.14+), so search is keyword-only. For full search use Python 3.12: "
                "`uvx --python 3.12 ctxbook ...`.",
            )
        ]
    embedder = FastembedEmbedder(paths.model_cache_dir)
    if embedder.is_downloaded():
        return [Check("ok", "Embeddings", f"{DEFAULT_MODEL} cached in {paths.model_cache_dir}")]
    return [
        Check(
            "info",
            "Embeddings",
            f"{DEFAULT_MODEL} not downloaded yet (about 67 MB, once, on first use). Behind a "
            "firewall? Use --no-embeddings.",
        )
    ]
