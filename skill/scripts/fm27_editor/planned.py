"""What a plan consists of: the file it starts from, and the records and histories it is about."""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from fm27_editor.award_history import AwardHistory
from fm27_editor.change_reading import is_existing, read_change, uid_of
from fm27_editor.editor_file import EditorFile
from fm27_editor.record_changes import is_uid
from fm27_editor.record_fields import Setting
from fm27_editor.record_kinds import RecordGroup, RecordKind, kind_of
from fm27_editor.request import RequestError

type Address = tuple[int, int]
"""The table and the uid of a record in the database."""
type HeldItems = tuple[Mapping[str, object], ...]
"""The items a list holds now, by the codes of their parts, without the parts not known."""


@dataclass(frozen=True)
class StartingFile:
    path: Path
    file: EditorFile
    digest: str

    @cached_property
    def changed(self) -> set[tuple[Address, str]]:
        """Every field of the database that the file changes: the record and the code."""
        changes = map(read_change, self.file.changes.changes)
        return {
            ((change.table, uid_of(change.record)), change.code)
            for change in changes
            if is_existing(change.record)
        }


@dataclass(frozen=True)
class KnownRecord:
    """A record as the lookup describes it."""

    uid: int
    kind: RecordKind
    facts: Mapping[str, Any]

    @property
    def name(self) -> str:
        return self.facts["name"]

    @property
    def address(self) -> Address:
        return self.kind.group.table, self.uid


def known_record(group: RecordGroup, uid: Any, lookup: sqlite3.Connection) -> KnownRecord:
    cursor = lookup.cursor()
    cursor.row_factory = sqlite3.Row
    row = None
    if is_uid(uid):
        row = cursor.execute(f"SELECT * FROM {group.view} WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        raise RequestError(f"the lookup has no {group.one} with uid {uid!r}")
    facts = dict(row)
    return KnownRecord(facts["uid"], kind_of(group, facts), facts)


def known_value(record: KnownRecord, code: str, lookup: sqlite3.Connection) -> object:
    """What the lookup says a field of the record is now, or None when it does not know."""
    held = record.kind.held_lists.get(code)
    if held is None:
        return record.facts.get(record.kind.names.get(code, ""))
    if held.known_by is not None and record.facts.get(held.known_by) is None:
        return None
    columns = ", ".join(held.parts)
    rows = lookup.execute(
        f"SELECT {columns} FROM {held.table} WHERE {held.owner} = ? ORDER BY {held.order}",
        (record.uid,),
    )
    return tuple(
        {
            code: value
            for code, value in zip(held.parts.values(), row, strict=True)
            if value is not None
        }
        for row in rows
    )


@dataclass(frozen=True)
class Edit:
    record: KnownRecord
    setting: Setting
    old: str | int | HeldItems | None
    """What the lookup says now; nothing when it does not know."""


@dataclass(frozen=True)
class HistoryEdit:
    award: KnownRecord
    history: AwardHistory


@dataclass(frozen=True)
class Addition:
    kind: RecordKind
    name: str | None
    """What the request calls it, for other records to refer to."""
    settings: list[Setting]
