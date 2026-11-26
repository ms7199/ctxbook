from pathlib import Path

import platformdirs
import pytest

from ctxbook.paths import resolve_paths


def test_ctxbook_home_puts_everything_in_one_folder(tmp_path: Path) -> None:
    paths = resolve_paths({"CTXBOOK_HOME": str(tmp_path)})

    assert paths.db_path == tmp_path / "memory.db"
    assert paths.model_cache_dir == tmp_path / "cache" / "models"


def test_ctxbook_home_expands_tilde(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows

    paths = resolve_paths({"CTXBOOK_HOME": "~/mem"})

    assert paths.data_dir == tmp_path / "mem"


def test_defaults_use_os_conventions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda *a, **k: str(tmp_path / "data"))
    monkeypatch.setattr(platformdirs, "user_cache_dir", lambda *a, **k: str(tmp_path / "cache"))

    paths = resolve_paths({})

    assert paths.db_path == tmp_path / "data" / "memory.db"
    assert paths.model_cache_dir == tmp_path / "cache" / "models"


def test_empty_ctxbook_home_is_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda *a, **k: str(tmp_path / "data"))
    monkeypatch.setattr(platformdirs, "user_cache_dir", lambda *a, **k: str(tmp_path / "cache"))

    assert resolve_paths({"CTXBOOK_HOME": ""}).data_dir == tmp_path / "data"
