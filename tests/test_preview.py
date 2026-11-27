import pytest

from fictional_editor import STAFF_KIND, write_editor
from fm27_editor.base_database import open_database
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

    def lines(examples=10, **request):
        return preview_lines(make_plan(request, editor, lookup), lookup, examples)

    yield lines
    lookup.close()


def test_each_field_says_how_many_people_change_and_in_which_direction(lines_for):
    query = "SELECT uid, 85 AS pa FROM people WHERE kind = 'player'"

    lines = lines_for(edits=[{"of": "people", "query": query}])

    # 140, 80 and 110 become 85
    assert "Edits: 3 changes to 3 people" in lines
    assert "  Potential Ability (PPAB): 3 people, 1 up, 2 down, new values 85 to 85" in lines


def test_an_example_shows_who_it_is_and_the_old_and_new_value(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"finishing": 17}}])

    assert (
        "  Alfa Striker (100), born 2004-02-29, Norwegia, Fictional City: Finishing 15 -> 17"
        in lines
    )


@pytest.mark.parametrize("pa", [-95, -8])
def test_a_potential_range_is_neither_up_nor_down(lines_for, pa):
    lines = lines_for(
        edits=[{"of": "people", "query": f"SELECT uid, {pa} AS pa FROM people WHERE uid = 100"}]
    )

    assert "  Potential Ability (PPAB): 1 person, 1 to or from a range" in lines


def test_a_potential_range_is_shown_as_what_it_stands_for(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"pa": -8}}])

    assert lines[-2].endswith("Potential Ability 140 -> 130-160 (-8)")


def test_ranges_are_kept_apart_from_numbers(lines_for):
    query = "SELECT uid, CASE uid WHEN 100 THEN -8 ELSE 150 END AS pa FROM people WHERE uid < 102"

    lines = lines_for(edits=[{"of": "people", "query": query}])

    assert (
        "  Potential Ability (PPAB): 2 people, 1 up, 1 to or from a range, new values 150 to 150"
        in lines
    )


@pytest.mark.parametrize(
    "values", [{"ca": 141}, {"pa": 119}, {"ca": 100, "pa": 99}], ids=["ca", "pa", "both"]
)
def test_ability_above_potential_is_pointed_out(lines_for, values):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": values}])

    assert "Warning: 1 person would have more ability than potential" in lines


@pytest.mark.parametrize("values", [{"ca": 140}, {"ca": 150, "pa": 150}, {"pa": -8}])
def test_ability_up_to_potential_is_not(lines_for, values):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": values}])

    assert not [line for line in lines if line.startswith("Warning")]


def test_new_people_with_more_ability_than_potential_are_pointed_out(lines_for):
    values = {"Pfna": "Testy", "Psna": "New", "birth_date": "2008-04-25", "nation_uid": 9001}

    lines = lines_for(new=[{"kind": "player", "set": values | {"ca": 100, "pa": 90}}])

    assert "Warning: 1 person would have more ability than potential" in lines


def test_an_old_value_the_lookup_does_not_know_is_not_made_up(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"Phes": 190}}])

    assert "  Height (Phes): 1 person, 1 from an unknown value, new values 190 to 190" in lines
    assert lines[-2].endswith("Height unknown -> 190")


def test_money_is_shown_in_pounds(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"Pcwg": 19943}}])

    assert (
        "  Wage (Pcwg): 1 person, 1 from an unknown value, new values £19,943 to £19,943" in lines
    )
    assert lines[-2].endswith("Wage unknown -> £19,943")


def test_nations_and_clubs_are_shown_by_name(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"club_uid": 9102}}])

    assert lines[-2].endswith("Club Fictional City (9101) -> Example United (9102)")
    assert "  Club (Pcti): 1 person" in lines


