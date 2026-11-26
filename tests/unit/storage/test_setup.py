import sqlite3

import pytest

from ctxbook.errors import CtxbookError, EmbeddingMismatchError
from ctxbook.storage.sqlite_store import SCHEMA_VERSION, SqliteStore
from tests.conftest import DIM, MODEL, StoreFactory


def test_fresh_db_has_all_tables(store: SqliteStore) -> None:
    db = sqlite3.connect(store.path)
    names = {row[0] for row in db.execute("select name from sqlite_master")}
    db.close()
    assert {"meta", "memories", "memory_events", "memory_fts"} <= names


def test_meta_records_schema_and_model(store: SqliteStore) -> None:
    assert store.get_meta("schema_version") == SCHEMA_VERSION
    assert store.get_meta("embed_model") == MODEL
    assert store.get_meta("embed_dim") == str(DIM)


def test_wal_mode_is_enabled(store: SqliteStore) -> None:
    db = sqlite3.connect(store.path)
    mode = db.execute("pragma journal_mode").fetchone()[0]
    db.close()
    assert mode == "wal"


def test_backend_matches_request(store: SqliteStore, backend: str) -> None:
    assert store.vector_backend == backend


def test_reopening_is_a_no_op(make_store: StoreFactory) -> None:
    first = make_store()
    first.set_meta("custom", "kept")
    first.close()

    second = make_store()

    assert second.get_meta("custom") == "kept"
    assert second.get_meta("schema_version") == SCHEMA_VERSION


@pytest.mark.parametrize(("model", "dim"), [("other-model", DIM), (MODEL, 768)])
def test_refuses_a_different_embedding_model(
    make_store: StoreFactory, model: str, dim: int
) -> None:
    make_store().close()

    with pytest.raises(EmbeddingMismatchError, match="built with the embedding model"):
        make_store(model=model, dim=dim)


def test_keyword_only_open_keeps_existing_model_meta(make_store: StoreFactory) -> None:
    make_store().close()

    keyword_only = make_store(model=None, dim=None)

    assert keyword_only.get_meta("embed_model") == MODEL


def test_refuses_newer_schema(make_store: StoreFactory) -> None:
    first = make_store()
    first.set_meta("schema_version", "999")
    first.close()

    with pytest.raises(CtxbookError, match="schema version 999"):
        make_store()


def test_model_and_dim_must_be_given_together(make_store: StoreFactory) -> None:
    with pytest.raises(ValueError, match="both"):
        make_store(model=MODEL, dim=None)
