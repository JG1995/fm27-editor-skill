import sqlite3
from contextlib import closing

import pytest

from fm27_editor.change_reading import EditError
from fm27_editor.person_fields import FIELD_NAMES
from fm27_editor.place_lookup import SCHEMA
from fm27_editor.record_kinds import CLUB, COMPETITION, PLAYER, kind_named

WITHOUT_A_CODE = {"name", "position_sw"}


def test_every_fact_the_lookup_has_for_players_has_a_code_or_a_reason_not_to():
    facts = {"name", "full_name", "birth_date", "nation_uid", "club_uid", "ca", "pa", *FIELD_NAMES}

    assert set(PLAYER.codes) == facts - WITHOUT_A_CODE


@pytest.mark.parametrize(
    ("kind", "table"), [(CLUB, "club"), (COMPETITION, "competition")], ids=lambda v: str(v)
)
def test_every_fact_the_lookup_has_for_clubs_and_competitions_has_a_code(kind, table):
    with closing(sqlite3.connect(":memory:")) as lookup:
        lookup.executescript(SCHEMA)
        columns = {row[1] for row in lookup.execute(f"PRAGMA table_info({table})")}

    assert set(kind.codes) == columns - {"uid"}


@pytest.mark.parametrize("kind", [PLAYER, CLUB, COMPETITION], ids=lambda kind: kind.name)
def test_no_two_facts_share_a_code(kind):
    assert len(kind.names) == len(kind.codes)


@pytest.mark.parametrize("name", ["both", "official", "retired"])
def test_kinds_of_people_not_seen_created_are_refused(name):
    with pytest.raises(EditError, match=f"player, staff.* not {name}"):
        kind_named(name)
