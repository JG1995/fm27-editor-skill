import datetime
import struct

import pytest

import synthetic
from fictional_editor import write_editor
from fm27_editor.base_database import open_database
from fm27_editor.change_reading import EditError
from fm27_editor.editor_file import load_editor_file
from fm27_editor.explain import explain_lines
from fm27_editor.plan import approval_code, build_file, make_plan

AWARD, PERSON, CLUB, STADIUM, COMPETITION = 0, 1, 3, 21, 25


def number(value):
    return synthetic.prop("nwvl", 0x11, struct.pack("<b", value))


def text(value):
    return synthetic.prop("nwvl", 0x1A, synthetic.text(value))


def reference(tag, uid):
    ids = synthetic.prop(tag, 0x0F, struct.pack("<II", uid, uid))
    return synthetic.prop("nwvl", 0x0A, synthetic.props(ids))


@pytest.fixture
def lines_for(tmp_path):
    editor = write_editor(tmp_path / "editor")
    lookup = open_database(editor, tmp_path / "cache.sqlite")

    def lines(*changes, find="", examples=10):
        path = tmp_path / "Given.fmf"
        path.write_bytes(
            synthetic.container(
                "Given",
                [("Given", ".dbc", synthetic.change_list(*changes))],
                folder=("_data", [("details", ".aom", synthetic.details("Given"))]),
            )
        )
        file = load_editor_file(path)
        return explain_lines(file, editor, lookup, find=find, examples=examples)

    yield lines
    lookup.close()


def test_changes_are_counted_by_table_and_field(lines_for):
    lines = lines_for(
        synthetic.record_change(PERSON, 100, "PDfn", text("17")),
        synthetic.record_change(PERSON, 101, "PDfn", text("16")),
        synthetic.record_change(PERSON, 101, "Phes", number(120)),
        synthetic.record_change(STADIUM, 5, "Secy", number(50)),
    )

    assert lines[0] == "4 changes, saved by fictional-branch"
    assert "Person: 3 changes to 2 records" in lines
    assert "  Finishing (PDfn): 2" in lines
    assert "  Height (Phes): 1" in lines
    assert "Stadium: 1 change to 1 record" in lines
    assert "  Seating Capacity (Secy): 1" in lines


def test_examples_name_the_person_the_field_and_the_value(lines_for):
    lines = lines_for(synthetic.record_change(PERSON, 100, "PDfn", text("17")))

    assert "  Alfa Striker (100): Finishing = 17" in lines


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (number(-8), "-8"),
        (text("Zoë"), "Zoë"),
        (text(""), '""'),
        (synthetic.prop("nwvl", 0x03, b"\x01"), "yes"),
        (synthetic.prop("nwvl", 0x03, b"\x00"), "no"),
        (synthetic.prop("nwvl", 0x00), "nothing"),
        (synthetic.prop("nwvl", 0x19, struct.pack("<f", 1.5)), "1.5"),
        (synthetic.prop("nwvl", 0x20, bytes.fromhex("00b5d60f")), "2027-06-30"),
        (synthetic.prop("nwvl", 0x20, bytes.fromhex("00000000")), "00000000"),
        (reference("Nnat", 9002), "Norwegia (9002)"),
        (reference("Ttea", 9101), "Fictional City (9101)"),
        (reference("city", 12), "12"),
        (synthetic.prop("nwvl", 0x0B, struct.pack("<I", 0)), "a list of 0"),
        (
            synthetic.prop("nwvl", 0x0A, synthetic.props(synthetic.prop("lsop", 0x11, b"\x00"))),
            "a change to a list",
        ),
    ],
)
def test_every_kind_of_value_is_shown_in_plain_words(lines_for, value, shown):
    lines = lines_for(synthetic.record_change(PERSON, 100, "Phes", value))

    assert f"  Alfa Striker (100): Height = {shown}" in lines


def test_changes_to_awards_name_the_award(lines_for):
    lines = lines_for(synthetic.record_change(AWARD, 9501, "AWap", number(1)))

    assert "Award: 1 change to 1 record" in lines
    assert "  Example Player of the Year (9501): Allow Previous Winner = 1" in lines


