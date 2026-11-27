import sqlite3
from contextlib import closing

import pytest

from fm27_editor import award_lookup, name_lookup, place_lookup
from fm27_editor.change_reading import EditError
from fm27_editor.person_fields import (
    ATTRIBUTES,
    PERSONALITY,
    POSITIONS,
    STAFF_ATTRIBUTES,
)
from fm27_editor.record_kinds import (
    AWARD,
    CITY,
    CLUB,
    COMPETITION,
    CONTINENT,
    DERBY,
    INJURY,
    MEDIA_SOURCE,
    NATION,
    PLAYER,
    STADIUM,
    STAFF,
    STAGE_NAME,
    WEATHER,
    kind_named,
)

WITHOUT_A_CODE = {"name", "position_sw"}
FACTS_OF_ANYONE = {"name", "full_name", "birth_date", "nation_uid", "club_uid", "ca", "pa"}


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        (PLAYER, {*ATTRIBUTES, *POSITIONS, *PERSONALITY}),
        (STAFF, {*STAFF_ATTRIBUTES, *PERSONALITY}),
    ],
    ids=["player", "staff"],
)
def test_every_fact_the_lookup_has_for_people_has_a_code_or_a_reason_not_to(kind, fields):
    assert set(kind.codes) == (FACTS_OF_ANYONE | fields) - WITHOUT_A_CODE


@pytest.mark.parametrize(
    ("kind", "table", "without_a_code"),
    [
        (CLUB, "club", {"uid"}),
        (COMPETITION, "competition", {"uid"}),
        (AWARD, "award", {"uid", "gender"}),  # the Editor's definitions have no gender of an award
        (STADIUM, "stadium", {"uid"}),
        (NATION, "nation", {"uid"}),
        (CITY, "city", {"uid"}),
        (CONTINENT, "continent", {"uid"}),
        (INJURY, "injury", {"uid"}),
        (WEATHER, "weather", {"uid"}),
        (MEDIA_SOURCE, "media_source", {"uid"}),
        (DERBY, "derby", {"uid"}),
        (STAGE_NAME, "stage_name", {"uid"}),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_every_fact_the_lookup_has_for_other_records_has_a_code(kind, table, without_a_code):
    with closing(sqlite3.connect(":memory:")) as lookup:
        lookup.executescript(place_lookup.SCHEMA + award_lookup.SCHEMA + name_lookup.SCHEMA)
        columns = {row[1] for row in lookup.execute(f"PRAGMA table_info({table})")}

    assert set(kind.codes) == columns - without_a_code


@pytest.mark.parametrize(
    "kind",
    [
        *(PLAYER, CLUB, COMPETITION, AWARD, STADIUM, NATION, CITY, CONTINENT, INJURY, WEATHER),
        *(MEDIA_SOURCE, DERBY, STAGE_NAME),
    ],
    ids=lambda kind: kind.name,
)
def test_no_two_facts_share_a_code(kind):
    assert len(kind.names) == len(kind.codes)


@pytest.mark.parametrize("name", ["both", "official", "retired"])
def test_kinds_of_people_not_seen_created_are_refused(name):
    with pytest.raises(EditError, match=f"player, staff.* not {name}"):
        kind_named(name)
