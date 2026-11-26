"""Hybrid ranking: Reciprocal Rank Fusion, a recency boost, and a token budget."""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import TypeVar

T = TypeVar("T")  # PEP 695 `def f[T]` syntax needs Python 3.12; we support 3.11.


def rrf_merge(rankings: Sequence[Sequence[int]], *, k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion: each list adds ``1 / (k + rank)`` (rank starts at 1)."""
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, memory_id in enumerate(ranking, start=1):
            scores[memory_id] += 1.0 / (k + rank)
    return dict(scores)


def recency_factor(
    updated_at: datetime, now: datetime, *, weight: float, half_life_days: float
) -> float:
    """``1 + weight * 0.5 ** (age / half_life)``: up to ``1 + weight`` for brand-new facts."""
    age_days = max(0.0, (now - updated_at).total_seconds() / 86400)
    return 1.0 + weight * 0.5 ** (age_days / half_life_days)


def rank(
    rankings: Sequence[Sequence[int]],
    updated_at: Mapping[int, datetime],
    now: datetime,
    *,
    rrf_k: int,
    recency_weight: float,
    half_life_days: float,
) -> list[tuple[int, float]]:
    """Merge ranked id lists and apply recency. Ids missing from ``updated_at`` are dropped."""
    fused = rrf_merge(rankings, k=rrf_k)
    scored = [
        (
            memory_id,
            score
            * recency_factor(
                updated_at[memory_id], now, weight=recency_weight, half_life_days=half_life_days
            ),
        )
        for memory_id, score in fused.items()
        if memory_id in updated_at
    ]
    return sorted(scored, key=lambda item: (-item[1], item[0]))


def estimate_tokens(text: str) -> int:
    """Rough token count (about 4 characters per token); avoids a tokenizer dependency."""
    return max(1, math.ceil(len(text) / 4))


def fit_budget(items: Sequence[T], cost: Callable[[T], int], budget: int) -> list[T]:
    """Keep items in order while the total cost fits. The first item is always kept."""
    kept: list[T] = []
    used = 0
    for item in items:
        item_cost = cost(item)
        if kept and used + item_cost > budget:
            break
        kept.append(item)
        used += item_cost
    return kept
