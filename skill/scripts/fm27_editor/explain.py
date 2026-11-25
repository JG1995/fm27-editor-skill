"""What an editor file does, in plain words."""

import datetime
import sqlite3
import struct
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from fm27_editor.binary import FormatError
from fm27_editor.change_list import Kind, Property
from fm27_editor.editor_file import EditorFile
from fm27_editor.field_definitions import (
    FieldDefinitionError,
    read_field_names,
    read_shared_choices,
)
from fm27_editor.preview import counted
from fm27_editor.record_changes import ADD_RECORD, Change, Table

REMOVE_RECORD = "DELE"
KINDS_OF_RECORD = "dbts"
FIELDS_SHOWN = 12
# Where the definition files are not called what the Editor calls the kind of record.
DEFINED_IN = {
    "Person": ["person", "player", "non player"],
    "National Team": ["national team container"],
    "Derby Name": ["derby"],
    "Competition": ["comp"],
}
NAME_PARTS = ("Pfna", "Psna")
WHOLE_NUMBERS = {Kind.INT8, Kind.INT16, Kind.INT32, Kind.INT64}
COUNTS = {Kind.INT8_2, Kind.INT16_2, Kind.INT32_2, Kind.COUNT}
LOOKUP_TABLES = {"Nnat": "nation", "Ttea": "club", "Cclu": "club"}
PERSON_LOOKUP = {"Person": "person", "Club": "club", "Nation": "nation"}


type Parts = dict[str, Property]


class ExplainError(FormatError):
    """The file holds something that cannot be put in words."""


@dataclass(frozen=True)
class Described:
    """One change, as far as it can be put in words."""

    kind_of_record: str
    record: bytes
    code: str
    new: Property | None


def explain_lines(
    file: EditorFile, editor_dir: Path, lookup: sqlite3.Connection, *, find: str, examples: int
) -> list[str]:
    changes = [_named_parts(change) for change in file.changes.changes]
    words = _Words(changes, editor_dir, lookup)
    described = [_described(change, words) for change in changes]
    added = [item for item in described if item.code == ADD_RECORD]
    removed = [item for item in described if item.code == REMOVE_RECORD]
    changed = [item for item in described if item.code not in (ADD_RECORD, REMOVE_RECORD)]
    return [
        _heading(file),
        *_record_lines("Adds", added),
        *_record_lines("Removes", removed),
        *_table_lines(changed, words),
        *_change_lines(changed, words, find, examples),
    ]


class _Words:
    """Names for kinds of records, fields, and records."""

    def __init__(self, changes: list[Parts], editor_dir: Path, lookup: sqlite3.Connection):
        self._editor_dir = editor_dir
        self._lookup = lookup
        self._kinds = read_shared_choices(editor_dir, KINDS_OF_RECORD)
        self._fields: dict[str, dict[str, str]] = {}
        self._new_names = _names_of_new_records(changes)

    def kind(self, number: int) -> str:
        return self._kinds.get(number, f"Table {number}")

    def field(self, kind_of_record: str, code: str) -> str:
        if kind_of_record not in self._fields:
            self._fields[kind_of_record] = self._read_fields(kind_of_record)
        return self._fields[kind_of_record].get(code) or code

    def record(self, kind_of_record: str, record: bytes) -> str:
        if record in self._new_names:
            return f"{self._new_names[record]} (new)"
        if len(record) != 8:
            return record.hex()
        uid, again = struct.unpack("<II", record)
        if uid != again:
            return f"{uid} (new)"
        return self.known(PERSON_LOOKUP.get(kind_of_record), uid)

    def known(self, table: str | None, uid: int) -> str:
        if table is None:
            return str(uid)
        row = self._lookup.execute(f"SELECT name FROM {table} WHERE uid = ?", (uid,)).fetchone()
        return f"{row[0]} ({uid})" if row else str(uid)

    def _read_fields(self, kind_of_record: str) -> dict[str, str]:
        names: dict[str, str] = {}
        for definitions in DEFINED_IN.get(kind_of_record, [kind_of_record.lower()]):
            try:
                names = read_field_names(self._editor_dir, definitions) | names
            except FieldDefinitionError:
                continue
        return names


def _named_parts(change: Change) -> Parts:
    parts = {item.tag: item for item in change}
    missing = {"dtty", "duni", "prty"} - parts.keys()
    if missing:
        raise ExplainError(f"a change has no {', '.join(sorted(missing))}")
    return parts


def _described(change: Parts, words: _Words) -> Described:
    code, said = str(change["prty"].value), change
    if code == ADD_RECORD and _number(change["dtty"]) == Table.DATABASE:
        said = _added(change.get("nwvl"))
    kind = words.kind(_number(said["dtty"]))
    return Described(kind, bytes(said["duni"].value), code, change.get("nwvl"))


