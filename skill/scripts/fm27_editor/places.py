"""Names of clubs and nations in the base database."""

import re
import struct

from fm27_editor.binary import FormatError

TABLE_HEADER_SIZE = 12
MAX_RECORD_SEARCH = 2000
MAX_CLUB_NAME_BYTES = 64
MAX_NATION_NAME_BYTES = 40
LENGTH = re.compile(rb"([\x02-\x40])\x00\x00\x00")
NATION_NAME_END = 0xFF


class PlacesError(FormatError):
    """The club or nation table does not follow the layout this library knows."""


def parse_clubs(table: bytes) -> dict[int, tuple[str | None, str | None]]:
    """Name and short name by club ID; a record whose name does not check out keeps None."""
    count = struct.unpack_from("<I", table, 8)[0]
    clubs, position = {}, TABLE_HEADER_SIZE
    for index in range(count):
        end, uid = _record_end(table, position, index)
        clubs[uid] = _club_names(table[position:end])
        position = end + 12
    return clubs


def parse_nations(table: bytes, uids: set[int]) -> dict[int, str]:
    """English nation names of `uids` found in the language table."""
    names = {}
    for uid in uids:
        name = _nation_name(table, uid)
        if name is not None:
            names[uid] = name
    return names


def _record_end(table: bytes, position: int, index: int) -> tuple[int, int]:
    """The end of the record for `index`: that index, then the ID twice.

    Zero bytes in front of a small index can make the pair readable a few bytes early, so the last
    of overlapping readings is the aligned one.
    """
    marker = struct.pack("<I", index)
    limit = position + MAX_RECORD_SEARCH
    at = table.find(marker, position, limit)
    while at >= 0:
        for start in range(at + 3, at - 1, -1):
            uid = _repeated_id(table, start, marker)
            if uid is not None:
                return start, uid
        at = table.find(marker, at + 1, limit)
    raise PlacesError(f"club {index} has no readable end")


def _repeated_id(table: bytes, at: int, marker: bytes) -> int | None:
    if at + 12 > len(table) or table[at : at + 4] != marker:
        return None
    uid, repeated = struct.unpack_from("<II", table, at + 4)
    return uid if uid == repeated and uid not in (0, 0xFFFFFFFF) else None


def _club_names(record: bytes) -> tuple[str | None, str | None]:
    for match in LENGTH.finditer(record):
        name = _text_at(record, match.start())
        if name is None:
            continue
        short_name = _text_at(record, match.end() + len(name.encode()))
        if short_name is not None:
            return name, short_name
    return None, None


def _text_at(record: bytes, at: int) -> str | None:
    if at + 4 > len(record):
        return None
    size = struct.unpack_from("<I", record, at)[0]
    raw = record[at + 4 : at + 4 + size]
    if not 2 <= size <= MAX_CLUB_NAME_BYTES or len(raw) != size:
        return None
    try:
        text = raw.decode()
    except UnicodeDecodeError:
        return None
    return text if text.isprintable() else None


def _nation_name(table: bytes, uid: int) -> str | None:
    marker = struct.pack("<I", uid)
    at = table.find(marker, TABLE_HEADER_SIZE)
    while at >= 0:
        size = struct.unpack_from("<I", table, at + 4)[0] if at + 8 <= len(table) else 0
        end = at + 8 + size
        if 2 <= size <= MAX_NATION_NAME_BYTES and table[end : end + 1] == bytes([NATION_NAME_END]):
            try:
                return table[at + 8 : end].decode()
            except UnicodeDecodeError:
                pass
        at = table.find(marker, at + 1)
    return None
