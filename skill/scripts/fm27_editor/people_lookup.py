"""The tables of the lookup for people."""

import sqlite3
from collections.abc import Iterable

from fm27_editor.dat_tables import read_string_table
from fm27_editor.people import BasicPerson, Names, Person, iter_people
from fm27_editor.person_fields import FIELD_NAMES
from fm27_editor.place_lookup import Tables

# First names, second names, and common names, by number.
NAME_TABLES = [f"name_table_extra_{number}" for number in range(3)]
CLIENT_TABLES = set(NAME_TABLES)
BATCH = 5_000
_FIELD_COLUMNS = ", ".join(f"{name} INTEGER" for name in FIELD_NAMES)
SCHEMA = f"""
CREATE TABLE person(uid INTEGER PRIMARY KEY, kind TEXT, name TEXT, full_name TEXT,
    birth_date TEXT, nation_uid INTEGER, club_uid INTEGER, ca INTEGER, pa INTEGER,
    {_FIELD_COLUMNS});
CREATE VIEW people AS SELECT person.*, nation.name AS nation, club.name AS club,
    club.gender AS club_gender, club.division_uid, competition.name AS division
    FROM person LEFT JOIN nation ON nation.uid = person.nation_uid
    LEFT JOIN club ON club.uid = person.club_uid
    LEFT JOIN competition ON competition.uid = club.division_uid;
"""
# Made after the rows are in, which is faster than keeping them up to date.
INDEXES = """
CREATE INDEX person_nation ON person(nation_uid);
CREATE INDEX person_club ON person(club_uid);
CREATE INDEX person_birth ON person(birth_date);
CREATE INDEX person_name ON person(name);
"""


def insert_people(
    cache: sqlite3.Connection, client: Tables, basic: list[BasicPerson], content: bytes
) -> None:
    """Every person that people_db holds in a known layout, from its records in `content`."""
    names = Names(*(read_string_table(client[table]) for table in NAME_TABLES))
    _insert(cache, iter_people(basic, content, names))
    cache.executescript(INDEXES)


def _insert(cache: sqlite3.Connection, people: Iterable[Person]) -> None:
    placeholders = ", ".join("?" * (9 + len(FIELD_NAMES)))
    statement = f"INSERT INTO person VALUES ({placeholders})"
    batch = []
    for person in people:
        batch.append(
            (
                person.uid,
                person.kind.name.lower(),
                person.name,
                person.full_name,
                person.birth_date.isoformat(),
                person.nation_uid,
                person.club_uid,
                person.ca,
                person.pa,
                *(person.fields.get(name) for name in FIELD_NAMES),
            )
        )
        if len(batch) == BATCH:
            cache.executemany(statement, batch)
            batch.clear()
    cache.executemany(statement, batch)
