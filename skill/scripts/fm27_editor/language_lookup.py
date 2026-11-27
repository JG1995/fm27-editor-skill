"""The table of the lookup for languages, which people speak.

A language record holds its own name in English, so it needs no table of names in lang_db.dat.
"""

import sqlite3

from fm27_editor.binary import Reader
from fm27_editor.dat_tables import DatError, read_records
from fm27_editor.place_lookup import Tables, insert_rows

LANGUAGES = "table_8"
CLIENT_TABLES = {LANGUAGES}
SCHEMA = "CREATE TABLE language(uid INTEGER PRIMARY KEY, name TEXT);"
HEAD = b"\x00"
# Behind the name: family, group, difficulty, and more, which the lookup does not use.
TAIL_SIZE = 17


def insert_languages(cache: sqlite3.Connection, client: Tables) -> None:
    insert_rows(cache, "language", list(parse_languages(client[LANGUAGES]).items()))


def parse_languages(table: bytes) -> dict[int, str]:
    """The name of each language, by its ID."""
    names = {}
    for record in read_records(table):
        reader = Reader(record.data, DatError)
        head = reader.take(len(HEAD))
        names[record.uid] = reader.text()
        tail = len(record.data) - reader.position
        if head != HEAD or tail != TAIL_SIZE:
            raise DatError(
                f"language {record.uid} starts with {head.hex()} and has {tail} bytes after its"
                f" name; expected {HEAD.hex()} and {TAIL_SIZE}"
            )
    return names