def _added(new: Property | None) -> Parts:
    parts = {}
    if new is not None and new.kind is Kind.NESTED:
        parts = {item.tag: item for item in new.value}
    if not {"dtty", "duni"} <= parts.keys():
        raise ExplainError("a change that adds a record does not say which")
    return parts


def _names_of_new_records(changes: Iterable[Parts]) -> dict[bytes, str]:
    names: dict[bytes, dict[str, str]] = {}
    for change in changes:
        record, code, new = change["duni"].value, change["prty"].value, change.get("nwvl")
        is_name = code in NAME_PARTS and new is not None and new.kind is Kind.TEXT and new.value
        if is_name and record[:4] != record[4:]:
            names.setdefault(record, {})[code] = new.value
    return {
        record: " ".join(parts[code] for code in NAME_PARTS if code in parts)
        for record, parts in names.items()
    }


# --- lines ---------------------------------------------------------------------------------


def _heading(file: EditorFile) -> str:
    editor = {item.tag: item for item in file.changes.editor}
    heading = counted(len(file.changes.changes), "change", "changes")
    if "EdBr" in editor:
        heading += f", saved by {editor['EdBr'].value}"
    if "EdDt" in editor and editor["EdDt"].kind is Kind.DATE:
        heading += f" on {_date(editor['EdDt'].value)}"
    return heading


def _record_lines(verb: str, items: list[Described]) -> list[str]:
    if not items:
        return []
    kinds = Counter(item.kind_of_record for item in items).most_common()
    listed = ", ".join(f"{kind} {count:,}" for kind, count in kinds)
    return [f"{verb} {counted(len(items), 'record', 'records')}: {listed}"]


def _table_lines(items: list[Described], words: _Words) -> list[str]:
    lines = []
    for kind, count in Counter(item.kind_of_record for item in items).most_common():
        of_kind = [item for item in items if item.kind_of_record == kind]
        records = counted(len({item.record for item in of_kind}), "record", "records")
        lines.append(f"{kind}: {counted(count, 'change', 'changes')} to {records}")
        fields = Counter(item.code for item in of_kind).most_common()
        lines += [f"  {_field(kind, code, words)}: {n:,}" for code, n in fields[:FIELDS_SHOWN]]
        if len(fields) > FIELDS_SHOWN:
            lines.append(f"  and {len(fields) - FIELDS_SHOWN} more fields")
    return lines


def _field(kind: str, code: str, words: _Words) -> str:
    name = words.field(kind, code)
    return code if name == code else f"{name} ({code})"


def _change_lines(items: list[Described], words: _Words, find: str, examples: int) -> list[str]:
    if not find:
        lines, total = [_change_line(item, words) for item in items[:examples]], len(items)
    else:
        every = (_change_line(item, words) for item in items)
        matching = [line for line in every if find.lower() in line.lower()]
        lines, total = matching[:examples], len(matching)
    if not lines:
        return [f"No change mentions {find!r}"] if find else []
    return [f"Changes, {len(lines)} of {total:,}:", *lines]


def _change_line(item: Described, words: _Words) -> str:
    record = words.record(item.kind_of_record, item.record)
    field = words.field(item.kind_of_record, item.code)
    return f"  {record}: {field} = {_plain(item.new, words)}"


# --- values --------------------------------------------------------------------------------


def _plain(value: Property | None, words: _Words) -> str:
    if value is None or value.kind is Kind.NULL:
        return "nothing"
    if value.kind is Kind.TEXT:
        return value.value or '""'
    if value.kind in WHOLE_NUMBERS or value.kind in COUNTS:
        return str(_number(value))
    if value.kind is Kind.BOOL:
        return "yes" if value.value[0] else "no"
    if value.kind is Kind.REAL:
        return f"{struct.unpack('<f', value.value)[0]:g}"
    if value.kind is Kind.DATE:
        return _date(value.value)
    if value.kind is Kind.LIST:
        return "a whole list"
    if value.kind is Kind.NESTED:
        return _reference(value.value, words)
    return value.value if isinstance(value.value, str) else value.value.hex()


def _reference(parts: list[Property], words: _Words) -> str:
    for part in parts:
        if part.kind is Kind.ID and len(parts) <= 3:
            return words.known(LOOKUP_TABLES.get(part.tag), struct.unpack("<II", part.value)[0])
    return "a change to a list"


def _number(value: Property) -> int:
    return int.from_bytes(value.value, "little", signed=value.kind not in COUNTS)


def _date(raw: bytes) -> str:
    number = struct.unpack("<I", raw)[0]
    year, day = number >> 17, number >> 8 & 0x1FF
    try:
        first = datetime.date(year, 1, 1)
    except ValueError:
        return raw.hex()
    date = first + datetime.timedelta(days=day - 1)
    return date.isoformat() if date.year == year else raw.hex()
