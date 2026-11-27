"""Names in one language: the tables of lang_db.dat, which hold one row of texts per record."""

from enum import Enum

from fm27_editor.dat_tables import DatError, open_table

TEXT = "text"
# Texts and runs of other bytes, in order. Those bytes are flags, or a number that is not used here.
type Layout = tuple[str | int, ...]


class NamedTable(Enum):
    """What a table names, and the shape of its rows behind the ID."""

    NATION = (TEXT, 1, TEXT, 1, TEXT, TEXT, 1)
    CLUB = (TEXT, 1, TEXT, 1, TEXT, TEXT, TEXT, 1, TEXT, 4, TEXT)
    COMPETITION = (TEXT, 1, TEXT, 1, TEXT, 1)
    AWARD = (TEXT, 1, TEXT, 2)
    CITY = (TEXT, 2)
    STADIUM = (TEXT, TEXT, 3)


WITH_SHORT_NAMES = {
    NamedTable.NATION,
    NamedTable.CLUB,
    NamedTable.COMPETITION,
    NamedTable.AWARD,
}


def read_names(kind: NamedTable, table: bytes) -> dict[int, tuple[str, str | None]]:
    """Name and short name by ID; cities and stadiums have no short name."""
    reader, count = open_table(table)
    names = {}
    for _ in range(count):
        uid = reader.u32()
        texts = []
        for part in kind.value:
            if part == TEXT:
                texts.append(reader.text())
            else:
                reader.take(part)
        names[uid] = (texts[0], texts[1] if kind in WITH_SHORT_NAMES else None)
    if not reader.at_end:
        raise DatError(f"bytes follow the last {kind.name.lower()} name")
    return names
