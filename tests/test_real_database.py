"""Optional check against an installed Editor; nothing from it enters the repository."""

import os
import re
import sqlite3
from pathlib import Path

import pytest

from fm27_editor.base_database import open_database
from fm27_editor.record_kinds import (
    AGREEMENT,
    AWARD,
    CITY,
    CLUB,
    COMPETITION,
    CONTINENT,
    DERBY,
    INJURY,
    KINDS,
    LOCAL_REGION,
    MEDIA_SOURCE,
    NATION,
    NATIONAL_TEAM,
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


@pytest.fixture(scope="module")
def lookup(tmp_path_factory):
    """One lookup for every test: building it takes about 40 seconds and 450 MB."""
    with open_database(Path(EDITOR), tmp_path_factory.mktemp("lookup") / "cache.sqlite") as db:
        yield db


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
    "item",
    "wage",
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
        *(MEDIA_SOURCE, DERBY, STAGE_NAME, LOCAL_REGION, AGREEMENT),
    ):
        writable = {field.code for field in rules.writable_fields(kind)}
        assert {*kind.codes.values(), *kind.needed, *kind.group.name_codes} <= writable


@needs_editor
def test_a_national_team_offers_its_own_fields_but_not_its_nations():
    rules = RecordRules(Path(EDITOR), sqlite3.connect(":memory:"))

    writable = {field.code for field in rules.writable_fields(NATIONAL_TEAM)}

    assert {"Nrep", "Nfpa", "NYRt", "Natt", "Tcap"} <= writable
    assert not {"Nnam", "NTCn", "PLgn", "Nmni", "Snam", "RP00", "NGpe", "EDsd", "Neu1"} & writable


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_national_teams(lookup):
    teams = lookup.execute(
        "SELECT gender, count(*), count(name), count(*) FILTER (WHERE nation_uid NOT IN"
        " (SELECT uid FROM nation)) FROM national_teams GROUP BY gender ORDER BY gender"
    ).fetchall()
    nations = lookup.execute("SELECT count(*), count(name) FROM nations").fetchone()

    assert teams == [("female", 251, 251, 0), ("male", 251, 251, 0)]
    assert nations == (251, 251)


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_people(lookup):
    people, with_nation, with_club = lookup.execute(
        "SELECT count(*), count(nation), count(club) FROM people WHERE kind = 'player'"
    ).fetchone()
    over_twenty = lookup.execute("SELECT count(*) FROM people WHERE finishing > 20").fetchone()[0]
    ability_above_potential = lookup.execute(
        "SELECT count(*) FROM people WHERE kind = 'player' AND pa > 0 AND ca > pa"
    ).fetchone()[0]

    assert people > 400_000
    assert with_nation > people * 0.95
    assert with_club > people * 0.8
    assert (over_twenty, ability_above_potential) == (0, 0)


