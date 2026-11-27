# Decisions and open questions

Status values: **proposed** (awaiting owner approval), **accepted**, **rejected**.
Each entry: the question, the proposal, and why.

| # | Question | Proposal | Status |
|---|---|---|---|
| D1 | `CLAUDE.MD` file name | Rename to `CLAUDE.md`; uppercase extension isn't loaded on case-sensitive file systems (Linux CI). | accepted 2026-11-26 |
| D2 | What does `update_memory` do vs `resolve_memory(update)`? | `update_memory(memory_id, new_content)`: the AI knowingly edits a fact it already has the id of. Creates a new active fact, supersedes the old one, no similarity check. `resolve_memory` only settles pending facts. | accepted 2026-11-26 |
| D3 | Does `forget_memory` delete for real? | Status -> `deleted`, removed from vector + FTS indexes (never returned by search); row and event kept so history is auditable. True purge (e.g. a secret saved by mistake) deferred to v0.2 unless wanted now. | accepted 2026-11-26 |
| D4 | Similarity measure for thresholds | Cosine similarity (= 1 - cosine distance). `vec0` declared with `distance_metric=cosine`; numpy fallback uses the same. Thresholds 0.60 / 0.95 stay placeholders until the eval. | accepted 2026-11-26 |
| D5 | What happens to pending facts never resolved? | After 7 days (config) they are auto-accepted as `new` (event `expired_auto_accept`). Keeping both facts is safer than losing one; recency boost favours the newer. `doctor` lists pending facts older than 1 day. | accepted 2026-11-26 |
| D6 | Does search include the `global` scope? | Yes: search covers the requested scope + `global`, ranked together. | accepted 2026-11-26 |
| D7 | Where do the DB and model cache live? | Add `platformdirs` (needs approval, hard rule 8) for OS-correct data/cache dirs; `CTXBOOK_HOME` env var overrides (also used by tests). Alternative without a dependency: `~/.ctxbook/`. | accepted 2026-11-26 |
| D8 | Limits | `content` ≤ 1,000 chars; `limit` default 5, max 20; result token budget ≈ 500 (chars/4 estimate). All in `config.py`. | accepted 2026-11-26 |
| D9 | Keyword-only conflict detection | FTS5 top 5 in the scope become candidates -> `needs_resolution`; `duplicate` only on exact match after normalising case/whitespace. Documented as weaker. **Refined in M3:** an FTS hit is a candidate only if ≥ 50% of meaningful words (stopwords removed) overlap (`keyword_overlap_threshold`), because FTS `OR` matching otherwise flags almost every save. | accepted 2026-11-26 |
| D10 | `make eval` needs an API key for extraction | `make eval` runs offline on cached extractions + own conflict set. `make eval-extract` (needs an API key) regenerates the cache. | accepted 2026-11-26 |
| D11 | Docker image when HTTP is localhost-only | Defer Docker to v0.2 (with network mode + auth). Inside a container, 127.0.0.1 isn't reachable from the host, so the only v0.1 use would be stdio via `docker run -i`. | accepted 2026-11-26 |
| D12 | CLI names not in the spec | `ctxbook serve --transport stdio\|http`, `ctxbook save TEXT --scope NAME`, `ctxbook init --yes`, `--no-embeddings` on `init` and `serve`. | accepted 2026-11-26 |
| D13 | Export format | JSONL: one memory per line with its events; includes `schema_version` header line. | accepted 2026-11-26 |
| D14 | LongMemEval license | Check before committing any extracted data; if unclear, commit only the harness and IDs, not the data. | open |
| D15 | Scope = folder name collides across repos with the same name | Accept for v0.1, document it; revisit (e.g. git remote URL) in v0.2. | accepted 2026-11-26 |
| D16 | Build backend | `hatchling` (build-time only, not a runtime dependency). | accepted 2026-11-26 |
| D17 | fastembed can't install on Intel Mac + Python ≥3.14 (onnxruntime's last Intel-Mac wheel is 1.23.2, fastembed needs ≥1.24.2 on 3.14) | Dependency marker skips fastembed on that platform only; ctxbook runs keyword-only there and `doctor` explains it and suggests `uvx --python 3.12 ctxbook`. `tool.uv.required-environments` keeps the lock installable on Intel Macs. | accepted 2026-11-26 |
| D18 | Vector search returns its top 20 even when nothing is related | Drop vector hits below `search_min_similarity` (0.50, placeholder; bge-small scores unrelated facts about 0.46). Keyword hits are unaffected. Tune in M7. | accepted 2026-11-26 (implementation detail within D8/section 7) |
| D19 | What `init` does when the `claude` CLI is not on PATH | Print the exact `claude mcp add` command and still write the memory rule to `~/.claude/CLAUDE.md`; never hand-edit `~/.claude.json`. | accepted 2026-11-27 (option a) |
| D20 | How AI clients start the server | `<abs uvx> --managed-python --python 3.12 --from <source> ctxbook serve`; `<source>` auto-detected from the install (PyPI name, git URL or local path), overridable with `--source`. Avoids Pythons without extension loading and the Intel Mac 3.14 case. | accepted 2026-11-27 |
| D21 | cryptography (via mcp -> pyjwt[crypto]) has no Intel-Mac wheels after 48.0.1, so Intel Macs without Rust could not install ctxbook | Platform-only constraint `cryptography<49` on Intel Macs in `pyproject.toml` (must be in package metadata, not only the lock, because `uvx` users don't use our lock). Other platforms keep the latest. Revisit if cryptography 48.x gets a security fix we need. | accepted 2026-11-27 |
