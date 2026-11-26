"""Input limits and safe output wrapping (CLAUDE.md section 8)."""

import re
import unicodedata

from ctxbook.config import Settings
from ctxbook.errors import CtxbookError
from ctxbook.models import DATA_NOTE, Memory, StoredFact

_WHITESPACE = re.compile(r"\s+")


class InvalidInputError(CtxbookError):
    """A tool argument is empty, too long, or malformed."""


def _clean(text: str) -> str:
    """Drop control characters and collapse whitespace."""
    without_controls = "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc"
    )
    return _WHITESPACE.sub(" ", without_controls).strip()


def clean_content(text: str, settings: Settings) -> str:
    content = _clean(text)
    if not content:
        raise InvalidInputError("The fact is empty. Send one short, non-empty fact.")
    if len(content) > settings.max_content_chars:
        raise InvalidInputError(
            f"The fact is {len(content)} characters; the limit is {settings.max_content_chars}. "
            "Save one short fact per call."
        )
    return content


def clean_query(text: str, settings: Settings) -> str:
    query = _clean(text)
    if not query:
        raise InvalidInputError("The search query is empty.")
    return query[: settings.max_query_chars]


def clean_scope(text: str, settings: Settings) -> str:
    """Scopes are case-insensitive names such as a repo folder name, or ``global``."""
    scope = _clean(text).lower()
    if not scope:
        raise InvalidInputError(
            'The scope is empty. Use the project folder name, or "global" for facts about the user.'
        )
    if len(scope) > settings.max_scope_chars:
        raise InvalidInputError(f"The scope is longer than {settings.max_scope_chars} characters.")
    return scope


def clamp_limit(limit: int | None, settings: Settings) -> int:
    if limit is None:
        return settings.default_limit
    return max(1, min(int(limit), settings.max_limit))


def normalise_for_compare(text: str) -> str:
    """Case- and punctuation-insensitive form used for exact-duplicate checks."""
    return " ".join(re.findall(r"\w+", text.lower()))


def as_data(memory: Memory) -> StoredFact:
    """Wrap a stored fact so clients see it as user data, never as instructions."""
    return StoredFact(
        id=memory.id,
        fact=memory.content,
        scope=memory.scope,
        saved_by=memory.source_app,
        date=memory.updated_at.date().isoformat(),
        status=memory.status,
        note=DATA_NOTE,
    )