def test_examples_are_spread_over_all_edits(lines_for):
    query = "SELECT uid, 7 AS finishing FROM people WHERE kind = 'player' ORDER BY uid"

    lines = lines_for(examples=2, edits=[{"of": "people", "query": query}])

    shown = [line.split(" (")[0].strip() for line in lines if "Finishing 15" in line]
    assert shown == ["Alfa Striker", "Delta Back"]
    assert "Examples, 2 of 3:" in lines


def test_values_left_out_are_mentioned(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"ca": 120, "finishing": 3}}])

    assert "Left out: 1 value that is so already" in lines


def test_new_people_are_listed_with_everything_that_is_set(lines_for):
    values = {"Pfna": "Testy", "Psna": "New", "birth_date": "2008-04-25", "nation_uid": 9001}

    lines = lines_for(new=[{"kind": "staff", "set": values}])

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

    lines = lines_for(examples=2, new=[person] * 5)

    assert "New people: 5" in lines
    assert "  and 3 more" in lines


def test_clubs_and_competitions_are_counted_apart_from_people(lines_for):
    lines = lines_for(
        edits=[
            {"of": "people", "uid": 100, "set": {"finishing": 17}},
            {
                "of": "clubs",
                "query": "SELECT uid, 9201 AS division_uid FROM clubs WHERE uid > 9101",
            },
        ]
    )

    assert "Edits: 1 change to 1 person" in lines
    assert "Edits: 3 changes to 3 clubs" in lines
    assert "  Division (Cdvi): 3 clubs" in lines
    assert (
        "  Example United (9102), Englandia, male, Example League North: "
        "Division Example League North (9203) -> Example League (9201)" in lines
    )


def test_awards_are_counted_and_described(lines_for):
    lines = lines_for(edits=[{"of": "awards", "uid": 9501, "set": {"previous_winner": 1}}])

    assert "Edits: 1 change to 1 award" in lines
    assert (
        "  Example Player of the Year (9501), Englandia, male, Example League: "
        "Allow Previous Winner Yes (3) -> Never (1)"
    ) in lines


NEW_2024 = {
    "award_uid": 9501,
    "year": 2024,
    "places": [
        {"person_uid": 101, "team_uid": 9102, "nation_uid": 9001, "points": 50, "age": 16},
        {"keep": 1},
    ],
}


def test_a_history_is_shown_with_what_was_there_before(lines_for):
    lines = lines_for(award_history=[NEW_2024])

    at = lines.index(
        "History of Example Player of the Year (9501), Englandia, male, Example League: "
        "1 of 3 years changes, 1 with another winner; the others stay as they are"
    )
    assert lines[at + 1 : at + 3] == [
        "  2024: 1 Bravo Keeper (101), Example United (9102), Englandia (9001), 50 points, age 16; "
        "2 Alfa Striker (100), Fictional City (9101), Norwegia (9002), 47 points, age 20, "
        "Wing-Back Left",
        "    was: 1 Alfa Striker (100), Fictional City (9101), Norwegia (9002), 47 points, age 20, "
        "Wing-Back Left; 2 Old Master (no person), Example United (9102), Englandia (9001), "
        "22 points, then 3,000; 3 Cup Hero (no person), Englandia (9001), Englandia (9001), "
        "9 points, age 33",
    ]


def test_a_history_without_other_years_does_not_mention_them(lines_for):
    lines = lines_for(award_history=[{"award_uid": 9502, "year": 2024, "not_held": True}])

    assert (
        "History of Example Women's Player (9502), female: 1 of 1 year changes, "
        "1 with another winner"
    ) in lines


def test_years_that_are_so_already_are_mentioned(lines_for):
    so_already = {"award_uid": 9501, "year": 2023, "places": [{"keep": 1}]}

    lines = lines_for(
        edits=[{"of": "people", "uid": 100, "set": {"finishing": 17}}], award_history=[so_already]
    )

    assert "Left out: 1 year that is so already" in lines
    assert not [line for line in lines if line.startswith("History")]


