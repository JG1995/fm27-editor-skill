"""The table of the lookup for languages, which people speak.

A language record holds its own name, so it needs no name table of lang_db.dat.
"""

import sqlite3

from fm27_editor.languages import parse_languages
from fm27_editor.place_lookup import Tables, insert_rows

LANGUAGES = "table_8"
CLIENT_TABLES = {LANGUAGES}
SCHEMA = "CREATE TABLE language(uid INTEGER PRIMARY KEY, name TEXT);"


def insert_languages(cache: sqlite3.Connection, client: Tables) -> None:
    insert_rows(cache, "language", list(parse_languages(client[LANGUAGES]).items()))
