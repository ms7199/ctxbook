"""Data models shared by every layer (no MCP, no SQLite)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class Status(StrEnum):
    """Lifecycle of a stored fact."""

    ACTIVE = "active"
    PENDING = "pending"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class EventAction(StrEnum):
    """What happened to a fact; one row in ``memory_events`` per change."""

    CREATED = "created"
    DUPLICATE_SEEN = "duplicate_seen"
    STATUS_CHANGED = "status_changed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"
    EXPIRED_AUTO_ACCEPT = "expired_auto_accept"
    IMPORTED = "imported"


class Memory(BaseModel):
    """One fact as stored."""

    id: int
    content: str
    scope: str
    source_app: str
    status: Status
    superseded_by: int | None = None
    created_at: datetime
    updated_at: datetime


class Event(BaseModel):
    """One audit-log entry for a fact."""

    id: int
    memory_id: int
    action: EventAction
    old: str | None = None
    new: str | None = None
    source_app: str
    created_at: datetime
