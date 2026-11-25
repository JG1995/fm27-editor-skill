"""Reading people from the Editor's base database.

A person's facts are split over two files. basic_people_db lists every person with nation, club, and
ability in records of a few fixed sizes. people_db holds the rest in records of varying size, in no
order, each ended by the person's index and unique ID, so it is found by those.
"""

import datetime
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from fm27_editor.binary import FormatError, Reader
from fm27_editor.person_fields import ATTRIBUTES, PERSONALITY, POSITIONS

BASIC_HEADER_SIZE = 5
BASIC_FOOTER_SIZE = 9
BASIC_MARK = 0x11
IDS_SIZE = 12
PEOPLE_HEADER_SIZE = 6
NATION_MARK = b"\x03\x01"
BIRTH_DATE_BEFORE_MARK = 12
MAX_NAME_BYTES = 80
SEARCH_CHUNK = 16_000_000
EARLIEST_BIRTH_YEAR, LATEST_BIRTH_YEAR = 1900, 2014


class PeopleError(FormatError):
    """The people files do not follow the layout this library knows."""


class PersonKind(IntEnum):
    STAFF = 1
    PLAYER = 2
    BOTH = 3
    OFFICIAL = 4
    RETIRED = 5


RECORD_SIZES = {
    PersonKind.STAFF: 84,
    PersonKind.PLAYER: 84,
    PersonKind.BOTH: 84,
    PersonKind.OFFICIAL: 34,
    PersonKind.RETIRED: 22,
}


@dataclass(slots=True, frozen=True)
class BasicPerson:
    """One person in basic_people_db. The short kinds carry no nation, club, or ability."""

    index: int
    uid: int
    kind: PersonKind
    nation_index: int | None = None
    nation_uid: int | None = None
    club_uid: int | None = None
    ca: int | None = None
    pa: int | None = None


@dataclass(slots=True, frozen=True)
class Names:
    """Name texts by number: first names, second names, common names."""

    first: dict[int, str]
    second: dict[int, str]
    common: dict[int, str]


@dataclass(slots=True)
class Person:
    uid: int
    kind: PersonKind
    name: str
    full_name: str
    birth_date: datetime.date
    nation_uid: int
    club_uid: int
    ca: int
    pa: int
    fields: dict[str, int]


def parse_basic_people(content: bytes) -> list[BasicPerson]:
    count = struct.unpack_from("<I", content)[0] if len(content) > 4 else 0
    position = BASIC_HEADER_SIZE
    people = []
    for index in range(count):
        person, position = _read_basic(content, position, index)
        people.append(person)
    if position + BASIC_FOOTER_SIZE != len(content):
        raise PeopleError(f"{len(content) - position} bytes follow the last person")
    return people


def iter_people(basic: list[BasicPerson], content: bytes, names: Names) -> Iterator[Person]:
    """Every person whose record holds a name and birth date that check out; others are skipped."""
    seen = set()
    start = PEOPLE_HEADER_SIZE
    for end in _record_ends(content, basic):
        uid = struct.unpack_from("<I", content, end + 4)[0]
        record, start = content[start:end], end + IDS_SIZE
        if uid in seen:
            continue
        person = _read_person(record, basic[struct.unpack_from("<I", content, end)[0]], names)
        if person is not None:
            seen.add(uid)
            yield person


def _read_basic(content: bytes, position: int, index: int) -> tuple[BasicPerson, int]:
    reader = Reader(content, PeopleError)
    reader.position = position
    mark, kind_number = reader.take(2)
    try:
        kind = PersonKind(kind_number)
    except ValueError as error:
        raise PeopleError(f"person {index} has unknown kind {kind_number}") from error
    record = content[position : position + RECORD_SIZES[kind]]
    if mark != BASIC_MARK or len(record) != RECORD_SIZES[kind]:
        raise PeopleError(f"person {index} does not fit the record layout")
    record_index, uid, repeated = struct.unpack_from("<III", record, len(record) - IDS_SIZE)
    if record_index != index or uid != repeated:
        raise PeopleError(f"person {index} does not end with its own index and ID")
    details = {}
    if RECORD_SIZES[kind] == 84:
        nation_index, nation_uid, _, club_uid = struct.unpack_from("<IIII", record, 2)
        ca, pa = struct.unpack_from("<Hh", record, 48)
        details = {"nation_index": nation_index, "nation_uid": nation_uid, "club_uid": club_uid}
        details |= {"ca": ca, "pa": pa}
    return BasicPerson(index, uid, kind, **details), position + len(record)


