"""Local embeddings with fastembed (default: BAAI/bge-small-en-v1.5, 384 dimensions).

fastembed is imported lazily: keyword-only mode never loads it, the MCP handshake is not
slowed down by it, and platforms where it is not installed (Intel Mac + Python 3.14+, see
decision D17) get a clear message instead of an import crash.
"""

import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ctxbook.errors import EmbeddingUnavailableError

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM = 384
DOWNLOAD_SIZE_MB = 67


def _stderr(message: str) -> None:
    # Never stdout: in stdio mode stdout carries the MCP protocol.
    print(message, file=sys.stderr, flush=True)


class FastembedEmbedder:
    """Embeds text with a local ONNX model, downloaded once into ``cache_dir``."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        model_name: str = DEFAULT_MODEL,
        dim: int = DEFAULT_DIM,
        notify: Callable[[str], None] = _stderr,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._model_name = model_name
        self._dim = dim
        self._notify = notify
        self._model: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def is_downloaded(self) -> bool:
        """Best-effort check that the model is already in the cache (Hugging Face layout)."""
        return any(self._cache_dir.glob("models--*/snapshots/*/*"))

    def load(self) -> None:
        """Load the model now (downloading it on first use). Safe to call repeatedly."""
        if self._model is not None:
            return
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingUnavailableError(
                "The local embedding model is not available on this platform (the "
                "onnxruntime package has no build for it, e.g. Intel Macs with Python 3.14+). "
                "ctxbook can run with --no-embeddings (keyword search only), or use Python "
                "3.12 for full search: `uvx --python 3.12 ctxbook ...`."
            ) from exc
        if not self.is_downloaded():
            self._notify(
                f"ctxbook: downloading the embedding model {self._model_name} "
                f"(about {DOWNLOAD_SIZE_MB} MB, one time only) into {self._cache_dir} ..."
            )
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._model = TextEmbedding(self._model_name, cache_dir=str(self._cache_dir))
        except ValueError as exc:
            raise EmbeddingUnavailableError(
                f"Could not download the embedding model {self._model_name} (needed once, "
                f"about {DOWNLOAD_SIZE_MB} MB, from Hugging Face). This usually means there is "
                "no internet connection or a company firewall blocks huggingface.co. Try again "
                "when online, or run ctxbook with --no-embeddings to use keyword search only "
                "(no download needed)."
            ) from exc

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.load()
        return [vector.tolist() for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        self.load()
        return next(iter(self._model.query_embed(text))).tolist()
