"""What can be set on a record: the fields of each kind, and the values that make sense in them.

A value must be one the Editor's definitions allow, and what it refers to must be in the lookup.
"""

import datetime
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from fm27_editor.base_database import record_name
from fm27_editor.change_reading import EditError
from fm27_editor.field_definitions import Field, read_fields
from fm27_editor.potential import PLAYER_POTENTIAL, POTENTIAL_RANGE, check_potential
from fm27_editor.record_changes import FieldValue, refusal, stored_value
from fm27_editor.record_kinds import CLUB, COMPETITION, RecordKind

# The lookup's table for what a field points to.
LOOKUP_TABLES = {
    "nation": "nation",
    "team": "club",
    "club": "club",
    "competition": "competition",
    "city": "city",
    "stadium": "stadium",
}
NEW_KINDS = {"team": CLUB, "club": CLUB, "competition": COMPETITION}
NEW_MARK = "@"


@dataclass(frozen=True)
class NewReference:
    """A record that the same request creates, by the name it has there."""

    name: str


@dataclass(frozen=True)
class Setting:
    """A field and the value it is to have."""

    field: Field
    value: FieldValue | NewReference

    @property
    def as_the_lookup_says(self) -> object:
        return self.value.isoformat() if isinstance(self.value, datetime.date) else self.value


NO_NEW: Mapping[str, RecordKind] = {}


class RecordRules:
    def __init__(self, editor_dir: Path, lookup: sqlite3.Connection):
        self._editor_dir = editor_dir
        self._lookup = lookup
        self._fields: dict[RecordKind, dict[str, Field]] = {}

    def fields(self, kind: RecordKind) -> dict[str, Field]:
        """The fields a record of this kind has, by code."""
        if kind not in self._fields:
            self._fields[kind] = self._read_fields(kind)
        return self._fields[kind]

    def writable_fields(self, kind: RecordKind) -> list[Field]:
        """The fields that can be given a value, by code."""
        return [
            field
            for _, field in sorted(self.fields(kind).items())
            if refusal(field) is None and field.points_to in (None, *LOOKUP_TABLES)
        ]

    def settings(
        self,
        kind: RecordKind,
        values: Mapping[str, FieldValue],
        new: Mapping[str, RecordKind] = NO_NEW,
    ) -> list[Setting]:
        """The checked settings for these values.

        Facts the lookup has are given by its names; any other field is given by its code. A date
        may be given as text, the way the lookup holds it, and yes or no as 1 or 0. A record among
        `new` is referred to by its name there, with a mark in front.
        """
        chosen: dict[str, Setting] = {}
        for name, given in values.items():
            field = self._field(kind, name)
            if field.code in chosen:
                raise EditError(f"{field.name} ({field.code}) is given twice")
            chosen[field.code] = Setting(field, self._value(field, given, new))
        return list(chosen.values())

    def new_record_settings(
        self,
        kind: RecordKind,
        values: Mapping[str, FieldValue],
        new: Mapping[str, RecordKind] = NO_NEW,
    ) -> list[Setting]:
        settings = self.settings(kind, values, new)
        given = {setting.field.code for setting in settings}
        missing = [f"{name} ({code})" for code, name in kind.needed.items() if code not in given]
        if missing:
            raise EditError(f"a new {kind.name} needs {', '.join(missing)}")
        return settings

    def _read_fields(self, kind: RecordKind) -> dict[str, Field]:
        fields: dict[str, Field] = {}
        for definitions in kind.defined_in:
            fields |= read_fields(self._editor_dir, definitions)
        if PLAYER_POTENTIAL in fields and POTENTIAL_RANGE in fields:
            # The Editor shows potential as two fields, a number and a choice of ranges.
            ranges = fields[POTENTIAL_RANGE].choices
            fields[PLAYER_POTENTIAL] = replace(fields[PLAYER_POTENTIAL], choices=ranges)
        return {code: field for code, field in fields.items() if kind.offers(code)}

    def _field(self, kind: RecordKind, name: str) -> Field:
        field = self.fields(kind).get(kind.codes.get(name, name))
        if field is None:
            raise EditError(f"{kind.name} has no field {name}")
        return field

    def _value(
        self, field: Field, given: FieldValue, new: Mapping[str, RecordKind]
    ) -> FieldValue | NewReference:
        if field.points_to is not None and isinstance(given, str) and given.startswith(NEW_MARK):
            return _new_reference(field, given, new)
        value = _typed(field, given)
        self._check(field, value)
        return value

    def _check(self, field: Field, value: FieldValue) -> None:
        stored_value(field, value)
        self._check_exists(field, value)
        if field.code == PLAYER_POTENTIAL:
            check_potential(field, value)

    def _check_exists(self, field: Field, value: FieldValue) -> None:
        if field.points_to is None:
            return
        table = LOOKUP_TABLES.get(field.points_to)
        if table is None:
            raise EditError(
                f"{field.name} ({field.code}) points to a {field.points_to}, "
                "which the lookup does not hold"
            )
        if record_name(self._lookup, table, value) is None:
            raise EditError(f"{field.name} ({field.code}): there is no {table} {value!r}")


def _new_reference(field: Field, given: str, new: Mapping[str, RecordKind]) -> NewReference:
    reason = refusal(field)
    if reason is not None:
        raise EditError(f"{field.name} ({field.code}) {reason}")
    name = given.removeprefix(NEW_MARK)
    if name not in new:
        raise EditError(f"{field.name} ({field.code}): no new record above is called {given}")
    if new[name] is not NEW_KINDS.get(field.points_to):
        raise EditError(
            f"{field.name} ({field.code}) points to a {field.points_to}, "
            f"and {given} is a {new[name].name}"
        )
    return NewReference(name)


def _typed(field: Field, given: FieldValue) -> FieldValue:
    if field.type == "boolean" and isinstance(given, int) and given in (0, 1):
        return bool(given)
    if field.type == "date" and isinstance(given, str):
        try:
            return datetime.date.fromisoformat(given)
        except ValueError as error:
            raise EditError(
                f"{field.name} ({field.code}) needs a date such as 2008-04-25, not {given!r}"
            ) from error
    return given
