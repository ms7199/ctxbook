from ctxbook.config import Settings
from ctxbook.core.service import MemoryService
from ctxbook.models import DATA_NOTE
from tests.unit.core.conftest import Clock, ServiceFactory


def _seed(service: MemoryService) -> dict[str, int]:
    return {
        "pg": service.save("The orders service database is Postgres", "shop", "a").memory_id,
        "react": service.save("Frontend uses React", "shop", "a").memory_id,
        "other": service.save("Billing database is Oracle", "billing", "a").memory_id,
        "pref": service.save("User prefers short answers", "global", "a").memory_id,
    }


def test_finds_relevant_fact_first_with_labels(service: MemoryService) -> None:
    ids = _seed(service)

    result = service.search("orders database", "shop")

    assert result.results[0].id == ids["pg"]
    assert result.results[0].note == DATA_NOTE
    assert result.mode == ("hybrid" if service._embedder else "keyword")


def test_includes_global_but_not_other_scopes(service: MemoryService) -> None:
    ids = _seed(service)

    found = {f.id for f in service.search("database answers prefers", "shop").results}

    assert ids["pref"] in found
    assert ids["other"] not in found


def test_only_active_facts(service: MemoryService) -> None:
    old = service.save("Orders database is Postgres", "shop", "a").memory_id
    new = service.update(old, "Orders database is MongoDB", "a").memory_id

    found = [f.id for f in service.search("orders database", "shop").results]

    assert found == [new]


def test_no_match_message(service: MemoryService) -> None:
    _seed(service)

    result = service.search("kubernetes helm charts", "shop")

    assert result.results == []
    assert result.message == "No matching memories."


def test_limit_and_token_budget(make_service: ServiceFactory, mode: str) -> None:
    service = make_service(mode, Settings(token_budget=60))
    for i in range(8):
        service.save(f"database fact number {i} " + "padding " * 10, "shop", "a")

    assert len(service.search("database fact", "shop", limit=3).results) <= 3
    # each fact is about 23 tokens + 20 for labels: only one fits in 60
    assert len(service.search("database fact", "shop", limit=20).results) == 1


def test_recency_breaks_ties(make_service: ServiceFactory, mode: str, clock: Clock) -> None:
    service = make_service(mode)
    older = service.save("Team standup at 10am", "shop", "a").memory_id
    clock.advance(days=200)
    newer = service.save("Team retro at 4pm", "shop", "a").memory_id

    found = [f.id for f in service.search("team", "shop").results]

    assert found.index(newer) < found.index(older)


def test_search_scope_is_case_insensitive(service: MemoryService) -> None:
    ids = _seed(service)

    assert service.search("orders database", "SHOP").results[0].id == ids["pg"]
