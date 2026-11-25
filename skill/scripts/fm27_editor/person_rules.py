"""What can be set on a person: the fields of each kind, and the values that make sense in them.

A value must be one the Editor's definitions allow, and what it refers to must be in the lookup.
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fm27_editor.field_definitions import Field, read_fields
from fm27_editor.people import PersonKind
from fm27_editor.person_codes import person_codes
from fm27_editor.record_changes import EditError, FieldValue, stored_value

DEFINED_IN = {PersonKind.PLAYER: "player", PersonKind.STAFF: "non player"}
# The record itself says the person type. The Editor works out the others, or shows them only in the
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


@dataclass(frozen=True)
class Setting:
    """A field and the value it is to have."""

    field: Field
    value: FieldValue


class PersonRules:
    def __init__(self, editor_dir: Path, lookup: sqlite3.Connection):
        self._editor_dir = editor_dir
        self._lookup = lookup
        self._fields: dict[PersonKind, dict[str, Field]] = {}

    def fields(self, kind: PersonKind) -> dict[str, Field]:
        """The fields a person of this kind has, by code."""
        if kind not in DEFINED_IN:
            raise EditError(f"only players and staff can be set, not {kind.name.lower()}")
        if kind not in self._fields:
            self._fields[kind] = self._read_fields(kind)
        return self._fields[kind]

    def settings(self, kind: PersonKind, values: Mapping[str, FieldValue]) -> list[Setting]:
        """The checked settings for these values.

        Facts the lookup has are given by its names; any other field is given by its code.
        """
        chosen: dict[str, Setting] = {}
        for name, value in values.items():
            field = self._field(kind, name)
            if field.code in chosen:
                raise EditError(f"{field.name} ({field.code}) is given twice")
            self._check(kind, field, value)
            chosen[field.code] = Setting(field, value)
        return list(chosen.values())

    def new_person_settings(
        self, kind: PersonKind, values: Mapping[str, FieldValue]
    ) -> list[Setting]:
        settings = self.settings(kind, values)
        given = {setting.field.code for setting in settings}
        missing = [f"{name} ({code})" for code, name in REQUIRED.items() if code not in given]
        if missing:
            raise EditError(f"a new person needs {', '.join(missing)}")
        return settings

    def _read_fields(self, kind: PersonKind) -> dict[str, Field]:
        fields = read_fields(self._editor_dir, DEFINED_IN[kind])
        fields |= read_fields(self._editor_dir, "person")
        return {code: field for code, field in fields.items() if code not in NOT_SET_BY_HAND}

    def _field(self, kind: PersonKind, name: str) -> Field:
        field = self.fields(kind).get(person_codes(kind).get(name, name))
        if field is None:
            raise EditError(f"{kind.name.lower()} has no field {name}")
        return field

    def _check(self, kind: PersonKind, field: Field, value: FieldValue) -> None:
        stored_value(field, value)
        self._check_exists(field, value)
        if field.code == PLAYER_POTENTIAL:
            self._check_potential(kind, value)

    def _check_exists(self, field: Field, value: FieldValue) -> None:
        if field.points_to is None:
            return
        table = LOOKUP_TABLES.get(field.points_to)
        if table is None:
            raise EditError(
                f"{field.name} ({field.code}) points to a {field.points_to}, "
                "which the lookup does not hold"
            )
        query = f"SELECT 1 FROM {table} WHERE uid = ?"
        if self._lookup.execute(query, (value,)).fetchone() is None:
            raise EditError(f"{field.name} ({field.code}): there is no {table} {value!r}")

    def _check_potential(self, kind: PersonKind, value: FieldValue) -> None:
        """A negative potential stands for a range, and only some numbers do."""
        ranges = self.fields(kind).get(POTENTIAL_RANGE)
        if value < 0 and (ranges is None or value not in (ranges.choices or {})):
            raise EditError(f"{value} is not one of the Editor's potential ranges")
