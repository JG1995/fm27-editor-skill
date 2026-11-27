"""The tables of the lookup for kinds of records that it knows only by name, and currencies.

Languages, weather, and currencies hold their own names; continents and injuries are named in
lang_db.dat. Currencies also say how many of them make a pound.
"""

import sqlite3

from fm27_editor.dat_tables import read_records
from fm27_editor.name_tables import NamedTable, read_names
from fm27_editor.named_records import parse_currencies, parse_named_records
from fm27_editor.place_lookup import Tables, insert_rows

# The table of each kind whose records hold their own name, and how many bytes follow the name:
# for a language its family, group, difficulty, and more; for a weather its chances of rain, wind,
# and heat in each season.
IN_RECORDS = {"language": ("table_8", 17), "weather": ("table_27", 95)}
# The table of each kind named in lang_db.dat, and the table of its names in English.
IN_NAME_TABLES = {
    "continent": ("table_5", NamedTable.CONTINENT, "8_5"),
    "injury": ("table_6", NamedTable.INJURY, "8_6"),
}
CURRENCIES = "table_41"
CLIENT_TABLES = {
    CURRENCIES,
    *(table for table, *_ in [*IN_RECORDS.values(), *IN_NAME_TABLES.values()]),
}
NAME_TABLES = {english for _, _, english in IN_NAME_TABLES.values()}
VIEWS = {"continent": "continents", "injury": "injuries", "weather": "weathers"}
SCHEMA = "".join(
    [
        *(f"CREATE TABLE {kind}(uid INTEGER PRIMARY KEY, name TEXT);" for kind in IN_RECORDS),
        *(f"CREATE TABLE {kind}(uid INTEGER PRIMARY KEY, name TEXT);" for kind in IN_NAME_TABLES),
        *(f"CREATE VIEW {view} AS SELECT * FROM {kind};" for kind, view in VIEWS.items()),
        "CREATE TABLE currency(uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, symbol TEXT,"
        " per_pound REAL);",
    ]
)


def insert_names(cache: sqlite3.Connection, client: Tables, name_tables: Tables) -> None:
    """A record without a name in English is kept with an empty one."""
    for kind, (table, tail_size) in IN_RECORDS.items():
        names = parse_named_records(client[table], kind, tail_size)
        insert_rows(cache, kind, list(names.items()))
    for kind, (table, layout, english) in IN_NAME_TABLES.items():
        names = read_names(layout, name_tables[english])
        rows = [(uid, names[uid][0] if uid in names else None) for uid in _uids(client[table])]
        insert_rows(cache, kind, rows)
    rows = [
        (
            uid,
            currency.name,
            currency.short_name,
            currency.symbol or None,
            currency.per_pound or None,
        )
        for uid, currency in parse_currencies(client[CURRENCIES]).items()
    ]
    insert_rows(cache, "currency", rows)


def _uids(table: bytes) -> list[int]:
    return [record.uid for record in read_records(table)]
