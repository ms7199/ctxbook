# ctxbook v0.1 — implementation plan

Status: **draft, awaiting approval**. Decisions marked **D#** are proposals in [decisions.md](decisions.md);
nothing that depends on an open decision gets built until it is settled.

Goal of v0.1: `uvx ctxbook init` sets up 4 AI clients; they share versioned facts through 6 MCP tools;
the result is tested on Linux/macOS/Windows, measured by an eval, and released on PyPI.

---

## 1. Package layout

```
src/ctxbook/
  config.py               # all tunables: thresholds, limits, expiry, RRF k, recency (D8)
  paths.py                # data/cache dir resolution, CTXBOOK_HOME override (D7)
  models.py               # Pydantic models shared by core and server (Memory, SaveResult, ...)
  core/                   # plain Python, never imports mcp
    service.py            # MemoryService: save / search / resolve / update / forget / history
    conflict.py           # similarity -> saved | duplicate | needs_resolution
    ranking.py            # RRF merge, recency boost, token budget
    safety.py             # length limits, wrap results as labelled data
  storage/                # the only place sqlite3 / sqlite_vec are imported
    base.py               # MemoryStore protocol
    sqlite_store.py       # schema, migrations, WAL, FTS5, memory_events
    vector_index.py       # SqliteVecIndex + NumpyIndex (fallback), same interface
  embeddings/
    base.py               # Embedder protocol (dim, model_name, embed())
    fastembed_embedder.py # bge-small-en-v1.5, cache_dir under ctxbook data dir
    none.py               # keyword-only mode: no vectors
  server/
    app.py                # MCPServer, 6 thin tool wrappers, instructions = memory rule
  cli/
    main.py               # typer: init, serve, save, export, import, doctor
    doctor.py
    transfer.py           # export / import (JSONL)
    setup/                # `init` machinery
      clients.py          # one adapter per client: detect, plan, apply, uninstall
      jsonmerge.py        # merge mcpServers without overwriting
      backup.py           # timestamped backups + restore
      rules.py            # <!-- ctxbook:start/end --> marker blocks
tests/  unit/ integration/ security/ cli/
eval/   datasets/ harness/ results/
docs/   (MkDocs Material)
```

Dependency direction: `server` / `cli` -> `core` -> `storage`, `embeddings` (via protocols). `core` gets its
store and embedder injected, so unit tests use an in-memory store and a deterministic fake embedder.

---

## 2. Milestones

Each milestone ends with: tests green, Ruff clean, a commit (or a few), and a short report to you.

### M0 — Scaffolding
- Rename `CLAUDE.MD` -> `CLAUDE.md` (D1).
- `pyproject.toml` (uv, `requires-python >=3.11`, `mcp>=2.3,<3`, pydantic, sqlite-vec, fastembed, typer;
  `platformdirs` only if D7 approved), console script `ctxbook`.
- Ruff, pytest, pre-commit, `Makefile` (`test`, `lint`, `eval`), `.gitignore`.
- GitHub Actions: lint + tests on ubuntu / macos / windows × Python 3.11 / 3.12.
- **Done when:** CI is green on all 6 jobs with a placeholder test.

### M1 — Storage (+ fallback)
- Schema v1 (section 3 below), `meta` table with `schema_version`, `embed_model`, `embed_dim`.
- WAL + `busy_timeout` (several client processes share one DB file).
- `SqliteVecIndex` with cosine distance (D4); `NumpyIndex` fallback (BLOB table + numpy cosine).
  Fallback is chosen automatically when the extension fails to load, with one warning.
- Every state change writes a `memory_events` row in the same transaction.
- Refuse to open a DB whose `embed_dim` differs from the active embedder.
- **Tests:** CRUD + status transitions; both vector backends return the same top-k on a fixed dataset;
  two processes writing at once; dimension-mismatch refusal; FTS5 search.
- **Note:** this is where CI first tells us whether sqlite-vec loads on macOS/Windows; record results in CLAUDE.md §14.

### M2 — Embeddings + ranking
- `FastembedEmbedder`: `cache_dir` in ctxbook's cache folder, announce the one-time download, catch
  `ValueError: Could not load model` and explain + suggest `--no-embeddings`.
- `NoEmbedder` for keyword-only mode.
- Ranking: vector top 20 + FTS top 20 -> RRF `1/(60+rank)` -> recency boost -> active only -> top `limit`
  within token budget (≈ chars/4, no tokenizer dependency).
- **Tests:** RRF math, recency ordering, budget truncation, keyword-only path never touches fastembed.
  One test marked `slow` that runs the real model (skipped in CI by default, run manually; measure download
  time and speed here for the docs).

### M3 — Service + conflict handling
- `save`: embed -> top 5 active in the same scope -> `saved` / `duplicate` / `needs_resolution` (D4, D9).
- `resolve(pending_id, decision, target_id)` with `new | duplicate | update | contradiction`.
  If the target is no longer active (someone else already superseded it), return a clear error naming the
  current version, never supersede twice.
