import sqlite3
from contextlib import closing

import pytest

import fictional_editor
import synthetic
from fictional_editor import write_editor
from fm27_editor.award_history import Place, Year, check_award_history, history_change
from fm27_editor.base_database import open_database
from fm27_editor.change_list import ChangeList, Kind
from fm27_editor.change_reading import EditError, read_number
from fm27_editor.record_changes import NewIds
from fm27_editor.record_kinds import AWARD
from fm27_editor.record_rules import RecordRules

NOBODY = synthetic.NO_INDEX
OLD_MASTER_2023 = Place(name="Old Master", team_uid=9102, points=30, nation_uid=9001)
ALFA_2024 = Place(
    person_uid=100,
    name="Alfa Striker",
    team_uid=9101,
    points=47,
    age=20,
    nation_uid=9002,
    position=64,
)
OLD_MASTER_2024 = Place(
    name="Old Master", team_uid=9102, points=22, more_points=3000, nation_uid=9001
)
CUP_HERO_2024 = Place(name="Cup Hero", team_uid=9001, points=9, age=33, nation_uid=9001)
HELD_2023 = Year(2023, {1: OLD_MASTER_2023})
HELD_2024 = Year(2024, {1: ALFA_2024, 2: OLD_MASTER_2024, 3: CUP_HERO_2024})
NOT_HELD_2020 = Year(2020, {}, not_held=True)


@pytest.fixture
def check(tmp_path):
    editor = write_editor(tmp_path / "editor")
    with closing(open_database(editor, tmp_path / "cache.sqlite")) as lookup:
        rules = RecordRules(editor, lookup)
        yield lambda *given: check_award_history(list(given), rules.fields(AWARD), lookup)


def year(number, *places, award=9501, **others):
    given = {"award": award, "year": number, **others}
    return given | ({"places": list(places)} if places else {})


def test_years_that_are_not_named_stay_as_the_database_has_them(check):
    (history,) = check(year(2025, {"name": "New Star"}))

    assert history.award_uid == 9501
    assert history.years == [
        NOT_HELD_2020,
        HELD_2023,
        HELD_2024,
        Year(2025, {1: Place(name="New Star")}),
    ]


def test_a_year_can_be_given_other_winners(check):
    (history,) = check(
        year(
            2024,
            {
                "person_uid": 101,
                "name": "B. Keeper",
                "team_uid": 9102,
                "points": 50,
                "age": 16,
                "nation_uid": 9001,
            },
            {"name": "Old Master", "points": 22},
        )
    )

    keeper = Place(
        person_uid=101, name="B. Keeper", team_uid=9102, points=50, age=16, nation_uid=9001
    )
    new = Year(2024, {1: keeper, 2: Place(name="Old Master", points=22)})
    assert history.years == [NOT_HELD_2020, HELD_2023, new]
    assert history.changed == [(HELD_2024, new)]


def test_who_is_in_the_history_already_can_be_kept_at_another_place(check):
    (history,) = check(year(2024, {"keep": 3}, {"keep": 1, "points": 8}))

    (_, new) = history.changed[0]
    assert new.places[1] == CUP_HERO_2024
    assert new.places[2] == Place(
        person_uid=100,
        name="Alfa Striker",
        team_uid=9101,
        points=8,
        age=20,
        nation_uid=9002,
        position=64,
    )


def test_a_person_goes_by_the_name_that_awards_use(check):
    (history,) = check(year(2025, {"person_uid": 100}, {"person_uid": 101}))

    (_, new) = history.changed[0]
    assert [place.name for place in new.places.values()] == ["Alfa Striker", "Bravo Keeper"]


def test_a_national_team_is_given_by_the_uid_of_the_nation(check):
    (history,) = check(year(2025, {"name": "Cup Hero", "team_uid": 9002}))

    assert history.changed[0][1].places[1].team_uid == 9002


def test_a_year_can_be_marked_as_not_held(check):
    (history,) = check(year(2023, not_held=True))

    assert history.changed == [(HELD_2023, Year(2023, {}, not_held=True))]


def test_a_year_that_was_not_held_can_be_given_winners(check):
    (history,) = check(year(2020, {"name": "New Star"}))

    assert history.changed == [(NOT_HELD_2020, Year(2020, {1: Place(name="New Star")}))]


def test_a_year_without_a_difference_is_not_a_change(check):
    (history,) = check(year(2023, {"keep": 1}), year(2024, {"keep": 2}))

    assert [new.year for _, new in history.changed] == [2024]
    assert history.already_so == 1


def test_the_years_of_each_award_are_its_own(check):
    first, second = check(year(2023, {"name": "A"}), year(2023, {"name": "B"}, award=9502))

    assert [first.award_uid, second.award_uid] == [9501, 9502]
    assert [len(first.years), len(second.years)] == [3, 2]


