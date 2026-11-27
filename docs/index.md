# ctxbook

**Your AI tools share one memory, and it handles facts that change.**

ctxbook is a local-first [MCP](https://modelcontextprotocol.io) server. Claude Code, Claude Desktop,
Cursor, Antigravity and any other MCP client read and write the same notebook of short facts about
you and your projects. When a fact changes ("we use Postgres" → "we moved to MongoDB"), the old one
is marked *superseded* and kept in history instead of lingering in search results.

## Quickstart

You need [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uvx ctxbook init      # detect your AI tools, preview changes, back up, configure
uvx ctxbook doctor    # check everything works
```

!!! note "Before the PyPI release"
    Install from GitHub instead: `uvx --from git+https://github.com/ms7199/ctxbook ctxbook init`.

Restart your AI tools, tell one of them a fact, then ask another.

## Why it is different

- **One memory for every tool**: a single SQLite file on your machine, shared by all MCP clients.
- **Facts that change are versioned**: conflicts are flagged and the AI you are already using
  decides whether the new fact replaces an old one. No extra LLM, no API key.
- **Hybrid search**: vector + keyword search merged with Reciprocal Rank Fusion.
- **Measured**: on ctxbook's conflict set, the correct current answer is ranked first in 96.7% of
  cases and outdated facts never appear in the results. See [Evaluation](evaluation.md).
- **Private and offline**: no account, no telemetry; one model download (about 67 MB) on first
  use, or none at all with `--no-embeddings`.

Next: [Setup](setup.md) · [MCP tools](tools.md) · [How it works](how-it-works.md)
