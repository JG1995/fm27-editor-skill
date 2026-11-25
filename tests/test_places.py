import pytest

import synthetic
from fm27_editor.binary import FormatError
from fm27_editor.places import parse_clubs, parse_nations


def test_reads_club_names_including_the_first_club():
    clubs = parse_clubs(
        synthetic.club_table([(9101, "Fictional City", "Fic City"), (9102, "Example", "Ex")])
    )

    assert clubs == {9101: ("Fictional City", "Fic City"), 9102: ("Example", "Ex")}


def test_a_club_record_of_many_kilobytes_is_read():
    table = synthetic.club_table([(9101, "Fictional City", "Fic City")])
    padded = table[:12] + b"\x07" * 5_000 + table[12:]

    assert parse_clubs(padded) == {9101: ("Fictional City", "Fic City")}


@pytest.mark.parametrize(
    "content", [b"", b"\x03\x01tad.", b"\x00" * 40], ids=["empty", "short", "no tag"]
)
def test_broken_place_tables_raise_a_format_error(content):
    with pytest.raises(FormatError):
        parse_clubs(content)
    with pytest.raises(FormatError):
        parse_nations(content, {9001})


def test_nation_names_are_found_for_the_ids_asked_for():
    table = synthetic.nation_names({9001: "Englandia", 9002: "Norwegia"})

    assert parse_nations(table, {9002, 4}) == {9002: "Norwegia"}
