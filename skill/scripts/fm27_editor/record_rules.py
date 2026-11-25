"""What can be set on a record: the fields of each kind, and the values that make sense in them.

A value must be one the Editor's definitions allow, and what it refers to must be in the lookup.
"""

import datetime
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

from fm27_editor.base_database import record_name
from fm27_editor.change_reading import EditError
from fm27_editor.field_definitions import Field, read_fields
from fm27_editor.potential import check_potential, with_ranges
from fm27_editor.record_changes import (
    HIGHEST_UID,
    FieldValue,
    checked_date,
    refusal,
    stored_value,
)
from fm27_editor.record_kinds import RecordKind

# The lookup's table for what a field points to.
LOOKUP_TABLES = {
    "nation": "nation",
    "team": "club",
    "club": "club",
    "competition": "competition",
    "city": "city",
    "stadium": "stadium",
}
NEW_MARK = "@"


@dataclass(frozen=True)
class NewReference:
    """A record that the same request creates, by the name it has there."""

    name: str

    def __str__(self) -> str:
        return f"{NEW_MARK}{self.name}"


@dataclass(frozen=True)
class Setting:
    """A field and the value it is to have."""

    field: Field
    value: FieldValue | NewReference
    words: Mapping[str, int] = dataclass_field(default_factory=dict, repr=False, compare=False)
    """The numbers of choices that the lookup holds as words."""

    @property
    def as_the_lookup_says(self) -> object:
        if isinstance(self.value, datetime.date):
            return self.value.isoformat()
        said = {number: word for word, number in self.words.items()}
        return said.get(self.value, self.value) if said else self.value


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
            words = kind.words.get(field.code, {})
            value = self._value(field, _number_of(given, words), new)
            chosen[field.code] = Setting(field, value, words)
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
        return {code: found for code, found in with_ranges(fields).items() if kind.offers(code)}

    def _field(self, kind: RecordKind, name: str) -> Field:
        field = self.fields(kind).get(kind.codes.get(name, name))
        if field is None:
            raise EditError(f"{kind.name} has no field {name}")
        return field

    def _value(
        self, field: Field, given: FieldValue, new: Mapping[str, RecordKind]
    ) -> FieldValue | NewReference:
        called = f"{field.name} ({field.code})"
        reason = refusal(field)
        if reason is not None:
            raise EditError(f"{called} {reason}")
        if field.points_to is not None:
            return self.refer(field.points_to, called, given, new)
        value = _typed(field, given)
        stored_value(field, value)
        check_potential(field, value)
        return value

    def refer(
        self, points_to: str, called: str, given: object, new: Mapping[str, RecordKind]
    ) -> int | NewReference:
        """A record that exists or is new, for something called `called` that points to it."""
        if is_new_reference(given):
            return _new_reference(points_to, called, given, new)
        self._check_exists(points_to, called, given)
        return given

    def _check_exists(self, points_to: str, called: str, uid: object) -> None:
        table = LOOKUP_TABLES.get(points_to)
        if table is None:
            raise EditError(f"{called} points to a {points_to}, which the lookup does not hold")
        is_uid = type(uid) is int and 0 < uid <= HIGHEST_UID
        if not is_uid or record_name(self._lookup, table, uid) is None:
            raise EditError(f"{called}: there is no {table} {uid!r}")


def is_new_reference(given: object) -> bool:
    return isinstance(given, str) and given.startswith(NEW_MARK)


def _new_reference(
    points_to: str, called: str, given: str, new: Mapping[str, RecordKind]
) -> NewReference:
    name = given.removeprefix(NEW_MARK)
    if name not in new:
        raise EditError(f"{called}: no new record above is called {given}")
    if points_to not in new[name].pointed_to_as:
        raise EditError(f"{called} points to a {points_to}, and {given} is a {new[name].name}")
    return NewReference(name)


def _number_of(given: FieldValue, words: Mapping[str, int]) -> FieldValue:
    return words.get(given, given) if isinstance(given, str) else given


def _typed(field: Field, given: FieldValue) -> FieldValue:
    if field.type == "boolean" and isinstance(given, int) and given in (0, 1):
        return bool(given)
    if field.type == "date" and isinstance(given, str):
        return checked_date(f"{field.name} ({field.code})", given)
    return given
