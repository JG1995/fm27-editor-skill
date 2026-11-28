import pytest

import synthetic
from fm27_editor.binary import FormatError
from fm27_editor.places import (
    Club,
    Competition,
    Gender,
    LocalRegion,
    PlacesError,
    Team,
    parse_cities,
    parse_clubs,
    parse_competitions,
    parse_derbies,
    parse_local_regions,
    parse_stadiums,
    parse_teams,
    team_clubs,
)


def test_reads_where_a_club_plays():
    table = synthetic.record_table(
        [
            (
                9101,
                synthetic.club_record("Fictional City", "Fic", nation=2, based_nation=3, city=4),
            ),
            (9102, synthetic.club_record("Example Women", "Ex", nation=2, female=True)),
        ]
    )

    assert parse_clubs(table) == [
        Club(9101, nation=2, based_nation=3, city=4, gender=Gender.MALE, is_extinct=False),
        Club(9102, nation=2, based_nation=None, city=None, gender=Gender.FEMALE, is_extinct=False),
    ]


def test_an_extinct_club_keeps_the_nation_it_played_in():
    table = synthetic.record_table(
        [(9103, synthetic.club_record("Gone Town", "Gone", extinct_nation=2))]
    )

    (club,) = parse_clubs(table)

    assert (club.nation, club.is_extinct) == (2, True)


def test_records_that_are_not_clubs_are_left_out():
    table = synthetic.record_table(
        [
            (9101, synthetic.club_record("Fictional City", "Fic", nation=2)),
            (2_000_000_000, synthetic.club_record("", "", kind=12)),
        ]
    )

    assert [club.uid for club in parse_clubs(table)] == [9101]


def test_a_club_of_another_shape_is_an_error():
    record = synthetic.club_record("Fictional City", "Fic", nation=2) + b"\x09"

    with pytest.raises(PlacesError, match="9101"):
        parse_clubs(synthetic.record_table([(9101, record)]))


def test_reads_the_standing_of_club_teams_and_leaves_out_national_teams():
    table = synthetic.record_table(
        [
            (5, synthetic.team_record(reputation=9000, kind=b"\x0b\x01")),
            (
                9101,
                synthetic.team_record(
                    last_position=3, reputation=8150, division=7, last_division=8, stadium=9
                ),
            ),
            (9102, synthetic.team_record()),
        ]
    )

    assert parse_teams(table) == [
        Team(9101, reputation=8150, division=7, last_division=8, last_position=3, stadium=9),
        Team(9102, reputation=0, division=None, last_division=None, last_position=0, stadium=None),
    ]


def test_national_teams_belong_to_no_club():
    table = synthetic.record_table(
        [(5, synthetic.team_record(kind=b"\x0b\x01")), (9101, synthetic.team_record())]
    )

    assert team_clubs(table) == [None, 9101]


def test_reads_the_teams_of_a_derby():
    table = synthetic.record_table(
        [
            (50, synthetic.derby_record("Fictional Derby", "Derby", 0, 1)),
            (52, synthetic.derby_record("Lonely Derby", "Lonely", 1, synthetic.NO_INDEX)),
        ]
    )

    assert parse_derbies(table) == {50: (0, 1), 52: (1, None)}


def test_a_derby_of_another_shape_is_an_error():
    record = synthetic.derby_record("Fictional Derby", "Derby", 0, 1) + b"\x00"

    with pytest.raises(PlacesError, match="50"):
        parse_derbies(synthetic.record_table([(50, record)]))


def test_reads_competitions():
    client = synthetic.record_table(
        [
            (9201, synthetic.competition_record(nation=2, level=1)),
            (9202, synthetic.competition_record(nation=2, parent=0)),
        ]
    )
    server = synthetic.record_table(
        [
            (9201, synthetic.competition_server_record()),
            (9202, synthetic.competition_server_record(female=True)),
        ]
    )

    assert parse_competitions(client, server) == [
        Competition(9201, nation=2, parent=None, level=1, gender=Gender.MALE),
        Competition(9202, nation=2, parent=0, level=None, gender=Gender.FEMALE),
    ]


def test_competition_tables_that_disagree_are_an_error():
    client = synthetic.record_table([(9201, synthetic.competition_record())])
    server = synthetic.record_table([(9202, synthetic.competition_server_record())])

    with pytest.raises(PlacesError):
        parse_competitions(client, server)


def test_competition_tables_of_different_length_are_an_error():
    client = synthetic.record_table([(9201, synthetic.competition_record())])

    with pytest.raises(PlacesError):
        parse_competitions(client, synthetic.record_table([]))


def test_a_gender_other_than_two_is_an_error():
    client = synthetic.record_table([(9201, synthetic.competition_record())])
    server = synthetic.record_table([(9201, b"\x07" * 179)])

    with pytest.raises(PlacesError, match="gender"):
        parse_competitions(client, server)


def test_reads_the_nation_of_a_city_and_the_city_of_a_stadium():
    cities = synthetic.record_table(
        [(9301, synthetic.city_record(2)), (9302, synthetic.city_record())]
    )
    stadiums = synthetic.record_table([(9401, synthetic.stadium_record(1))])

    assert parse_cities(cities) == {9301: 2, 9302: None}
    assert parse_stadiums(stadiums) == {9401: 1}


def test_reads_the_nation_and_population_of_a_local_region():
    regions = synthetic.record_table(
        [
            (9601, synthetic.local_region_record(1, 2_500_000, languages=((8, 60), (22, 40)))),
            (9602, synthetic.local_region_record(weather=0)),
        ]
    )

    assert parse_local_regions(regions) == [
        LocalRegion(9601, 1, 2_500_000),
        LocalRegion(9602, None, None),
    ]


@pytest.mark.parametrize(
    "record",
    [
        pytest.param(b"\x01" + synthetic.local_region_record()[1:], id="another first byte"),
        pytest.param(synthetic.local_region_record(languages=((8, 100),))[:-1], id="cut short"),
        pytest.param(synthetic.local_region_record() + b"\x00", id="a byte too many"),
    ],
)
def test_a_local_region_of_another_shape_is_an_error(record):
    with pytest.raises(PlacesError, match="local region 9601"):
        parse_local_regions(synthetic.record_table([(9601, record)]))


@pytest.mark.parametrize(
    "parse",
    [parse_clubs, parse_teams, parse_cities, parse_stadiums, parse_derbies, parse_local_regions],
)
@pytest.mark.parametrize(
    "content",
    [b"", b"\x03\x01tad.", b"\x00" * 40],
    ids=["empty", "short", "no tag"],
)
def test_broken_tables_raise_a_format_error(parse, content):
    with pytest.raises(FormatError):
        parse(content)


@pytest.mark.parametrize(
    ("parse", "start"),
    [
        (parse_clubs, b"\x00"),
        (parse_teams, b"\x0a\x00"),
        (parse_cities, b""),
        (parse_stadiums, b""),
        (parse_derbies, b"\x00"),
    ],
)
def test_a_record_that_is_too_short_is_an_error(parse, start):
    with pytest.raises(FormatError):
        parse(synthetic.record_table([(9101, start + b"\x09")]))
