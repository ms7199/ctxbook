from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ctxbook.cli.setup.env import CommandResult, SetupEnv

UVX = "/opt/uv/bin/uvx"
CLAUDE = "/opt/claude/bin/claude"


@dataclass
class FakeMachine:
    """A fake home folder, PATH and command runner. Never touches real configs."""

    home: Path
    system: str = "Darwin"
    on_path: dict[str, str] = field(default_factory=lambda: {"uvx": UVX})
    ran: list[list[str]] = field(default_factory=list)
    reply: Callable[[list[str]], CommandResult] = lambda argv: CommandResult(0, "ok")

    @property
    def env(self) -> SetupEnv:
        def run(argv: list[str]) -> CommandResult:
            self.ran.append(argv)
            return self.reply(argv)

        return SetupEnv(
            home=self.home,
            system=self.system,
            appdata=self.home / "AppData" / "Roaming" if self.system == "Windows" else None,
            which=self.on_path.get,
            run=run,
        )

    def install(self, *clients: str) -> None:
        """Create the folders that make a client look installed."""
        folders = {
            "claude-code": self.home / ".claude",
            "claude-desktop": self.home / "Library" / "Application Support" / "Claude",
            "claude-desktop-win": self.home / "AppData" / "Roaming" / "Claude",
            "cursor": self.home / ".cursor",
            "antigravity": self.home / ".gemini",
        }
        for client in clients:
            folders[client].mkdir(parents=True, exist_ok=True)


@pytest.fixture
def machine(tmp_path: Path) -> FakeMachine:
    home = tmp_path / "home"
    home.mkdir()
    return FakeMachine(home=home)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "ctxbook-data"
