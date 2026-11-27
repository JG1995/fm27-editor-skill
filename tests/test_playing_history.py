import pytest

import synthetic
from fm27_editor.playing_history import PlayingHistoryError, Season, parse_playing_histories


def parse(histories):
    return list(parse_playing_histories(*synthetic.playing_histories(histories)))


def test_each_season_is_read_with_its_person_and_place_in_the_history():
    seasons = parse(
        {
            100: [
                synthetic.history_item(
                    2016,
                    1295,
                    order=2,
                    division=4501,
                    apps=16,
                    goals=0,
                    fee=87_621,
                    joined=(1, 2016),
                    left=(32, 2017),
                ),
                synthetic.history_item(2017, 1353, apps=14, goals=2, joined=(32, 2017)),
            ],
            101: [synthetic.history_item(2020, 9101)],
        }
    )

    assert seasons == [
        Season(100, 0, 2016, 2, 1295, 4501, 16, 0, 87_621, None, "2016-01-01", "2017-02-01"),
        Season(100, 1, 2017, 0, 1353, None, 14, 2, None, None, "2017-02-01", None),
        Season(101, 0, 2020, 0, 9101, None, 0, 0, None, None, None, None),
    ]


@pytest.mark.parametrize(
    ("fee", "transfer_fee", "other"),
    [(-1, None, None), (0, 0, None), (5_000, 5_000, None), (-2, None, -2), (-13, None, -13)],
)
def test_a_fee_below_minus_one_is_the_editors_other_choice(fee, transfer_fee, other):
    """The Editor offers Undisc. (-2), Nom. Fee (-3), and drafts in Other, and -1 is no fee."""
    (season,) = parse({100: [synthetic.history_item(2020, 9101, fee=fee)]})

    assert (season.transfer_fee, season.other) == (transfer_fee, other)


def test_apps_and_goals_of_255_are_not_known():
    (season,) = parse({100: [synthetic.history_item(2020, 9101, apps=255, goals=255)]})

    assert (season.apps, season.goals) == (None, None)


def test_no_club_is_missing():
    (season,) = parse({100: [synthetic.history_item(2020, synthetic.NO_INDEX)]})

    assert season.club_uid is None


def broken_next():
    index, offsets, items = synthetic.playing_histories(
        {100: [synthetic.history_item(2020, 9101), synthetic.history_item(2021, 9101)]}
    )
    return index, offsets, items[:40] + b"\x00\x00\x00\x00" + items[44:]


def offsets_with_a_gap():
    index, offsets, items = synthetic.playing_histories(
        {100: [synthetic.history_item(2020, 9101)], 101: [synthetic.history_item(2021, 9101)]}
    )
    return index, offsets, items[:44] + bytes(44) + items[44:]


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(broken_next(), id="a season that does not point to the next"),
        pytest.param(offsets_with_a_gap(), id="seasons that belong to nobody"),
        pytest.param(
            (
                *synthetic.playing_histories({100: [synthetic.history_item(2020, 9101)]})[:2],
                synthetic.history_item(2020, 9101, joined=(400, 2020)) + b"\xff" * 4,
            ),
            id="a date that is not one",
        ),
        pytest.param(
            (b"\x02\x00\x00\x00", *synthetic.playing_histories({})[1:]), id="a short index"
        ),
    ],
)
def test_histories_outside_the_known_layout_are_refused(files):
    with pytest.raises(PlayingHistoryError):
        list(parse_playing_histories(*files))
