import datetime
import sqlite3

import pytest

from fictional_editor import write_database
from fm27_editor import base_database
from fm27_editor.base_database import DatabaseError, open_database


@pytest.fixture
def editor(tmp_path):
    return write_database(tmp_path / "editor")


def test_lookup_joins_people_with_nation_and_club(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT name, nation, club, ca, pa, birth_date, finishing FROM people ORDER BY uid"
        ).fetchall()

    assert rows == [
        ("Alfa Striker", "Norwegia", "Fictional City", 120, 140, "2004-02-29", 15),
        ("Bravo Keeper", "Englandia", "Example United", 60, 80, "2008-02-29", 15),
    ]


def test_age_can_be_queried_from_the_birth_date(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        cutoff = datetime.date(2026, 11, 25).replace(year=2005).isoformat()
        young = db.execute("SELECT name FROM people WHERE birth_date >= ?", (cutoff,)).fetchall()

    assert young == [("Bravo Keeper",)]


def test_cache_is_reused_until_the_editor_files_change(editor, tmp_path):
    cache = tmp_path / "cache.sqlite"
    open_database(editor, cache).close()
    built = cache.stat().st_mtime_ns

    open_database(editor, cache).close()
    assert cache.stat().st_mtime_ns == built

    write_database(editor, [(0, 100, "Charlie Changed", 2004, 100, (41, 9001), (0, 9101))])

    with open_database(editor, cache) as db:
        assert db.execute("SELECT name FROM people").fetchall() == [("Charlie Changed",)]


def test_the_database_is_opened_read_only(editor, tmp_path):
    with (
        open_database(editor, tmp_path / "cache.sqlite") as db,
        pytest.raises(sqlite3.OperationalError),
    ):
        db.execute("DELETE FROM person")


def test_no_other_database_can_be_attached(editor, tmp_path):
    with (
        open_database(editor, tmp_path / "cache.sqlite") as db,
        pytest.raises(sqlite3.OperationalError, match="attached"),
    ):
        db.execute("ATTACH ? AS other", (str(tmp_path / "other.sqlite"),))


def test_an_interrupted_build_leaves_no_usable_cache(editor, tmp_path, monkeypatch):
    cache = tmp_path / "cache.sqlite"

    def explode(*_):
        raise RuntimeError("stopped")

    monkeypatch.setattr(base_database, "iter_people", explode)
    with pytest.raises(RuntimeError):
        open_database(editor, cache)

    assert not cache.exists()


def test_a_missing_editor_folder_is_reported(tmp_path):
    with pytest.raises(DatabaseError, match="database"):
        open_database(tmp_path / "nowhere", tmp_path / "cache.sqlite")


def test_unmatched_clubs_and_nations_are_kept_with_an_empty_name(tmp_path):
    editor = write_database(
        tmp_path / "editor", [(0, 100, "Solo", 2004, 100, (1, 999), (1, 12345))]
    )

    with open_database(editor, tmp_path / "cache.sqlite") as db:
        assert db.execute("SELECT name, nation, club FROM people").fetchall() == [
            ("Solo", None, None)
        ]


def test_a_changed_library_rebuilds_the_cache(editor, tmp_path, monkeypatch):
    cache = tmp_path / "cache.sqlite"
    open_database(editor, cache).close()
    monkeypatch.setattr(base_database, "_code_fingerprint", lambda: "other code")

    with open_database(editor, cache) as db:
        (fingerprint,) = db.execute("SELECT fingerprint FROM meta").fetchone()

    assert fingerprint.startswith("other code")


def test_a_file_that_is_not_a_cache_is_not_replaced(editor, tmp_path):
    cache = tmp_path / "cache.sqlite"
    cache.write_text("my notes")

    with pytest.raises(DatabaseError, match="not a lookup cache"):
        open_database(editor, cache)

    assert cache.read_text() == "my notes"


def test_the_newest_database_is_used_when_the_editor_has_several(tmp_path):
    editor = write_database(tmp_path / "editor")
    newer = write_database(
        tmp_path / "newer", [(0, 100, "Newer Person", 2004, 100, (1, 9001), (1, 9101))]
    )
    source = newer / "shared/data/database/db/2700"
    source.rename(editor / "shared/data/database/db/2710")
    (editor / "shared/data/database/db/2710/2700_fm").rename(
        editor / "shared/data/database/db/2710/2710_fm"
    )

    with open_database(editor, tmp_path / "cache.sqlite") as db:
        assert db.execute("SELECT name FROM people").fetchall() == [("Newer Person",)]
