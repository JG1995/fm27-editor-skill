"""People's playing histories: the seasons each person spent at clubs, from the pl_hist files.

pl_hist_index lists the uid of each person who has a history, with the number of its entry.
pl_hist_id gives each entry the offsets of its first and last season in pl_hist_dt. A season is 44
bytes and ends with the offset of the next season of the same history, or none after the last.
Checked on 2026-11-27 against the career of a well-known player: the years, clubs, appearances,
goals, fees, and the dates he joined and left each club hold. The bits of a flags byte are the
Editor's boxes and extras, as eight seasons that the Editor saved showed them on 2026-11-28; one
bit is no part the Editor saves. Two parts are not read: a second year, and a date that only the
last season holds.
"""

import struct
from collections.abc import Iterator
from typing import NamedTuple

import numpy as np

from fm27_editor.binary import FormatError
from fm27_editor.person_names import NO_DATE

SEASON = np.dtype(
    [
        ("year", "<u2"),
        ("second_year", "<u2"),
        ("flags", "u1"),
        ("apps", "u1"),
        ("goals", "u1"),
        ("fee", "<i4"),
        ("club", "<u4"),
        ("club_again", "<u4"),
        ("division", "<u4"),
        ("division_again", "<u4"),
        ("order", "u1"),
        ("joined_day", "<u2"),
        ("joined_year", "<u2"),
        ("left_day", "<u2"),
        ("left_year", "<u2"),
        ("last_date", "<u4"),
        ("next", "<u4"),
    ]
)
NO_ID = 0xFFFFFFFF
NOT_KNOWN = 255
NO_FEE = -1
ON_LOAN, YOUTH_TEAM, TRIBUNAL_FEE = 0x01, 0x02, 0x20
# The Editor's extras, such as a part exchange, are bits of the flags with the same numbers. One
# more bit is set in most seasons, but is no part the Editor saves.
EXTRAS, UNSAVED = 0x1C, 0x40
FLAGS = ON_LOAN | YOUTH_TEAM | TRIBUNAL_FEE | EXTRAS | UNSAVED
# One season was joined in 1887, so dates before the first day of 1900 are real too.
EARLIEST_YEAR, LATEST_YEAR = 1800, 2100
BATCH = 100_000


class PlayingHistoryError(FormatError):
    """The history files do not follow the layout this library knows."""


class Season(NamedTuple):
    """A season at a club; dates are text such as 2017-02-01, and missing values are None."""

    person_uid: int
    item: int
    """Its place in the person's history, counted from 0."""
    year: int
    order_in_year: int
    club_uid: int | None
    division_uid: int | None
    apps: int | None
    goals: int | None
    transfer_fee: int | None
    other: int | None
    """A choice the Editor offers instead of a fee, such as -2 for undisclosed."""
    date_joined: str | None
    date_left: str | None
    on_loan: int
    youth_team: int
    tribunal_fee: int
    extras: int | None
    """The sum of the numbers of the Editor's extras, such as 4 for a part exchange."""


