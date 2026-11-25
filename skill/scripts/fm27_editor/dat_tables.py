"""Reading the files of the Editor's base database: a 12-byte prefix, then a stream or tables."""

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from fm27_editor.binary import FormatError, Reader, unpack_frame
from fm27_editor.container import ContainerError, read_members

PREFIX_TAG = b"\x03\x01tad."
PREFIX_SIZE = 12
# Bytes 6-7 of every file in the database checked. Their meaning is inferred, not known.
DATABASE_VERSION = 4000
TABLE_TAG_SIZE = 8
RECORD_IDS_SIZE = 12
NO_RECORD = 0xFFFFFFFF
TABLE_FOOTER_SIZE = 9
MAX_RECORD_SIZE = 64 * 1024
MAX_STREAM_SIZE = 4 * 1024 * 1024 * 1024


class DatError(FormatError):
    """The bytes are not a base database file this library can read."""


@dataclass(frozen=True, slots=True)
class Record:
    uid: int
    data: bytes


def read_stream(path: Path) -> bytes:
    """The body of a file that is one compressed stream, such as people_db.dat."""
    return unpack_frame(_body(path), path.name, DatError, MAX_STREAM_SIZE)


def read_tables(path: Path, names: set[str]) -> dict[str, bytes]:
    """The named tables of a file that is a container, such as client_db.dat."""
    try:
        tables = read_members(_body(path), names)
    except ContainerError as error:
        raise DatError(f"{path.name}: {error}") from error
    missing = names - tables.keys()
    if missing:
        raise DatError(f"{path.name} has no table {', '.join(sorted(missing))}")
    return tables


def open_table(table: bytes) -> tuple[Reader, int]:
    """A reader behind the table's header, and the number of records it announces."""
    reader = Reader(table, DatError)
    if reader.take(len(PREFIX_TAG)) != PREFIX_TAG:
        raise DatError("not a database table")
    reader.take(TABLE_TAG_SIZE - len(PREFIX_TAG))
    return reader, reader.u32()


def read_string_table(table: bytes) -> dict[int, str]:
    """Texts by number, for example first names."""
    reader, count = open_table(table)
    texts = {}
    for _ in range(count):
        number = reader.u32()
        texts[number] = reader.text()
    return texts


def read_records(table: bytes) -> Iterator[Record]:
    """The records of a table in order. Each ends in its index, counted from 0, and its ID twice."""
    reader, count = open_table(table)
    reader.take(1)  # 0 in every table checked
    position = reader.position
    for index in range(count):
        end = _record_end(table, position, index)
        yield Record(struct.unpack_from("<I", table, end + 4)[0], table[position:end])
        position = end + RECORD_IDS_SIZE
    if position + TABLE_FOOTER_SIZE != len(table):
        raise DatError(f"{len(table) - position} bytes follow the last record")


def index_at(data: bytes, offset: int) -> int | None:
    """The place of another record in its table, if there is one."""
    index = struct.unpack_from("<I", data, offset)[0]
    return None if index == NO_RECORD else index


def _record_end(table: bytes, position: int, index: int) -> int:
    """Where the index and ID that end a record start.

    Zero bytes in front of index 0 make the ID readable up to three bytes early, so the last of
    overlapping readings is the aligned one. No first ID has a lowest byte of 0, which would make it
    readable late.
    """
    marker = struct.pack("<I", index)
    limit = position + MAX_RECORD_SIZE
    at = table.find(marker, position, limit)
    while at >= 0:
        if _are_ids(table, at, marker):
            return max(start for start in range(at, at + 4) if _are_ids(table, start, marker))
        at = table.find(marker, at + 1, limit)
    raise DatError(f"record {index} has no readable end")


def _are_ids(table: bytes, at: int, marker: bytes) -> bool:
    if at + RECORD_IDS_SIZE > len(table) or table[at : at + 4] != marker:
        return False
    uid, repeated = struct.unpack_from("<II", table, at + 4)
    return uid == repeated and uid not in (0, NO_RECORD)


def _body(path: Path) -> bytes:
    content = path.read_bytes()
    if content[: len(PREFIX_TAG)] != PREFIX_TAG or len(content) <= PREFIX_SIZE:
        raise DatError(f"{path.name} is not an Editor database file")
    version = struct.unpack_from("<H", content, len(PREFIX_TAG))[0]
    if version != DATABASE_VERSION:
        raise DatError(
            f"{path.name} has database version {version}, only {DATABASE_VERSION} is known"
        )
    return content[PREFIX_SIZE:]
