"""Safe file edits for `init`: backups, JSON merge/removal, marked rule blocks.

Every write is atomic (temp file + replace). Nothing is ever written over a file we could not
parse: a malformed JSON config raises ``ConfigFileError`` and is left untouched.
"""

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ctxbook.errors import CtxbookError

START = "<!-- ctxbook:start -->"
END = "<!-- ctxbook:end -->"
BACKUP_TAG = ".ctxbook-backup-"


class ConfigFileError(CtxbookError):
    """A config file exists but cannot be read or parsed; it was not changed."""


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup(path: Path, now: datetime | None = None) -> Path:
    """Copy ``path`` next to itself as ``<name>.ctxbook-backup-<UTC time>`` and return it."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    target = path.with_name(f"{path.name}{BACKUP_TAG}{stamp}")
    shutil.copy2(path, target)
    return target


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ── JSON ─────────────────────────────────────────────────────────────────────


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigFileError(
            f"{path} is not valid JSON ({exc.msg}, line {exc.lineno}); it was not changed. "
            "Fix or move the file, then run init again."
        ) from None
    if not isinstance(data, dict):
        raise ConfigFileError(f"{path} does not contain a JSON object; it was not changed.")
    return data


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _parent(data: dict[str, Any], keys: tuple[str, ...], path: Path) -> dict[str, Any]:
    node = data
    for key in keys:
        child = node.setdefault(key, {})
        if not isinstance(child, dict):
            raise ConfigFileError(f"{path}: {key!r} is not a JSON object; it was not changed.")
        node = child
    return node


def json_with_entry(path: Path, keys: tuple[str, ...], value: Any) -> str | None:
    """New file text with ``keys`` set to ``value``; ``None`` if it is already set."""
    data = read_json(path)
    parent = _parent(data, keys[:-1], path)
    if parent.get(keys[-1]) == value:
        return None
    parent[keys[-1]] = value
    return dump_json(data)


def json_without_entry(path: Path, keys: tuple[str, ...]) -> str | None:
    """New file text with ``keys`` removed; ``None`` if it is not there."""
    data = read_json(path)
    node: Any = data
    for key in keys[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, dict) or keys[-1] not in node:
        return None
    del node[keys[-1]]
    return dump_json(data)


def json_with_list_item(path: Path, keys: tuple[str, ...], item: str) -> str | None:
    data = read_json(path)
    parent = _parent(data, keys[:-1], path)
    items = parent.setdefault(keys[-1], [])
    if not isinstance(items, list):
        raise ConfigFileError(f"{path}: {keys[-1]!r} is not a JSON list; it was not changed.")
    if item in items:
        return None
    items.append(item)
    return dump_json(data)


def json_without_list_item(path: Path, keys: tuple[str, ...], item: str) -> str | None:
    data = read_json(path)
    node: Any = data
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, list) or item not in node:
        return None
    node.remove(item)
    return dump_json(data)


def json_is_empty_shell(text: str) -> bool:
    """True if every top-level value is an empty ``{}`` or ``[]`` (e.g. ``{"mcpServers": {}}``).

    Deliberately shallow: ``{"mcpServers": {"x": {}}}`` still holds the user's server ``x``.
    """
    data = json.loads(text)
    return isinstance(data, dict) and all(value in ({}, []) for value in data.values())


# ── Marked rule blocks ───────────────────────────────────────────────────────


def block(rule: str) -> str:
    return f"{START}\n{rule.rstrip()}\n{END}\n"


def _find_block(text: str) -> tuple[int, int] | None:
    start = text.find(START)
    if start == -1:
        return None
    end = text.find(END, start)
    if end == -1:
        return None
    end += len(END)
    if text[end : end + 1] == "\n":
        end += 1
    return start, end


def text_with_block(path: Path, rule: str) -> str | None:
    """New text with our marked block added or refreshed; ``None`` if already identical."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new_block = block(rule)
    found = _find_block(text)
    if found:
        start, end = found
        if text[start:end] == new_block:
            return None
        return text[:start] + new_block + text[end:]
    if not text:
        return new_block
    separator = "\n" if text.endswith("\n") else "\n\n"
    return text + separator + new_block


def text_without_block(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    found = _find_block(text)
    if not found:
        return None
    start, end = found
    before = text[:start]
    if before.endswith("\n\n"):
        before = before[:-1]  # drop the blank line init added before the block
    return before + text[end:]
