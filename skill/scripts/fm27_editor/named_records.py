"""Records of the base database that hold their own name in English, such as languages.

Such a record is a zero byte, the name, and a fixed number of bytes that the lookup does not use.
"""

from fm27_editor.binary import FormatError, Reader
from fm27_editor.dat_tables import read_records

HEAD = b"\x00"


class NamedRecordError(FormatError):
    """A record that holds its own name does not follow the layout this library knows."""


def parse_named_records(table: bytes, one: str, tail_size: int) -> dict[int, str]:
    """The name of each record, by its ID; `one` is what a record is, for errors."""
    names = {}
    for record in read_records(table):
        reader = Reader(record.data, NamedRecordError)
        head = reader.take(len(HEAD))
        names[record.uid] = reader.text()
        tail = len(record.data) - reader.position
        if head != HEAD or tail != tail_size:
            raise NamedRecordError(
                f"{one} {record.uid} starts with {head.hex()} and has {tail} bytes after its"
                f" name; expected {HEAD.hex()} and {tail_size}"
            )
    return names
