import pytest

from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore, _fts_query
from tests.conftest import T0, at

ACTIVE = [Status.ACTIVE]


def _add(store: SqliteStore, content: str, scope: str = "orders", **kw: object) -> int:
    args: dict[str, object] = {
        "content": content,
        "scope": scope,
        "source_app": "a",
        "status": Status.ACTIVE,
        "now": T0,
        **kw,
    }
    return store.add(**args).id  # type: ignore[arg-type]


def test_finds_matching_fact_ranked_first(store: SqliteStore) -> None:
    pg = _add(store, "The orders service uses Postgres")
    _add(store, "Frontend is written in React")

    hits = store.keyword_search("postgres database", k=5, scopes=["orders"], statuses=ACTIVE)

    assert [h[0] for h in hits] == [pg]
    assert hits[0][1] > 0  # higher is better


def test_respects_scope_and_status(store: SqliteStore) -> None:
    _add(store, "uses Postgres", scope="other")
    pending = _add(store, "uses Postgres", status=Status.PENDING)

    assert store.keyword_search("postgres", k=5, scopes=["orders"], statuses=ACTIVE) == []
    hits = store.keyword_search(
        "postgres", k=5, scopes=["orders"], statuses=[Status.ACTIVE, Status.PENDING]
    )
    assert [h[0] for h in hits] == [pending]


def test_deleted_fact_leaves_keyword_index(store: SqliteStore) -> None:
    memory_id = _add(store, "uses Postgres")
    store.change_status(
        memory_id, expected=Status.ACTIVE, new=Status.DELETED, source_app="a", now=at(1)
    )

    hits = store.keyword_search(
        "postgres", k=5, scopes=["orders"], statuses=[Status.ACTIVE, Status.DELETED]
    )

    assert hits == []


def test_more_matching_words_rank_higher(store: SqliteStore) -> None:
    weak = _add(store, "Postgres is mentioned once here among many other unrelated words")
    strong = _add(store, "orders database is Postgres")

    hits = store.keyword_search("orders postgres", k=5, scopes=["orders"], statuses=ACTIVE)

    assert [h[0] for h in hits] == [strong, weak]


@pytest.mark.parametrize(
    "query",
    ['what "about" quotes', "orders-db: NEAR(x)", "AND OR NOT", "col:val *", "日本語 test"],
)
def test_unsafe_queries_do_not_raise(store: SqliteStore, query: str) -> None:
    _add(store, "orders db")

    store.keyword_search(query, k=5, scopes=["orders"], statuses=ACTIVE)


def test_query_without_words_returns_nothing(store: SqliteStore) -> None:
    _add(store, "orders")

    assert store.keyword_search("?!  --", k=5, scopes=["orders"], statuses=ACTIVE) == []


def test_fts_query_quotes_and_dedupes() -> None:
    assert _fts_query('Postgres "OR" postgres-db') == '"postgres" OR "or" OR "db"'
