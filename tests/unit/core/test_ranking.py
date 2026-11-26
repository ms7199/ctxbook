from datetime import timedelta

import pytest

from ctxbook.core.ranking import estimate_tokens, fit_budget, rank, recency_factor, rrf_merge
from tests.conftest import T0


def test_rrf_hand_computed() -> None:
    scores = rrf_merge([[1, 2, 3], [3, 1]], k=60)

    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[2] == pytest.approx(1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)


def test_rrf_item_in_both_lists_beats_item_in_one() -> None:
    scores = rrf_merge([[1, 2], [2]], k=60)
    assert scores[2] > scores[1]


def test_rrf_empty() -> None:
    assert rrf_merge([[], []]) == {}


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [(0, 1.2), (90, 1.1), (180, 1.05), (-5, 1.2)],  # future timestamps clamp to age 0
)
def test_recency_factor_halves_every_half_life(age_days: int, expected: float) -> None:
    factor = recency_factor(T0 - timedelta(days=age_days), T0, weight=0.2, half_life_days=90)
    assert factor == pytest.approx(expected)


def test_rank_applies_recency_to_break_close_calls() -> None:
    # 1 and 2 have equal RRF (each first in one list); 2 is newer, so it wins.
    updated = {1: T0 - timedelta(days=365), 2: T0}

    ranked = rank([[1], [2]], updated, T0, rrf_k=60, recency_weight=0.2, half_life_days=90)

    assert [memory_id for memory_id, _ in ranked] == [2, 1]
    assert ranked[0][1] == pytest.approx(1 / 61 * 1.2)


def test_rank_drops_ids_without_metadata() -> None:
    ranked = rank([[1, 99]], {1: T0}, T0, rrf_k=60, recency_weight=0.0, half_life_days=90)
    assert [memory_id for memory_id, _ in ranked] == [1]


def test_rank_ties_are_deterministic() -> None:
    updated = {5: T0, 3: T0}
    ranked = rank([[5], [3]], updated, T0, rrf_k=60, recency_weight=0.0, half_life_days=90)
    assert [memory_id for memory_id, _ in ranked] == [3, 5]


@pytest.mark.parametrize(("text", "tokens"), [("", 1), ("abcd", 1), ("abcde", 2), ("a" * 400, 100)])
def test_estimate_tokens(text: str, tokens: int) -> None:
    assert estimate_tokens(text) == tokens


def test_fit_budget_stops_before_exceeding() -> None:
    assert fit_budget([3, 3, 3, 3], lambda x: x, budget=7) == [3, 3]


def test_fit_budget_keeps_first_even_if_too_big() -> None:
    assert fit_budget([10, 1], lambda x: x, budget=5) == [10]


def test_fit_budget_empty() -> None:
    assert fit_budget([], lambda x: x, budget=5) == []
