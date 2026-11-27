"""What `init` does for each AI client (CLAUDE.md section 10, verified against official docs)."""

from pathlib import Path

from ctxbook.cli.setup.actions import (
    ClientPlan,
    CommandAction,
    json_entry,
    json_list_item,
    rule_block,
)
from ctxbook.cli.setup.env import SetupEnv
from ctxbook.cli.setup.launch import display
from ctxbook.rules import MEMORY_RULE

SERVER_NAME = "ctxbook"
SERVER_KEYS = ("mcpServers", SERVER_NAME)
TOOL_PERMISSION = "mcp__ctxbook__*"


def _stdio_entry(command: list[str]) -> dict[str, object]:
    return {"command": command[0], "args": command[1:]}


def claude_code(env: SetupEnv, command: list[str], *, allow_tools: bool) -> ClientPlan:
    claude = env.which("claude")
    claude_dir = env.home / ".claude"
    plan = ClientPlan("Claude Code", detected=bool(claude) or claude_dir.is_dir())
    if not plan.detected:
        return plan
    add_argv = ["mcp", "add", "--scope", "user", SERVER_NAME, "--", *command]
    if claude:
        plan.actions.append(
            CommandAction(
                client=plan.name,
                argv=[claude, *add_argv],
                undo_argv=[claude, "mcp", "remove", SERVER_NAME, "--scope", "user"],
                description="register the server: claude mcp add --scope user ctxbook ...",
                env=env,
            )
        )
    else:
        # Decision (2026-11-27, option a): never hand-edit ~/.claude.json; print the command.
        plan.notes.append(
            "Claude Code: the `claude` command was not found, so register the server yourself "
            "by running this once where `claude` is available:\n    "
            + display(["claude", *add_argv], env.system)
        )
    plan.actions.append(
        rule_block(plan.name, claude_dir / "CLAUDE.md", MEMORY_RULE, "add the memory rule")
    )
    if allow_tools:
        plan.actions.append(
            json_list_item(
                plan.name,
                claude_dir / "settings.json",
                ("permissions", "allow"),
                TOOL_PERMISSION,
                "allow ctxbook tools without approval prompts",
            )
        )
    return plan


def claude_desktop_config(env: SetupEnv) -> Path | None:
    if env.system == "Darwin":
        support = env.home / "Library" / "Application Support"
        return support / "Claude" / "claude_desktop_config.json"
    if env.system == "Windows" and env.appdata:
        return env.appdata / "Claude" / "claude_desktop_config.json"
    return None  # Claude Desktop is macOS and Windows only


def claude_desktop(env: SetupEnv, command: list[str]) -> ClientPlan:
    config = claude_desktop_config(env)
    plan = ClientPlan("Claude Desktop", detected=bool(config and config.parent.is_dir()))
    if not plan.detected or config is None:
        return plan
    plan.actions.append(
        json_entry(plan.name, config, SERVER_KEYS, _stdio_entry(command), "register the server")
    )
    plan.notes.append(
        "Claude Desktop: restart it to load ctxbook. It has no rules file; ctxbook sends the "
        "memory rule as its server instructions."
    )
    return plan


def cursor(env: SetupEnv, command: list[str]) -> ClientPlan:
    cursor_dir = env.home / ".cursor"
    plan = ClientPlan("Cursor", detected=cursor_dir.is_dir())
    if not plan.detected:
        return plan
    plan.actions.append(
        json_entry(
            plan.name,
            cursor_dir / "mcp.json",
            SERVER_KEYS,
            _stdio_entry(command),
            "register the server",
        )
    )
    plan.notes.append(
        "Cursor: its global rules live in Cursor Settings > Rules > User Rules (not a file "
        "ctxbook can edit). Paste this there:\n\n" + MEMORY_RULE
    )
    return plan


def antigravity(env: SetupEnv, command: list[str]) -> ClientPlan:
    gemini_dir = env.home / ".gemini"
    plan = ClientPlan("Antigravity", detected=gemini_dir.is_dir())
    if not plan.detected:
        return plan
    plan.actions.append(
        json_entry(
            plan.name,
            gemini_dir / "config" / "mcp_config.json",
            SERVER_KEYS,
            _stdio_entry(command),
            "register the server",
        )
    )
    plan.actions.append(
        rule_block(plan.name, gemini_dir / "AGENTS.md", MEMORY_RULE, "add the memory rule")
    )
    return plan


def plan_all(env: SetupEnv, command: list[str], *, allow_tools: bool) -> list[ClientPlan]:
    return [
        claude_code(env, command, allow_tools=allow_tools),
        claude_desktop(env, command),
        cursor(env, command),
        antigravity(env, command),
    ]
