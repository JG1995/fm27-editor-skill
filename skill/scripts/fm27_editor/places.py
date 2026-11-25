"""Clubs, competitions, cities, and stadiums in the base database, without their names.

Records refer to each other by index: the position of a record in its own table.
"""

import struct
from dataclasses import dataclass
from enum import StrEnum

from fm27_editor.binary import FormatError, Reader
from fm27_editor.dat_tables import NO_RECORD, read_records

CLUB = 0  # other records in the club table are placeholders without a name
CLUB_HEAD_SIZE, CLUB_TAIL_SIZE = 27, 3
CLUB_TEAM = b"\x0a\x00"  # the team table also holds national teams
TEAM_HEAD_SIZE = 21
COMPETITION_SIZE, NO_LEVEL = 115, 100
CITY_SIZE, STADIUM_SIZE = 31, 26


class PlacesError(FormatError):
    """A record does not follow the layout this library knows."""


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


@dataclass(frozen=True, slots=True)
class Club:
    uid: int
    nation: int | None
    based_nation: int | None
    city: int | None
    gender: Gender
    is_extinct: bool


@dataclass(frozen=True, slots=True)
class Team:
    """The first team of a club, which has the uid of the club."""

    uid: int
    reputation: int
    division: int | None
    last_division: int | None
    last_position: int
    stadium: int | None


@dataclass(frozen=True, slots=True)
class Competition:
    uid: int
    nation: int | None
    parent: int | None
    level: int | None
    gender: Gender


def parse_clubs(table: bytes) -> list[Club]:
    clubs = []
    for record in read_records(table):
        if record.data[:1] != bytes([CLUB]):
            continue
        reader = Reader(record.data, PlacesError)
        head = reader.take(CLUB_HEAD_SIZE)
        reader.text()
        reader.text()
        tail = reader.take(CLUB_TAIL_SIZE)
        if not reader.at_end:
            raise PlacesError(f"club {record.uid} has bytes behind its names")
        nation, extinct_nation = _index(head, 1), _index(head, 5)
        clubs.append(
            Club(
                record.uid,
                nation if extinct_nation is None else extinct_nation,
                based_nation=_index(head, 9),
                city=_index(head, 17),
                gender=_gender(tail[-1], record.uid),
                is_extinct=extinct_nation is not None,
            )
        )
    return clubs


def parse_teams(table: bytes) -> list[Team]:
    teams = []
    for record in read_records(table):
        if record.data[: len(CLUB_TEAM)] != CLUB_TEAM:
            continue
        head = Reader(record.data, PlacesError).take(TEAM_HEAD_SIZE)
        last_position, reputation = struct.unpack_from("<BH", head, 2)
        teams.append(
            Team(
                record.uid,
                reputation,
                division=_index(head, 5),
                last_division=_index(head, 9),
                last_position=last_position,
                stadium=_index(head, 17),
            )
        )
    return teams


def parse_competitions(client_table: bytes, server_table: bytes) -> list[Competition]:
    """Competitions from two tables that list the same ones in the same order."""
    competitions = []
    for record, rest in zip(read_records(client_table), read_records(server_table), strict=True):
        if record.uid != rest.uid:
            raise PlacesError(f"competition {record.uid} stands where {rest.uid} should")
        _check_size(record.data, COMPETITION_SIZE, record.uid)
        level = record.data[16]
        competitions.append(
            Competition(
                record.uid,
                nation=_index(record.data, 57),
                parent=_index(record.data, 65),
                level=None if level == NO_LEVEL else level + 1,
                gender=_gender(Reader(rest.data, PlacesError).take(121)[120], record.uid),
            )
        )
    return competitions


def parse_cities(table: bytes) -> dict[int, int | None]:
    """The nation of each city, by the ID of the city."""
    return _references(table, CITY_SIZE, 11)


def parse_stadiums(table: bytes) -> dict[int, int | None]:
    """The city of each stadium, by the ID of the stadium."""
    return _references(table, STADIUM_SIZE, 4)


def _references(table: bytes, size: int, offset: int) -> dict[int, int | None]:
    references = {}
    for record in read_records(table):
        _check_size(record.data, size, record.uid)
        references[record.uid] = _index(record.data, offset)
    return references


def _index(data: bytes, offset: int) -> int | None:
    index = struct.unpack_from("<I", data, offset)[0]
    return None if index == NO_RECORD else index


def _gender(value: int, uid: int) -> Gender:
    if value not in (0, 1):
        raise PlacesError(f"record {uid} has gender {value}, only 0 and 1 are known")
    return Gender.FEMALE if value else Gender.MALE


def _check_size(data: bytes, size: int, uid: int) -> None:
    if len(data) != size:
        raise PlacesError(f"record {uid} has {len(data)} bytes, expected {size}")
