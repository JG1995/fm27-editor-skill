"""Names in one language: the tables of lang_db.dat, which hold one row of texts per record."""

from enum import Enum

from fm27_editor.dat_tables import DatError, open_table

TEXT = "text"
# Texts and runs of other bytes, in order. Those bytes are flags, or a number that is not used here.
type Layout = tuple[str | int, ...]


class NamedTable(Enum):
    """What a table names: the shape of its rows behind the ID, and whether a short name follows
    the name. Two tables can have rows of one shape."""

    NATION = ((TEXT, 1, TEXT, 1, TEXT, TEXT, 1), True)
    CLUB = ((TEXT, 1, TEXT, 1, TEXT, TEXT, TEXT, 1, TEXT, 4, TEXT), True)
    COMPETITION = ((TEXT, 1, TEXT, 1, TEXT, 1), True)
    AWARD = ((TEXT, 1, TEXT, 2), True)
    CITY = ((TEXT, 2), False)
    STADIUM = ((TEXT, TEXT, 3), False)

    @property
    def layout(self) -> Layout:
        return self.value[0]

    @property
    def has_short_names(self) -> bool:
        return self.value[1]


def read_names(kind: NamedTable, table: bytes) -> dict[int, tuple[str, str | None]]:
    """Name and short name by ID; cities and stadiums have no short name."""
    reader, count = open_table(table)
    names = {}
    for _ in range(count):
        uid = reader.u32()
        texts = []
        for part in kind.layout:
            if part == TEXT:
                texts.append(reader.text())
            else:
                reader.take(part)
        names[uid] = (texts[0], texts[1] if kind.has_short_names else None)
    if not reader.at_end:
        raise DatError(f"bytes follow the last {kind.name.lower()} name")
    return names
