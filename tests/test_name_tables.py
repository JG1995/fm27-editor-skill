import pytest

import synthetic
from fm27_editor.dat_tables import DatError
from fm27_editor.name_tables import NamedTable, read_names


@pytest.mark.parametrize(
    ("kind", "table", "names"),
    [
        (
            NamedTable.NATION,
            synthetic.nation_names({9001: "Englandia", 9002: "Norwegia"}),
            {9001: ("Englandia", "Englandia"), 9002: ("Norwegia", "Norwegia")},
        ),
        (
            NamedTable.CLUB,
            synthetic.club_names({9101: ("Fictional City", "Fic"), 9102: ("Žofia Ægir", "Žo")}),
            {9101: ("Fictional City", "Fic"), 9102: ("Žofia Ægir", "Žo")},
        ),
        (
            NamedTable.COMPETITION,
            synthetic.competition_names({9201: ("Example League", "League")}),
            {9201: ("Example League", "League")},
        ),
        (
            NamedTable.AWARD,
            synthetic.award_names({9501: ("Example Player of the Year", "Player")}),
            {9501: ("Example Player of the Year", "Player")},
        ),
        (NamedTable.CITY, synthetic.city_names({9301: "Testby"}), {9301: ("Testby", None)}),
        (
            NamedTable.CONTINENT,
            synthetic.continent_names({3: "Europia"}),
            {3: ("Europia", None)},
        ),
        (
            NamedTable.INJURY,
            synthetic.injury_names({6: "twisted ankle"}),
            {6: ("twisted ankle", None)},
        ),
        (
            NamedTable.DERBY,
            synthetic.derby_names({50: ("Fictional Derby", "Derby")}),
            {50: ("Fictional Derby", "Derby")},
        ),
        (
            NamedTable.MEDIA_SOURCE,
            synthetic.media_source_names({18: "Testby Echo"}),
            {18: ("Testby Echo", None)},
        ),
        (
            NamedTable.STAGE_NAME,
            synthetic.stage_names({3: "Final"}),
            {3: ("Final", "Fina")},
        ),
        (
            NamedTable.LOCAL_REGION,
            synthetic.local_region_names({9601: "Testshire"}),
            {9601: ("Testshire", None)},
        ),
        (
            NamedTable.AGREEMENT,
            synthetic.award_names({1: ("Example Union", "EU")}),
            {1: ("Example Union", "EU")},
        ),
        (
            NamedTable.STADIUM,
            synthetic.stadium_names({9401: "Test Park"}),
            {9401: ("Test Park", None)},
        ),
    ],
    ids=lambda value: value.name.lower() if isinstance(value, NamedTable) else "",
)
def test_reads_names_and_short_names(kind, table, names):
    assert read_names(kind, table) == names


def test_bytes_after_the_last_name_are_an_error():
    with pytest.raises(DatError):
        read_names(NamedTable.CITY, synthetic.city_names({9301: "Testby"}) + b"\x00")


def test_a_table_of_another_shape_is_an_error():
    with pytest.raises(DatError):
        read_names(NamedTable.CLUB, synthetic.city_names({9301: "Testby", 9302: "Testham"}))
