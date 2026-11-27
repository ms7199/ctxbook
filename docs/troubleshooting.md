# Troubleshooting

Start with `ctxbook doctor`. It changes nothing and reports the Python and SQLite versions, which
vector search mode is active, the database and its counts, the embedding model cache, unresolved
facts older than a day, and which AI clients `init` has set up.

## "Could not download the embedding model"

The model (about 67 MB) comes from Hugging Face on first use. Behind a company firewall or offline,
use keyword-only mode: `ctxbook init --no-embeddings`. Search and conflict detection still work,
just less precisely. Once downloaded, the model is cached and works offline.

## "sqlite-vec could not be loaded" / pure-Python vector search

Some Pythons cannot load SQLite extensions (macOS system Python, python.org installers, some CI
images). ctxbook then switches to a numpy fallback automatically: the results are the same, only
slower, which is fine for a personal memory. Servers started by `init` always use uv's own
Python 3.12, which can load extensions.

## Intel Mac with Python 3.14: keyword-only

The embedding runtime has no Intel-Mac build for Python 3.14+, so ctxbook installs without it and
runs keyword-only. Use Python 3.12 for full search; `init` already does this for AI clients.

## "This memory database was built with the embedding model ..."

A database remembers which model built its vectors and refuses to mix models. Switch back to the
original model, or run with `--no-embeddings`.

## The AI doesn't use memory

`init` adds a short memory rule for Claude Code and Antigravity, and prints one to paste into
Cursor's User Rules. Restart the app after `init`. You can always ask explicitly ("save this with
ctxbook", "check ctxbook for ...").

## A fact was flagged but never resolved

Pending facts are hidden from search until the AI calls `resolve_memory`. If nobody does, they are
accepted automatically after 7 days. `ctxbook doctor` lists the ones older than a day.

## Remove everything

```bash
ctxbook init --uninstall       # restores your config files
ctxbook export backup.jsonl    # optional: keep a copy of your memories first
```

Then delete the data folder shown by `ctxbook doctor`.
