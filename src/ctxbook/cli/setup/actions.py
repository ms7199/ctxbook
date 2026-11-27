"""The individual changes `init` can make, each with an exact undo.

A ``Change`` records what was done (backup, whether the file was created, the file's hash
right after the write) in the manifest, so `init --uninstall` can restore the original file
byte for byte when nobody has edited it since, or remove only ctxbook's part when they have.
"""

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from ctxbook.cli.setup import files
from ctxbook.cli.setup.env import SetupEnv
from ctxbook.errors import CtxbookError

Kind = Literal["json_entry", "json_list_item", "rule_block", "command"]


class Change(BaseModel):
    client: str
    kind: Kind
    path: str | None = None
    keys: list[str] | None = None
    item: str | None = None
    backup: str | None = None
    created: bool = False
    sha_after: str | None = None
    undo: list[str] | None = None

    def identity(self) -> tuple[object, ...]:
        return (self.kind, self.path, tuple(self.keys or ()), self.item)


@dataclass
class FileAction:
    """Add something to a file (JSON entry, JSON list item or marked rule block)."""

    client: str
    kind: Kind
    path: Path
    description: str
    add: Callable[[], str | None]  # new text, or None when already in place
    remove: Callable[[], str | None]  # text without our part, or None when absent
    keys: tuple[str, ...] = ()
    item: str | None = None

    def pending(self) -> bool:
        return self.add() is not None

    def apply(self) -> Change | None:
        new_text = self.add()
        if new_text is None:
            return None
        existed = self.path.exists()
        saved = files.backup(self.path) if existed else None
        files.write_atomic(self.path, new_text)
        return Change(
            client=self.client,
            kind=self.kind,
            path=str(self.path),
            keys=list(self.keys) or None,
            item=self.item,
            backup=str(saved) if saved else None,
            created=not existed,
            sha_after=files.sha256(self.path),
        )

    def undo(self, change: Change | None) -> str | None:
        """Remove our part. Returns a description of what happened, or None if nothing to do."""
        if change and change.sha_after and files.sha256(self.path) == change.sha_after:
            # Untouched since init wrote it: put the original back exactly.
            if change.created:
                self.path.unlink()
                return f"deleted {self.path} (created by init)"
            if change.backup and Path(change.backup).exists():
                shutil.copy2(change.backup, self.path)
                return f"restored {self.path} from its backup"
        remaining = self.remove()
        if remaining is None:
            return None
        if change and change.created and self._is_empty(remaining):
            self.path.unlink()
            return f"deleted {self.path} (created by init)"
        files.backup(self.path)
        files.write_atomic(self.path, remaining)
        return f"removed ctxbook from {self.path} (your other edits kept)"

    def _is_empty(self, text: str) -> bool:
        if self.kind == "rule_block":
            return not text.strip()
        return files.json_is_empty_shell(text) if text.strip() else True


@dataclass
class CommandAction:
    """Run a command (``claude mcp add``) whose undo is another command."""

    client: str
    argv: list[str]
    undo_argv: list[str]
    description: str
    env: SetupEnv
    already_ok: tuple[str, ...] = ("already exists",)

    def pending(self) -> bool:
        return True  # cannot be checked without running it; `claude` reports duplicates

    def apply(self) -> Change | None:
        result = self.env.run(self.argv)
        if result.returncode == 0:
            return Change(client=self.client, kind="command", undo=self.undo_argv)
        if any(marker in result.output for marker in self.already_ok):
            return None
        raise CommandFailedError(f"{' '.join(self.argv[:3])} failed: {result.output.strip()}")

    def undo(self, change: Change | None) -> str | None:
        result = self.env.run(self.undo_argv)
        if result.returncode == 0:
            return f"ran: {' '.join(self.undo_argv)}"
        return None


class CommandFailedError(CtxbookError):
    """A setup command (e.g. ``claude mcp add``) failed."""


Action = FileAction | CommandAction


@dataclass
class ClientPlan:
    name: str
    detected: bool
    actions: list[Action] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def json_entry(client: str, path: Path, keys: tuple[str, ...], value: Any, what: str) -> FileAction:
    return FileAction(
        client=client,
        kind="json_entry",
        path=path,
        description=what,
        add=lambda: files.json_with_entry(path, keys, value),
        remove=lambda: files.json_without_entry(path, keys),
        keys=keys,
    )


def json_list_item(
    client: str, path: Path, keys: tuple[str, ...], item: str, what: str
) -> FileAction:
    return FileAction(
        client=client,
        kind="json_list_item",
        path=path,
        description=what,
        add=lambda: files.json_with_list_item(path, keys, item),
        remove=lambda: files.json_without_list_item(path, keys, item),
        keys=keys,
        item=item,
    )


def rule_block(client: str, path: Path, rule: str, what: str) -> FileAction:
    return FileAction(
        client=client,
        kind="rule_block",
        path=path,
        description=what,
        add=lambda: files.text_with_block(path, rule),
        remove=lambda: files.text_without_block(path),
    )
