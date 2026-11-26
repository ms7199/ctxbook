import math

from ctxbook.embeddings.base import Embedder
from tests.fakes import FakeEmbedder


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_satisfies_protocol() -> None:
    embedder: Embedder = FakeEmbedder()
    assert embedder.dim == 64


def test_deterministic_and_normalised() -> None:
    e = FakeEmbedder()
    [a] = e.embed_documents(["We use Postgres"])
    assert a == e.embed_query("we use postgres!")
    assert math.isclose(math.sqrt(sum(v * v for v in a)), 1.0)


def test_shared_words_mean_higher_similarity() -> None:
    e = FakeEmbedder()
    base, close, far = e.embed_documents(
        ["orders database is Postgres", "orders database is MongoDB", "frontend uses React"]
    )
    assert _cos(base, close) > 0.6
    assert _cos(base, far) < _cos(base, close)
