"""`ctxbook init` and `ctxbook init --uninstall`: preview, confirm, apply, record, undo."""

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from ctxbook.cli.setup import files
from ctxbook.cli.setup.actions import Change, ClientPlan, CommandAction, FileAction
from ctxbook.cli.setup.clients import plan_all
from ctxbook.cli.setup.env import SetupEnv
from ctxbook.cli.setup.launch import display

Echo = Callable[[str], None]
Confirm = Callable[[str], bool]

SUPPORTED = "Claude Code, Claude Desktop, Cursor, Antigravity"


class Manifest(BaseModel):
    version: int = 1
    changes: list[Change] = []


def manifest_path(data_dir: Path) -> Path:
    return data_dir / "init-manifest.json"


def load_manifest(data_dir: Path) -> Manifest:
    path = manifest_path(data_dir)
    if not path.exists():
        return Manifest()
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def save_manifest(data_dir: Path, manifest: Manifest) -> None:
    path = manifest_path(data_dir)
    if not manifest.changes:
        path.unlink(missing_ok=True)
        return
    files.write_atomic(path, manifest.model_dump_json(indent=2) + "\n")


def _record(manifest: Manifest, change: Change) -> None:
    """Keep the first backup/created flag for a location; refresh its post-write hash."""
    for existing in manifest.changes:
        if existing.identity() == change.identity():
            existing.sha_after = change.sha_after
            return
    manifest.changes.append(change)


def _short(path: Path, home: Path) -> str:
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def _describe(action: FileAction | CommandAction, home: Path) -> str:
    if isinstance(action, FileAction):
        return f"{action.description} in {_short(action.path, home)}"
    return action.description


def run_init(
    env: SetupEnv,
    data_dir: Path,
    command: list[str],
    *,
    allow_tools: bool,
    yes: bool,
    confirm: Confirm,
    echo: Echo,
) -> list[ClientPlan]:
    """Preview and apply. Returns the plans so the caller can print notes."""
    plans = plan_all(env, command, allow_tools=allow_tools)
    found = [p for p in plans if p.detected]
    if not found:
        echo(f"No supported AI client found ({SUPPORTED}).")
        echo("See the README's 'Manual setup' section to add ctxbook to another MCP client.")
        return []

    todo = {id(a): a.pending() for p in found for a in p.actions}
    echo("ctxbook will start with:\n    " + display(command, env.system) + "\n")
    for plan in found:
        echo(plan.name)
        for action in plan.actions:
            state = "" if todo[id(action)] else "  (already done)"
            echo(f"  - {_describe(action, env.home)}{state}")
        if plan.notes:
            echo("  - plus a manual step, shown at the end")
    missing = [p.name for p in plans if not p.detected]
    if missing:
        echo(f"Not found: {', '.join(missing)}")

    if not any(todo.values()):
        echo("\nEverything is already set up; nothing to change.")
        return found
    echo("\nEvery file is backed up next to itself (*.ctxbook-backup-<time>) before it changes.")
    if not yes and not confirm("Apply these changes?"):
        echo("Nothing was changed.")
        return []

    manifest = load_manifest(data_dir)
    try:
        for plan in found:
            for action in plan.actions:
                if not todo[id(action)]:
                    continue
                change = action.apply()
                if change is not None:
                    _record(manifest, change)
                    echo(f"  done: {plan.name}: {_describe(action, env.home)}")
    finally:
        save_manifest(data_dir, manifest)  # keep what was done even if a later step failed
    return found


def run_uninstall(
    env: SetupEnv,
    data_dir: Path,
    *,
    yes: bool,
    confirm: Confirm,
    echo: Echo,
) -> int:
    """Remove exactly what init added. Returns how many things were undone."""
    manifest = load_manifest(data_dir)
    recorded = {c.identity(): c for c in manifest.changes}
    # The command in the plan does not matter for undo; locations and names do.
    plans = [p for p in plan_all(env, ["uvx"], allow_tools=True) if p.detected]
    if not yes and not confirm(
        "Remove ctxbook from all AI clients (originals restored where untouched)?"
    ):
        echo("Nothing was changed.")
        return 0

    undone = 0
    for plan in plans:
        for action in plan.actions:
            if isinstance(action, FileAction):
                key = Change(
                    client=plan.name,
                    kind=action.kind,
                    path=str(action.path),
                    keys=list(action.keys) or None,
                    item=action.item,
                ).identity()
                change = recorded.get(key)
            else:
                change = next((c for c in manifest.changes if c.kind == "command"), None)
            result = action.undo(change)
            if result:
                undone += 1
                echo(f"  {plan.name}: {result}")
        if plan.name == "Claude Code" and not any(
            isinstance(a, CommandAction) for a in plan.actions
        ):
            echo(
                "  Claude Code: if you registered the server, remove it where `claude` is "
                "available:\n    claude mcp remove ctxbook --scope user"
            )
    save_manifest(data_dir, Manifest())
    echo("Done." if undone else "Nothing to remove: ctxbook was not set up in any client.")
    return undone


def configured_clients(data_dir: Path) -> list[str]:
    """Clients init has changed (for doctor)."""
    return sorted({c.client for c in load_manifest(data_dir).changes})
