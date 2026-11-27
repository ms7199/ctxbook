"""Steps 7.2 and 7.3: the dataset is valid and reproducible; the harness measures correctly."""

import json
import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[2] / "eval"
sys.path.insert(0, str(EVAL))

import build_conflicts  # noqa: E402
from harness import CONFIGS, Dataset, Result, run_config  # noqa: E402

from tests.fakes import FakeEmbedder  # noqa: E402

TOY = [
    {
        "id": "t-01",
        "scope": "toy",
        "kind": "update",
        "topic": "database",
        "facts": [
            {"role": "old", "text": "The orders service uses Postgres"},
            {"role": "new", "text": "The orders service uses MongoDB"},
        ],
        "query": "orders service database",
        "current": "new",
    },
    {
        "id": "t-02",
        "scope": "toy",
        "kind": "stable",
        "topic": "deploy day",
        "facts": [{"role": "old", "text": "We deploy the API every Friday"}],
        "query": "deploy API Friday",
        "current": "old",
    },
]


@pytest.fixture
def toy(tmp_path: Path) -> Dataset:
    path = tmp_path / "toy.jsonl"
    header = {"type": "header", "seed": 0, "distractors": ["Design files live in Figma"]}
    path.write_text("\n".join(json.dumps(x) for x in [header, *TOY]) + "\n")
    return Dataset.load(path)


def _run(key: str, toy: Dataset) -> Result:
    config = next(c for c in CONFIGS if c.key == key)
    return run_config(config, toy, FakeEmbedder)


def test_without_conflict_handling_the_old_fact_lingers(toy: Dataset) -> None:
    result = _run("b", toy)

    assert result.stale_in_top_5 == 1.0  # Postgres is still returned
    assert result.recall_at_5 == 1.0


def test_with_conflict_handling_the_old_fact_is_gone(toy: Dataset) -> None:
    result = _run("c", toy)

    assert result.stale_at_1 == 0.0
    assert result.stale_in_top_5 == 0.0
    assert result.recall_at_1 == 1.0
    assert result.detection["updates_flagged"] == 1.0


def test_keyword_only_config_runs_without_embeddings(toy: Dataset) -> None:
    result = _run("d", toy)

    assert result.cases == 2
    assert 0.0 <= result.recall_at_1 <= 1.0


def test_dataset_is_reproducible_and_valid() -> None:
    first, second = build_conflicts.build(), build_conflicts.build()
    assert first == second

    committed = (EVAL / "datasets" / "conflicts.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in committed[1:]] == first  # committed file is current

    assert 100 <= len(first) <= 200
    for case in first:
        roles = [f["role"] for f in case["facts"]]
        assert roles == (["old", "new"] if case["kind"] == "update" else ["old"])
        assert case["current"] in roles
        assert case["query"].endswith("?")
    scoped = [(c["scope"], f["text"]) for c in first for f in c["facts"]]
    assert len(scoped) == len(set(scoped))  # no duplicate fact text within a project


def test_same_text_in_two_projects_is_tracked_per_project(tmp_path: Path) -> None:
    """Regression: roles were keyed by text only, hiding stale facts repeated across projects."""
    same = "The orders service uses Postgres"
    cases = [
        {
            "id": "p1-01",
            "scope": "p1",
            "kind": "update",
            "topic": "database",
            "facts": [
                {"role": "old", "text": same},
                {"role": "new", "text": "The orders service uses MongoDB"},
            ],
            "query": "orders service database",
            "current": "new",
        },
        {
            "id": "p2-01",
            "scope": "p2",
            "kind": "stable",
            "topic": "database",
            "facts": [{"role": "old", "text": same}],
            "query": "orders service database",
            "current": "old",
        },
    ]
    path = tmp_path / "two.jsonl"
    header = {"type": "header", "seed": 0, "distractors": []}
    path.write_text("\n".join(json.dumps(x) for x in [header, *cases]) + "\n")
    dataset = Dataset.load(path)
    without = next(c for c in CONFIGS if c.key == "b")

    result = run_config(without, dataset, FakeEmbedder)

    assert result.stale_in_top_5 == 1.0  # p1's outdated fact is counted, not masked by p2
    assert result.recall_at_5 == 1.0
