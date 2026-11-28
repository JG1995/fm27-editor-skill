import datetime
import sqlite3

import pytest

import fictional_editor
import synthetic
from fictional_editor import write_database
from fm27_editor import base_database
from fm27_editor.base_database import DatabaseError, open_database
from fm27_editor.named_records import NamedRecordError
from fm27_editor.people import DAYS_BOXES
from fm27_editor.places import PlacesError


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


def test_days_at_clubs_and_in_nations_are_found_with_their_names(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT name, item, club_or_nation, club_or_nation_uid, days"
            " FROM days_at_club_or_nation ORDER BY person_uid, item"
        ).fetchall()

    assert rows == [
        ("Alfa Striker", 0, "Fictional City", 9101, 400),
        ("Alfa Striker", 1, "Norwegia", 9002, 6000),
    ]


def test_people_say_how_many_clubs_and_nations_they_have_days_at_if_that_is_known(tmp_path):
    someone = (2, 102, "Charlie Unread", 2000, 50, (41, 9001), (0, 9102))
    editor = fictional_editor.write_editor(tmp_path / "editor", [*fictional_editor.PEOPLE, someone])

    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute("SELECT uid, clubs_and_nations FROM people ORDER BY uid").fetchall()

    assert rows == [(100, 2), (101, 0), (102, None)]


def test_playing_history_is_found_with_the_names_of_people_clubs_and_divisions(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT name, item, year, order_in_year, club, division, apps, goals, transfer_fee,"
            " other, date_joined, date_left FROM playing_history ORDER BY person_uid, item"
        ).fetchall()

    assert rows == [
        (
            "Alfa Striker",
            0,
            2021,
            0,
            "Example United",
            "Example League North",
            30,
            12,
            None,
            None,
            "2021-07-01",
            None,
        ),
        (
            "Alfa Striker",
            1,
            2022,
            1,
            "Example United",
            "Example League North",
            12,
            4,
            2_500_000,
            None,
            None,
            "2023-01-31",
        ),
        (
            "Alfa Striker",
            2,
            2022,
            2,
            "Fictional City",
            "Example League",
            None,
            None,
            None,
            -2,
            None,
            None,
        ),
    ]


def test_seasons_say_which_of_the_editors_boxes_and_extras_they_have(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT item, on_loan, youth_team, tribunal_fee, extras FROM playing_history"
            " ORDER BY person_uid, item"
        ).fetchall()

    assert rows == [(0, 0, 0, 0, None), (1, 0, 0, 0, None), (2, 1, 0, 0, 12)]


def test_days_at_clubs_say_which_of_the_editors_boxes_are_ticked(editor, tmp_path):
    boxes = ", ".join(DAYS_BOXES)
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            f"SELECT item, {boxes} FROM days_at_club_or_nation ORDER BY person_uid, item"
        ).fetchall()

    assert rows == [(0, 0, 0, 0, 0, 0, 0), (1, 0, 0, 0, 1, 0, 0)]


def test_a_history_file_that_changes_rebuilds_the_lookup(editor, tmp_path):
    cache = tmp_path / "cache.sqlite"
    with open_database(editor, cache) as db:
        before = db.execute("SELECT count(*) FROM playing_history").fetchone()
    history = next(editor.glob("shared/data/database/db/*/*_fm")) / "pl_hist_dt.dat"
    index, offsets, seasons = synthetic.playing_histories(
        {100: [synthetic.history_item(2025, 9101)]}
    )
    history.write_bytes(synthetic.seekable_file(seasons, kind=3))
    (history.parent / "pl_hist_id.dat").write_bytes(synthetic.seekable_file(offsets, kind=1))
    (history.parent / "pl_hist_index.dat").write_bytes(synthetic.dat_file(index))
    with open_database(editor, cache) as db:
        after = db.execute("SELECT count(*) FROM playing_history").fetchone()

    assert (before, after) == ((3,), (1,))


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

    monkeypatch.setattr(base_database, "insert_people", explode)
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


def test_clubs_have_their_place_and_standing(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, short_name, gender, is_extinct, reputation, last_position, nation,"
            " nation_uid, based_nation_uid, city, stadium, division, division_uid,"
            " last_division_uid FROM clubs ORDER BY uid"
        ).fetchall()

    assert rows == [
        (9101, "Fictional City", "Fic City", "male", 0, 5_000, 1, "Englandia", 9001, 9002)
        + ("Testby", "Test Park", "Example League", 9201, 9203),
        (9102, "Example United", "Example", "male", 0, None, None, "Englandia", 9001, None)
        + (None, None, "Example League North", 9203, None),
        (9103, "Fictional City", "Fic Women", "female", 0, None, None, "Englandia", 9001, None)
        + (None, None, "Example Women's League", 9202, None),
        (9104, "Gone Town", "Gone", "male", 1, None, None, "Norwegia", 9002, None)
        + (None, None, None, None, None),
    ]


