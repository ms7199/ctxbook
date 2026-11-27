# ctxbook v0.1 — step-by-step checklist

The execution version of [plan-v0.1.md](plan-v0.1.md). Each step is small, and is **done only when its
`Verify` passes**. Steps marked 👤 need you (accounts, keys, a real machine, approvals).

## Rules that prevent errors and made-up APIs

1. **One step at a time.** Run its `Verify`, report the result, then move on. Never batch unverified steps.
2. **No guessed APIs.** Before using any library call not already in CLAUDE.md §5/§6, run a *spike*
   (a tiny script against the installed package) or read the installed source. Record what was confirmed
   in CLAUDE.md §5/§14 with the date. Spike steps are marked 🔬.
3. **A failing check stops the line.** Find the root cause; never loosen a test to make it pass.
4. **Never invent numbers.** Performance and eval figures come only from commands actually run.
5. **Commit at the end of each milestone** (Conventional Commits), with tests + lint green.
6. **Ask, don't assume**, for anything not covered by the plan or decisions (CLAUDE.md hard rule 9).

---

## Gate — before any code
- [x] **G1** 👤 Decisions D1–D16 in [decisions.md](decisions.md) accepted or changed.
- [x] **G2** 👤 `git push` works as ms7199 (token). *Verify:* `git ls-remote origin` succeeds.

## M0 — Scaffolding
- [x] **0.1** Rename `CLAUDE.MD` -> `CLAUDE.md`. *Verify:* `git ls-files | grep -i claude` shows `CLAUDE.md`.
- [x] **0.2** Toolchain check. *Verify:* `uv --version` ≥ 0.11; `uv python find 3.12` succeeds.
- [x] **0.3** `pyproject.toml`, `src/ctxbook/__init__.py`, typer stub with `--version`.
      *Verify:* `uv sync && uv run ctxbook --version`.
- [x] **0.4** Installed versions match CLAUDE.md §4. *Verify:* `uv pip list` shows mcp ≥2.3, sqlite-vec ≥0.1.9, fastembed ≥0.9.1, typer, pydantic.
- [x] **0.5** Ruff + pre-commit config. *Verify:* `uv run ruff check . && uv run ruff format --check .`
- [x] **0.6** pytest config + one smoke test. *Verify:* `uv run pytest`.
- [x] **0.7** `Makefile` with `test`, `lint`, `eval` (eval prints "no eval yet", exit 0). *Verify:* `make test lint eval`.
- [x] **0.8** GitHub Actions: lint + tests, ubuntu/macos/windows × 3.11/3.12.
      *Verify:* 👤 after push, all 6 jobs green on GitHub.
- [ ] Commit `chore: scaffold project`.

## M1 — Storage
- [x] **1.1** 🔬 Spike on this Mac with uv Python: sqlite-vec loads; `vec0(... distance_metric=cosine)` syntax
      works in 0.1.9 and returns cosine distance; FTS5 present. *Verify:* spike output recorded in CLAUDE.md §6/§14.
- [x] **1.2** `models.py`: `Status` enum, `Memory`, `Event` (Pydantic). *Verify:* unit tests.
- [x] **1.3** `storage/base.py`: `MemoryStore` + `VectorIndex` protocols. *Verify:* `ruff` + import test.
- [x] **1.4** Connection: WAL, `busy_timeout`, extension load with fallback, schema v1, `meta`.
      *Verify:* tests — fresh DB has all tables + meta; reopening is a no-op; wrong `embed_dim` is refused.
- [x] **1.5** Memory CRUD + status changes, each writing `memory_events` in the same transaction.
      *Verify:* tests for every status transition + event row.
- [x] **1.6** FTS5 kept in sync (insert, deactivate). *Verify:* keyword search tests.
- [x] **1.7** `SqliteVecIndex`. *Verify:* KNN tests on a fixed dataset.
- [x] **1.8** `NumpyIndex` fallback + a setting to force it. *Verify:* both indexes return identical top-k on the same dataset.
- [x] **1.9** Two processes writing at once. *Verify:* concurrency test passes, no `database is locked`.
- [ ] Commit `feat(storage): sqlite store with vector fallback`.

## M2 — Embeddings + ranking
- [x] **2.1** `Embedder` protocol + deterministic `FakeEmbedder` for tests. *Verify:* unit tests.
- [x] **2.2** 🔬 Spike fastembed 0.9.1: `TextEmbedding(model_name, cache_dir)` signature, output type,
      whether vectors are already normalised, offline error. *Verify:* recorded in CLAUDE.md §6.
- [x] **2.3** `FastembedEmbedder` (cache in ctxbook dir, download notice, friendly offline error).
      *Verify:* unit test with mocked failure; `slow` test with the real model (run locally; note download time).
- [x] **2.4** `NoEmbedder` (keyword-only). *Verify:* test proves fastembed is never imported in this mode.
- [x] **2.5** `paths.py` (D7) with `CTXBOOK_HOME` override. *Verify:* tests on fake home dirs.
- [x] **2.6** `ranking.py`: RRF, recency boost, token budget. *Verify:* tests with hand-computed expected values.
- [ ] Commit `feat: embeddings and hybrid ranking`.

