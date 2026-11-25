"""Awards and their past winners in the base database, without the names of the awards.

Records refer to others by index: the position of a record in its own table. Teams are given by ID
as well, which also holds for the national teams: theirs is the one of the nation.
"""

import struct
from dataclasses import dataclass

from fm27_editor.binary import FormatError, Reader
from fm27_editor.dat_tables import Record, index_at, read_records
from fm27_editor.places import Gender, gender_of

AWARD_SIZE = 65
PLACES = 3
YEAR_HEAD_SIZE = 43
ONLY_KIND = 0  # of the 33,608 years checked


class AwardsError(FormatError):
    """A record of an award does not follow the layout this library knows."""


@dataclass(frozen=True, slots=True)
class Award:
    uid: int
    nation: int | None
    competition: int | None
    gender: Gender
    previous_winner: int
    """Whether it can be won again, by the Editor's number; 0 when that is not set."""


@dataclass(frozen=True, slots=True)
class AwardPlace:
    """One of the first three; what is 0 or empty is not known."""

    person: int | None
    name: str
    team_uid: int | None
    points: int
    more_points: int
    age: int
    nation: int | None
    position: int


@dataclass(frozen=True, slots=True)
class AwardYear:
    uid: int
    award: int
    year: int
    places: tuple[AwardPlace, ...]
    has_no_data: bool
    was_not_held: bool


def parse_awards(table: bytes) -> list[Award]:
    awards = []
    for record in read_records(table):
        if len(record.data) != AWARD_SIZE:
            raise AwardsError(
                f"award {record.uid} has {len(record.data)} bytes, expected {AWARD_SIZE}"
            )
        awards.append(
            Award(
                record.uid,
                nation=index_at(record.data, 28),
                competition=index_at(record.data, 42),
                gender=gender_of(record.data[37], record.uid),
                previous_winner=record.data[51],
            )
        )
    return awards


def parse_award_years(table: bytes) -> list[AwardYear]:
    """The history of every award, in the order of the database."""
    return [_award_year(record) for record in read_records(table)]


def _award_year(record: Record) -> AwardYear:
    reader = Reader(record.data, AwardsError)
    try:
        head = reader.take(YEAR_HEAD_SIZE)
        names = [reader.text() for _ in range(PLACES)]
        teams, nations = reader.take(8 * PLACES), reader.take(4 * PLACES)
        ages, marks = reader.take(PLACES), reader.take(2)
    except AwardsError as error:
        raise AwardsError(f"year {record.uid} of an award: {error}") from error
    kind, award, year = struct.unpack_from("<BIH", head)
    if not reader.at_end or kind != ONLY_KIND or not {0, 1}.issuperset(marks):
        raise AwardsError(f"year {record.uid} of an award does not fit the known layout")
    points, more_points = struct.unpack_from("<3H", head, 19), struct.unpack_from("<3H", head, 25)
    positions = struct.unpack_from("<3I", head, 31)
    places = tuple(
        AwardPlace(
            person=index_at(head, 7 + 4 * place),
            name=names[place],
            team_uid=index_at(teams, 8 * place + 4),
            points=points[place],
            more_points=more_points[place],
            age=ages[place],
            nation=index_at(nations, 4 * place),
            position=positions[place],
        )
        for place in range(PLACES)
    )
    has_no_data, was_not_held = map(bool, marks)
    return AwardYear(record.uid, award, year, places, has_no_data, was_not_held)
