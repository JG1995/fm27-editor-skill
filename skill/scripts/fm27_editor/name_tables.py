"""Names in one language: the tables of lang_db.dat, which hold one row of texts per record."""

from enum import Enum

from fm27_editor.dat_tables import DatError, open_table

TEXT = "text"
# Texts and runs of other bytes, in order. Those bytes are flags, or a number that is not used here.
type Layout = tuple[str | int, ...]


class NamedTable(Enum):
    """What a table names: the shape of its rows behind the ID, and whether a short name follows
    the name. Two tables can have rows of one shape, and are still two members."""

    layout: Layout
    has_short_names: bool

    def __new__(cls, layout: Layout, has_short_names: bool) -> NamedTable:
        # Numbered in order, because members of equal values would be one member.
        member = object.__new__(cls)
        member._value_ = len(cls.__members__)
        member.layout, member.has_short_names = layout, has_short_names
        return member

    NATION = ((TEXT, 1, TEXT, 1, TEXT, TEXT, 1), True)
    CLUB = ((TEXT, 1, TEXT, 1, TEXT, TEXT, TEXT, 1, TEXT, 4, TEXT), True)
    COMPETITION = ((TEXT, 1, TEXT, 1, TEXT, 1), True)
    AWARD = ((TEXT, 1, TEXT, 2), True)
    CITY = ((TEXT, 2), False)
    STADIUM = ((TEXT, TEXT, 3), False)
    # A three-letter name, the word for its people, and the full and short name of its federation
    CONTINENT = ((TEXT, 1, TEXT, TEXT, TEXT, 1, TEXT, 2), False)
    # The name as a sentence says it, such as "a cold"
    INJURY = ((TEXT, 1, TEXT, 2), False)
    MEDIA_SOURCE = ((TEXT, 1), False)
    # Two other names, which the Editor calls alternative ones, follow the name and short name.
    DERBY = ((TEXT, TEXT, TEXT, TEXT, 5), True)
    # The name, a short name, and the name of more than one, such as "Finals"
    STAGE_NAME = ((TEXT, 1, TEXT, 1, TEXT, 2), True)


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