@pytest.mark.parametrize(
    ("given", "complaint"),
    [
        ({"award": 9501}, "year"),
        ({"year": 2024}, "award"),
        ("2024", "named parts"),
        (year(2024, {"name": "A"}, award=77), "no award 77"),
        (year(2024, {"name": "A"}, award="Player"), "no award 'Player'"),
        (year(2024, {"name": "A"}, winner="B"), "winner"),
        (year(2024), "places or not_held"),
        (year(2024, {"name": "A"}, not_held=True), "places or not_held"),
        (year(2024, not_held=False), "not_held"),
        (year(1066, {"name": "A"}), "from 1800 to 2100"),
        (year("2024", {"name": "A"}), "whole number"),
        (year(2024, *[{"name": "A"}] * 4), "one to three"),
        ({"award": 9501, "year": 2024, "places": []}, "one to three"),
        ({"award": 9501, "year": 2024, "places": {"name": "A"}}, "one to three"),
        (year(2024, "Alfa"), "named parts"),
        (year(2024, {"name": "A", "shirt": 9}), "shirt"),
        (year(2024, {"points": 9}), "needs a name"),
        (year(2024, {"name": ""}), "text"),
        (year(2024, {"name": "A\tB"}), "text"),
        (year(2024, {"name": "A", "points": 0}), "from 1 to 5000"),
        (year(2024, {"name": "A", "points": "9"}), "whole number"),
        (year(2024, {"name": "A", "age": 200}), "from 14 to 120"),
        (year(2024, {"name": "A", "points": None}), "no value"),
        (year(2024, {"person_uid": 999}), "no person 999"),
        (year(2024, {"person_uid": True}), "no person True"),
        (year(2024, {"person_uid": 10**20}), "no person 1000"),
        (year(2024, {"name": "A", "team_uid": 999}), "no club or nation 999"),
        (year(2024, {"name": "A", "nation_uid": 9101}), "no nation 9101"),
        (year(2024, {"keep": 4}), "keep"),
        (year(2023, {"keep": 2}), "no place 2"),
        (year(2025, {"keep": 1}), "no place 1"),
    ],
)
def test_what_does_not_fit_is_refused_with_a_reason(check, given, complaint):
    with pytest.raises(EditError, match=complaint):
        check(given)


def test_a_year_is_given_once(check):
    with pytest.raises(EditError, match="2024.*twice"):
        check(year(2024, {"name": "A"}), year(2024, {"name": "B"}))


def test_a_year_that_the_database_has_twice_cannot_be_changed(check, tmp_path, monkeypatch):
    twice = [
        *fictional_editor.AWARD_YEARS,
        (9605, synthetic.award_year_record(0, 2023, (NOBODY, "B", 9101, 1, 0, 0, NOBODY, 0))),
    ]
    monkeypatch.setattr(fictional_editor, "AWARD_YEARS", twice)
    editor = write_editor(tmp_path / "twice")
    with closing(open_database(editor, tmp_path / "twice.sqlite")) as lookup:
        fields = RecordRules(editor, lookup).fields(AWARD)

        (history,) = check_award_history([year(2024, {"keep": 2})], fields, lookup)
        assert [entry.year for entry in history.years] == [2020, 2023, 2023, 2024]
        with pytest.raises(EditError, match="2023.*more than one"):
            check_award_history([year(2023, {"name": "A"})], fields, lookup)


def test_the_histories_must_be_a_list(check, tmp_path):
    with (
        closing(sqlite3.connect(":memory:")) as lookup,
        pytest.raises(EditError, match="list"),
    ):
        check_award_history({"award": 9501}, {}, lookup)


def test_a_person_goes_by_the_name_that_most_awards_use(tmp_path, monkeypatch):
    others = [
        (uid, synthetic.award_year_record(0, 2000 + uid, (0, "A. Striker", 9101, 1, 0, 0, 0, 0)))
        for uid in (1, 2)
    ]
    monkeypatch.setattr(fictional_editor, "AWARD_YEARS", [*fictional_editor.AWARD_YEARS, *others])
    editor = write_editor(tmp_path / "more")
    with closing(open_database(editor, tmp_path / "more.sqlite")) as lookup:
        fields = RecordRules(editor, lookup).fields(AWARD)
        (history,) = check_award_history([year(2025, {"person_uid": 100})], fields, lookup)

    assert history.changed[0][1].places[1].name == "A. Striker"


def test_a_person_known_only_from_awards_can_be_named(tmp_path, monkeypatch):
    people = [
        *fictional_editor.PEOPLE,
        (2, 102, "Omar Official", 1970, 0, (41, 9001), (0, 9102), 4),
    ]
    known = (9607, synthetic.award_year_record(0, 2022, (2, "O. Official", 9101, 1, 0, 0, 0, 0)))
    monkeypatch.setattr(fictional_editor, "AWARD_YEARS", [*fictional_editor.AWARD_YEARS, known])
    editor = write_editor(tmp_path / "more", people)
    with closing(open_database(editor, tmp_path / "more.sqlite")) as lookup:
        fields = RecordRules(editor, lookup).fields(AWARD)
        assert lookup.execute("SELECT count(*) FROM person WHERE uid = 102").fetchone() == (0,)
        (history,) = check_award_history([year(2025, {"person_uid": 102})], fields, lookup)

    assert history.changed[0][1].places[1].name == "O. Official"


def test_a_history_is_stored_with_every_year_and_every_part(check):
    (history,) = check(year(2024, {"keep": 1}))

    change = history_change(history, NewIds(ChangeList()))

    (stored,) = [part for part in change if part.tag == "nwvl"]
    items = [{part.tag: part for part in item.value} for item in stored.value]
    assert [len(item) for item in items] == [27, 27, 27]
    assert [read_number(item["AHye"]) for item in items] == [2020, 2023, 2024]
    assert [bool(item["Ahnt"].value[0]) for item in items] == [True, False, False]
    assert items[2]["AH1n"].value == "Alfa Striker"
    assert (read_number(items[2]["AH1i"]), read_number(items[2]["AHp1"])) == (47, 64)
    assert items[2]["AH2n"].value == "" and items[2]["AH2i"].kind is Kind.NULL
