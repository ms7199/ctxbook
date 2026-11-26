from pathlib import Path

import numpy as np
import pytest

from ctxbook.errors import EmbeddingMismatchError
from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore
from tests.conftest import T0, StoreFactory, at

ACTIVE = [Status.ACTIVE]


def _add(store: SqliteStore, vector: list[float], scope: str = "s", **kw: object) -> int:
    args: dict[str, object] = {
        "content": f"fact {vector}",
        "scope": scope,
        "source_app": "a",
        "status": Status.ACTIVE,
        "now": T0,
        "vector": vector,
        **kw,
    }
    return store.add(**args).id  # type: ignore[arg-type]


def test_nearest_first_with_cosine_similarity(store: SqliteStore) -> None:
    same = _add(store, [1, 0, 0])
    diagonal = _add(store, [1, 1, 0])
    orthogonal = _add(store, [0, 1, 0])

    hits = store.vector_search([2, 0, 0], k=3, scopes=["s"], statuses=ACTIVE)

    assert [h[0] for h in hits] == [same, diagonal, orthogonal]
    assert [round(h[1], 4) for h in hits] == [1.0, round(1 / np.sqrt(2), 4), 0.0]


def test_k_limits_results(store: SqliteStore) -> None:
    for i in range(5):
        _add(store, [1, i, 0])

    assert len(store.vector_search([1, 0, 0], k=2, scopes=["s"], statuses=ACTIVE)) == 2


def test_filters_scope_and_status(store: SqliteStore) -> None:
    keep = _add(store, [1, 0, 0])
    _add(store, [1, 0, 0], scope="other")
    _add(store, [1, 0, 0], status=Status.PENDING)

    hits = store.vector_search([1, 0, 0], k=10, scopes=["s"], statuses=ACTIVE)

    assert [h[0] for h in hits] == [keep]


def test_multiple_scopes(store: SqliteStore) -> None:
    a = _add(store, [1, 0, 0], scope="s")
    b = _add(store, [1, 0.1, 0], scope="global")

    hits = store.vector_search([1, 0, 0], k=10, scopes=["s", "global"], statuses=ACTIVE)

    assert {h[0] for h in hits} == {a, b}


def test_deleted_fact_leaves_vector_index(store: SqliteStore) -> None:
    memory_id = _add(store, [1, 0, 0])
    store.change_status(
        memory_id, expected=Status.ACTIVE, new=Status.DELETED, source_app="a", now=at(1)
    )

    hits = store.vector_search(
        [1, 0, 0], k=5, scopes=["s"], statuses=[Status.ACTIVE, Status.DELETED]
    )

    assert hits == []


def test_wrong_vector_length_is_rejected(store: SqliteStore) -> None:
    with pytest.raises(EmbeddingMismatchError):
        _add(store, [1, 0])
    assert store.list_memories() == []


def test_ids_missing_vectors(store: SqliteStore) -> None:
    with_vector = _add(store, [1, 0, 0])
    without = store.add(content="x", scope="s", source_app="a", status=Status.PENDING, now=T0).id

    assert store.ids_missing_vectors() == [without]
    store.set_vector(without, [0, 1, 0])
    assert store.ids_missing_vectors() == []
    assert with_vector not in store.ids_missing_vectors()


def test_keyword_only_store_has_no_vector_search(make_store: StoreFactory) -> None:
    store = make_store(model=None, dim=None)
    store.add(content="x", scope="s", source_app="a", status=Status.ACTIVE, now=T0)

    assert store.vector_search([1, 0, 0], k=5, scopes=["s"], statuses=ACTIVE) == []
    with pytest.raises(ValueError, match="without an embedding model"):
        store.set_vector(1, [1, 0, 0])


def test_backends_return_same_top_results(tmp_path: Path) -> None:
    """CLAUDE.md section 11: sqlite-vec and the numpy fallback must agree."""
    rng = np.random.default_rng(seed=7)
    data = rng.normal(size=(300, 32)).astype(np.float32)
    queries = rng.normal(size=(15, 32)).astype(np.float32)
    scopes = ["a", "b", "global"]

    stores = {
        name: SqliteStore(
            tmp_path / f"{name}.db",
            embed_model="parity",
            embed_dim=32,
            force_numpy=name == "numpy",
        )
        for name in ("sqlite-vec", "numpy")
    }
    assert {s.vector_backend for s in stores.values()} == {"sqlite-vec", "numpy"}
    for store in stores.values():
        with store.transaction():
            for i, vec in enumerate(data):
                store.add(
                    content=f"fact {i}",
                    scope=scopes[i % 3],
                    source_app="a",
                    status=Status.ACTIVE,
                    now=T0,
                    vector=vec.tolist(),
                )

    for query in queries:
        results = {
            name: store.vector_search(query.tolist(), k=10, scopes=["a", "global"], statuses=ACTIVE)
            for name, store in stores.items()
        }
        vec_hits, np_hits = results["sqlite-vec"], results["numpy"]
        assert [h[0] for h in vec_hits] == [h[0] for h in np_hits]
        assert np.allclose([h[1] for h in vec_hits], [h[1] for h in np_hits], atol=1e-5)

    for store in stores.values():
        store.close()
