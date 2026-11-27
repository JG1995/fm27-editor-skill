"""What a change says: which record and field it is about, and its value in plain form.

This is the reading side of `record_changes`.
"""

import datetime
import struct
from dataclasses import dataclass
from enum import IntEnum

from fm27_editor.binary import FormatError
from fm27_editor.change_list import Kind, Property

ADD_RECORD = "ADDR"
REMOVE_RECORD = "DELE"
ID_SIZE = 8
UNSIGNED = {Kind.INT8_2, Kind.INT16_2, Kind.INT32_2, Kind.COUNT}
NUMBERS = {Kind.INT8, Kind.INT16, Kind.INT32, Kind.INT64, *UNSIGNED}

type Change = list[Property]
type PlainValue = str | int | float | bool | datetime.date | None


class EditError(FormatError):
    """An edit that the Editor would not accept, or a change that cannot be read."""


class Table(IntEnum):
    """Where a changed record lives, numbered as in the base database."""

    AWARD = 0
    PERSON = 1
    CITY = 2
    CLUB = 3
    NATION = 9  # the Editor's list of tables calls it National Team; see place_lookup
    STADIUM = 21
    COMPETITION = 25
    DATABASE = 55  # the table of tables; records are added to it


@dataclass(frozen=True)
class ReadChange:
    table: int
    record: bytes
    code: str
    new: Property | None


def read_change(change: Change) -> ReadChange:
    """What a change is about; one that adds a record is about the record it adds."""
    parts = {item.tag: item for item in change}
    missing = {"dtty", "duni", "prty"} - parts.keys()
    if missing:
        raise EditError(f"a change has no {', '.join(sorted(missing))}")
    code, new = str(parts["prty"].value), parts.get("nwvl")
    if code == ADD_RECORD and read_number(parts["dtty"]) == Table.DATABASE:
        return ReadChange(*_added(new), code, new)
    return ReadChange(read_number(parts["dtty"]), bytes(parts["duni"].value), code, new)


def adds_record(change: Change) -> bool:
    return any(item.tag == "prty" and item.value == ADD_RECORD for item in change)


def added_record(change: Change) -> bytes:
    """The ID of the record that a change adds."""
    new = next((item for item in change if item.tag == "nwvl"), None)
    return _added(new)[1]


def existing_record(uid: int) -> bytes:
    return struct.pack("<II", uid, uid)


def uid_of(record: bytes) -> int:
    return struct.unpack_from("<I", record)[0]


def is_existing(record: bytes) -> bool:
    """Whether an ID is that of a record in the base database: its uid, twice."""
    return len(record) == ID_SIZE and record == existing_record(uid_of(record))


def read_number(value: Property) -> int:
    return int.from_bytes(value.value, "little", signed=value.kind not in UNSIGNED)


def read_plain(value: Property) -> PlainValue:
    """A value of a kind that stands for itself; others, such as lists, are an error."""
    if value.kind is Kind.NULL:
        return None
    if value.kind is Kind.TEXT:
        return value.value
    if value.kind in NUMBERS:
        return read_number(value)
    if value.kind is Kind.BOOL:
        return bool(value.value[0])
    if value.kind is Kind.REAL:
        return struct.unpack("<f", value.value)[0]
    if value.kind is Kind.DATE:
        return read_date(value.value)
    raise EditError(f"a value of kind {value.kind.name} does not stand for itself")


def says_nothing(value: Property) -> bool:
    """Whether a value is nothing, an empty text, or a no; a number of 0 says something."""
    return value.kind in (Kind.NULL, Kind.TEXT, Kind.BOOL) and not read_plain(value)


def read_date(raw: bytes) -> datetime.date:
    number = struct.unpack("<I", raw)[0]
    year, day = number >> 17, number >> 8 & 0x1FF
    try:
        date = datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)
    except (ValueError, OverflowError) as error:
        raise EditError(f"{raw.hex()} is not a date") from error
    if date.year != year:
        raise EditError(f"{raw.hex()} is not a date")
    return date


def referred_to(value: Property) -> tuple[str, bytes] | None:
    """The tag and ID of the record a value refers to, if that is all it says."""
    if value.kind is not Kind.NESTED or len(value.value) > 3:
        return None
    for part in value.value:
        if part.kind is Kind.ID:
            return part.tag, part.value
    return None


def _added(new: Property | None) -> tuple[int, bytes]:
    parts = {}
    if new is not None and new.kind is Kind.NESTED:
        parts = {item.tag: item for item in new.value}
    record = parts.get("duni")
    if "dtty" not in parts or record is None or record.kind is not Kind.ID:
        raise EditError("a change that adds a record does not say which")
    return read_number(parts["dtty"]), record.value
