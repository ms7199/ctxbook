"""Test doubles."""

import hashlib
import math
import re
from collections.abc import Sequence

_WORD = re.compile(r"\w+")


class FakeEmbedder:
    """Deterministic bag-of-words embedder: texts sharing words get similar vectors.

    Identical texts (ignoring case and punctuation) give cosine similarity 1.0; texts with no
    shared words give 0.0. Good enough to drive the conflict logic without a real model.
    """

    model_name = "fake-bow"

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim
        self.calls = 0

    @property
    def dim(self) -> int:
        return self._dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for word in _WORD.findall(text.lower()):
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self._dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vector(text)
