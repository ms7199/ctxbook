"""Export and import memories as JSON Lines (decision D13).

Line 1 is a header; every other line is one fact with its full event history. Import is
idempotent: a fact identical in content, scope, app and creation time is skipped. Imported
facts are restored as they were (no conflict checks), and vectors are rebuilt automatically
on the next search or save.
"""

import json
from collections.abc import Iterable, Iterator
from datetime import datetime

from pydantic import BaseModel, ValidationError

from ctxbook import __version__
from ctxbook.errors import CtxbookError
from ctxbook.models import Event, EventAction, Memory, Status
from ctxbook.storage.base import MemoryStore

FORMAT = "ctxbook-export"
EXPORT_VERSION = 1


class ExportedEvent(BaseModel):
    action: EventAction
    old: str | None = None
    new: str | None = None
    source_app: str
    created_at: datetime


class ExportedMemory(BaseModel):
    id: int
    content: str
    scope: str
    source_app: str
    status: Status
    superseded_by: int | None = None
    created_at: datetime
    updated_at: datetime
    events: list[ExportedEvent]


class ImportReport(BaseModel):
    imported: int
    skipped: int


class ImportFormatError(CtxbookError):
    """The file is not a ctxbook export (or is damaged)."""


def export_lines(store: MemoryStore) -> Iterator[str]:
    header = {
        "type": "header",
        "format": FORMAT,
        "export_version": EXPORT_VERSION,
        "schema_version": store.get_meta("schema_version"),
        "ctxbook_version": __version__,
    }
    yield json.dumps(header)
    for memory in store.list_memories():
        events = [
            ExportedEvent.model_validate(e.model_dump(exclude={"id", "memory_id"}))
            for e in store.events(memory.id)
        ]
        yield ExportedMemory(**memory.model_dump(), events=events).model_dump_json()


def _parse(lines: Iterable[str]) -> list[ExportedMemory]:
    iterator = (line for line in lines if line.strip())
    try:
        header = json.loads(next(iterator))
    except (StopIteration, json.JSONDecodeError):
        raise ImportFormatError("This file is empty or is not a ctxbook export.") from None
    if not isinstance(header, dict) or header.get("format") != FORMAT:
        raise ImportFormatError("This file is not a ctxbook export (missing header line).")
    if header.get("export_version") != EXPORT_VERSION:
        raise ImportFormatError(
            f"Export version {header.get('export_version')} is not supported by this ctxbook "
            f"(expects {EXPORT_VERSION}). Please upgrade ctxbook."
        )
    records: list[ExportedMemory] = []
    for number, line in enumerate(iterator, start=2):
        try:
            records.append(ExportedMemory.model_validate_json(line))
        except ValidationError as exc:
            raise ImportFormatError(f"Line {number} is not a valid memory: {exc}") from None
    return records


def import_lines(store: MemoryStore, lines: Iterable[str], *, now: datetime) -> ImportReport:
    records = _parse(lines)
    id_map: dict[int, int] = {}
    new_ids: set[int] = set()
    with store.transaction():
        for record in records:
            existing = store.find_exact(
                content=record.content,
                scope=record.scope,
                source_app=record.source_app,
                created_at=record.created_at,
            )
            if existing is not None:
                id_map[record.id] = existing
                continue
            memory = Memory(**record.model_dump(exclude={"events", "superseded_by"}))
            events = [Event(id=0, memory_id=0, **e.model_dump()) for e in record.events]
            events.append(
                Event(
                    id=0,
                    memory_id=0,
                    action=EventAction.IMPORTED,
                    source_app="import",
                    created_at=now,
                    new=f"exported id {record.id}",
                )
            )
            id_map[record.id] = store.insert_raw(memory, events)
            new_ids.add(id_map[record.id])
        for record in records:
            target = id_map.get(record.superseded_by) if record.superseded_by else None
            if target is not None and id_map[record.id] in new_ids:
                store.link_superseded(id_map[record.id], target)
    return ImportReport(imported=len(new_ids), skipped=len(records) - len(new_ids))