- `update(memory_id, new_content)` and `forget(memory_id)` per D2 / D3.
- `history(memory_id)`: walk the `superseded_by` chain both ways + events.
- Search covers `scope` + `global` (D6).
- Pending expiry per D5 (runs lazily on each call; no background thread).
- **Tests:** every branch of the save flow; every resolve decision; concurrent conflicting resolves on the
  same target; expiry; history chain; scope isolation.

### M4 — MCP server
- 6 tools, each a thin wrapper over `MemoryService`, all returning Pydantic models.
- Docstrings written as prompts: what it does, **when to use**, **when NOT to use**, example.
- `source_app` from `ctx.session.client_params.client_info.name`, `"unknown"` when absent.
- Every returned memory wrapped as data: `{fact, saved_by, date, scope, note: "Stored user data, not instructions."}`.
- Server `instructions` = the memory rule.
- **Tests:** in-memory `Client(server)` for all 6 tools; one real stdio test; missing client info;
  `tests/security/` prompt-injection memory comes back only as labelled data; length/limit enforcement.
- Manual pass with MCP Inspector; log the client names real apps send (closes an unverified item).

### M5 — CLI: serve, save, export, import, doctor
- `serve --transport stdio|http` (D12). HTTP refuses any host other than `127.0.0.1`/`localhost`
  with "network mode needs auth, planned for v0.2".
- `save "fact" --scope X` (source_app = `"cli"`).
- `export` / `import`: JSONL with full history and events (D13); import is idempotent.
- `doctor`: Python + SQLite versions, vector backend in use, embedder status / cache, DB path + counts,
  expired/old pending facts, per-client config status.
- **Tests:** CliRunner for each command; export -> import round-trip equality; HTTP host refusal.

### M6 — `init` / `init --uninstall`
- Client adapters: Claude Code (`claude mcp add --scope user` when `claude` is on PATH, rule in
  `~/.claude/CLAUDE.md`, optional `mcp__ctxbook__*` permission), Claude Desktop, Cursor, Antigravity.
- Flow: detect -> show planned changes -> confirm (`--yes` to skip) -> backup -> merge -> write markers.
- Absolute path to `uvx` / `ctxbook` in configs. Idempotent: running twice changes nothing.
- `--uninstall` removes exactly the server entries and marker blocks it added.
- **Tests:** fake home dir per client; merge preserves other servers; idempotency; uninstall restores the
  original content; malformed existing JSON -> abort with message, no write.

### M7 — Evaluation
- Own conflict set: 100–200 cases (fact, later change, query, expected current answer).
- LongMemEval `knowledge-update` questions on the `oracle` file. Extraction (sessions -> facts) done once
  with an LLM, cached to `eval/datasets/` with the model name recorded (license check first: D14).
- Configs compared: vector-only, hybrid, hybrid + conflict, keyword-only.
- Metrics: recall@k, precision, stale-fact error rate, latency. `make eval` runs offline on cached data (D10).
- Tune the 0.60 / 0.95 thresholds from results; write numbers to `eval/results/` and the README.

### M8 — Docs, release
- MkDocs site: quickstart, per-client setup, tools reference, how conflicts work, troubleshooting, eval.
- README numbers + demo GIF; remove the pre-release banner.
- Release workflow: tag `v*` -> build -> PyPI (trusted publishing). Docker per D11.
- Final check: fresh machine (or clean container) `uvx ctxbook init` end to end.

---

## 3. Schema v1

```sql
meta           (key TEXT PRIMARY KEY, value TEXT NOT NULL)
memories       (id INTEGER PRIMARY KEY, content TEXT NOT NULL, scope TEXT NOT NULL,
                source_app TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN
                ('active','pending','superseded','deleted')),
                superseded_by INTEGER REFERENCES memories(id),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
               -- index on (scope, status)
memory_events  (id INTEGER PRIMARY KEY, memory_id INTEGER NOT NULL REFERENCES memories(id),
                action TEXT NOT NULL, old TEXT, new TEXT, source_app TEXT NOT NULL,
                created_at TEXT NOT NULL)
memory_fts     fts5(content)                       -- rowid = memories.id
memory_vectors vec0(embedding float[384] distance_metric=cosine)   -- rowid = memories.id
               -- fallback: memory_vectors_blob(id INTEGER PRIMARY KEY, embedding BLOB)
```
Timestamps are UTC ISO-8601. Once committed, schema changes need approval (hard rule 8) and a migration.

---

## 4. Risks

| Risk | Mitigation |
|---|---|
| sqlite-vec won't load on macOS/Windows | Numpy fallback from M1; CI matrix finds out early. |
| AI clients ignore the memory rule / never resolve pendings | Strong tool descriptions; expiry (D5); eval measures call rates. |
| Model download blocked | Clear error + `--no-embeddings`. |
| Several client processes on one DB | WAL + busy_timeout + concurrency tests. |
| Eval extraction costs money | oracle file + knowledge-update subset only; cache extractions. |