@needs_editor
def test_the_installed_editor_database_reads_everyone_with_a_name(lookup):
    """Names as the game shows them differ from the full name for many people."""
    kinds = dict(lookup.execute("SELECT kind, count(*) FROM people GROUP BY kind").fetchall())
    unnamed, shortened = lookup.execute(
        "SELECT count(*) - count(NULLIF(name, '')), count(NULLIF(name, full_name)) FROM people"
    ).fetchone()
    coached, wages, contracts, odd_dates = lookup.execute(
        "SELECT count(working_with_youngsters), count(wage), count(contract_expires),"
        " count(*) FILTER (WHERE contract_expires NOT BETWEEN '2000' AND '2045') FROM people"
    ).fetchone()

    assert set(kinds) == {"player", "staff", "both", "official", "retired"}
    assert sum(kinds.values()) > 690_000
    assert unnamed == 0
    assert shortened > 100_000
    assert coached > 10_000
    assert (wages > 20_000, contracts > 100_000, odd_dates) == (True, True, 0)


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_days_at_clubs_and_in_nations(lookup):
    """The Editor allows up to 30,000 days. Many are in women's national teams."""
    known, unknown = lookup.execute(
        "SELECT count(clubs_and_nations), count(*) - count(clubs_and_nations) FROM people"
        " WHERE kind IN ('player', 'staff', 'both')"
    ).fetchone()
    items, unknown_places, too_many = lookup.execute(
        "SELECT count(*), count(*) FILTER (WHERE club_or_nation_uid NOT IN (SELECT uid FROM club)"
        " AND club_or_nation_uid NOT IN (SELECT uid FROM national_team)),"
        " count(*) FILTER (WHERE days > 30000) FROM days_at_club_or_nation"
    ).fetchone()
    counted = lookup.execute("SELECT sum(clubs_and_nations) FROM people").fetchone()[0]
    open_ended = lookup.execute(
        "SELECT count(wage) FROM people WHERE kind = 'staff' AND contract_expires IS NULL"
    ).fetchone()[0]

    assert known > 690_000
    assert unknown < 100
    assert items > 3_000_000
    assert (unknown_places, too_many, counted) == (0, 0, items)
    assert open_ended > 1_000


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_playing_histories(lookup):
    seasons, people, unnamed_clubs, odd_years = lookup.execute(
        "SELECT count(*), count(DISTINCT person_uid),"
        " count(*) FILTER (WHERE club_uid IS NOT NULL AND club IS NULL),"
        " count(*) FILTER (WHERE year NOT BETWEEN 1900 AND 2030) FROM playing_history"
    ).fetchone()
    too_many = lookup.execute(
        "SELECT count(*) FROM playing_history WHERE apps > 200 OR goals > 200"
    ).fetchone()[0]
    loans, youth, tribunals = lookup.execute(
        "SELECT sum(on_loan), sum(youth_team), sum(tribunal_fee) FROM playing_history"
    ).fetchone()

    assert seasons > 4_000_000
    assert people > 400_000
    assert (unnamed_clubs, odd_years, too_many) == (0, 0, 0)
    assert loans > 250_000
    assert youth > 750_000
    assert 0 < tribunals < 1_000


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_relations(lookup):
    """Each relation is with a record of the lookup, and second nations say one of the Editor's
    choices of nationality info. A few favourite people are among those the lookup cannot read."""
    known = lookup.execute(
        "SELECT count(relations) FROM people WHERE kind IN ('player', 'staff', 'both')"
    ).fetchone()[0]
    outside = sum(
        lookup.execute(
            f"SELECT count(*) FROM {table} WHERE {column} NOT IN (SELECT uid FROM {of})"
        ).fetchone()[0]
        for table, column, of in (
            ("second_nation", "nation_uid", "nation"),
            ("trained_in_nation", "nation_uid", "nation"),
            ("trained_at_club", "club_uid", "club"),
            ("favourite_club", "club_uid", "club"),
        )
    )
    unread_favourites = lookup.execute(
        "SELECT count(*) FROM favourite_person WHERE favourite_uid NOT IN (SELECT uid FROM person)"
    ).fetchone()[0]
    second, odd_info = lookup.execute(
        "SELECT count(*), count(*) FILTER (WHERE nationality_info NOT IN"
        " (0, 80, 81, 82, 84, 85, 86, 87, 88, 89, 90)) FROM second_nation"
    ).fetchone()

    assert known > 685_000
    assert second > 80_000
    assert (outside, odd_info) == (0, 0)
    assert unread_favourites < 20


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_awards(lookup):
    awards, named = lookup.execute("SELECT count(*), count(name) FROM awards").fetchone()
    unlike_their_competition = lookup.execute(
        "SELECT count(*) FROM award JOIN competition ON competition.uid = competition_uid"
        " WHERE award.gender <> competition.gender OR award.nation_uid <>"
        " competition.nation_uid"
    ).fetchone()[0]
    unknown_choice = lookup.execute(
        "SELECT count(*) FROM awards WHERE previous_winner NOT IN (1, 2, 3)"
    ).fetchone()[0]
    years, outside = lookup.execute(
        "SELECT count(*), sum(year NOT BETWEEN 1800 AND 2100) FROM award_year"
    ).fetchone()
    places, with_team = lookup.execute("SELECT count(*), count(team) FROM award_history").fetchone()
    ordered, scored = lookup.execute(
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
def test_the_installed_editor_database_reads_as_plausible_clubs(lookup):
    clubs, named, with_nation = lookup.execute(
        "SELECT count(*), count(name), count(nation) FROM clubs"
    ).fetchone()
    unnamed_nations = lookup.execute(
        "SELECT (SELECT count(*) FROM clubs WHERE nation_uid IS NOT NULL AND nation IS NULL)"
        " + (SELECT count(*) FROM people WHERE nation_uid IS NOT NULL AND nation IS NULL)"
    ).fetchone()[0]
    mixed = lookup.execute(
        "SELECT count(*) FROM (SELECT 1 FROM club WHERE division_uid IS NOT NULL"
        " GROUP BY division_uid HAVING count(DISTINCT gender) > 1)"
    ).fetchone()[0]
    unlike_their_division = lookup.execute(
        "SELECT count(*) FROM club JOIN competition ON competition.uid = division_uid"
        " WHERE club.gender <> competition.gender"
    ).fetchone()[0]
    extinct_in_a_division = lookup.execute(
        "SELECT count(*) FROM club WHERE is_extinct AND division_uid IS NOT NULL"
    ).fetchone()[0]
    unlikely = lookup.execute(
        "SELECT count(*) FROM club WHERE reputation > 10000 OR last_position > 100"
    ).fetchone()[0]
    competitions = lookup.execute("SELECT count(*), count(name) FROM competitions").fetchone()

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
def test_the_installed_editor_database_reads_as_plausible_names(lookup, table, at_least):
    records, named, different, printable = lookup.execute(
        f"SELECT count(*), count(name), count(DISTINCT name),"
        f" sum(name GLOB '*[A-Za-z]*') FROM {table}"
    ).fetchone()

    # A few media sources and stages share a name.
    assert records >= at_least
    assert records == named == printable
    assert different > records * 0.95


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_local_regions_and_agreements(lookup):
    regions, named, in_a_nation, populated, crowded = lookup.execute(
        "SELECT count(*), count(name), count(nation), count(population),"
        " count(*) FILTER (WHERE population > 100000000) FROM local_regions"
    ).fetchone()
    agreements, short_names = lookup.execute(
        "SELECT count(name), count(NULLIF(short_name, '')) FROM agreements"
    ).fetchone()

    assert regions > 2_000
    assert regions == named == in_a_nation
    assert (populated > 1_000, crowded) == (True, 0)
    assert agreements >= 6 and short_names >= 5


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_currencies(lookup):
    records, named, different, with_rate, lowest, pounds = lookup.execute(
        "SELECT count(*), count(name), count(DISTINCT name), count(per_pound),"
        " min(per_pound), sum(per_pound = 1) FROM currency"
    ).fetchone()

    assert records >= 100
    assert records == named == different == with_rate
    assert lowest > 0 and pounds >= 1


@needs_editor
def test_the_installed_editor_database_reads_as_plausible_derbies(lookup):
    derbies, named, with_clubs = lookup.execute(
        "SELECT count(*), count(name), count(club_1_uid + club_2_uid) FROM derbies"
    ).fetchone()
    one_club, mixed, across_borders = lookup.execute(
        "SELECT sum(one.uid = two.uid), sum(one.gender <> two.gender),"
        " sum(one.nation_uid <> two.nation_uid) FROM derby"
        " JOIN club AS one ON one.uid = club_1_uid JOIN club AS two ON two.uid = club_2_uid"
    ).fetchone()

    assert derbies > 1_000 and named == derbies
    assert with_clubs > derbies * 0.95
    assert (one_club, mixed) == (0, 0)
    assert across_borders < with_clubs * 0.05
