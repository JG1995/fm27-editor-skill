"""Optional check against an installed Editor; nothing from it enters the repository."""

import os
from pathlib import Path

import pytest

from fm27_editor.base_database import open_database

EDITOR = os.environ.get("FM27_EDITOR_DIR", "")


@pytest.mark.skipif(not EDITOR, reason="set FM27_EDITOR_DIR to the Editor's install folder")
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
