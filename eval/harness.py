"""Evaluation harness for ctxbook's own conflict set (CLAUDE.md section 12).

Configurations:
  a. vector search only, every fact kept active (baseline)
  b. hybrid search (vector + keyword, RRF, recency), every fact kept active
  c. hybrid search + conflict handling
  d. keyword-only search + conflict handling (no embedding model)

In c and d the client AI that settles needs_resolution is an *oracle*: it always picks the
right decision. That isolates what ctxbook itself detects and retrieves; a real LLM resolver
is measured separately (LongMemEval, step 7.4).
"""

import hashlib
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ctxbook.config import Settings
from ctxbook.core.service import MemoryService
from ctxbook.embeddings.base import Embedder
from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore

K = 5
START = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Config:
    key: str
    label: str
    embeddings: bool
    search: str  # "vector" or "service" (hybrid, or keyword-only without embeddings)
    conflicts: bool


CONFIGS = (
    Config("a", "vector only (baseline)", True, "vector", False),
    Config("b", "hybrid", True, "service", False),
    Config("c", "hybrid + conflict handling", True, "service", True),
    Config("d", "keyword-only + conflict handling", False, "service", True),
)


@dataclass
class Dataset:
    cases: list[dict[str, object]]
    distractors: list[str]
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "Dataset":
        raw = path.read_bytes()
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        header, cases = rows[0], rows[1:]
        return cls(cases, list(header["distractors"]), hashlib.sha256(raw).hexdigest())


@dataclass
class Result:
    config: str
    label: str
    cases: int
    update_cases: int
    recall_at_1: float
    recall_at_5: float
    mrr: float
    stale_at_1: float  # update cases whose top result is the outdated fact
    stale_in_top_5: float  # update cases with the outdated fact anywhere in the top 5
    save_ms_mean: float
    search_ms_mean: float
    detection: dict[str, float] = field(default_factory=dict)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def _timeline(dataset: Dataset) -> list[tuple[int, str, str, str]]:
    """(day, scope, text, role-key) in save order: distractors, old facts, then updates."""
    events: list[tuple[int, str, str, str]] = []
    scopes = sorted({str(c["scope"]) for c in dataset.cases})
    for scope in scopes:
        for text in dataset.distractors:
            events.append((0, scope, text, "distractor"))
    for i, case in enumerate(dataset.cases):
        for fact in case["facts"]:  # type: ignore[attr-defined]
            day = 1 + i % 30 if fact["role"] == "old" else 60 + i % 30
            events.append((day, str(case["scope"]), fact["text"], f"{case['id']}:{fact['role']}"))
    return sorted(events, key=lambda e: e[0])


def run_config(
    config: Config,
    dataset: Dataset,
    make_embedder: Callable[[], Embedder],
    settings: Settings | None = None,
) -> Result:
    embedder = make_embedder() if config.embeddings else None
    with tempfile.TemporaryDirectory() as tmp:
        store = SqliteStore(
            Path(tmp) / "eval.db",
            embed_model=embedder.model_name if embedder else None,
            embed_dim=embedder.dim if embedder else None,
        )
        clock = Clock()
        service = MemoryService(store, embedder, settings=settings, clock=clock)
        # (scope, text) -> role key. Keyed by scope too: the same sentence can occur in
        # several projects, and a text-only key would mix their roles up.
        role_of: dict[tuple[str, str], str] = {}
        save_ms: list[float] = []
        detection = {
            "updates": 0,
            "flagged": 0,
            "missed": 0,
            "merged": 0,
            "false_flags": 0,
            "other_saves": 0,
        }

        for day, scope, text, role in _timeline(dataset):
            clock.now = START + timedelta(days=day)
            role_of[(scope, text)] = role
            started = time.perf_counter()
            if config.conflicts:
                _save_with_oracle(service, scope, text, role, role_of, detection)
            else:
                vector = embedder.embed_documents([text])[0] if embedder else None
                store.add(
                    content=text,
                    scope=scope,
                    source_app="eval",
                    status=Status.ACTIVE,
                    now=clock(),
                    vector=vector,
                )
            save_ms.append((time.perf_counter() - started) * 1000)

        clock.now = START + timedelta(days=100)
        search_ms: list[float] = []
        ranks: list[int | None] = []
        stale_top1 = stale_top5 = 0
        for case in dataset.cases:
            started = time.perf_counter()
            texts = _search(config, service, store, embedder, case)
            search_ms.append((time.perf_counter() - started) * 1000)
            scopes = (str(case["scope"]), "global")
            roles = [
                next((role_of[(s, t)] for s in scopes if (s, t) in role_of), "?") for t in texts
            ]
            current = f"{case['id']}:{case['current']}"
            ranks.append(roles.index(current) + 1 if current in roles else None)
            if case["kind"] == "update":
                stale = f"{case['id']}:old"
                stale_top1 += bool(roles) and roles[0] == stale
                stale_top5 += stale in roles
        store.close()

    n = len(dataset.cases)
    updates = sum(c["kind"] == "update" for c in dataset.cases)
    found = [r for r in ranks if r is not None]
    return Result(
        config=config.key,
        label=config.label,
        cases=n,
        update_cases=updates,
        recall_at_1=sum(r == 1 for r in found) / n,
        recall_at_5=len(found) / n,
        mrr=sum(1 / r for r in found) / n,
        stale_at_1=stale_top1 / updates,
        stale_in_top_5=stale_top5 / updates,
        save_ms_mean=statistics.mean(save_ms),
        search_ms_mean=statistics.mean(search_ms),
        detection=_rates(detection) if config.conflicts else {},
    )


