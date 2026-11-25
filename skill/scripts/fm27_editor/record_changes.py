"""Building the changes that set a field or add a record, the way the Editor writes them.

Which tags a change carries and how each type of value is stored was measured over the changes in
real FM27 files, see ARCHITECTURE.md. A value outside what the Editor's definitions allow is an
error, and so is a type of field that was not seen in those files.
"""

import datetime
import random
import re
import struct

from fm27_editor.change_list import ChangeList, Kind, Property, Value
from fm27_editor.change_reading import (
    ADD_RECORD,
    ID_SIZE,
    Change,
    EditError,
    Table,
    added_record,
    adds_record,
    existing_record,
    uid_of,
)
from fm27_editor.field_definitions import Field

EDITOR_DATA_VERSION = 3756  # written by the Editor build fm27-rel-04-update1
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
WRITTEN_TYPES = {"string", "attribute", "integer", "enum", "boolean", "date", "colour", REFERENCE}
REFERENCE_TAGS = {
    "nation": "Nnat",
    "team": "Ttea",
    "city": "city",
    "language": "lang",
    "competition": "comp",
    "stadium": "stad",
}
COLOUR = re.compile("#[0-9a-fA-F]{6}")
OPAQUE = b"\xff"

type FieldValue = str | int | bool | datetime.date | bytes
"""What a field is set to; a record is given by its uid, or by its whole ID when it is new."""


class NewIds:
    """Random numbers and record IDs for the changes of one file."""

    def __init__(self, changes: ChangeList, source: random.Random | None = None):
        self._source = source or random.SystemRandom()
        added = filter(adds_record, changes.changes)
        self._used = {uid_of(added_record(change)) for change in added}

    def record(self) -> bytes:
        """The ID of a new record; its first half is the uid, which no other new record has."""
        uid = self._source.choice(NEW_UIDS)
        while uid in self._used:
            uid = self._source.choice(NEW_UIDS)
        self._used.add(uid)
        return struct.pack("<II", uid, self._source.randrange(SECOND_ID_NUMBERS))

    def below(self, limit: int) -> int:
        return self._source.randrange(limit)


def add_record(table: Table, person_type: int | None, record: bytes, ids: NewIds) -> Change:
    """The change that adds an empty record; changes to its fields follow it.

    Only people have a type. Other records have a 0 in its place, stored as a number.
    """
    if person_type is None:
        record_type = number("dcty", 0)
    else:
        record_type = Property("dcty", Kind.CODE, "\x00\x00\x00" + chr(person_type))
    described = [
        Property("id  ", Kind.CODE, "nwvl"),
        number("dtty", table),
        record_type,
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


def reference(tag: str, points_to: str, record: bytes) -> list[Property]:
    """What a property called `tag` holds to point to a record."""
    return [
        Property("id  ", Kind.CODE, tag),
        Property(REFERENCE_TAGS[points_to], Kind.ID, record),
        number("DBID", uid_of(record)),
    ]


def check_whole(called: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EditError(f"{called} needs a whole number, not {value!r}")


def checked_number(called: str, value: object, lowest: int, highest: int) -> int:
    check_whole(called, value)
    if not lowest <= value <= highest:
        raise EditError(f"{called} must be from {lowest} to {highest}, not {value}")
    return value


def checked_date(called: str, value: object) -> datetime.date:
    """A date given as text."""
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise EditError(f"{called} needs a date such as 2008-04-25, not {value!r}") from error


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
        case "colour" if isinstance(value, str) and COLOUR.fullmatch(value):
            return Kind.COLOUR_2, bytes.fromhex(value[1:])[::-1] + OPAQUE
        case "colour":
            raise _refused(field, f"needs a colour such as #480024, not {value!r}")
        case _ if field.type == REFERENCE:
            return Kind.NESTED, _reference(field, value)
    raise _refused(field, f"is a {field.type}, not {value!r}")


def _stored_number(value: int) -> tuple[Kind, Value]:
    stored = number("nwvl", value)
    return stored.kind, stored.value


def _checked_text(field: Field, value: FieldValue) -> str:
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise _refused(field, f"needs a text of one line, not {value!r}")
    return value


def _checked_number(field: Field, value: FieldValue, lowest: int, highest: int) -> int:
    return checked_number(_called(field), value, lowest, highest)


def _checked_choice(field: Field, value: FieldValue) -> int:
    check_whole(_called(field), value)
    if value not in field.choices:
        options = ", ".join(f"{key} {name}" for key, name in sorted(field.choices.items()))
        raise _refused(field, f"must be one of {options}; not {value}")
    return value


def _reference(field: Field, value: FieldValue) -> list[Property]:
    if isinstance(value, bytes) and len(value) == ID_SIZE:
        record = value
    else:
        record = existing_record(_checked_number(field, value, 1, HIGHEST_UID))
    return reference("nwvl", field.points_to, record)


def _called(field: Field) -> str:
    return f"{field.name} ({field.code})"


def _refused(field: Field, reason: str) -> EditError:
    return EditError(f"{_called(field)} {reason}")
