from ctxbook.models import Status
from tests.fakes import FakeEmbedder
from tests.unit.core.conftest import ServiceFactory


def test_facts_saved_keyword_only_get_vectors_when_embeddings_turn_on(
    make_service: ServiceFactory,
) -> None:
    keyword = make_service("keyword")
    memory_id = keyword.save("Deploys happen on Fridays", "shop", "a").memory_id
    keyword._store.close()

    hybrid = make_service("hybrid")
    assert hybrid._store.ids_missing_vectors() == [memory_id]

    hybrid.search("deploys fridays", "shop")  # first operation embeds missing facts

    assert hybrid._store.ids_missing_vectors() == []
    hits = hybrid._store.vector_search(
        FakeEmbedder().embed_query("Deploys happen on Fridays"),
        k=1,
        scopes=["shop"],
        statuses=[Status.ACTIVE],
    )
    assert hits[0][0] == memory_id
    assert hits[0][1] > 0.99