def parse_playing_histories(index: bytes, offsets: bytes, items: bytes) -> Iterator[Season]:
    """Every season of every history, person after person, in the order the files hold them."""
    people, firsts, lasts = _entries(index, offsets, len(items))
    seasons = np.frombuffer(items, dtype=SEASON)
    _check_links(seasons, lasts)
    _check_flags(seasons)
    counts = (lasts - firsts) // SEASON.itemsize + 1
    person = np.repeat(people, counts)
    place = np.arange(len(seasons)) - np.repeat(firsts // SEASON.itemsize, counts)
    joined = _dates(seasons["joined_day"], seasons["joined_year"])
    left = _dates(seasons["left_day"], seasons["left_year"])
    for start in range(0, len(seasons), BATCH):
        part = slice(start, start + BATCH)
        some = seasons[part]
        fees = some["fee"].tolist()
        columns = zip(
            person[part].tolist(),
            place[part].tolist(),
            some["year"].tolist(),
            some["order"].tolist(),
            _missing(some["club"], NO_ID),
            _missing(some["division"], NO_ID),
            _missing(some["apps"], NOT_KNOWN),
            _missing(some["goals"], NOT_KNOWN),
            [fee if fee > NO_FEE else None for fee in fees],
            [fee if fee < NO_FEE else None for fee in fees],
            joined[part].tolist(),
            left[part].tolist(),
            *(_is_set(some["flags"], bit) for bit in (ON_LOAN, YOUTH_TEAM, TRIBUNAL_FEE)),
            _missing(some["flags"] & EXTRAS, 0),
            strict=True,
        )
        yield from map(Season._make, columns)


def _entries(index: bytes, offsets: bytes, size: int) -> tuple[np.ndarray, ...]:
    """The uid of each history and the offsets of its first and last season, checked to cover
    the seasons from the first to the last, each once."""
    count = struct.unpack_from("<I", index)[0] if len(index) >= 4 else -1
    if len(index) != 4 + 8 * count or len(offsets) != 8 * count:
        raise PlayingHistoryError("the history index and offsets do not list the same histories")
    pairs = np.frombuffer(index, dtype="<u4", offset=4).reshape(-1, 2)
    if not (pairs[:, 1] == np.arange(count)).all():
        raise PlayingHistoryError("the history index does not list its entries in order")
    spans = np.frombuffer(offsets, dtype="<u4").reshape(-1, 2).astype(np.int64)
    firsts, lasts = spans[:, 0], spans[:, 1]
    starts = np.concatenate([[0], lasts[:-1] + SEASON.itemsize])
    ends_at = lasts[-1] + SEASON.itemsize if count else 0
    if (
        size % SEASON.itemsize
        or (firsts != starts).any()
        or ((lasts - firsts) % SEASON.itemsize).any()
        or (lasts < firsts).any()
        or ends_at != size
    ):
        raise PlayingHistoryError("the histories do not cover their seasons one after another")
    return pairs[:, 0].astype(np.int64), firsts, lasts


def _check_links(seasons: np.ndarray, lasts: np.ndarray) -> None:
    expected = np.arange(1, len(seasons) + 1, dtype=np.int64) * SEASON.itemsize
    expected[lasts // SEASON.itemsize] = NO_ID
    wrong = np.flatnonzero(seasons["next"] != expected)
    if wrong.size:
        raise PlayingHistoryError(f"season {wrong[0]} does not point to the next one")


def _check_flags(seasons: np.ndarray) -> None:
    wrong = np.flatnonzero(seasons["flags"] & (0xFF & ~FLAGS))
    if wrong.size:
        raise PlayingHistoryError(f"season {wrong[0]} has a flag that is no known part")


def _dates(days: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Dates as text, None for the first day of 1900, which stands for no date."""
    leap = (years % 4 == 0) & ((years % 100 != 0) | (years % 400 == 0))
    valid = (days >= 1) & (days <= 365 + leap) & (years >= EARLIEST_YEAR) & (years <= LATEST_YEAR)
    wrong = np.flatnonzero(~valid)
    if wrong.size:
        raise PlayingHistoryError(f"season {wrong[0]} has a date that is not one")
    first_days = (years.astype(np.int64) - 1970).astype("datetime64[Y]").astype("datetime64[D]")
    text = np.datetime_as_string(first_days + (days.astype(np.int64) - 1), unit="D").astype(object)
    text[(days == NO_DATE.timetuple().tm_yday) & (years == NO_DATE.year)] = None
    return text


def _is_set(flags: np.ndarray, bit: int) -> list[int]:
    return ((flags & bit) != 0).astype(int).tolist()


def _missing(values: np.ndarray, missing: int) -> list[int | None]:
    return [None if value == missing else value for value in values.tolist()]
