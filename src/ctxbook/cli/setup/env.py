"""The parts of the machine `init` depends on, injectable so tests use a fake home folder."""

import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


def _run(argv: list[str]) -> CommandResult:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(returncode=1, output=str(exc))
    return CommandResult(done.returncode, (done.stdout or "") + (done.stderr or ""))


@dataclass(frozen=True)
class SetupEnv:
    home: Path
    system: str  # platform.system(): "Darwin", "Windows" or "Linux"
    appdata: Path | None  # %APPDATA% on Windows
    which: Callable[[str], str | None]
    run: Callable[[list[str]], CommandResult]

    @classmethod
    def current(cls) -> "SetupEnv":
        appdata = os.environ.get("APPDATA")
        return cls(
            home=Path.home(),
            system=platform.system(),
            appdata=Path(appdata) if appdata else None,
            which=shutil.which,
            run=_run,
        )
