"""The name and birth date in a people_db record, which stand just before the nation marker.

The name block is three numbered names (first, second, common), each followed by a zero byte, then
the full name as text. The birth date follows it.
"""

import calendar
import datetime
import struct
from dataclasses import dataclass

BIRTH_DATE_BEFORE_MARK = 12
MAX_NAME_BYTES = 80
NO_NAME = 0xFFFFFFFF
EARLIEST_BIRTH_YEAR, LATEST_BIRTH_YEAR = 1900, 2014


@dataclass(slots=True, frozen=True)
class Names:
    """Name texts by number: first names, second names, common names."""

    first: dict[int, str]
    second: dict[int, str]
    common: dict[int, str]


@dataclass(slots=True, frozen=True)
class Identity:
    name: str
    """The name to show."""
    full_name: str
    birth_date: datetime.date


def read_identity(record: bytes, marker_at: int, names: Names) -> Identity | None:
    """The name and birth date in front of a nation marker, or None when they do not check out."""
    date_at = marker_at - BIRTH_DATE_BEFORE_MARK
    if date_at < 0:
        return None
    day, year = struct.unpack_from("<HH", record, date_at)
    if not EARLIEST_BIRTH_YEAR <= year <= LATEST_BIRTH_YEAR:
        return None
    if not 1 <= day <= 365 + calendar.isleap(year):
        return None
    for size in range(MAX_NAME_BYTES + 1):
        length_at = date_at - size - 4
        if length_at < 15:
            break
        if struct.unpack_from("<I", record, length_at)[0] != size:
            continue
        name = _read_names(record, length_at, size, names)
        if name is not None:
            full_name, display = name
            birth_date = datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)
            return Identity(display, full_name, birth_date)
    return None


def _read_names(record: bytes, length_at: int, size: int, names: Names) -> tuple[str, str] | None:
    """The stored full name and the name to show, or None when the block is not a name block."""
    separators = (record[length_at - 1], record[length_at - 6], record[length_at - 11])
    if any(separators):
        return None
    try:
        full_name = record[length_at + 4 : length_at + 4 + size].decode()
    except UnicodeDecodeError:
        return None
    first, second, common = (
        struct.unpack_from("<I", record, length_at - back)[0] for back in (15, 10, 5)
    )
    if first not in names.first or second not in names.second:
        return None
    if common != NO_NAME and common not in names.common:
        return None
    if common != NO_NAME:
        return full_name, names.common[common]
    return full_name, full_name or f"{names.first[first]} {names.second[second]}"
