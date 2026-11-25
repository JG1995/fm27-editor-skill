"""Building the changes that set a field or add a record, the way the Editor writes them.

Which tags a change carries and how each type of value is stored was measured over the changes in
real FM27 files, see ARCHITECTURE.md. A value outside what the Editor's definitions allow is an
error, and so is a type of field that was not seen in those files.
"""

import datetime
import random
import struct
from enum import IntEnum

from fm27_editor.binary import FormatError
from fm27_editor.change_list import ChangeList, Kind, Property, Value
from fm27_editor.field_definitions import Field

EDITOR_DATA_VERSION = 3756  # written by the Editor build fm27-rel-04-update1
ADD_RECORD = "ADDR"
LOWEST_ATTRIBUTE, HIGHEST_ATTRIBUTE = 0, 20
RANDOM_NUMBERS = 1_000_000_000
CLIENT_NUMBERS = 10_000_000
SECOND_ID_NUMBERS = 2**30
# People in the database lie below or above this range, except for a few dozen of 657,000.
# The Editor hands out IDs above it.
NEW_UIDS = range(100_000_000, 2_000_000_000)
HIGHEST_UID = 2**31 - 1  # no real file refers to a higher one
INTEGER_KINDS = [(Kind.INT8, 1), (Kind.INT16, 2), (Kind.INT32, 4), (Kind.INT64, 8)]
REFERENCE = "database_record_unique_id"
WRITTEN_TYPES = {"string", "attribute", "integer", "enum", "boolean", "date", REFERENCE}
REFERENCE_TAGS = {
    "nation": "Nnat",
    "team": "Ttea",
    "city": "city",
    "language": "lang",
    "competition": "comp",
}

type Change = list[Property]
type FieldValue = str | int | bool | datetime.date


class EditError(FormatError):
    """The requested edit is not one the Editor would accept."""


class Table(IntEnum):
    """Where a changed record lives, numbered as in the base database."""

    PERSON = 1
    DATABASE = 55  # the table of tables; records are added to it


class NewIds:
    """Random numbers and record IDs for the changes of one file."""

    def __init__(self, changes: ChangeList, source: random.Random | None = None):
        self._source = source or random.SystemRandom()
        self._used = {_uid(record) for record in _added_records(changes)}

    def record(self) -> bytes:
        """The ID of a new record; its first half is the uid, which no other new record has."""
        uid = self._source.choice(NEW_UIDS)
        while uid in self._used:
            uid = self._source.choice(NEW_UIDS)
        self._used.add(uid)
        return struct.pack("<II", uid, self._source.randrange(SECOND_ID_NUMBERS))

    def below(self, limit: int) -> int:
        return self._source.randrange(limit)


def existing_record(uid: int) -> bytes:
    return struct.pack("<II", uid, uid)


def add_record(table: Table, record_type: int, record: bytes, ids: NewIds) -> Change:
    """The change that adds an empty record; changes to its fields follow it."""
    described = [
        Property("id  ", Kind.CODE, "nwvl"),
        number("dtty", table),
        Property("dcty", Kind.CODE, "\x00\x00\x00" + chr(record_type)),
        Property("duni", Kind.ID, record),
    ]
    new_value = Property("nwvl", Kind.NESTED, described)
    return _change(
        Table.DATABASE, existing_record(1), ADD_RECORD, new_value, ids, is_client_field=True
    )


def field_change(
    table: Table, record: bytes, field: Field, value: FieldValue, ids: NewIds
) -> Change:
    return _change(
        table,
        record,
        field.code,
        stored_value(field, value),
        ids,
        is_client_field=field.is_client_field,
        is_language_field=field.is_language_field,
    )


def refusal(field: Field) -> str | None:
    """Why no value of this field can be written, if that is so."""
    if not field.is_editable:
        return "cannot be edited in the Editor"
    if field.type not in WRITTEN_TYPES:
        return f"has type {field.type}, which cannot be written yet"
    if field.type == "enum" and field.choices is None:
        return "has choices that the Editor's definitions do not list"
    if field.type == "integer" and (field.lowest is None or field.highest is None):
        return "has no range in the Editor's definitions"
    if field.type == REFERENCE and field.points_to not in REFERENCE_TAGS:
        return f"points to a {field.points_to}, which cannot be written yet"
    return None


