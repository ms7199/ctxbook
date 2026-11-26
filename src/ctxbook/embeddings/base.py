"""Embedder interface. Keyword-only mode is represented by having no embedder at all."""

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    """Turns text into fixed-size vectors."""

    @property
    def model_name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectors for stored facts (also used to compare one fact with another)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Vector for a search query."""
        ...
