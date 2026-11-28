"""Filling the lookup's tables: the tables read from the database, rows, and places as uids."""

import sqlite3
from collections.abc import Mapping, Sequence

from fm27_editor.places import PlacesError

type Tables = Mapping[str, bytes]


def insert_rows(cache: sqlite3.Connection, table: str, rows: Sequence[tuple]) -> None:
    if rows:
        placeholders = ", ".join("?" * len(rows[0]))
        cache.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def uid_at(uids: Sequence[int | None], index: int | None, kind: str) -> int | None:
    """The uid of the record at a place in its table, as records refer to one another."""
    if index is None:
        return None
    if index >= len(uids):
        raise PlacesError(f"there is no {kind} at index {index}")
    return uids[index]
