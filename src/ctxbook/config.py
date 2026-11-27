"""All tunable values in one place.

Tuned on 2026-11-27 with the conflict-set evaluation (eval/results/conflicts.md, bge-small):
- similar_threshold 0.60 -> 0.70: still flags 100% of changed facts, false flags 42% -> 12.5%.
- recency_weight 0.2 -> 0.02 in hybrid mode: with conflict handling, outdated facts are already
  gone, and a strong recency boost let recent but irrelevant facts outrank the answer
  (Recall@1 85.0% -> 96.7%, stale answers still 0%).
- keyword-only mode misses some changes (no embeddings), so it keeps the stronger recency boost,
  which keeps stale answers at 0% there.
The dataset is synthetic: confirm these with LongMemEval before treating them as final.
"""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class Settings:
    # Conflict detection (embedding mode): cosine similarity to the closest active fact.
    similar_threshold: float = 0.70  # below: unrelated -> saved
    duplicate_threshold: float = 0.95  # at/above: same fact -> duplicate
    conflict_candidates: int = 5
    # Conflict detection (keyword-only mode): share of meaningful words in common.
    keyword_overlap_threshold: float = 0.5

    # Search
    search_pool: int = 20  # hits taken from each of vector and keyword search
    search_min_similarity: float = 0.50  # vector hits below this are dropped (placeholder)
    rrf_k: int = 60
    recency_weight: float = 0.02  # hybrid mode: a tie-breaker, not a relevance override
    keyword_recency_weight: float = 0.2  # keyword-only mode (see module docstring)
    recency_half_life_days: float = 90.0
    default_limit: int = 5
    max_limit: int = 20
    token_budget: int = 500  # rough tokens for all returned facts together

    # Input limits (decision D8)
    max_content_chars: int = 1000
    max_query_chars: int = 500
    max_scope_chars: int = 100

    # Pending facts never resolved are auto-accepted after this (decision D5)
    pending_expiry: timedelta = timedelta(days=7)

    global_scope: str = "global"

    def __post_init__(self) -> None:
        if not 0 <= self.similar_threshold < self.duplicate_threshold <= 1:
            raise ValueError("need 0 <= similar_threshold < duplicate_threshold <= 1")
        if not 1 <= self.default_limit <= self.max_limit:
            raise ValueError("need 1 <= default_limit <= max_limit")
