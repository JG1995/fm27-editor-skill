"""The tables of the lookup for awards and their past winners."""

import sqlite3
from collections.abc import Iterator, Sequence

from fm27_editor.awards import AwardPlace, AwardYear, parse_award_years, parse_awards
from fm27_editor.dat_tables import read_records
from fm27_editor.name_tables import NamedTable, read_names
from fm27_editor.place_lookup import COMPETITIONS, NATIONS, Tables, insert_rows, uid_at

AWARDS, HISTORY = "table_0", "table_12"
AWARD_NAMES = "8_0"
CLIENT_TABLES = {AWARDS, NATIONS, COMPETITIONS}
SERVER_TABLES = {HISTORY}
NAME_TABLES = {AWARD_NAMES}
SCHEMA = """
CREATE TABLE award(uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, gender TEXT,
    nation_uid INTEGER, competition_uid INTEGER, previous_winner INTEGER);
CREATE TABLE award_year(uid INTEGER PRIMARY KEY, award_uid INTEGER, year INTEGER,
    not_held INTEGER, no_data INTEGER);
CREATE TABLE award_place(year_uid INTEGER, place INTEGER, person_uid INTEGER, name TEXT,
    team_uid INTEGER, points INTEGER, more_points INTEGER, age INTEGER, nation_uid INTEGER,
    position INTEGER);
CREATE INDEX award_year_award ON award_year(award_uid);
CREATE INDEX award_place_year ON award_place(year_uid);
CREATE INDEX award_place_person ON award_place(person_uid);
CREATE VIEW awards AS SELECT award.*, nation.name AS nation, competition.name AS competition,
    (SELECT count(*) FROM award_year WHERE award_year.award_uid = award.uid) AS years
    FROM award LEFT JOIN nation ON nation.uid = award.nation_uid
    LEFT JOIN competition ON competition.uid = award.competition_uid;
CREATE VIEW award_history AS SELECT award_year.award_uid, award.name AS award, award_year.year,
    award_place.place, award_place.person_uid, award_place.name, award_place.team_uid,
    coalesce(club.name, home.name) AS team, award_place.points, award_place.age,
    award_place.nation_uid, nation.name AS nation, award_year.not_held, award_year.no_data
    FROM award_year JOIN award ON award.uid = award_year.award_uid
    LEFT JOIN award_place ON award_place.year_uid = award_year.uid
    LEFT JOIN club ON club.uid = award_place.team_uid
    LEFT JOIN nation AS home ON home.uid = award_place.team_uid
    LEFT JOIN nation ON nation.uid = award_place.nation_uid;
"""


def insert_awards(
    cache: sqlite3.Connection,
    client: Tables,
    server: Tables,
    name_tables: Tables,
    people: Sequence[int],
) -> None:
    """Fill the tables; `people` are the IDs of everyone in the database, by index."""
    names = read_names(NamedTable.AWARD, name_tables[AWARD_NAMES])
    nations = [record.uid for record in read_records(client[NATIONS])]
    competitions = [record.uid for record in read_records(client[COMPETITIONS])]
    awards = parse_awards(client[AWARDS])
    uids = [award.uid for award in awards]
    years = parse_award_years(server[HISTORY])
    insert_rows(
        cache,
        "award",
        [
            (
                award.uid,
                *names.get(award.uid, (None, None)),
                award.gender,
                uid_at(nations, award.nation, "nation"),
                uid_at(competitions, award.competition, "competition"),
                award.previous_winner or None,
            )
            for award in awards
        ],
    )
    insert_rows(
        cache,
        "award_year",
        [
            (
                year.uid,
                uid_at(uids, year.award, "award"),
                year.year,
                year.was_not_held,
                year.has_no_data,
            )
            for year in years
        ],
    )
    insert_rows(
        cache,
        "award_place",
        [
            (
                year_uid,
                place,
                uid_at(people, winner.person, "person"),
                winner.name or None,
                winner.team_uid,
                winner.points or None,
                winner.more_points or None,
                winner.age or None,
                uid_at(nations, winner.nation, "nation"),
                winner.position or None,
            )
            for year_uid, place, winner in _winners(years)
        ],
    )


def _winners(years: Sequence[AwardYear]) -> Iterator[tuple[int, int, AwardPlace]]:
    """The year, the place counted from 1, and who has it; empty places are left out."""
    for year in years:
        for place, winner in enumerate(year.places, 1):
            if winner.name or winner.person is not None or winner.team_uid is not None:
                yield year.uid, place, winner
