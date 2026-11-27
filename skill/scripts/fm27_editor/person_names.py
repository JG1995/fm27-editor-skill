"""The name and birth date in a people_db record, which stand just before the nation marker.

The name block is three names (first, second, common), then the full name as text. Each of the three
is the number of a name in a name table, then a zero byte. A name that the tables lack is written
out instead: its number, a one byte, the text, the number again, and twelve bytes about the name.
The birth date follows the block. The game shows the common name, or else the first and second.
"""

import calendar
import datetime
import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

BIRTH_DATE_BEFORE_MARK = 12
MAX_NAME_BYTES = 200
NO_NAME = 0xFFFFFFFF
IN_TABLE, WRITTEN_OUT = 0, 1
# The name's nation, how often it is used, and three more numbers.
WRITTEN_OUT_TAIL = 12
EARLIEST_BIRTH_YEAR, LATEST_BIRTH_YEAR = 1900, 2014
# The Editor's date for no date, in people's records and the files of their histories alike.
NO_DATE = datetime.date(1900, 1, 1)


@dataclass(slots=True, frozen=True)
class Names:
    """Name texts by number: first names, second names, common names."""

    first: dict[int, str]
    second: dict[int, str]
    common: dict[int, str]


@dataclass(slots=True, frozen=True)
class Identity:
    name: str
    """The name the game shows."""
    full_name: str | None
    """As the record holds it; None when it holds none."""
    birth_date: datetime.date | None
    """None when the record says the first day of 1900, which stands for no date."""


def read_identity(record: bytes, marker_at: int, names: Names) -> Identity | None:
    """The name and birth date in front of a nation marker, or None when they do not check out."""
    date_at = marker_at - BIRTH_DATE_BEFORE_MARK
    if date_at < 0:
        return None
    birth_date = read_date(record, date_at)
    if birth_date is None or not EARLIEST_BIRTH_YEAR <= birth_date.year <= LATEST_BIRTH_YEAR:
        return None
    for length_at, full_name in _texts_ending_at(record, date_at):
        commons = _names_ending_at(record, length_at, names.common, can_be_none=True)
        for common_at, common in commons:
            for second_at, second in _names_ending_at(record, common_at, names.second):
                for _, first in _names_ending_at(record, second_at, names.first):
                    name = common or " ".join(part for part in (first, second) if part)
                    known = None if birth_date == NO_DATE else birth_date
                    return Identity(name, full_name or None, known)
    return None


def read_date(record: bytes, at: int) -> datetime.date | None:
    """A date stored as the day of the year, counted from 1, and the year; None if it is not one."""
    day, year = struct.unpack_from("<HH", record, at)
    if not datetime.MINYEAR <= year <= datetime.MAXYEAR:
        return None
    if not 1 <= day <= 365 + calendar.isleap(year):
        return None
    return datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)


def _texts_ending_at(record: bytes, end: int) -> Iterator[tuple[int, str]]:
    """Each text with its length in front that could end at `end`: where it starts, and the text."""
    for size in range(min(MAX_NAME_BYTES, end - 4) + 1):
        length_at = end - size - 4
        if _number(record, length_at) == size:
            text = _decoded(record[length_at + 4 : end])
            if text is not None:
                yield length_at, text


def _names_ending_at(
    record: bytes, end: int, table: Mapping[int, str], *, can_be_none: bool = False
) -> Iterator[tuple[int, str | None]]:
    """Each way a name of the block could end at `end`: where it starts, and the name it gives."""
    if end >= 5 and record[end - 1] == IN_TABLE:
        number = _number(record, end - 5)
        if number in table:
            yield end - 5, table[number]
        elif can_be_none and number == NO_NAME:
            yield end - 5, None
    number_at = end - WRITTEN_OUT_TAIL - 4
    if number_at < 0:
        return
    number = _number(record, number_at)
    for length_at, text in _texts_ending_at(record, number_at):
        start = length_at - 5
        if start >= 0 and record[length_at - 1] == WRITTEN_OUT and _number(record, start) == number:
            yield start, text


def _number(record: bytes, at: int) -> int:
    return struct.unpack_from("<I", record, at)[0]


def _decoded(raw: bytes) -> str | None:
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return None