def past_winner(year, name, person=None, points=None):
    winner = synthetic.prop("AH1p", 0x00)
    if person is not None:
        ids = synthetic.prop("Pers", 0x0F, struct.pack("<II", person, person))
        winner = synthetic.prop("AH1p", 0x0A, synthetic.props(ids))
    return b"\x01\x0a" + synthetic.props(
        synthetic.prop("AHye", 0x12, struct.pack("<h", year)),
        winner,
        synthetic.prop("AH1n", 0x1A, synthetic.text(name)),
        synthetic.prop("AH1i", 0x00)
        if points is None
        else synthetic.prop("AH1i", 0x11, struct.pack("<b", points)),
        synthetic.prop("Ahnt", 0x03, b"\x00"),
    )


def history(*items):
    body = struct.pack("<I", len(items)) + b"".join(items)
    return synthetic.record_change(AWARD, 9501, "AWsh", synthetic.prop("nwvl", 0x0B, body))


def test_a_list_says_how_long_it_is(lines_for):
    lines = lines_for(history(past_winner(2023, "Old Master"), past_winner(2024, "")))

    assert "  Example Player of the Year (9501): History = a list of 2" in lines


def test_a_search_finds_what_stands_in_a_list(lines_for):
    lines = lines_for(
        history(
            past_winner(2023, "Old Master", points=30),
            past_winner(2024, "Alfa", person=100, points=47),
        ),
        find="alfa",
    )

    assert lines[-2:] == [
        "Changes, 1 of 1:",
        "  Example Player of the Year (9501): History: Year 2024, Placed Alfa Striker (100), "
        "Placed Name Alfa, Info 47",
    ]


def test_a_national_team_in_a_list_is_named_by_its_nation(lines_for):
    ids = synthetic.prop("Ttea", 0x0F, struct.pack("<II", 9002, 9002))
    team = synthetic.prop("AH1t", 0x0A, synthetic.props(ids))

    lines = lines_for(history(b"\x01\x0a" + synthetic.props(team)), find="norwegia")

    assert lines[-1].endswith("History: Team Norwegia (9002)")


def test_new_people_are_counted_and_named_by_the_file_itself(lines_for):
    def named(code, value):
        return synthetic.record_change(PERSON, struct.pack("<II", 7001, 77), code, text(value))

    lines = lines_for(
        synthetic.added_person(7001), named("Pfna", "Testy"), named("Psna", "Newcomer")
    )

    assert "Adds 1 record: Person 1" in lines
    assert "  Testy Newcomer (new): First Name = Testy" in lines


def test_a_new_club_is_named_and_so_is_the_new_competition_it_plays_in(lines_for):
    """The Editor renumbers new records when it saves, and keeps the second half of their IDs."""
    league, rovers = struct.pack("<II", 7001, 77), struct.pack("<II", 7002, 78)
    renumbered = struct.pack("<II", 2_000_000_001, 77)
    division = synthetic.props(synthetic.prop("comp", 0x0F, renumbered))

    lines = lines_for(
        synthetic.record_change(COMPETITION, league, "cnam", text("Test League")),
        synthetic.record_change(CLUB, rovers, "Cnam", text("Test Rovers")),
        synthetic.record_change(CLUB, rovers, "Cdvi", synthetic.prop("nwvl", 0x0A, division)),
        synthetic.record_change(CLUB, 9101, "Cdvi", reference("comp", 9203)),
    )

    assert "  Test League (new): Name = Test League" in lines
    assert "  Test Rovers (new): Division = Test League (new)" in lines
    assert "  Fictional City (9101): Division = Example League North (9203)" in lines


