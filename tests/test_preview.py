import pytest

from fictional_editor import STAFF_KIND, write_editor
from fm27_editor.base_database import open_database
from fm27_editor.person_rules import PersonRules
from fm27_editor.plan import make_plan
from fm27_editor.preview import preview_lines

TEAM = [
    (0, 100, "Alfa Striker", 2004, 120, (51, 9002), (1, 9101)),
    (1, 101, "Bravo Keeper", 2008, 60, (41, 9001), (0, 9102)),
    (2, 102, "Charlie Coach", 1980, 110, (41, 9001), (0, 9102), STAFF_KIND),
    (3, 103, "Delta Back", 2001, 90, (41, 9001), (0, 9102)),
]


@pytest.fixture
def lines_for(tmp_path):
    editor = write_editor(tmp_path / "editor", TEAM)
    lookup = open_database(editor, tmp_path / "cache.sqlite")
    rules = PersonRules(editor, lookup)

    def lines(examples=10, **request):
        return preview_lines(make_plan(request, rules, lookup), lookup, examples)

    yield lines
    lookup.close()


def test_each_field_says_how_many_people_change_and_in_which_direction(lines_for):
    query = "SELECT uid, 85 AS pa FROM people WHERE kind = 'player'"

    lines = lines_for(edits=[{"query": query}])

    # 140, 80 and 110 become 85
    assert "Edits: 3 changes to 3 people" in lines
    assert "  Potential Ability (PPAB): 3 people, 1 up, 2 down, new values 85 to 85" in lines


def test_an_example_shows_who_it_is_and_the_old_and_new_value(lines_for):
    lines = lines_for(edits=[{"uid": 100, "set": {"finishing": 17}}])

    assert (
        "  Alfa Striker (100), born 2004-02-29, Norwegia, Fictional City: Finishing 15 -> 17"
        in lines
    )


def test_an_old_value_the_lookup_does_not_know_is_not_made_up(lines_for):
    lines = lines_for(edits=[{"uid": 100, "set": {"Phes": 190}}])

    assert "  Height (Phes): 1 person, 1 from an unknown value, new values 190 to 190" in lines
    assert lines[-2].endswith("Height unknown -> 190")


def test_nations_and_clubs_are_shown_by_name(lines_for):
    lines = lines_for(edits=[{"uid": 100, "set": {"club_uid": 9102}}])

    assert lines[-2].endswith("Club Fictional City (9101) -> Example United (9102)")
    assert "  Club (Pcti): 1 person" in lines


def test_examples_are_spread_over_all_edits(lines_for):
    query = "SELECT uid, 7 AS finishing FROM people WHERE kind = 'player' ORDER BY uid"

    lines = lines_for(examples=2, edits=[{"query": query}])

    shown = [line.split(" (")[0].strip() for line in lines if "Finishing 15" in line]
    assert shown == ["Alfa Striker", "Delta Back"]
    assert "Examples, 2 of 3:" in lines


def test_values_left_out_are_mentioned(lines_for):
    lines = lines_for(edits=[{"uid": 100, "set": {"ca": 120, "finishing": 3}}])

    assert "Left out: 1 value that people have already" in lines


def test_new_people_are_listed_with_everything_that_is_set(lines_for):
    values = {"Pfna": "Testy", "Psna": "New", "birth_date": "2008-04-25", "nation_uid": 9001}

    lines = lines_for(new_people=[{"kind": "staff", "set": values}])

    assert "New people: 1" in lines
    assert (
        "  staff: First Name Testy; Second Name New; Date Of Birth 2008-04-25; "
        "Nation Englandia (9001)" in lines
    )


def test_more_new_people_than_examples_are_counted(lines_for):
    person = {
        "kind": "player",
        "set": {"Pfna": "Testy", "Psna": "New", "birth_date": "2008-04-25", "nation_uid": 9001},
    }

    lines = lines_for(examples=2, new_people=[person] * 5)

    assert "New people: 5" in lines
    assert "  and 3 more" in lines


def test_the_last_line_is_the_approval_code(lines_for):
    lines = lines_for(edits=[{"uid": 100, "set": {"finishing": 17}}])

    assert lines[-1].startswith("Approval code: ")
    assert len(lines[-1].split(": ")[1]) == 12
