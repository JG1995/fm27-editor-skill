"""Optional check against an installed Editor; nothing from it enters the repository."""

import os
import re
import sqlite3
from pathlib import Path

import pytest

from fm27_editor.base_database import open_database
from fm27_editor.record_kinds import (
    AWARD,
    CITY,
    CLUB,
    COMPETITION,
    CONTINENT,
    DERBY,
    INJURY,
    KINDS,
    MEDIA_SOURCE,
    NATION,
    PLAYER,
    STADIUM,
    STAFF,
    STAGE_NAME,
    WEATHER,
)
from fm27_editor.record_rules import RecordRules
from fm27_editor.rule_definitions import RuleDefinitions
from fm27_editor.rule_words import RULES_OF, offered_lines

EDITOR = os.environ.get("FM27_EDITOR_DIR", "")
needs_editor = pytest.mark.skipif(
    not EDITOR, reason="set FM27_EDITOR_DIR to the Editor's install folder"
)
# Parts of a request and columns, not codes of fields.
WORDS_OF_FOUR_LETTERS = {
    "find",
    "name",
    "city",
    "both",
    "kind",
    "club",
    "NULL",
    "LIKE",
    "KIND",
    "male",
    "type",
    "date",
    "keep",
    "team",
    "year",
}
# Where the Editor words a name differently from the game's own screens.
EDITOR_NAMES = {
    "birth_date": "date_of_birth",
    "nation_uid": "nation",
    "club_uid": "club",
    "ca": "current_ability",
    "pa": "potential_ability",
    "off_the_ball": "movement",
    "teamwork": "team_work",
    "aerial_reach": "aerial_ability",
    "punching": "tendency_to_punch",
    "rushing_out": "rushing_out_tendency",
    "position_gk": "goalkeeper",
    "position_dl": "defender_left",
    "position_dc": "defender_central",
    "position_dr": "defender_right",
    "position_dm": "defensive_midfielder",
    "position_ml": "midfielder_left",
    "position_mc": "midfielder_central",
    "position_mr": "midfielder_right",
    "position_aml": "attacking_midfielder_left",
    "position_amc": "attacking_midfielder_central",
    "position_amr": "attacking_midfielder_right",
    "position_st": "striker",
    "position_wbl": "wing_back_left",
    "position_wbr": "wing_back_right",
    "coaching_goalkeeping": "coaching_goakeeping",
}


@needs_editor
@pytest.mark.parametrize("kind", [PLAYER, STAFF])
def test_every_code_names_the_same_fact_in_the_installed_editor(kind):
    fields = RecordRules(Path(EDITOR), sqlite3.connect(":memory:")).fields(kind)

    for name, code in kind.codes.items():
        worded = re.sub("[^a-z]+", "_", fields[code].name.lower()).strip("_")
        assert worded == EDITOR_NAMES.get(name, name)
        assert fields[code].is_editable


@needs_editor
def test_the_codes_that_the_instructions_name_can_be_written():
    text = (Path(__file__).parents[1] / "skill" / "SKILL.md").read_text(encoding="utf-8")
    named = set(re.findall(r"[`\"]([A-Za-z]{4})(?:`|\":)", text)) - WORDS_OF_FOUR_LETTERS
    rules = RecordRules(Path(EDITOR), sqlite3.connect(":memory:"))
    fields = [field for kind in KINDS.values() for field in rules.writable_fields(kind)]
    parts = {part.code for field in fields for part in field.items}

    assert len(named) > 10
    assert named <= {field.code for field in fields} | parts


@needs_editor
def test_the_installed_editor_defines_every_part_of_the_lists_offered():
    rules = RecordRules(Path(EDITOR), sqlite3.connect(":memory:"))
    defined = rules.fields(PLAYER) | rules.fields(STAFF)

    for code, shape in PLAYER.lists.items():
        assert set(shape.parts) <= {part.code for part in defined[code].items}, code


@needs_editor
def test_the_installed_editor_names_the_jobs_of_staff():
    rules = RecordRules(Path(EDITOR), sqlite3.connect(":memory:"))
    jobs = {code: rules.fields(STAFF)[code].choices for code in ("PCJO", "PSJO")}

    assert all(len(choices or {}) > 20 for choices in jobs.values()), jobs


@needs_editor
def test_the_installed_editor_defines_every_rule_that_is_offered():
    definitions = RuleDefinitions(Path(EDITOR))

    for name in RULES_OF:
        lines = offered_lines(name, definitions)
        assert lines and not [line for line in lines if "one of ," in line or "None" in line]