def _record_ends(content: bytes, basic: list[BasicPerson]) -> list[int]:
    """Where each record's ids start, found by an index whose ID is the one listed for it."""
    uids = np.array([person.uid for person in basic], dtype=np.uint32)
    ends = []
    for shift in range(4):
        words = np.frombuffer(content, dtype="<u4", count=(len(content) - shift) // 4, offset=shift)
        for start in range(0, len(words) - 2, SEARCH_CHUNK):
            part = words[start : start + SEARCH_CHUNK + 2]
            same = np.flatnonzero((part[1:-1] == part[2:]) & (part[:-2] < len(uids)))
            matches = same[uids[part[same]] == part[same + 1]]
            ends.extend(int(i + start) * 4 + shift for i in matches)
    return sorted(ends)


def _read_person(record: bytes, basic: BasicPerson, names: Names) -> Person | None:
    if basic.nation_uid is None:
        return None
    marker = NATION_MARK + struct.pack("<II", basic.nation_index, basic.nation_uid)
    at = record.find(marker)
    while at >= 0:
        identity = _read_identity(record, at, names)
        if identity is not None:
            name, full_name, birth_date = identity
            return Person(
                basic.uid,
                basic.kind,
                name,
                full_name,
                birth_date,
                basic.nation_uid,
                basic.club_uid,
                basic.ca,
                basic.pa,
                _read_fields(record, at),
            )
        at = record.find(marker, at + 1)
    return None


def _read_identity(
    record: bytes, marker_at: int, names: Names
) -> tuple[str, str, datetime.date] | None:
    """The name and birth date in front of a nation marker, or None when they do not check out."""
    date_at = marker_at - BIRTH_DATE_BEFORE_MARK
    if date_at < 0:
        return None
    day, year = struct.unpack_from("<HH", record, date_at)
    if not 1 <= day <= 366 or not EARLIEST_BIRTH_YEAR <= year <= LATEST_BIRTH_YEAR:
        return None
    for size in range(MAX_NAME_BYTES + 1):
        length_at = date_at - size - 4
        if length_at < 15:
            break
        if struct.unpack_from("<I", record, length_at)[0] != size:
            continue
        name = _read_names(record, length_at, size, names)
        if name is not None:
            full_name, display = name
            birth_date = datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)
            return display, full_name, birth_date
    return None


def _read_names(record: bytes, length_at: int, size: int, names: Names) -> tuple[str, str] | None:
    """The stored full name and the name to show, or None when the block is not a name block."""
    separators = (record[length_at - 1], record[length_at - 6], record[length_at - 11])
    if any(separators):
        return None
    try:
        full_name = record[length_at + 4 : length_at + 4 + size].decode()
    except UnicodeDecodeError:
        return None
    first, second, common = (
        struct.unpack_from("<I", record, length_at - back)[0] for back in (15, 10, 5)
    )
    if first not in names.first or second not in names.second:
        return None
    if common != 0xFFFFFFFF and common not in names.common:
        return None
    if common != 0xFFFFFFFF:
        return full_name, names.common[common]
    return full_name, full_name or f"{names.first[first]} {names.second[second]}"


def _read_fields(record: bytes, marker_at: int) -> dict[str, int]:
    """Values that are set; a 0 is left out because the game fills it in."""
    fields = {}
    for name, offset in {**ATTRIBUTES, **POSITIONS}.items():
        if offset < len(record) and record[offset]:
            fields[name] = record[offset]
    for name, offset in PERSONALITY.items():
        position = marker_at + offset
        if position < len(record) and record[position]:
            fields[name] = record[position]
    return fields
