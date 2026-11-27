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
from fm27_editor.person_names import Names, read_identity

BASIC_HEADER_SIZE = 5
BASIC_FOOTER_SIZE = 9
BASIC_MARK = 0x11
IDS_SIZE = 12
PEOPLE_HEADER_SIZE = 6
NO_ID = 0xFFFFFFFF
NATION_MARK = b"\x03\x01"
SEARCH_CHUNK = 16_000_000
LOWEST_VALUE, HIGHEST_VALUE = 1, 20


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

    @property
    def is_player(self) -> bool:
        """Players are the only kind whose attribute positions were checked."""
        return self.kind is PersonKind.PLAYER


@dataclass(slots=True)
class Person:
    uid: int
    kind: PersonKind
    name: str
    full_name: str
    birth_date: datetime.date
    nation_uid: int
    club_uid: int | None
    ca: int | None
    pa: int | None
    fields: dict[str, int]


def parse_basic_people(content: bytes) -> list[BasicPerson]:
    count = Reader(content, PeopleError).u32()
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
        details = {
            "nation_index": nation_index,
            "nation_uid": nation_uid,
            "club_uid": club_uid if club_uid != NO_ID else None,
            "ca": ca or None,
            "pa": pa or None,
        }
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
        identity = read_identity(record, at, names)
        if identity is not None:
            return Person(
                basic.uid,
                basic.kind,
                identity.name,
                identity.full_name,
                identity.birth_date,
                basic.nation_uid,
                basic.club_uid,
                basic.ca,
                basic.pa,
                _read_fields(record, at) if _has_player_layout(record, basic) else {},
            )
        at = record.find(marker, at + 1)
    return None


def _has_player_layout(record: bytes, basic: BasicPerson) -> bool:
    """Whether the record starts where a player's does, so that fixed positions hold."""
    start = struct.pack("<IB", basic.index, PersonKind.PLAYER)
    return basic.is_player and record[: len(start)] == start


def _read_fields(record: bytes, marker_at: int) -> dict[str, int]:
    """Values between 1 and 20. Anything else is missing: the game fills it in or it is a range."""
    positions = {**ATTRIBUTES, **POSITIONS}
    positions |= {name: marker_at + offset for name, offset in PERSONALITY.items()}
    return {
        name: record[position]
        for name, position in positions.items()
        if position < len(record) and LOWEST_VALUE <= record[position] <= HIGHEST_VALUE
    }
