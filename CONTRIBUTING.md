# Contributing to ctxbook

Thanks for helping! ctxbook is a small, focused project. These notes keep contributions easy to review.

## Quick setup

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python 3.11+ for you).

```bash
git clone https://github.com/ms7199/ctxbook.git
cd ctxbook
uv sync                     # install dependencies
uv run pytest               # run tests
uv run ruff check . && uv run ruff format .   # lint + format
```

To try the server by hand with the MCP Inspector (needs Node.js):

```bash
npx @modelcontextprotocol/inspector uv run ctxbook serve
```

## Before you start

- **Check the scope.** v0.1 scope is frozen (see the Roadmap in the README). For anything outside it,
  please open an issue first so we can agree on it before you write code.
- **Bigger changes:** open an issue describing the problem and your approach first.
- **Small fixes** (typos, docs, clear bugs): just open a PR.

## Code guidelines

- `core/` is plain Python and never imports MCP. `server/` stays thin.
- Storage and embeddings sit behind the `MemoryStore` and `Embedder` interfaces;
  `sqlite3` / `sqlite_vec` are only imported inside `storage/`.
- Type hints everywhere, Ruff clean, no commented-out code.
- A change is done when it has **code + tests + docstring + docs note** (if user-facing).
- Tool docstrings are prompts the AI reads: say **when to use** and **when not to use** the tool.
- Never touch real user config files in tests. Use temp directories and fake home folders.
- New dependencies need discussion in an issue first.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Keep PRs small and focused on one thing.
- Make sure `uv run pytest` and `uv run ruff check .` pass.
- If you change user-facing behaviour, update the README quickstart.

## Great first contributions

- Run the test suite on **Windows** or **macOS** and report results (sqlite-vec loading is unverified there).
- Find out which client name each AI app sends in MCP `clientInfo`.
- Add realistic cases to the conflict evaluation set (facts that change over time).
- Improve docs and error messages.

## Reporting bugs

Please include your OS, Python version, which AI client you use, and the output of `ctxbook doctor`.

## Security

Please **don't** open public issues for security problems. Report them via
[GitHub Security Advisories](https://github.com/ms7199/ctxbook/security/advisories/new).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
