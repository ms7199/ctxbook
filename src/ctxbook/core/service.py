"""MemoryService: the whole save / search / resolve / update / forget / history logic.

Plain Python: the MCP server and the CLI are thin wrappers around this class.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime

from ctxbook.config import Settings
from ctxbook.core.ranking import estimate_tokens, fit_budget, rank
from ctxbook.core.safety import (
    InvalidInputError,
    as_data,
    clamp_limit,
    clean_content,
    clean_query,
    clean_scope,
    normalise_for_compare,
)
from ctxbook.embeddings.base import Embedder
from ctxbook.errors import NotFoundError, StaleStateError
from ctxbook.models import (
    Decision,
    EventAction,
    ForgetResult,
    HistoryEvent,
    HistoryResult,
    Memory,
    ResolveResult,
    SaveResult,
    SearchResult,
    Status,
    StoredFact,
    UpdateResult,
)
from ctxbook.storage.base import MemoryStore

ACTIVE = (Status.ACTIVE,)

# Words too common to signal that two facts are about the same thing (keyword-only mode).
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
        "i", "in", "is", "it", "its", "of", "on", "or", "our", "that", "the", "their",
        "this", "to", "use", "used", "uses", "was", "we", "were", "will", "with", "you",
        "your",
    }
)  # fmt: skip


def _meaningful_words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if w not in _STOPWORDS}


def word_overlap(a: str, b: str) -> float:
    """Shared meaningful words divided by the smaller word set (0..1)."""
    wa, wb = _meaningful_words(a), _meaningful_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


_RESOLVE_HELP = (
    "This fact may overlap with the existing facts listed in candidates. Compare them and "
    "call resolve_memory with pending_id={pending_id} and decision: 'new' (a different fact, "
    "keep both), 'duplicate' (same as a candidate), 'update' (replaces a candidate, e.g. a "
    "newer value; pass its id as target_id) or 'contradiction' (a candidate is no longer "
    "true; pass its id as target_id)."
)


class MemoryService:
    """Stores, versions and searches facts. ``embedder=None`` means keyword-only mode."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: Embedder | None,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._settings = settings or Settings()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._backfilled = False

    @property
    def mode(self) -> str:
        return "keyword" if self._embedder is None else "hybrid"

    @property
    def settings(self) -> Settings:
        return self._settings

    # ── housekeeping ─────────────────────────────────────────────────────

    def _prepare(self) -> None:
        """Run before every operation: expire old pending facts, embed facts missing vectors."""
        self.expire_pending()
        if self._embedder is not None and not self._backfilled:
            missing = self._store.ids_missing_vectors()
            if missing:
                memories = self._store.get_many(missing)
                ids = [i for i in missing if i in memories]
                vectors = self._embedder.embed_documents([memories[i].content for i in ids])
                with self._store.transaction():
                    for memory_id, vector in zip(ids, vectors, strict=True):
                        self._store.set_vector(memory_id, vector)
            self._backfilled = True

    def expire_pending(self) -> int:
        """Auto-accept pending facts older than the expiry (decision D5). Returns how many."""
        cutoff = self._clock() - self._settings.pending_expiry
        expired = 0
        for memory in self._store.list_memories(statuses=[Status.PENDING], updated_before=cutoff):
            try:
                self._store.change_status(
                    memory.id,
                    expected=Status.PENDING,
                    new=Status.ACTIVE,
                    action=EventAction.EXPIRED_AUTO_ACCEPT,
                    source_app="ctxbook",
                    now=self._clock(),
                )
                expired += 1
            except StaleStateError:
                pass  # another process resolved or expired it first
        return expired

    # ── save ─────────────────────────────────────────────────────────────

    def save(self, content: str, scope: str, source_app: str) -> SaveResult:
        content = clean_content(content, self._settings)
        scope = clean_scope(scope, self._settings)
        self._prepare()
        vector = None if self._embedder is None else self._embedder.embed_documents([content])[0]
        now = self._clock()
        with self._store.transaction():
            duplicate_id, close_ids = self._find_similar(content, scope, vector)
            if duplicate_id is not None:
                self._store.touch(duplicate_id, source_app=source_app, now=now)
                return SaveResult(
                    status="duplicate",
                    memory_id=duplicate_id,
                    message="This fact is already stored; nothing new was saved.",
                )
            status = Status.PENDING if close_ids else Status.ACTIVE
            memory = self._store.add(
                content=content,
                scope=scope,
                source_app=source_app,
                status=status,
                now=now,
                vector=vector,
            )
            if not close_ids:
                return SaveResult(status="saved", memory_id=memory.id, message="Saved.")
            candidates = self._store.get_many(close_ids)
            return SaveResult(
                status="needs_resolution",
                memory_id=memory.id,
                candidates=[as_data(candidates[i]) for i in close_ids if i in candidates],
                message=_RESOLVE_HELP.format(pending_id=memory.id),
            )

    def _find_similar(
        self, content: str, scope: str, vector: list[float] | None
    ) -> tuple[int | None, list[int]]:
        """Return (duplicate id or None, ids of close-but-different active facts)."""
        cfg = self._settings
        if vector is not None:
            hits = self._store.vector_search(
                vector, k=cfg.conflict_candidates, scopes=[scope], statuses=ACTIVE
            )
            close = [(i, s) for i, s in hits if s >= cfg.similar_threshold]
            if close and close[0][1] >= cfg.duplicate_threshold:
                return close[0][0], []
            return None, [i for i, _ in close]

        # Keyword-only mode (decision D9): weaker, word-based.
        hits = self._store.keyword_search(
            content, k=cfg.conflict_candidates, scopes=[scope], statuses=ACTIVE
        )
        memories = self._store.get_many(i for i, _ in hits)
        wanted = normalise_for_compare(content)
        close: list[int] = []
        for memory_id, _ in hits:
            existing = memories[memory_id].content
            if normalise_for_compare(existing) == wanted:
                return memory_id, []
            if word_overlap(content, existing) >= cfg.keyword_overlap_threshold:
                close.append(memory_id)
        return None, close

    # ── resolve ──────────────────────────────────────────────────────────

    def resolve(
        self, pending_id: int, decision: str, target_id: int | None, source_app: str
    ) -> ResolveResult:
        try:
            choice = Decision(decision)
        except ValueError:
            options = ", ".join(d.value for d in Decision)
            raise InvalidInputError(
                f"Unknown decision {decision!r}; use one of: {options}."
            ) from None
        self._prepare()
        now = self._clock()
        with self._store.transaction():
            pending = self._require(pending_id)
            if pending.status is not Status.PENDING:
                raise StaleStateError(
                    f"Memory {pending_id} is {pending.status.value}, not pending; it was "
                    "already resolved (or expired and was accepted automatically)."
                )

            def move(memory_id: int, frm: Status, to: Status, **kw: object) -> Memory:
                return self._store.change_status(
                    memory_id, expected=frm, new=to, source_app=source_app, now=now, **kw
                )  # type: ignore[arg-type]

            if choice is Decision.NEW:
                move(pending_id, Status.PENDING, Status.ACTIVE)
                return ResolveResult(
                    decision=choice, active_id=pending_id, message="Saved as a new fact."
                )

            if choice is Decision.DUPLICATE:
                move(pending_id, Status.PENDING, Status.DELETED, action=EventAction.DELETED)
                if target_id is not None:
                    self._same_scope_target(target_id, pending)
                    self._store.touch(target_id, source_app=source_app, now=now)
                return ResolveResult(
                    decision=choice,
                    active_id=target_id,
                    message="Dropped the new fact as a duplicate.",
                )

            if target_id is None:
                raise InvalidInputError(
                    f"decision {choice.value!r} needs target_id: the id of the existing fact "
                    "it replaces (from candidates)."
                )
            self._same_scope_target(target_id, pending)
            move(
                target_id,
                Status.ACTIVE,
                Status.SUPERSEDED,
                superseded_by=pending_id,
                action=EventAction.SUPERSEDED,
            )
            move(pending_id, Status.PENDING, Status.ACTIVE)
            return ResolveResult(
                decision=choice,
                active_id=pending_id,
                superseded_id=target_id,
                message=f"Memory {pending_id} is now current; memory {target_id} is kept in "
                "history as superseded.",
            )

    def _same_scope_target(self, target_id: int, pending: Memory) -> Memory:
        if target_id == pending.id:
            raise InvalidInputError("target_id must be a different fact from pending_id.")
        target = self._require(target_id)
        if target.scope != pending.scope:
            raise InvalidInputError(
                f"Memory {target_id} is in scope {target.scope!r}, but the pending fact is in "
                f"{pending.scope!r}; pick a target from the candidates."
            )
        return target

    # ── update and forget ────────────────────────────────────────────────

    def update(self, memory_id: int, new_content: str, source_app: str) -> UpdateResult:
        """Replace a fact with a new version (decision D2); the old one stays in history."""
        content = clean_content(new_content, self._settings)
        self._prepare()
        vector = None if self._embedder is None else self._embedder.embed_documents([content])[0]
        now = self._clock()
        with self._store.transaction():
            old = self._require(memory_id)
            if old.status is not Status.ACTIVE:
                hint = (
                    f" The current version is memory {old.superseded_by}."
                    if old.superseded_by
                    else ""
                )
                raise StaleStateError(
                    f"Memory {memory_id} is {old.status.value}; only active facts can be "
                    f"updated.{hint}"
                )
            if normalise_for_compare(old.content) == normalise_for_compare(content):
                self._store.touch(memory_id, source_app=source_app, now=now)
                return UpdateResult(
                    status="unchanged", memory_id=memory_id, message="The fact already says that."
                )
            new = self._store.add(
                content=content,
                scope=old.scope,
                source_app=source_app,
                status=Status.ACTIVE,
                now=now,
                vector=vector,
            )
            self._store.change_status(
                memory_id,
                expected=Status.ACTIVE,
                new=Status.SUPERSEDED,
                superseded_by=new.id,
                action=EventAction.SUPERSEDED,
                source_app=source_app,
                now=now,
            )
        return UpdateResult(
            status="updated",
            memory_id=new.id,
            superseded_id=memory_id,
            message=f"Updated. Memory {new.id} is current; memory {memory_id} is kept in history.",
        )

    def forget(self, memory_id: int, source_app: str) -> ForgetResult:
        """Hide a fact from search for good (decision D3); its history record is kept."""
        now = self._clock()
        with self._store.transaction():
            memory = self._require(memory_id)
            if memory.status is Status.DELETED:
                raise StaleStateError(f"Memory {memory_id} was already forgotten.")
            self._store.change_status(
                memory_id,
                expected=memory.status,
                new=Status.DELETED,
                action=EventAction.DELETED,
                source_app=source_app,
                now=now,
            )
        return ForgetResult(
            memory_id=memory_id, message="Forgotten: it will no longer appear in search."
        )

    # ── search ───────────────────────────────────────────────────────────

    def search(self, query: str, scope: str, limit: int | None = None) -> SearchResult:
        cfg = self._settings
        query = clean_query(query, cfg)
        scopes = list(dict.fromkeys([clean_scope(scope, cfg), cfg.global_scope]))
        limit = clamp_limit(limit, cfg)
        self._prepare()

        vector_ids: list[int] = []
        if self._embedder is not None:
            hits = self._store.vector_search(
                self._embedder.embed_query(query),
                k=cfg.search_pool,
                scopes=scopes,
                statuses=ACTIVE,
            )
            vector_ids = [i for i, s in hits if s >= cfg.search_min_similarity]
        keyword_ids = [
            i
            for i, _ in self._store.keyword_search(
                query, k=cfg.search_pool, scopes=scopes, statuses=ACTIVE
            )
        ]
        memories = self._store.get_many([*vector_ids, *keyword_ids])
        ranked = rank(
            [vector_ids, keyword_ids],
            {i: m.updated_at for i, m in memories.items() if m.status is Status.ACTIVE},
            self._clock(),
            rrf_k=cfg.rrf_k,
            recency_weight=(
                cfg.recency_weight if self._embedder is not None else cfg.keyword_recency_weight
            ),
            half_life_days=cfg.recency_half_life_days,
        )
        facts = [as_data(memories[i]) for i, _ in ranked[:limit]]
        facts = fit_budget(facts, _fact_tokens, cfg.token_budget)
        message = f"{len(facts)} matching memories." if facts else "No matching memories."
        return SearchResult(mode=self.mode, results=facts, message=message)  # type: ignore[arg-type]

    # ── history ──────────────────────────────────────────────────────────

    def history(self, memory_id: int) -> HistoryResult:
        start = self._require(memory_id)
        chain = [start]
        seen = {start.id}
        current = start
        while predecessors := [p for p in self._store.predecessors(current.id) if p.id not in seen]:
            current = predecessors[0]
            seen.add(current.id)
            chain.insert(0, current)
        current = start
        while current.superseded_by is not None and current.superseded_by not in seen:
            current = self._require(current.superseded_by)
            seen.add(current.id)
            chain.append(current)

        events = [
            HistoryEvent(
                memory_id=e.memory_id,
                action=e.action,
                by=e.source_app,
                at=e.created_at,
                old=e.old,
                new=e.new,
            )
            for memory in chain
            for e in self._store.events(memory.id)
        ]
        events.sort(key=lambda e: e.at)
        active = [m.id for m in chain if m.status is Status.ACTIVE]
        return HistoryResult(
            versions=[as_data(m) for m in chain],
            current_id=active[-1] if active else None,
            events=events,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _require(self, memory_id: int) -> Memory:
        memory = self._store.get(memory_id)
        if memory is None:
            raise NotFoundError(f"No memory with id {memory_id}.")
        return memory


def _fact_tokens(fact: StoredFact) -> int:
    # The fact text plus a small allowance for its labels (id, scope, saved_by, date, note).
    return estimate_tokens(fact.fact) + 20
