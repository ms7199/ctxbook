"""Builds the store, embedder and service the CLI commands share."""

import importlib.util
import logging
import sys
from dataclasses import dataclass

from ctxbook.core.service import MemoryService
from ctxbook.embeddings.base import Embedder
from ctxbook.embeddings.fastembed_embedder import FastembedEmbedder
from ctxbook.paths import Paths, resolve_paths
from ctxbook.storage.sqlite_store import SqliteStore

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def fastembed_installed() -> bool:
    """False on platforms where the dependency marker skipped it (decision D17)."""
    return importlib.util.find_spec("fastembed") is not None


def configure_logging() -> None:
    # stderr only: in stdio mode stdout carries the MCP protocol.
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="ctxbook: %(message)s")


@dataclass
class Runtime:
    paths: Paths
    store: SqliteStore
    embedder: Embedder | None
    service: MemoryService

    def close(self) -> None:
        self.store.close()


def open_runtime(*, no_embeddings: bool = False) -> Runtime:
    paths = resolve_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    embedder: Embedder | None = None
    if not no_embeddings:
        if fastembed_installed():
            embedder = FastembedEmbedder(paths.model_cache_dir)
        else:
            print(
                "ctxbook: the local embedding model is not available on this platform, so "
                "search is keyword-only. Run `ctxbook doctor` for details.",
                file=sys.stderr,
            )
    store = SqliteStore(
        paths.db_path,
        embed_model=embedder.model_name if embedder else None,
        embed_dim=embedder.dim if embedder else None,
    )
    return Runtime(paths, store, embedder, MemoryService(store, embedder))
