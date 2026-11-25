import pytest

import synthetic
from fm27_editor.awards import (
    Award,
    AwardPlace,
    AwardsError,
    AwardYear,
    parse_award_years,
    parse_awards,
)
from fm27_editor.places import Gender

NO_INDEX = synthetic.NO_INDEX


def years(*records):
    table = synthetic.record_table(list(enumerate(records, 501)))
    return parse_award_years(table)


def test_reads_what_tells_an_award_from_others():
    table = synthetic.record_table(
        [
            (9501, synthetic.award_record(nation=2, competition=3, previous_winner=1)),
            (9502, synthetic.award_record(female=True)),
        ]
    )

    assert parse_awards(table) == [
        Award(9501, nation=2, competition=3, gender=Gender.MALE, previous_winner=1),
        Award(9502, nation=None, competition=None, gender=Gender.FEMALE, previous_winner=0),
    ]


def test_an_award_of_another_size_is_an_error():
    table = synthetic.record_table([(9501, synthetic.award_record() + b"\x09")])

    with pytest.raises(AwardsError, match="9501"):
        parse_awards(table)


def test_reads_who_came_first_to_third():
    (year,) = years(
        synthetic.award_year_record(
            7,
            1973,
            (12, "Alfa Striker", 9101, 47, 3000, 31, 2, 64),
            (NO_INDEX, "Old Master", 9102, 22, 0, 0, NO_INDEX, 0),
        )
    )

    assert year == AwardYear(
        uid=501,
        award=7,
        year=1973,
        places=(
            AwardPlace(12, "Alfa Striker", 9101, 47, 3000, 31, 2, 64),
            AwardPlace(None, "Old Master", 9102, 22, 0, 0, None, 0),
            AwardPlace(None, "", None, 0, 0, 0, None, 0),
        ),
        has_no_data=False,
        was_not_held=False,
    )


def test_reads_why_a_year_has_no_winner():
    held, unknown = years(
        synthetic.award_year_record(7, 2020, not_held=True),
        synthetic.award_year_record(7, 1940, no_data=True),
    )

    assert (held.was_not_held, held.has_no_data) == (True, False)
    assert (unknown.was_not_held, unknown.has_no_data) == (False, True)


@pytest.mark.parametrize(
    "record",
    [
        synthetic.award_year_record(7, 1973) + b"\x09",
        synthetic.award_year_record(7, 1973)[:-1],
        b"\x01" + synthetic.award_year_record(7, 1973)[1:],
        synthetic.award_year_record(7, 1973)[:-1] + b"\x02",
    ],
    ids=["longer", "shorter", "another kind", "not a yes or no"],
)
def test_a_year_of_another_shape_is_an_error(record):
    with pytest.raises(AwardsError, match="501"):
        years(record)
