"""Languages in the base database. Each record holds its own name in English."""

from fm27_editor.binary import FormatError, Reader
from fm27_editor.dat_tables import read_records

HEAD = b"\x00"
# Behind the name: family, group, difficulty, and more, which the lookup does not use.
TAIL_SIZE = 17


class LanguagesError(FormatError):
    """A record of a language does not follow the layout this library knows."""


def parse_languages(table: bytes) -> dict[int, str]:
    """The name of each language, by its ID."""
    names = {}
    for record in read_records(table):
        reader = Reader(record.data, LanguagesError)
        head = reader.take(len(HEAD))
        names[record.uid] = reader.text()
        tail = len(record.data) - reader.position
        if head != HEAD or tail != TAIL_SIZE:
            raise LanguagesError(
                f"language {record.uid} starts with {head.hex()} and has {tail} bytes after its"
                f" name; expected {HEAD.hex()} and {TAIL_SIZE}"
            )
    return names
