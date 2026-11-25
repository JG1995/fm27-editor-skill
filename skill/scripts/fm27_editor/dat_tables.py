"""Reading the files of the Editor's base database: a 12-byte prefix, then a stream or tables."""

import struct
from pathlib import Path

from fm27_editor.binary import FormatError, Reader, unpack_frame
from fm27_editor.container import ContainerError, read_members

PREFIX_TAG = b"\x03\x01tad."
PREFIX_SIZE = 12
# Bytes 6-7 of every file in the database checked. Their meaning is inferred, not known.
DATABASE_VERSION = 4000
TABLE_TAG_SIZE = 8
TABLE_FOOTER_SIZE = 9
MAX_STREAM_SIZE = 4 * 1024 * 1024 * 1024


class DatError(FormatError):
    """The bytes are not a base database file this library can read."""


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
