"""Where ctxbook keeps its files (decision D7).

Defaults follow each OS's conventions via platformdirs. Setting ``CTXBOOK_HOME`` puts
everything under one folder instead (useful for tests, portable setups and backups).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "ctxbook"
HOME_ENV = "CTXBOOK_HOME"


@dataclass(frozen=True)
class Paths:
    data_dir: Path
    cache_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def model_cache_dir(self) -> Path:
        return self.cache_dir / "models"


def resolve_paths(env: Mapping[str, str] | None = None) -> Paths:
    env = os.environ if env is None else env
    home = env.get(HOME_ENV)
    if home:
        base = Path(home).expanduser()
        return Paths(data_dir=base, cache_dir=base / "cache")
    return Paths(
        data_dir=Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
        cache_dir=Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False)),
    )
