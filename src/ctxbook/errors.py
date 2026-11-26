"""Errors shared across layers. Messages are written for the end user."""


class CtxbookError(Exception):
    """Base class for all ctxbook errors."""


class NotFoundError(CtxbookError):
    """A memory id does not exist."""


class StaleStateError(CtxbookError):
    """A fact was not in the expected state (usually changed by another client first)."""


class EmbeddingUnavailableError(CtxbookError):
    """The embedding model cannot be installed, downloaded or loaded."""


class EmbeddingMismatchError(CtxbookError):
    """The database was built with a different embedding model or dimension."""
