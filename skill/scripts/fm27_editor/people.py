"""Reading people from the Editor's base database.

A person's facts are split over two files. basic_people_db lists every person with nation, club, and
ability in records of a few fixed sizes; an official's short record has only the nation, and a
retired person's nothing. people_db holds the rest in records of varying size, in no order, each
ended by the person's index and unique ID, so it is found by those. A retired person's record holds
only a name.
"""

import datetime
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import IntEnum
from typing import NamedTuple

import numpy as np

from fm27_editor.binary import FormatError, Reader
from fm27_editor.person_fields import (
    ATTRIBUTES,
    PERSONALITY,
    POSITIONS,
    STAFF_ATTRIBUTES,
    STAFF_LIST_ITEM_MARKS,
    STAFF_LIST_ITEM_SIZE,
)
from fm27_editor.person_names import NO_DATE, Names, read_date, read_identity

BASIC_HEADER_SIZE = 5
BASIC_FOOTER_SIZE = 9
BASIC_MARK = 0x11
IDS_SIZE = 12
PEOPLE_HEADER_SIZE = 6
NO_ID = 0xFFFFFFFF
NATION_MARK = b"\x03\x01"
SEARCH_CHUNK = 16_000_000
LOWEST_VALUE, HIGHEST_VALUE = 1, 20
# A retired person's record: the index and kind, four zero bytes, the name, and eight zero bytes.
RETIRED_GAP, RETIRED_TAIL = bytes(4), bytes(8)
# A contract starts with the person's index, then the club's index and uid, and the weekly wage in
# pounds. It follows a date and a zero byte, and the date it expires stands 43 bytes before it.
# Matched against an FM27 save: the expiry date of 88,983 of 99,700 people, and most of the others
# expire later there, renewed; the wage of 34,854 of the 38,127 people whose wage the database sets.
CONTRACT_DATE_BEFORE, CONTRACT_EXPIRES_BEFORE, CONTRACT_CLUB_AT, CONTRACT_WAGE_AT = 5, 43, 8, 12
# Days at clubs and in nations end ten bytes before the end of the record: ff 01 and a byte, the
# number of items, and the items. An item is a byte of flags whose lowest bit is set, the days, a
# byte the lookup does not read, and the uid of the club or nation. Every player and staff member
# but one has them in this layout alone, at known clubs and nations, and days at the current club
# go back to the day the playing history says the person joined it.
DAYS_BEFORE, DAYS_TAIL_SIZE = b"\xff\x01", 10
DAYS_ITEM = struct.Struct("<BHBI")
# The other bits of the flags are the Editor's boxes of an item, as 21 items that the Editor saved
# showed them on 2026-11-28. Days contracted between 0 and 21 is the one bit left over, which no
# item of the database has. The byte that is not read is no part the Editor saves.
DAYS_BOXES = {
    "between_0_and_21": 0x04,
    "between_15_and_21": 0x02,
    "between_18_and_23": 0x10,
    "between_0_and_19": 0x40,
    "contracted_between_15_and_21": 0x20,
    "contracted_between_0_and_21": 0x08,
}
DAYS_FLAGS = 0x01 | sum(DAYS_BOXES.values())
# A contract without an end follows these bytes instead. Only staff have one, and in the save they
# have no expiry date; its wage is the save's for 807 of the 808 staff whose wage both set.
OPEN_ENDED = b"\xff\xff\xff\xff\x05\x05"


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
    """One person in basic_people_db. The short kinds carry no club or ability."""

    index: int
    uid: int
    kind: PersonKind
    nation_index: int | None = None
    nation_uid: int | None = None
    club_uid: int | None = None
    ca: int | None = None
    pa: int | None = None


class ClubOrNationDays(NamedTuple):
    """How many days a person has spent at a club or in a nation, as the Editor counts them, and
    the ages that the Editor's boxes limit them to."""

    club_or_nation_uid: int
    days: int
    between_0_and_21: bool
    between_15_and_21: bool
    between_18_and_23: bool
    between_0_and_19: bool
    contracted_between_15_and_21: bool
    contracted_between_0_and_21: bool


@dataclass(slots=True)
class Person:
    uid: int
    kind: PersonKind
    name: str
    full_name: str | None
    birth_date: datetime.date | None = None
    nation_uid: int | None = None
    club_uid: int | None = None
    ca: int | None = None
    pa: int | None = None
    fields: dict[str, int] = field(default_factory=dict)
    wage: int | None = None
    contract_expires: datetime.date | None = None
    club_or_nation_days: tuple[ClubOrNationDays, ...] | None = None
    """None when the record does not hold them in the known layout."""


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
    """Every person whose record follows a known layout, with a name (and, but for retired people,
    a birth date) that checks out; others are skipped."""
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
    elif kind is PersonKind.OFFICIAL:
        nation_index, nation_uid = struct.unpack_from("<II", record, 2)
        details = {"nation_index": nation_index, "nation_uid": nation_uid}
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
    if basic.kind is PersonKind.RETIRED:
        return _read_retired(record, basic)
    if basic.nation_uid is None:
        return None
    marker = NATION_MARK + struct.pack("<II", basic.nation_index, basic.nation_uid)
    at = record.find(marker)
    while at >= 0:
        identity = read_identity(record, at, names)
        if identity is not None:
            wage, expires = _read_contract(record, basic)
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
                _read_fields(record, basic, at),
                wage,
                expires,
                _read_club_or_nation_days(record),
            )
        at = record.find(marker, at + 1)
    return None


