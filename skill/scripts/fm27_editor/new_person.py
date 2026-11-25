"""Creating a person: one change that adds the record, then one for each field."""

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
PERSON_TYPE = "Ptyp"  # the added record says it already
REQUIRED = ("Pfna", "Psna", "Pdob", "Pnti")


def person_fields(editor_dir: Path, kind: PersonKind) -> dict[str, Field]:
    """The fields a person of this kind has, by code."""
    if kind not in DEFINED_IN:
        raise EditError(f"a new person must be a player or staff, not {kind.name.lower()}")
    fields = read_fields(editor_dir, DEFINED_IN[kind]) | read_fields(editor_dir, "person")
    return {code: field for code, field in fields.items() if code != PERSON_TYPE}


def new_person(
    kind: PersonKind,
    values: Mapping[str, FieldValue],
    fields: Mapping[str, Field],
    ids: NewIds,
) -> list[Change]:
    """The changes that create a person with these values.

    Facts the lookup has are given by its names; any other field is given by its code.
    """
    chosen = _by_code(kind, values, fields)
    missing = [f"{fields[code].name} ({code})" for code in REQUIRED if code not in chosen]
    if missing:
        raise EditError(f"a new person needs {', '.join(missing)}")
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
