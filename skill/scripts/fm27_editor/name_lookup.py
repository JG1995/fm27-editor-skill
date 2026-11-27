"""The tables of the lookup for kinds of records that it knows only by name, such as languages.

A language record holds its own name, so it needs no name table of lang_db.dat.
"""

import sqlite3

from fm27_editor.named_records import parse_named_records
from fm27_editor.place_lookup import Tables, insert_rows

LANGUAGES = "table_8"
# Behind the name of a language: family, group, difficulty, and more.
LANGUAGE_TAIL_SIZE = 17
CLIENT_TABLES = {LANGUAGES}
SCHEMA = "CREATE TABLE language(uid INTEGER PRIMARY KEY, name TEXT);"


def insert_names(cache: sqlite3.Connection, client: Tables) -> None:
    languages = parse_named_records(client[LANGUAGES], "language", LANGUAGE_TAIL_SIZE)
    insert_rows(cache, "language", list(languages.items()))
