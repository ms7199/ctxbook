from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ctxbook at a throwaway data folder (never the real one)."""
    folder = tmp_path / "ctxbook-home"
    monkeypatch.setenv("CTXBOOK_HOME", str(folder))
    return folder


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