def stored_value(field: Field, value: FieldValue) -> Property:
    """The new value as a change holds it, if the Editor would accept it."""
    reason = refusal(field)
    if reason is not None:
        raise _refused(field, reason)
    return Property("nwvl", *_stored(field, value))


def number(tag: str, value: int) -> Property:
    """A property holding a number in the smallest signed size that fits."""
    for kind, size in INTEGER_KINDS:
        if -(1 << (8 * size - 1)) <= value < 1 << (8 * size - 1):
            return Property(tag, kind, value.to_bytes(size, "little", signed=True))
    raise EditError(f"{value} is too large for an editor file")


def date_bytes(day: datetime.date) -> bytes:
    """Year, day of the year counted from 1, and an empty time of day."""
    return struct.pack("<I", day.year << 17 | day.timetuple().tm_yday << 8)


def _change(
    table: Table,
    record: bytes,
    code: str,
    new_value: Property,
    ids: NewIds,
    *,
    is_client_field: bool = False,
    is_language_field: bool = False,
) -> Change:
    change = [
        number("dtty", table),
        Property("duni", Kind.ID, record),
        Property("prty", Kind.CODE, code),
        new_value,
        number("vers", EDITOR_DATA_VERSION),
        number("rdui", ids.below(RANDOM_NUMBERS)),
    ]
    if is_client_field:
        change.append(Property("ISCF", Kind.BOOL, b"\x01"))
    if is_language_field:
        change.append(Property("ISLF", Kind.BOOL, b"\x01"))
    if is_client_field:
        change.append(number("DBCI", ids.below(CLIENT_NUMBERS)))
    return change


def _stored(field: Field, value: FieldValue) -> tuple[Kind, Value]:
    match field.type:
        case "string":
            return Kind.TEXT, _checked_text(field, value)
        case "attribute":
            return Kind.TEXT, str(
                _checked_number(field, value, LOWEST_ATTRIBUTE, HIGHEST_ATTRIBUTE)
            )
        case "integer":
            return _stored_number(_checked_number(field, value, field.lowest, field.highest))
        case "enum":
            return _stored_number(_checked_choice(field, value))
        case "boolean" if isinstance(value, bool):
            return Kind.BOOL, bytes([value])
        case "date" if type(value) is datetime.date:
            return Kind.DATE, date_bytes(value)
        case "database_record_unique_id":
            return Kind.NESTED, _reference(field, value)
    raise _refused(field, f"is a {field.type}, not {value!r}")


def _stored_number(value: int) -> tuple[Kind, Value]:
    stored = number("nwvl", value)
    return stored.kind, stored.value


def _checked_text(field: Field, value: FieldValue) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _refused(field, f"needs a text, not {value!r}")
    return value


def _checked_number(field: Field, value: FieldValue, lowest: int, highest: int) -> int:
    _check_whole(field, value)
    if not lowest <= value <= highest:
        raise _refused(field, f"must be from {lowest} to {highest}, not {value}")
    return value


def _check_whole(field: Field, value: FieldValue) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _refused(field, f"needs a whole number, not {value!r}")


def _checked_choice(field: Field, value: FieldValue) -> int:
    _check_whole(field, value)
    if value not in field.choices:
        options = ", ".join(f"{key} {name}" for key, name in sorted(field.choices.items()))
        raise _refused(field, f"must be one of {options}; not {value}")
    return value


def _reference(field: Field, value: FieldValue) -> list[Property]:
    uid = _checked_number(field, value, 1, HIGHEST_UID)
    return [
        Property("id  ", Kind.CODE, "nwvl"),
        Property(REFERENCE_TAGS[field.points_to], Kind.ID, existing_record(uid)),
        number("DBID", uid),
    ]


def _refused(field: Field, reason: str) -> EditError:
    return EditError(f"{field.name} ({field.code}) {reason}")


def _added_records(changes: ChangeList) -> list[bytes]:
    """The IDs of the records that the list adds."""
    return [_added_record(change) for change in changes.changes if _adds_record(change)]


def _adds_record(change: Change) -> bool:
    return any(item.tag == "prty" and item.value == ADD_RECORD for item in change)


def _added_record(change: Change) -> bytes:
    for item in change:
        if item.tag == "nwvl" and item.kind is Kind.NESTED:
            for inner in item.value:
                if inner.tag == "duni" and inner.kind is Kind.ID:
                    return inner.value
    raise EditError("a change that adds a record does not say which")


def _uid(record: bytes) -> int:
    return struct.unpack_from("<I", record)[0]
