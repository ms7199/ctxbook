import subprocess
import sys
from pathlib import Path

_SCRIPT = """
import sys
from datetime import UTC, datetime
from ctxbook.embeddings.fastembed_embedder import FastembedEmbedder  # module only, no model
from ctxbook.models import Status
from ctxbook.storage.sqlite_store import SqliteStore

store = SqliteStore(sys.argv[1], embed_model=None, embed_dim=None)
store.add(content="orders use Postgres", scope="s", source_app="a",
          status=Status.ACTIVE, now=datetime.now(UTC))
hits = store.keyword_search("postgres", k=5, scopes=["s"], statuses=[Status.ACTIVE])
assert len(hits) == 1, hits
print(sorted(m for m in ("fastembed", "onnxruntime") if m in sys.modules))
"""


def test_keyword_only_never_imports_fastembed(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(tmp_path / "m.db")],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
