import math
import sys
from pathlib import Path

import pytest

from ctxbook.embeddings.base import Embedder
from ctxbook.embeddings.fastembed_embedder import DEFAULT_DIM, FastembedEmbedder
from ctxbook.errors import EmbeddingUnavailableError


def test_constructing_does_not_load_the_model(tmp_path: Path) -> None:
    embedder: Embedder = FastembedEmbedder(tmp_path)
    assert embedder.dim == DEFAULT_DIM
    assert embedder._model is None  # type: ignore[attr-defined]


def test_offline_error_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fastembed

    def offline(*_a: object, **_k: object) -> None:
        raise ValueError("Could not load model BAAI/bge-small-en-v1.5 from any source.")

    monkeypatch.setattr(fastembed, "TextEmbedding", offline)
    messages: list[str] = []

    with pytest.raises(EmbeddingUnavailableError, match="--no-embeddings"):
        FastembedEmbedder(tmp_path, notify=messages.append).embed_query("x")

    assert len(messages) == 1
    assert "one time only" in messages[0]


def test_missing_package_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fastembed", None)  # makes `import fastembed` fail

    with pytest.raises(EmbeddingUnavailableError, match=r"Python 3\.12"):
        FastembedEmbedder(tmp_path).load()


def test_no_announcement_when_already_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fastembed

    (tmp_path / "models--Qdrant--x" / "snapshots" / "abc").mkdir(parents=True)
    (tmp_path / "models--Qdrant--x" / "snapshots" / "abc" / "model.onnx").write_bytes(b"")
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda *a, **k: object())
    messages: list[str] = []

    FastembedEmbedder(tmp_path, notify=messages.append).load()

    assert messages == []


@pytest.mark.slow
def test_real_model_downloads_once_and_keeps_stdout_clean(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    embedder = FastembedEmbedder(tmp_path / "cache")

    vectors = embedder.embed_documents(["The orders service uses Postgres", "Unrelated"])
    query = embedder.embed_query("which database does orders use")

    out, err = capfd.readouterr()
    assert out == "", "stdout must stay clean: it carries the MCP protocol in stdio mode"
    assert "one time only" in err
    assert len(vectors) == 2
    assert len(query) == DEFAULT_DIM
    assert math.isclose(math.sqrt(sum(v * v for v in query)), 1.0, rel_tol=1e-5)
    assert embedder.is_downloaded()
