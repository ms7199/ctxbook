# Decisions and open questions

Status values: **proposed** (awaiting owner approval), **accepted**, **rejected**.
Each entry: the question, the proposal, and why.

| # | Question | Proposal | Status |
|---|---|---|---|
| D1 | `CLAUDE.MD` file name | Rename to `CLAUDE.md`; uppercase extension isn't loaded on case-sensitive file systems (Linux CI). | proposed |
| D2 | What does `update_memory` do vs `resolve_memory(update)`? | `update_memory(memory_id, new_content)`: the AI knowingly edits a fact it already has the id of. Creates a new active fact, supersedes the old one, no similarity check. `resolve_memory` only settles pending facts. | proposed |
| D3 | Does `forget_memory` delete for real? | Status -> `deleted`, removed from vector + FTS indexes (never returned by search); row and event kept so history is auditable. True purge (e.g. a secret saved by mistake) deferred to v0.2 unless wanted now. | proposed |
| D4 | Similarity measure for thresholds | Cosine similarity (= 1 - cosine distance). `vec0` declared with `distance_metric=cosine`; numpy fallback uses the same. Thresholds 0.60 / 0.95 stay placeholders until the eval. | proposed |
| D5 | What happens to pending facts never resolved? | After 7 days (config) they are auto-accepted as `new` (event `expired_auto_accept`). Keeping both facts is safer than losing one; recency boost favours the newer. `doctor` lists pending facts older than 1 day. | proposed |
| D6 | Does search include the `global` scope? | Yes: search covers the requested scope + `global`, ranked together. | proposed |
| D7 | Where do the DB and model cache live? | Add `platformdirs` (needs approval, hard rule 8) for OS-correct data/cache dirs; `CTXBOOK_HOME` env var overrides (also used by tests). Alternative without a dependency: `~/.ctxbook/`. | proposed |
| D8 | Limits | `content` ≤ 1,000 chars; `limit` default 5, max 20; result token budget ≈ 500 (chars/4 estimate). All in `config.py`. | proposed |
| D9 | Keyword-only conflict detection | FTS5 top 5 in the scope become candidates -> `needs_resolution`; `duplicate` only on exact match after normalising case/whitespace. Documented as weaker. | proposed |
| D10 | `make eval` needs an API key for extraction | `make eval` runs offline on cached extractions + own conflict set. `make eval-extract` (needs an API key) regenerates the cache. | proposed |
| D11 | Docker image when HTTP is localhost-only | Defer Docker to v0.2 (with network mode + auth). Inside a container, 127.0.0.1 isn't reachable from the host, so the only v0.1 use would be stdio via `docker run -i`. | proposed |
| D12 | CLI names not in the spec | `ctxbook serve --transport stdio\|http`, `ctxbook save TEXT --scope NAME`, `ctxbook init --yes`, `--no-embeddings` on `init` and `serve`. | proposed |
| D13 | Export format | JSONL: one memory per line with its events; includes `schema_version` header line. | proposed |
| D14 | LongMemEval license | Check before committing any extracted data; if unclear, commit only the harness and IDs, not the data. | open |
| D15 | Scope = folder name collides across repos with the same name | Accept for v0.1, document it; revisit (e.g. git remote URL) in v0.2. | proposed |
| D16 | Build backend | `hatchling` (build-time only, not a runtime dependency). | proposed |
