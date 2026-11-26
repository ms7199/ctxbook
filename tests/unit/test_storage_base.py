import ast
from pathlib import Path

import ctxbook.storage.base as base

SRC = Path(__file__).resolve().parents[2] / "src" / "ctxbook"


def test_protocol_is_importable() -> None:
    assert hasattr(base, "MemoryStore")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_sqlite_is_only_imported_inside_storage() -> None:
    """CLAUDE.md hard rule 3."""
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if "storage" not in p.relative_to(SRC).parts
        and _imported_modules(p) & {"sqlite3", "sqlite_vec"}
    ]
    assert offenders == []


def test_core_never_imports_mcp() -> None:
    """CLAUDE.md hard rule 2."""
    core = SRC / "core"
    offenders = [str(p) for p in core.rglob("*.py") if "mcp" in _imported_modules(p)]
    assert offenders == []