def _read_contract(record: bytes, basic: BasicPerson) -> tuple[int | None, datetime.date | None]:
    """The wage and the date the contract with the person's club expires, if the person has one
    contract with it. A contract without an end has a wage alone."""
    if basic.club_uid is None:
        return None, None
    starts = [
        at
        for at in _found(record, struct.pack("<I", basic.index))
        if _is_with(record, at, basic.club_uid)
    ]
    ending = [at for at in starts if _follows_dates(record, at)]
    open_ended = [at for at in starts if record[max(0, at - len(OPEN_ENDED)) : at] == OPEN_ENDED]
    if len(ending) + len(open_ended) != 1:
        return None, None
    (at,) = ending or open_ended
    wage = struct.unpack_from("<I", record, at + CONTRACT_WAGE_AT)[0] or None
    if open_ended:
        return wage, None
    expires = read_date(record, at - CONTRACT_EXPIRES_BEFORE)
    return wage, None if expires == NO_DATE else expires


def _is_with(record: bytes, at: int, club_uid: int) -> bool:
    """Whether a contract with the club could start here."""
    if at + CONTRACT_WAGE_AT + 4 > len(record):
        return False
    return struct.unpack_from("<I", record, at + CONTRACT_CLUB_AT)[0] == club_uid


def _follows_dates(record: bytes, at: int) -> bool:
    """Whether a contract that ends follows: a date and a zero byte, and the date it expires."""
    return (
        at >= CONTRACT_EXPIRES_BEFORE
        and record[at - 1] == 0
        and read_date(record, at - CONTRACT_DATE_BEFORE) is not None
        and read_date(record, at - CONTRACT_EXPIRES_BEFORE) is not None
    )


def _read_club_or_nation_days(record: bytes) -> tuple[ClubOrNationDays, ...] | None:
    """The days at clubs and in nations that end the record, if they can be read one way only.

    Going back from the end, each item that starts with a set lowest bit could be the first, if the
    number before it counts the items from there.
    """
    end = len(record) - DAYS_TAIL_SIZE
    starts = []
    for count in range(256):
        start = end - count * DAYS_ITEM.size
        if start < len(DAYS_BEFORE) + 2:
            break
        if record[start - 1] == count and record[start - 4 : start - 2] == DAYS_BEFORE:
            starts.append(start)
        if start < DAYS_ITEM.size or not record[start - DAYS_ITEM.size] & 1:
            break
    if len(starts) != 1:
        return None
    items = list(DAYS_ITEM.iter_unpack(record[starts[0] : end]))
    if any(flags & ~DAYS_FLAGS for flags, *_ in items):
        return None
    return tuple(
        ClubOrNationDays(uid, days, *(bool(flags & bit) for bit in DAYS_BOXES.values()))
        for flags, days, _, uid in items
    )


def _found(record: bytes, part: bytes) -> Iterator[int]:
    at = record.find(part)
    while at >= 0:
        yield at
        at = record.find(part, at + 1)


def _read_retired(record: bytes, basic: BasicPerson) -> Person | None:
    head = struct.pack("<IB", basic.index, basic.kind) + RETIRED_GAP
    if not record.startswith(head) or not record.endswith(RETIRED_TAIL):
        return None
    reader = Reader(record[len(head) : -len(RETIRED_TAIL)], PeopleError)
    try:
        name = reader.text()
    except PeopleError:
        return None
    return Person(basic.uid, basic.kind, name, name) if name and reader.at_end else None


def _read_fields(record: bytes, basic: BasicPerson, marker_at: int) -> dict[str, int]:
    """Values between 1 and 20, of players and staff whose record starts with its index and kind.

    Anything else is missing: the game fills it in, or it is a range.
    """
    if not record.startswith(struct.pack("<IB", basic.index, basic.kind)):
        return {}
    if basic.kind is PersonKind.PLAYER:
        positions = {**ATTRIBUTES, **POSITIONS}
    elif basic.kind is PersonKind.STAFF:
        start = _staff_attributes_start(record)
        known = start is not None
        positions = (
            {name: start + offset for name, offset in STAFF_ATTRIBUTES.items()} if known else {}
        )
    else:
        return {}
    positions |= {name: marker_at + offset for name, offset in PERSONALITY.items()}
    return {
        name: record[position]
        for name, position in positions.items()
        if position < len(record) and LOWEST_VALUE <= record[position] <= HIGHEST_VALUE
    }


def _staff_attributes_start(record: bytes) -> int | None:
    """Where staff attributes count from: after the list that follows the kind, if it checks out."""
    if len(record) < 7:
        return None
    start = 7 + STAFF_LIST_ITEM_SIZE * struct.unpack_from("<H", record, 5)[0]
    if start >= len(record):
        return None
    for item_at in range(7, start, STAFF_LIST_ITEM_SIZE):
        if any(record[item_at + at] != mark for at, mark in STAFF_LIST_ITEM_MARKS.items()):
            return None
    return start
