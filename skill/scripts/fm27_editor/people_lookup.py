"""The tables of the lookup for people, their days at clubs and in nations, their relations, and
their playing histories."""

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from itertools import batched

from fm27_editor.dat_tables import read_string_table
from fm27_editor.people import (
    DAYS_BOXES,
    BasicPerson,
    ClubOrNationDays,
    FavouriteClub,
    FavouritePerson,
    Person,
    Relation,
    SecondNation,
    TrainedAtClub,
    TrainedInNation,
    iter_people,
)
from fm27_editor.person_fields import FIELD_NAMES
from fm27_editor.person_names import Names
from fm27_editor.place_lookup import Tables
from fm27_editor.playing_history import Season, parse_playing_histories

# First names, second names, and common names, by number.
NAME_TABLES = [f"name_table_extra_{number}" for number in range(3)]
CLIENT_TABLES = set(NAME_TABLES)
_FIELD_COLUMNS = ", ".join(f"{name} INTEGER" for name in FIELD_NAMES)
_BOX_COLUMNS = ", ".join(f"{name} INTEGER" for name in DAYS_BOXES)
SCHEMA = f"""
CREATE TABLE person(uid INTEGER PRIMARY KEY, kind TEXT, name TEXT, full_name TEXT,
    birth_date TEXT, nation_uid INTEGER, club_uid INTEGER, ca INTEGER, pa INTEGER,
    wage INTEGER, contract_expires TEXT, clubs_and_nations INTEGER, relations INTEGER,
    {_FIELD_COLUMNS});
CREATE VIEW people AS SELECT person.*, nation.name AS nation, club.name AS club,
    club.gender AS club_gender, club.division_uid, competition.name AS division
    FROM person LEFT JOIN nation ON nation.uid = person.nation_uid
    LEFT JOIN club ON club.uid = person.club_uid
    LEFT JOIN competition ON competition.uid = club.division_uid;
CREATE TABLE club_or_nation_days(person_uid INTEGER, item INTEGER, club_or_nation_uid INTEGER,
    days INTEGER, {_BOX_COLUMNS}, PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW days_at_club_or_nation AS SELECT club_or_nation_days.*, person.name,
    coalesce(club.name, nation.name) AS club_or_nation
    FROM club_or_nation_days LEFT JOIN person ON person.uid = club_or_nation_days.person_uid
    LEFT JOIN club ON club.uid = club_or_nation_uid
    LEFT JOIN national_team ON national_team.uid = club_or_nation_uid
    LEFT JOIN nation ON nation.uid = national_team.nation_uid;
CREATE TABLE second_nation(person_uid INTEGER, item INTEGER, nation_uid INTEGER,
    nationality_info INTEGER, PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW second_nations AS SELECT second_nation.*, person.name, nation.name AS nation
    FROM second_nation LEFT JOIN person ON person.uid = second_nation.person_uid
    LEFT JOIN nation ON nation.uid = second_nation.nation_uid;
CREATE TABLE trained_in_nation(person_uid INTEGER, item INTEGER, nation_uid INTEGER, type INTEGER,
    PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW trained_in_nations AS SELECT trained_in_nation.*, person.name, nation.name AS nation
    FROM trained_in_nation LEFT JOIN person ON person.uid = trained_in_nation.person_uid
    LEFT JOIN nation ON nation.uid = trained_in_nation.nation_uid;
CREATE TABLE trained_at_club(person_uid INTEGER, item INTEGER, club_uid INTEGER, type INTEGER,
    PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW trained_at_clubs AS SELECT trained_at_club.*, person.name, club.name AS club
    FROM trained_at_club LEFT JOIN person ON person.uid = trained_at_club.person_uid
    LEFT JOIN club ON club.uid = trained_at_club.club_uid;
CREATE TABLE favourite_person(person_uid INTEGER, item INTEGER, favourite_uid INTEGER,
    level INTEGER, reason INTEGER, permanent INTEGER, PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW favourite_people AS SELECT favourite_person.*, person.name,
    favourite.name AS favourite
    FROM favourite_person LEFT JOIN person ON person.uid = favourite_person.person_uid
    LEFT JOIN person AS favourite ON favourite.uid = favourite_person.favourite_uid;
CREATE TABLE favourite_club(person_uid INTEGER, item INTEGER, club_uid INTEGER, level INTEGER,
    reason INTEGER, PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW favourite_clubs AS SELECT favourite_club.*, person.name, club.name AS club
    FROM favourite_club LEFT JOIN person ON person.uid = favourite_club.person_uid
    LEFT JOIN club ON club.uid = favourite_club.club_uid;
CREATE TABLE history_season(person_uid INTEGER, item INTEGER, year INTEGER,
    order_in_year INTEGER, club_uid INTEGER, division_uid INTEGER, apps INTEGER, goals INTEGER,
    transfer_fee INTEGER, other INTEGER, date_joined TEXT, date_left TEXT, on_loan INTEGER,
    youth_team INTEGER, tribunal_fee INTEGER, extras INTEGER,
    PRIMARY KEY (person_uid, item)) WITHOUT ROWID;
CREATE VIEW playing_history AS SELECT history_season.*, person.name, club.name AS club,
    competition.name AS division
    FROM history_season LEFT JOIN person ON person.uid = history_season.person_uid
    LEFT JOIN club ON club.uid = history_season.club_uid
    LEFT JOIN competition ON competition.uid = history_season.division_uid;
"""
# Made after the rows are in, which is faster than keeping them up to date.
INDEXES = """
CREATE INDEX person_nation ON person(nation_uid);
CREATE INDEX person_club ON person(club_uid);
CREATE INDEX person_birth ON person(birth_date);
CREATE INDEX person_name ON person(name);
"""
_DAYS_PLACEHOLDERS = ", ".join("?" * (2 + len(ClubOrNationDays._fields)))
# The table of each kind of relation, whose columns after the person and the item are its facts.
RELATION_TABLES: dict[type[Relation], str] = {
    SecondNation: "second_nation",
    TrainedInNation: "trained_in_nation",
    TrainedAtClub: "trained_at_club",
    FavouritePerson: "favourite_person",
    FavouriteClub: "favourite_club",
}
# People are inserted in batches, each with their days at clubs and in nations: both come from one
# reading of people_db, and the 3.5 million days held at once would take hundreds of megabytes.
PEOPLE_PER_BATCH = 10_000


