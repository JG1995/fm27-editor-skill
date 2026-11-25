"""Reading the files of the Editor's base database: a 12-byte prefix, then a stream or tables."""

from compression import zstd
from pathlib import Path

from fm27_editor.binary import FormatError, Reader
from fm27_editor.container import ContainerError, read_members

PREFIX_TAG = b"\x03\x01tad."
PREFIX_SIZE = 12


class DatError(FormatError):
    """The bytes are not a base database file this library can read."""


def read_stream(path: Path) -> bytes:
    """The body of a file that is one compressed stream, such as people_db.dat."""
    content = _body(path)
    try:
        return zstd.decompress(content)
    except zstd.ZstdError as error:
        raise DatError(f"{path.name} cannot be decompressed") from error


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


def read_string_table(table: bytes) -> dict[int, str]:
    """Texts by number, for example first names."""
    reader = Reader(table, DatError)
    if reader.take(len(PREFIX_TAG)) != PREFIX_TAG:
        raise DatError("not a database table")
    reader.take(2)
    texts = {}
    for _ in range(reader.u32()):
        number = reader.u32()
        texts[number] = reader.text()
    return texts


def _body(path: Path) -> bytes:
    content = path.read_bytes()
    if content[: len(PREFIX_TAG)] != PREFIX_TAG or len(content) <= PREFIX_SIZE:
        raise DatError(f"{path.name} is not an Editor database file")
    return content[PREFIX_SIZE:]
