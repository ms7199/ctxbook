# Setup

## Automatic: `ctxbook init`

```bash
uvx ctxbook init
```

`init` detects which AI tools are installed, **shows every change it will make and asks first**,
backs up each file it touches (`<file>.ctxbook-backup-<time>`, next to the original), then:

| Tool | Server registered in | Memory rule |
|---|---|---|
| Claude Code | `claude mcp add --scope user ctxbook -- ...` | `~/.claude/CLAUDE.md` |
| Claude Desktop | `claude_desktop_config.json` (macOS, Windows) | sent as server instructions |
| Cursor | `~/.cursor/mcp.json` | printed for *Settings → Rules → User Rules* |
| Antigravity | `~/.gemini/config/mcp_config.json` | `~/.gemini/AGENTS.md` |

If the `claude` command is not on your PATH (for example you only use the VS Code extension),
`init` prints the exact `claude mcp add` command to run; it never edits `~/.claude.json` by hand.

The memory rule is wrapped in markers so it can be updated or removed cleanly:

```
<!-- ctxbook:start -->
...rule...
<!-- ctxbook:end -->
```

Finally, `init` downloads the embedding model once so the first search is fast.

### Options

| Option | Effect |
|---|---|
| `--yes` | Skip the confirmation prompt. |
| `--no-embeddings` | Keyword search only: no model download; clients start the server with `--no-embeddings`. |
| `--allow-tools` | Add `mcp__ctxbook__*` to Claude Code's `permissions.allow`, so calls are not interrupted. |
| `--source TEXT` | Where clients install ctxbook from. Default: wherever this ctxbook came from (PyPI, a git URL or a local folder). |

### How clients start the server

Every client gets the same command:

```
<absolute path to uvx> --managed-python --python 3.12 --from <source> ctxbook serve
```

An absolute path, because clients may start servers with a different `PATH`; uv's own Python
3.12, because some Pythons cannot load SQLite extensions and Intel Macs have no embedding runtime
for Python 3.14+.

### Undo: `ctxbook init --uninstall`

Removes exactly what `init` added. A file nobody has edited since is **restored from its backup
byte for byte** (or deleted if `init` created it); a file you edited since keeps your edits and
only loses ctxbook's entry or marked block. Running `init` twice changes nothing the second time.

## Manual setup

Use the same command as above in any MCP client's config, for example:

```json
{
  "mcpServers": {
    "ctxbook": {
      "command": "/absolute/path/to/uvx",
      "args": ["--managed-python", "--python", "3.12", "--from", "ctxbook", "ctxbook", "serve"]
    }
  }
}
```

For HTTP clients: `ctxbook serve --transport http` serves `http://127.0.0.1:8000/mcp`. It refuses
any host other than `127.0.0.1`, `localhost` or `::1`: network mode needs authentication, planned
for v0.2.

## Where data lives

| OS | Data (`memory.db`, init record) | Model cache |
|---|---|---|
| macOS | `~/Library/Application Support/ctxbook/` | `~/Library/Caches/ctxbook/` |
| Linux | `~/.local/share/ctxbook/` | `~/.cache/ctxbook/` |
| Windows | `%LOCALAPPDATA%\ctxbook\` | `%LOCALAPPDATA%\ctxbook\Cache\` |

Set `CTXBOOK_HOME=/some/folder` to keep everything in one folder instead.

```bash
ctxbook export backup.jsonl   # every fact with its full history
ctxbook import backup.jsonl   # restore or move; importing twice adds nothing
```