@needs_editor
def test_every_code_of_a_place_or_award_names_a_field_that_can_be_written():
    rules = RecordRules(Path(EDITOR), sqlite3.connect(":memory:"))

    for kind in (
        *(CLUB, COMPETITION, AWARD, STADIUM, NATION, CITY, CONTINENT, INJURY, WEATHER),
        *(MEDIA_SOURCE, DERBY, STAGE_NAME),
    ):
        writable = {field.code for field in rules.writable_fields(kind)}
        assert {*kind.codes.values(), *kind.needed, *kind.group.name_codes} <= writable


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_people(tmp_path):
    with open_database(Path(EDITOR), tmp_path / "cache.sqlite") as db:
        people, with_nation, with_club = db.execute(
            "SELECT count(*), count(nation), count(club) FROM people WHERE kind = 'player'"
        ).fetchone()
        over_twenty = db.execute("SELECT count(*) FROM people WHERE finishing > 20").fetchone()[0]
        ability_above_potential = db.execute(
            "SELECT count(*) FROM people WHERE kind = 'player' AND pa > 0 AND ca > pa"
        ).fetchone()[0]

    assert people > 400_000
    assert with_nation > people * 0.95
    assert with_club > people * 0.8
    assert (over_twenty, ability_above_potential) == (0, 0)


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_awards(tmp_path):
    with open_database(Path(EDITOR), tmp_path / "cache.sqlite") as db:
        awards, named = db.execute("SELECT count(*), count(name) FROM awards").fetchone()
        unlike_their_competition = db.execute(
            "SELECT count(*) FROM award JOIN competition ON competition.uid = competition_uid"
            " WHERE award.gender <> competition.gender OR award.nation_uid <>"
            " competition.nation_uid"
        ).fetchone()[0]
        unknown_choice = db.execute(
            "SELECT count(*) FROM awards WHERE previous_winner NOT IN (1, 2, 3)"
        ).fetchone()[0]
        years, outside = db.execute(
            "SELECT count(*), sum(year NOT BETWEEN 1800 AND 2100) FROM award_year"
        ).fetchone()
        places, with_team = db.execute("SELECT count(*), count(team) FROM award_history").fetchone()
        ordered, scored = db.execute(
            "SELECT sum(first.points >= second.points), count(*) FROM award_place AS first"
            " JOIN award_place AS second USING (year_uid)"
            " WHERE first.place = 1 AND second.place = 2"
            " AND first.points IS NOT NULL AND second.points IS NOT NULL"
        ).fetchone()

    assert awards > 3_000 and named == awards
    assert (unlike_their_competition, unknown_choice, outside) == (0, 0, 0)
    assert years > 30_000
    assert with_team > places * 0.9
    assert ordered > scored * 0.95


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_clubs(tmp_path):
    with open_database(Path(EDITOR), tmp_path / "cache.sqlite") as db:
        clubs, named, with_nation = db.execute(
            "SELECT count(*), count(name), count(nation) FROM clubs"
        ).fetchone()
        unnamed_nations = db.execute(
            "SELECT (SELECT count(*) FROM clubs WHERE nation_uid IS NOT NULL AND nation IS NULL)"
            " + (SELECT count(*) FROM people WHERE nation_uid IS NOT NULL AND nation IS NULL)"
        ).fetchone()[0]
        mixed = db.execute(
            "SELECT count(*) FROM (SELECT 1 FROM club WHERE division_uid IS NOT NULL"
            " GROUP BY division_uid HAVING count(DISTINCT gender) > 1)"
        ).fetchone()[0]
        unlike_their_division = db.execute(
            "SELECT count(*) FROM club JOIN competition ON competition.uid = division_uid"
            " WHERE club.gender <> competition.gender"
        ).fetchone()[0]
        extinct_in_a_division = db.execute(
            "SELECT count(*) FROM club WHERE is_extinct AND division_uid IS NOT NULL"
        ).fetchone()[0]
        unlikely = db.execute(
            "SELECT count(*) FROM club WHERE reputation > 10000 OR last_position > 100"
        ).fetchone()[0]
        competitions = db.execute("SELECT count(*), count(name) FROM competitions").fetchone()

    assert clubs > 90_000
    assert clubs == named
    assert unnamed_nations == 0
    assert with_nation > clubs * 0.95
    assert (mixed, unlike_their_division, extinct_in_a_division, unlikely) == (0, 0, 0, 0)
    assert competitions[0] > 8_000
    assert competitions[0] == competitions[1]


@needs_editor
@pytest.mark.parametrize(
    ("table", "at_least"),
    [
        *(("language", 100), ("continent", 7), ("injury", 100), ("weather", 300)),
        *(("media_source", 100), ("stage_name", 200)),
    ],
)
def test_the_installed_editor_database_reads_as_plausible_names(tmp_path, table, at_least):
    with open_database(Path(EDITOR), tmp_path / "cache.sqlite") as db:
        records, named, different, printable = db.execute(
            f"SELECT count(*), count(name), count(DISTINCT name),"
            f" sum(name GLOB '*[A-Za-z]*') FROM {table}"
        ).fetchone()

    # A few media sources and stages share a name.
    assert records >= at_least
    assert records == named == printable
    assert different > records * 0.95


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_currencies(tmp_path):
    with open_database(Path(EDITOR), tmp_path / "cache.sqlite") as db:
        records, named, different, with_rate, lowest, pounds = db.execute(
            "SELECT count(*), count(name), count(DISTINCT name), count(per_pound),"
            " min(per_pound), sum(per_pound = 1) FROM currency"
        ).fetchone()

    assert records >= 100
    assert records == named == different == with_rate
    assert lowest > 0 and pounds >= 1


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_derbies(tmp_path):
    with open_database(Path(EDITOR), tmp_path / "cache.sqlite") as db:
        derbies, named, with_clubs = db.execute(
            "SELECT count(*), count(name), count(club_1_uid + club_2_uid) FROM derbies"
        ).fetchone()
        one_club, mixed, across_borders = db.execute(
            "SELECT sum(one.uid = two.uid), sum(one.gender <> two.gender),"
            " sum(one.nation_uid <> two.nation_uid) FROM derby"
            " JOIN club AS one ON one.uid = club_1_uid JOIN club AS two ON two.uid = club_2_uid"
        ).fetchone()

    assert derbies > 1_000 and named == derbies
    assert with_clubs > derbies * 0.95
    assert (one_club, mixed) == (0, 0)
    assert across_borders < with_clubs * 0.05
