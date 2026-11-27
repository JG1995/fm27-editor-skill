"""The tables of the lookup for nations, cities, stadiums, competitions, clubs, and derbies."""

import sqlite3
from collections.abc import Mapping, Sequence

from fm27_editor.dat_tables import read_records
from fm27_editor.name_tables import NamedTable, read_names
from fm27_editor.places import (
    PlacesError,
    Team,
    parse_cities,
    parse_clubs,
    parse_competitions,
    parse_derbies,
    parse_stadiums,
    parse_teams,
    team_clubs,
)

# Nations are table 9, not table 10: the names of lang_db, people, and real changes to nations go by
# its uids, and records refer to a nation by its place there.
NATIONS, CITIES, STADIUMS = "table_9", "table_2", "table_21"
COMPETITIONS, CLUBS, TEAMS, DERBIES = "table_25", "table_3", "table_24", "table_18"
CLIENT_TABLES = {NATIONS, CITIES, STADIUMS, COMPETITIONS, CLUBS, DERBIES}
SERVER_TABLES = {COMPETITIONS, TEAMS}
ENGLISH_NAMES = {
    NamedTable.NATION: "8_9",
    NamedTable.CITY: "8_2",
    NamedTable.STADIUM: "8_21",
    NamedTable.COMPETITION: "8_25",
    NamedTable.CLUB: "8_3",
    NamedTable.DERBY: "8_18",
}
NAME_TABLES = set(ENGLISH_NAMES.values())
SCHEMA = """
CREATE TABLE nation(uid INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE city(uid INTEGER PRIMARY KEY, name TEXT, nation_uid INTEGER);
CREATE TABLE stadium(uid INTEGER PRIMARY KEY, name TEXT, city_uid INTEGER);
CREATE TABLE competition(uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, gender TEXT,
    level INTEGER, nation_uid INTEGER, parent_uid INTEGER);
CREATE TABLE club(uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, gender TEXT,
    is_extinct INTEGER, nation_uid INTEGER, based_nation_uid INTEGER, city_uid INTEGER,
    stadium_uid INTEGER, reputation INTEGER, division_uid INTEGER, last_division_uid INTEGER,
    last_position INTEGER);
CREATE TABLE derby(uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, club_1_uid INTEGER,
    club_2_uid INTEGER);
CREATE INDEX club_division ON club(division_uid);
CREATE INDEX club_nation ON club(nation_uid);
CREATE VIEW clubs AS SELECT club.*, nation.name AS nation, city.name AS city,
    stadium.name AS stadium, competition.name AS division
    FROM club LEFT JOIN nation ON nation.uid = club.nation_uid
    LEFT JOIN city ON city.uid = club.city_uid
    LEFT JOIN stadium ON stadium.uid = club.stadium_uid
    LEFT JOIN competition ON competition.uid = club.division_uid;
CREATE VIEW derbies AS SELECT derby.*, one.name AS club_1, two.name AS club_2
    FROM derby LEFT JOIN club AS one ON one.uid = derby.club_1_uid
    LEFT JOIN club AS two ON two.uid = derby.club_2_uid;
CREATE VIEW nations AS SELECT * FROM nation;
CREATE VIEW cities AS SELECT city.*, nation.name AS nation
    FROM city LEFT JOIN nation ON nation.uid = city.nation_uid;
CREATE VIEW stadiums AS SELECT stadium.*, city.name AS city, city.nation_uid,
    nation.name AS nation
    FROM stadium LEFT JOIN city ON city.uid = stadium.city_uid
    LEFT JOIN nation ON nation.uid = city.nation_uid;
CREATE VIEW competitions AS SELECT competition.*, nation.name AS nation, parent.name AS parent,
    (SELECT count(*) FROM club WHERE club.division_uid = competition.uid) AS clubs
    FROM competition LEFT JOIN nation ON nation.uid = competition.nation_uid
    LEFT JOIN competition AS parent ON parent.uid = competition.parent_uid;
"""

type Tables = Mapping[str, bytes]


def insert_places(
    cache: sqlite3.Connection, client: Tables, server: Tables, name_tables: Tables
) -> None:
    names = {kind: read_names(kind, name_tables[table]) for kind, table in ENGLISH_NAMES.items()}
    nations = [record.uid for record in read_records(client[NATIONS])]
    city_nations, stadium_cities = parse_cities(client[CITIES]), parse_stadiums(client[STADIUMS])
    cities, stadiums = list(city_nations), list(stadium_cities)
    competitions = parse_competitions(client[COMPETITIONS], server[COMPETITIONS])
    divisions = [competition.uid for competition in competitions]
    teams = {team.uid: team for team in parse_teams(server[TEAMS])}

    insert_rows(cache, "nation", [(uid, _name(names[NamedTable.NATION], uid)) for uid in nations])
    insert_rows(
        cache,
        "city",
        [
            (uid, _name(names[NamedTable.CITY], uid), uid_at(nations, nation, "nation"))
            for uid, nation in city_nations.items()
        ],
    )
    insert_rows(
        cache,
        "stadium",
        [
            (uid, _name(names[NamedTable.STADIUM], uid), uid_at(cities, city, "city"))
            for uid, city in stadium_cities.items()
        ],
    )
    insert_rows(
        cache,
        "competition",
        [
            (
                competition.uid,
                *names[NamedTable.COMPETITION].get(competition.uid, (None, None)),
                competition.gender,
                competition.level,
                uid_at(nations, competition.nation, "nation"),
                uid_at(divisions, competition.parent, "competition"),
            )
            for competition in competitions
        ],
    )
    insert_rows(
        cache,
        "club",
        [
            (
                club.uid,
                *names[NamedTable.CLUB].get(club.uid, (None, None)),
                club.gender,
                club.is_extinct,
                uid_at(nations, club.nation, "nation"),
                uid_at(nations, club.based_nation, "nation"),
                uid_at(cities, club.city, "city"),
                *_standing(_team(teams, club.uid), stadiums, divisions),
            )
            for club in parse_clubs(client[CLUBS])
        ],
    )
    # A national team plays some derbies; it is no club, so the derby has none there.
    clubs_of_teams = team_clubs(server[TEAMS])
    insert_rows(
        cache,
        "derby",
        [
            (
                uid,
                *names[NamedTable.DERBY].get(uid, (None, None)),
                *(uid_at(clubs_of_teams, team, "team") for team in teams),
            )
            for uid, teams in parse_derbies(client[DERBIES]).items()
        ],
    )


def _team(teams: Mapping[int, Team], uid: int) -> Team:
    if uid not in teams:
        raise PlacesError(f"club {uid} has no team")
    return teams[uid]


def _standing(
    team: Team, stadiums: Sequence[int], divisions: Sequence[int]
) -> tuple[int | None, ...]:
    return (
        uid_at(stadiums, team.stadium, "stadium"),
        team.reputation or None,
        uid_at(divisions, team.division, "competition"),
        uid_at(divisions, team.last_division, "competition"),
        team.last_position or None,
    )


def insert_rows(cache: sqlite3.Connection, table: str, rows: Sequence[tuple]) -> None:
    if rows:
        placeholders = ", ".join("?" * len(rows[0]))
        cache.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def _name(names: Mapping[int, tuple[str, str | None]], uid: int) -> str | None:
    return names[uid][0] if uid in names else None


def uid_at(uids: Sequence[int | None], index: int | None, kind: str) -> int | None:
    if index is None:
        return None
    if index >= len(uids):
        raise PlacesError(f"there is no {kind} at index {index}")
    return uids[index]