## M3 — Service + conflict handling
- [x] **3.1** `config.py` (thresholds, limits D8, expiry D5). *Verify:* import test.
- [x] **3.2** `safety.py`: length/limit checks, wrap-as-data. *Verify:* unit tests.
- [x] **3.3** `save`: saved / duplicate / needs_resolution; keyword-mode rule D9. *Verify:* one test per outcome, both modes.
- [x] **3.4** `resolve`: new / duplicate / update / contradiction; target-not-active error. *Verify:* tests per decision.
- [x] **3.5** `update` (D2) and `forget` (D3). *Verify:* tests incl. forgotten fact never returned by search.
- [x] **3.6** `history`. *Verify:* chain of 3 versions returned in order with source apps.
- [x] **3.7** `search` over scope + global (D6). *Verify:* scope isolation + global inclusion tests.
- [x] **3.8** Pending expiry (D5). *Verify:* test with an injected clock.
- [x] **3.9** Two conflicting resolves on one target. *Verify:* exactly one wins, the other gets a clear error.
- [ ] Commit `feat(core): memory service with conflict handling`.

## M4 — MCP server
- [x] **4.1** 🔬 Spike: re-confirm §5 against the installed SDK (`MCPServer`, `@server.tool()`, `Context`,
      in-memory `Client`). *Verify:* spike runs.
- [x] **4.2** `server/app.py`: 6 tools, prompt-style docstrings, Pydantic outputs, `instructions` = memory rule.
- [x] **4.3** In-memory integration tests for all 6 tools. *Verify:* `structured_content` present on every result.
- [x] **4.4** Missing client info -> `source_app == "unknown"`. *Verify:* test.
- [x] **4.5** `tests/security/`: injection text comes back only as labelled data; limits enforced. *Verify:* tests.
- [x] **4.6** One real stdio test. *Verify:* test.
- [ ] **4.7** 👤 MCP Inspector manual pass (needs Node.js); connect from Claude Code and note the client name it sends.
      *Verify:* names recorded in CLAUDE.md §14.
- [ ] Commit `feat(server): six MCP tools`.

## M5 — CLI
- [x] **5.1** `serve --transport stdio|http`; refuses non-localhost hosts. *Verify:* CliRunner tests.
- [x] **5.2** HTTP keeps Host/Origin protection. *Verify:* test expects 403 / 421 like §5.
- [x] **5.3** `save "fact" --scope X`. *Verify:* test.
- [x] **5.4** `export` / `import` JSONL (D13). *Verify:* round-trip equality test; import twice = no duplicates.
- [x] **5.5** `doctor`. *Verify:* test output in normal, fallback and keyword-only modes.
- [ ] Commit `feat(cli): serve, save, export, import, doctor`.

## M6 — `init`
- [x] **6.1** Shared pieces: backup, JSON merge, marker blocks. *Verify:* unit tests (malformed JSON aborts, no write).
- [x] **6.2** Claude Code adapter (`claude mcp add`, mocked in tests). *Verify:* tests on fake home.
- [x] **6.3** Claude Desktop adapter. *Verify:* tests on fake home (macOS + Windows paths).
- [x] **6.4** Cursor adapter (`mcp.json` + `.mdc` rule). *Verify:* tests.
- [x] **6.5** Antigravity adapter. *Verify:* tests.
- [x] **6.6** `init` flow: detect, preview, confirm, `--yes`; running twice changes nothing. *Verify:* tests.
- [x] **6.7** `init --uninstall` restores originals. *Verify:* byte-for-byte comparison test.
- [ ] **6.8** 👤 Real run on your Mac, then confirm a fact saved in one app is found in another.
- [ ] Commit `feat(cli): init and uninstall for four clients`.

## M7 — Evaluation
- [ ] **7.1** 👤 Check LongMemEval license (D14). *Verify:* recorded in decisions.md.
- [x] **7.2** Own conflict set, 100–200 cases. *Verify:* schema-validated by a test.
- [x] **7.3** Harness: 4 configs, recall@k / precision / stale-fact error / latency. *Verify:* runs on a 5-case toy set.
- [ ] **7.4** 👤 Extraction of LongMemEval knowledge-update (oracle) with an LLM — needs your API key; cached with model name.
- [ ] **7.5** Full run, tune 0.60 / 0.95 thresholds, write `eval/results/`. (Own conflict set done 2026-11-27: threshold 0.70, recency 0.02; LongMemEval part pending 7.1/7.4.) *Verify:* `make eval` reproduces the numbers offline.
- [ ] Commit `feat(eval): evaluation harness and results`.

## M8 — Docs + release
- [ ] **8.1** MkDocs site. *Verify:* `uv run mkdocs build --strict`.
- [ ] **8.2** README: real numbers, remove pre-release banner. *Verify:* every command in the quickstart run once.
- [ ] **8.3** 👤 PyPI account + trusted publisher for the repo; release workflow on `v*` tags.
- [ ] **8.4** 👤 Approve and push tag `v0.1.0`. *Verify:* package on PyPI; `uvx ctxbook --version` from a clean dir.
- [ ] **8.5** Clean-machine end-to-end `uvx ctxbook init`. *Verify:* fact shared between two clients.
