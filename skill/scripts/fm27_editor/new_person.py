"""Creating a person: one change that adds the record, then one for each field."""

import sqlite3
from collections.abc import Mapping
from pathlib import Path

from fm27_editor.field_definitions import Field, read_fields
from fm27_editor.people import PersonKind
from fm27_editor.person_codes import person_codes
from fm27_editor.record_changes import (
    Change,
    EditError,
    FieldValue,
    NewIds,
    Table,
    add_record,
    field_change,
)

DEFINED_IN = {PersonKind.PLAYER: "player", PersonKind.STAFF: "non player"}
# The added record says the person type. The Editor works out the others, or shows them only in the
# game, though its definitions do not mark them.
NOT_SET_BY_HAND = {
    *("Ptyp", "Page", "PnRV", "PShN", "dbnm", "Pbrl", "ERCL", "Pnhs", "NpCw"),
    *("PcHC", "Pion", "Phij", "Phbn"),
    *("PCRI", "PHRI", "PWRI", "NcrI", "NhmI", "NwrI"),
    *(f"BR{position:02}" for position in range(1, 15)),
}
PLAYER_POTENTIAL, POTENTIAL_RANGE = "PPAB", "PPAR"
LOOKUP_TABLES = {"nation": "nation", "team": "club", "club": "club"}
REQUIRED = {
    "Pfna": "First Name",
    "Psna": "Second Name",
    "Pdob": "Date Of Birth",
    "Pnti": "Nation",
}


def person_fields(editor_dir: Path, kind: PersonKind) -> dict[str, Field]:
    """The fields a person of this kind has, by code."""
    if kind not in DEFINED_IN:
        raise EditError(f"a new person must be a player or staff, not {kind.name.lower()}")
    fields = read_fields(editor_dir, DEFINED_IN[kind]) | read_fields(editor_dir, "person")
    return {code: field for code, field in fields.items() if code not in NOT_SET_BY_HAND}


def new_person(
    kind: PersonKind,
    values: Mapping[str, FieldValue],
    fields: Mapping[str, Field],
    ids: NewIds,
    lookup: sqlite3.Connection,
) -> list[Change]:
    """The changes that create a person with these values.

    Facts the lookup has are given by its names; any other field is given by its code. Nations and
    clubs must exist in the lookup.
    """
    chosen = _by_code(kind, values, fields)
    missing = [f"{name} ({code})" for code, name in REQUIRED.items() if code not in chosen]
    if missing:
        raise EditError(f"a new person needs {', '.join(missing)}")
    for code, value in chosen.items():
        _check_exists(fields[code], value, lookup)
    _check_potential(chosen.get(PLAYER_POTENTIAL), fields)
    record = ids.record()
    added = add_record(Table.PERSON, kind, record, ids)
    return [
        added,
        *(
            field_change(Table.PERSON, record, fields[code], value, ids)
            for code, value in chosen.items()
        ),
    ]


def _by_code(
    kind: PersonKind, values: Mapping[str, FieldValue], fields: Mapping[str, Field]
) -> dict[str, FieldValue]:
    codes = person_codes(kind)
    chosen: dict[str, FieldValue] = {}
    for name, value in values.items():
        code = codes.get(name, name)
        if code not in fields:
            raise EditError(f"{kind.name.lower()} has no field {name}")
        if code in chosen:
            raise EditError(f"{fields[code].name} ({code}) is given twice")
        chosen[code] = value
    return chosen


def _check_exists(field: Field, value: FieldValue, lookup: sqlite3.Connection) -> None:
    if field.points_to is None:
        return
    table = LOOKUP_TABLES.get(field.points_to)
    if table is None:
        raise EditError(
            f"{field.name} ({field.code}) points to a {field.points_to}, "
            "which the lookup does not hold"
        )
    if lookup.execute(f"SELECT 1 FROM {table} WHERE uid = ?", (value,)).fetchone() is None:
        raise EditError(f"{field.name} ({field.code}): there is no {table} {value!r}")


def _check_potential(value: FieldValue | None, fields: Mapping[str, Field]) -> None:
    """A negative potential stands for a range, and only some numbers do."""
    if not isinstance(value, int) or value >= 0:
        return
    ranges = fields[POTENTIAL_RANGE].choices if POTENTIAL_RANGE in fields else None
    if value not in (ranges or {}):
        raise EditError(f"{value} is not one of the Editor's potential ranges")