def _save_with_oracle(
    service: MemoryService,
    scope: str,
    text: str,
    role: str,
    role_of: dict[tuple[str, str], str],
    detection: dict[str, float],
) -> None:
    result = service.save(text, scope, "eval")
    is_update = role.endswith(":new")
    predecessor = role.replace(":new", ":old") if is_update else None
    candidates = {role_of.get((c.scope, c.fact)): c.id for c in result.candidates}
    if is_update:
        detection["updates"] += 1
        if result.status == "needs_resolution" and predecessor in candidates:
            detection["flagged"] += 1
        elif result.status == "duplicate":
            detection["merged"] += 1  # new value lost: counted as an error
        else:
            detection["missed"] += 1
    else:
        detection["other_saves"] += 1
        if result.status == "needs_resolution":
            detection["false_flags"] += 1
    if result.status != "needs_resolution":
        return
    # Oracle client AI: "update" against the true predecessor, otherwise "new".
    if predecessor in candidates:
        service.resolve(result.memory_id, "update", candidates[predecessor], "eval")
    else:
        service.resolve(result.memory_id, "new", None, "eval")


def _search(
    config: Config,
    service: MemoryService,
    store: SqliteStore,
    embedder: Embedder | None,
    case: dict[str, object],
) -> list[str]:
    scope, query = str(case["scope"]), str(case["query"])
    if config.search == "vector":
        assert embedder is not None
        hits = store.vector_search(
            embedder.embed_query(query), k=K, scopes=[scope, "global"], statuses=[Status.ACTIVE]
        )
        memories = store.get_many(i for i, _ in hits)
        return [memories[i].content for i, _ in hits]
    return [fact.fact for fact in service.search(query, scope, limit=K).results]


def _rates(d: dict[str, float]) -> dict[str, float]:
    updates, others = d["updates"] or 1, d["other_saves"] or 1
    return {
        "updates_flagged": d["flagged"] / updates,
        "updates_missed": d["missed"] / updates,
        "updates_merged_as_duplicate": d["merged"] / updates,
        "false_flag_rate": d["false_flags"] / others,
    }


def run_all(
    dataset: Dataset, make_embedder: Callable[[], Embedder], settings: Settings | None = None
) -> list[Result]:
    return [run_config(c, dataset, make_embedder, settings) for c in CONFIGS]


def sweep(
    dataset: Dataset,
    make_embedder: Callable[[], Embedder],
    thresholds: list[float],
    duplicate: float,
) -> list[dict[str, float]]:
    """Config c at several lower thresholds: detection vs. false flags vs. end results."""
    config = CONFIGS[2]
    rows = []
    for value in thresholds:
        settings = Settings(similar_threshold=value, duplicate_threshold=duplicate)
        result = run_config(config, dataset, make_embedder, settings)
        rows.append(
            {
                "similar_threshold": value,
                "duplicate_threshold": duplicate,
                **result.detection,
                "recall_at_1": result.recall_at_1,
                "stale_at_1": result.stale_at_1,
            }
        )
    return rows


def as_dicts(results: list[Result]) -> list[dict[str, object]]:
    return [asdict(r) for r in results]


def sweep_recency(
    dataset: Dataset, make_embedder: Callable[[], Embedder], weights: list[float]
) -> list[dict[str, float]]:
    """Configs b, c and d at several recency weights (keyword-only uses its own weight)."""
    rows = []
    for weight in weights:
        settings = Settings(recency_weight=weight, keyword_recency_weight=weight)
        row: dict[str, float] = {"recency_weight": weight}
        for config in CONFIGS[1:]:
            result = run_config(config, dataset, make_embedder, settings)
            row[f"{config.key}_recall_at_1"] = result.recall_at_1
            row[f"{config.key}_stale_at_1"] = result.stale_at_1
            row[f"{config.key}_stale_in_top_5"] = result.stale_in_top_5
        rows.append(row)
    return rows