def test_years_without_winners_and_new_years_say_so(lines_for):
    lines = lines_for(
        award_history=[
            {"award_uid": 9501, "year": 2023, "not_held": True},
            {"award_uid": 9501, "year": 2025, "places": [{"name": "New Star"}]},
        ]
    )

    assert "  2023: not held" in lines
    assert "  2025: 1 New Star (no person)" in lines
    assert "    was: not in the history" in lines


def test_the_years_of_a_history_are_spread_over_the_examples(lines_for):
    years = [
        {"award_uid": 9502, "year": year, "places": [{"name": f"Star {year}"}]}
        for year in range(2001, 2010)
    ]

    lines = lines_for(examples=3, award_history=years)

    shown = [line.strip().split(":")[0] for line in lines if line.startswith("  20")]
    assert shown == ["2001", "2005", "2009"]
    assert "  and 6 more years" in lines


def test_new_records_are_shown_with_their_names_in_the_request(lines_for):
    league = {"name": "Test League", "short_name": "League", "nation_uid": 9001, "dbty": 0}
    rovers = {
        "name": "Test Rovers",
        "short_name": "Rovers",
        "nation_uid": 9001,
        "division_uid": "@D1",
        "ttcl": "#480024",
    }

    lines = lines_for(
        new=[
            {"kind": "competition", "as": "D1", "set": league},
            {"kind": "club", "set": rovers},
            {"kind": "club", "set": rovers},
        ]
    )

    assert "New competitions: 1" in lines
    assert "New clubs: 2" in lines
    assert (
        "  competition @D1: Name Test League; Short Name League; Nation Englandia (9001); "
        "Type Top Division (0)" in lines
    )
    assert (
        "  club: Name Test Rovers; Short Name Rovers; Nation Englandia (9001); "
        "Division @D1; Foreground Colour #480024" in lines
    )


def test_rules_are_shown_in_full(lines_for):
    rules = {
        "nation": 9001,
        "season_update_day": {"day_of_month": 20, "month": "jun"},
        "start_date": "2026-08-01",
        "end_date": "2027-05-31",
        "transfer_windows": [{"start_date": "2026-07-01", "end_date": "2026-08-31"}],
        "league_comps": [
            {
                "competition": 9201,
                "minimum_number_teams": 2,
                "maximum_number_teams": 2,
                "start_date": "2026-08-15",
                "end_date": "2027-05-15",
                "child_competitions": [{"competition": 9203}],
            }
        ],
        "cup_comps": [
            {
                "competition": 9204,
                "type": "main_cup",
                "teams": [{"competition": 9201, "number_teams": 2}],
                "rounds": [{"number_matches": 1, "number_extra_teams": 2, "date": "2027-05-22"}],
            }
        ],
    }

    lines = lines_for(nation_rules=rules)

    start = lines.index("Nation rules: Englandia (9001)")
    assert lines[start + 1 : start + 5] == [
        "  season_update_day: day_of_month 20, month jun",
        "  start_date: 2026-08-01",
        "  end_date: 2027-05-31",
        "  bosman_number_days: 183",
    ]
    assert (
        "  transfer_windows 1: start_date (day_of_month 1, month jul, year 2026), "
        "end_date (day_of_month 31, month aug, year 2026), window_type normal" in lines
    )
    division = next(line for line in lines if line.startswith("  Division 1: "))
    assert "competition Example League (9201), minimum_number_teams 2" in division
    assert "sort_rules goal_difference and goals_for" in division
    assert "use_game_rules" not in division
    assert "child_competitions Example League North (9203)" in division
    cup = next(line for line in lines if line.startswith("  Cup 1: "))
    assert "type main_cup" in cup and "competition Example Cup (9204)" in cup
    assert "  Cup 1, round 1: number_matches 1, number_extra_teams 2, number_legs 1" in "\n".join(
        lines
    )


def test_the_last_line_is_the_approval_code(lines_for):
    lines = lines_for(edits=[{"of": "people", "uid": 100, "set": {"finishing": 17}}])

    assert lines[-1].startswith("Approval code: ")
    assert len(lines[-1].split(": ")[1]) == 12