def test_rules_for_a_nation_are_mentioned(tmp_path):
    editor = write_editor(tmp_path / "editor")
    with open_database(editor, tmp_path / "cache.sqlite") as lookup:
        rules = {
            "nation": 9001,
            "season_update_day": {"day_of_month": 20, "month": "jun"},
            "start_date": "2026-08-01",
            "end_date": "2027-05-31",
            "league_comps": [
                {
                    "competition": 9201,
                    "minimum_number_teams": 2,
                    "maximum_number_teams": 2,
                    "start_date": "2026-08-15",
                    "end_date": "2027-05-15",
                }
            ],
        }
        plan = make_plan({"nation_rules": rules}, editor, lookup)
        file = build_file(plan, approval_code(plan), datetime.date(2026, 11, 12))

        lines = explain_lines(file, editor, lookup, find="", examples=10)

    assert "Rules for Englandia (9001): 1 division, 0 cups" in lines


def test_removed_records_are_counted(lines_for):
    removal = synthetic.prop("nwvl", 0x03, b"\x01")

    lines = lines_for(synthetic.record_change(STADIUM, 5, "DELE", removal))

    assert "Removes 1 record: Stadium 1" in lines


def test_records_and_fields_without_a_known_name_go_by_number_and_code(lines_for):
    lines = lines_for(
        synthetic.record_change(STADIUM, 5, "Zzzz", number(1)),
        synthetic.record_change(77, 6, "Yyyy", number(1)),
        synthetic.record_change(99, 8, "Xxxx", number(1)),
    )

    assert "  5: Zzzz = 1" in lines
    assert "Table 77: 1 change to 1 record" in lines
    assert "Moon: 1 change to 1 record" in lines


def test_a_change_that_does_not_say_what_it_changes_is_reported(lines_for):
    with pytest.raises(EditError, match="prty"):
        lines_for(
            synthetic.change(
                synthetic.prop("dtty", 0x11, b"\x01"), synthetic.prop("duni", 0x0F, b"\x01" * 8)
            )
        )


@pytest.mark.parametrize(
    "new",
    [
        synthetic.prop("nwvl", 0x03, b"\x01"),
        synthetic.prop("nwvl", 0x0A, synthetic.props(synthetic.prop("dtty", 0x11, b"\x01"))),
    ],
    ids=["not a record", "no ID"],
)
def test_an_added_record_of_unknown_shape_is_reported(lines_for, new):
    with pytest.raises(EditError, match="adds a record"):
        lines_for(synthetic.record_change(55, 1, "ADDR", new))


def test_a_name_without_a_record_is_reported(lines_for):
    with pytest.raises(EditError, match="duni"):
        lines_for(
            synthetic.change(
                synthetic.prop("dtty", 0x11, b"\x01"),
                synthetic.prop("prty", 0x02, b"anfP"),
                text("Testy"),
            )
        )


def test_a_new_person_without_a_name_goes_by_number(lines_for):
    nameless = synthetic.change(
        synthetic.prop("dtty", 0x11, b"\x01"),
        synthetic.prop("duni", 0x0F, struct.pack("<II", 7001, 77)),
        synthetic.prop("prty", 0x02, b"anfP"),
        synthetic.prop("nwvl", 0x00),
    )

    assert "  7001 (new): First Name = nothing" in lines_for(nameless)


def test_a_search_without_a_match_says_so(lines_for):
    lines = lines_for(synthetic.record_change(PERSON, 100, "PDfn", text("17")), find="zzz")

    assert lines[-1] == "No change mentions 'zzz'"


def test_only_changes_that_match_are_shown(lines_for):
    changes = [
        synthetic.record_change(PERSON, 100, "PDfn", text("17")),
        synthetic.record_change(PERSON, 101, "PDfn", text("16")),
        synthetic.record_change(PERSON, 101, "Phes", number(120)),
    ]

    by_name = lines_for(*changes, find="bravo")
    by_field = lines_for(*changes, find="finishing")

    assert [line for line in by_name if " = " in line] == [
        "  Bravo Keeper (101): Finishing = 16",
        "  Bravo Keeper (101): Height = 120",
    ]
    assert len([line for line in by_field if " = " in line]) == 2


def test_a_long_list_is_cut_and_says_so(lines_for):
    changes = [synthetic.record_change(PERSON, 100, "Phes", number(n)) for n in range(5)]

    assert "Changes, 2 of 5:" in lines_for(*changes, examples=2)
