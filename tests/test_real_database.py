"""Optional check against an installed Editor; nothing from it enters the repository."""

import os
import re
from pathlib import Path

import pytest

from fm27_editor.base_database import open_database
from fm27_editor.new_person import person_definitions
from fm27_editor.people import PersonKind
from fm27_editor.person_codes import person_codes

EDITOR = os.environ.get("FM27_EDITOR_DIR", "")
needs_editor = pytest.mark.skipif(
    not EDITOR, reason="set FM27_EDITOR_DIR to the Editor's install folder"
)
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
}


@needs_editor
@pytest.mark.parametrize("kind", [PersonKind.PLAYER, PersonKind.STAFF])
def test_every_code_names_the_same_fact_in_the_installed_editor(kind):
    fields = person_definitions(Path(EDITOR), kind)

    for name, code in person_codes(kind).items():
        worded = re.sub("[^a-z]+", "_", fields[code].name.lower()).strip("_")
        assert worded == EDITOR_NAMES.get(name, name)
        assert fields[code].is_editable


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