def insert_people(
    cache: sqlite3.Connection, client: Tables, basic: list[BasicPerson], content: bytes
) -> None:
    """Every person that people_db holds in a known layout, from its records in `content`."""
    names = Names(*(read_string_table(client[table]) for table in NAME_TABLES))
    _insert(cache, iter_people(basic, content, names))
    cache.executescript(INDEXES)


def insert_playing_histories(
    cache: sqlite3.Connection,
    basic: list[BasicPerson],
    index: bytes,
    offsets: bytes,
    seasons: bytes,
) -> None:
    """The seasons of the people of the database, from the streams of the three pl_hist files.

    A tenth of the histories belong to uids that are not people of the database, and nobody can
    change those.
    """
    people = {person.uid for person in basic}
    placeholders = ", ".join("?" * len(Season._fields))
    cache.executemany(
        f"INSERT INTO history_season VALUES ({placeholders})",
        (
            season
            for season in parse_playing_histories(index, offsets, seasons)
            if season.person_uid in people
        ),
    )


def _insert(cache: sqlite3.Connection, people: Iterable[Person]) -> None:
    placeholders = ", ".join("?" * (13 + len(FIELD_NAMES)))
    for batch in batched(people, PEOPLE_PER_BATCH, strict=False):
        cache.executemany(f"INSERT INTO person VALUES ({placeholders})", map(_row, batch))
        cache.executemany(
            f"INSERT INTO club_or_nation_days VALUES ({_DAYS_PLACEHOLDERS})", _days(batch)
        )
        for kind, table in RELATION_TABLES.items():
            rows = list(_relations(batch, kind))
            if rows:
                marks = ", ".join("?" * len(rows[0]))
                cache.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)


def _days(people: Sequence[Person]) -> Iterator[tuple[int, ...]]:
    for person in people:
        for item, days in enumerate(person.club_or_nation_days or ()):
            yield (person.uid, item, *days)


def _relations(people: Sequence[Person], kind: type[Relation]) -> Iterator[tuple]:
    """The rows of one kind of relation, numbered from 0 for each person."""
    for person in people:
        of_kind = (relation for relation in person.relations or () if type(relation) is kind)
        for item, relation in enumerate(of_kind):
            yield (person.uid, item, *relation)


def _row(person: Person) -> tuple:
    return (
        person.uid,
        person.kind.name.lower(),
        person.name,
        person.full_name,
        person.birth_date and person.birth_date.isoformat(),
        person.nation_uid,
        person.club_uid,
        person.ca,
        person.pa,
        person.wage,
        person.contract_expires and person.contract_expires.isoformat(),
        None if person.club_or_nation_days is None else len(person.club_or_nation_days),
        None if person.relations is None else len(person.relations),
        *(person.fields.get(name) for name in FIELD_NAMES),
    )