def test_competitions_say_where_they_belong_and_how_many_clubs_they_have(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, gender, level, nation, parent, parent_uid, clubs"
            " FROM competitions ORDER BY uid"
        ).fetchall()

    assert rows == [
        (9201, "Example League", "male", 1, "Englandia", None, None, 1),
        (9202, "Example Women's League", "female", 1, "Englandia", None, None, 1),
        (9203, "Example League North", "male", 2, "Englandia", "Example League", 9201, 1),
        (9204, "Example Cup", "male", None, "Englandia", None, None, 0),
    ]


def test_cities_and_stadiums_can_be_found(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        cities = db.execute("SELECT uid, name, nation_uid FROM city ORDER BY uid").fetchall()
        stadiums = db.execute("SELECT uid, name, city_uid FROM stadium").fetchall()

    assert cities == [(9301, "Testby", 9001), (9302, "Testham", 9002)]
    assert stadiums == [(9401, "Test Park", 9301)]


def test_nations_can_be_found(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute("SELECT uid, name FROM nations ORDER BY uid").fetchall()

    assert rows == [(9001, "Englandia"), (9002, "Norwegia")]


def test_stadiums_say_where_they_are(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute("SELECT uid, name, city, nation_uid, nation FROM stadiums").fetchall()

    assert rows == [(9401, "Test Park", "Testby", 9001, "Englandia")]


def test_cities_say_where_they_are(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, nation_uid, nation FROM cities ORDER BY uid"
        ).fetchall()

    assert rows == [(9301, "Testby", 9001, "Englandia"), (9302, "Testham", 9002, "Norwegia")]


def test_derbies_say_which_clubs_play_them(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, short_name, club_1_uid, club_1, club_2_uid, club_2 FROM derbies"
            " ORDER BY uid"
        ).fetchall()

    assert rows == [
        (50, "Fictional Derby", "Derby", 9101, "Fictional City", 9102, "Example United"),
        (51, "Testian Clásico", "Clásico", None, None, None, None),
        (52, "Lonely Derby", "Lonely", 9102, "Example United", None, None),
    ]


def test_a_derby_of_a_team_outside_its_table_is_an_error(editor, tmp_path, monkeypatch):
    monkeypatch.setattr(fictional_editor, "DERBIES", {50: ("Fictional Derby", "Derby", (0, 9))})
    write_database(editor)

    with pytest.raises(PlacesError, match="team"):
        open_database(editor, tmp_path / "cache.sqlite")


def test_languages_can_be_found(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        languages = db.execute("SELECT uid, name FROM language ORDER BY uid").fetchall()

    assert languages == [(8, "Englandish"), (22, "Norwegish")]


@pytest.mark.parametrize(
    ("view", "found"),
    [
        ("continents", [(1, "Testica"), (3, "Europia")]),
        ("injuries", [(1, "cold"), (6, "twisted ankle")]),
        ("weathers", [(1, "Testish Coastal"), (115052, "Testish Inland")]),
        ("media_sources", [(18, "Testby Echo"), (19, "The Example Times")]),
        ("stage_names", [(1, "Replay"), (3, "Final")]),
    ],
)
def test_kinds_known_only_by_name_can_be_found(editor, tmp_path, view, found):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(f"SELECT uid, name FROM {view} ORDER BY uid").fetchall()

    assert rows == found


def test_local_regions_say_where_they_are_and_how_many_live_there(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, nation_uid, nation, population FROM local_regions ORDER BY uid"
        ).fetchall()

    assert rows == [
        (9601, "Testshire", 9001, "Englandia", 2_500_000),
        (9602, "Empty Moor", 9002, "Norwegia", None),
    ]


def test_agreements_between_nations_can_be_found_by_name(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute("SELECT uid, name, short_name FROM agreements ORDER BY uid").fetchall()

    assert rows == [(1, "Example Union", "EU"), (4, "Territories Act", "")]


def test_currencies_say_how_many_of_them_make_a_pound(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, short_name, symbol, per_pound FROM currency ORDER BY uid"
        ).fetchall()

    assert rows == [
        (7, "Testish Pound", "Pound", "£", 1.0),
        (12, "Exampleland Crown", "Crown", None, 2.5),
        (13, "Old Testmark", "Mark", "M", None),
    ]


POUND = ("Testish Pound", "Pound", "£", 1.0)


@pytest.mark.parametrize(
    ("table", "broken", "complaint"),
    [
        ("table_8", synthetic.language_record("Englandish", tail=18), "language 8"),
        ("table_27", synthetic.weather_record("Testish Coastal", tail=96), "weather 8"),
        ("table_41", synthetic.currency_record(*POUND) + b"\x00", "currency 8"),
        ("table_41", synthetic.currency_record(*POUND, year_mark=2), "currency 8"),
    ],
    ids=["language", "weather", "currency followed by a byte", "currency with another year mark"],
)
def test_a_record_that_names_itself_in_another_layout_is_an_error(
    editor, tmp_path, monkeypatch, table, broken, complaint
):
    others = [found for found in fictional_editor.client_tables() if found[0] != table]
    broken_table = synthetic.record_table([(8, broken)])
    monkeypatch.setattr(fictional_editor, "client_tables", lambda: [*others, (table, broken_table)])
    write_database(editor)

    with pytest.raises(NamedRecordError, match=complaint):
        open_database(editor, tmp_path / "cache.sqlite")


def test_people_show_the_division_and_gender_of_their_club(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT name, division, division_uid, club_gender FROM people ORDER BY uid"
        ).fetchall()

    assert rows == [
        ("Alfa Striker", "Example League", 9201, "male"),
        ("Bravo Keeper", "Example League North", 9203, "male"),
    ]


def test_awards_say_where_they_belong_and_how_far_their_history_goes(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT uid, name, short_name, gender, nation, nation_uid, competition,"
            " competition_uid, previous_winner, years FROM awards ORDER BY uid"
        ).fetchall()

    assert rows == [
        (9501, "Example Player of the Year", "Player", "male", "Englandia", 9001)
        + ("Example League", 9201, 3, 3),
        (9502, "Example Women's Player", "Women", "female", None, None, None, None, None, 1),
    ]


def test_the_history_of_an_award_has_a_row_for_each_place(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT year, place, person_uid, name, team, team_uid, points, age, nation, nation_uid"
            " FROM award_history WHERE award_uid = 9501 ORDER BY year, place"
        ).fetchall()

    assert rows == [
        (2020, None, None, None, None, None, None, None, None, None),
        (2023, 1, None, "Old Master", "Example United", 9102, 30, None, "Englandia", 9001),
        (2024, 1, 100, "Alfa Striker", "Fictional City", 9101, 47, 20, "Norwegia", 9002),
        (2024, 2, None, "Old Master", "Example United", 9102, 22, None, "Englandia", 9001),
        (2024, 3, None, "Cup Hero", "Englandia", 9001, 9, 33, "Englandia", 9001),
    ]


def test_the_history_of_an_award_says_which_years_it_was_not_held(editor, tmp_path):
    with open_database(editor, tmp_path / "cache.sqlite") as db:
        rows = db.execute(
            "SELECT DISTINCT award, year, not_held, no_data FROM award_history ORDER BY award, year"
        ).fetchall()

    assert rows == [
        ("Example Player of the Year", 2020, 1, 0),
        ("Example Player of the Year", 2023, 0, 0),
        ("Example Player of the Year", 2024, 0, 0),
        ("Example Women's Player", 2024, 0, 0),
    ]


@pytest.mark.parametrize(
    ("place", "what"),
    [
        ((7, "Nobody", 9101, 1, 0, 0, 0, 0), "person"),
        ((0, "Alfa Striker", 9101, 1, 0, 0, 7, 0), "nation"),
    ],
)
def test_a_past_winner_outside_its_table_is_an_error(editor, tmp_path, monkeypatch, place, what):
    broken = [(9601, synthetic.award_year_record(0, 2024, place))]
    monkeypatch.setattr(fictional_editor, "AWARD_YEARS", broken)
    write_database(editor)

    with pytest.raises(PlacesError, match=what):
        open_database(editor, tmp_path / "cache.sqlite")


def test_a_reference_outside_its_table_is_an_error(editor, tmp_path, monkeypatch):
    broken = {9101: ("Fictional City", "Fic City", {"nation": 7}, {})}
    monkeypatch.setattr(fictional_editor, "CLUBS", broken)
    write_database(editor)

    with pytest.raises(PlacesError, match="nation"):
        open_database(editor, tmp_path / "cache.sqlite")


def test_a_club_without_a_team_is_an_error(editor, tmp_path, monkeypatch):
    teams = [(uid, synthetic.team_record()) for uid in list(fictional_editor.CLUBS)[1:]]
    others = fictional_editor.server_tables()[1:]
    tables = [("table_24", synthetic.record_table(teams)), *others]
    monkeypatch.setattr(fictional_editor, "server_tables", lambda: tables)
    write_database(editor)

    with pytest.raises(PlacesError, match="9101"):
        open_database(editor, tmp_path / "cache.sqlite")
