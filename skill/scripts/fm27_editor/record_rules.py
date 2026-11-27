"""What can be set on a record: the fields of each kind, and the values that make sense in them.

A value must be one the Editor's definitions allow, and what it refers to must be in the lookup.
"""

import datetime
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

from fm27_editor.base_database import record_name
from fm27_editor.change_reading import EditError
from fm27_editor.field_definitions import Field, read_fields
from fm27_editor.json_text import RepeatedNameError, read_json
from fm27_editor.list_changes import LIST, LIST_REFERENCE_TAGS, ListShape, is_blank
from fm27_editor.potential import check_potential, with_ranges
from fm27_editor.record_changes import (
    REFERENCE_TAGS,
    FieldValue,
    checked_date,
    is_uid,
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
    "person": "person",
}
NEW_MARK = "@"


@dataclass(frozen=True)
class NewReference:
    """A record that the same request creates, by the name it has there."""

    name: str

    def __str__(self) -> str:
        return f"{NEW_MARK}{self.name}"


type Item = Mapping[str, FieldValue | NewReference]
"""An item to add to a list: its parts by code."""
type Items = tuple[Item, ...]


@dataclass(frozen=True)
class Setting:
    """A field and the value it is to have; for a list, the items to add to it."""

    field: Field
    value: FieldValue | NewReference | Items
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
        return [field for _, field in sorted(self.fields(kind).items()) if _can_write(kind, field)]

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
            value = self._value(kind, field, _number_of(given, words), new)
            chosen[field.code] = Setting(field, value, words)
        return list(chosen.values())

    def new_record_settings(
        self,
        kind: RecordKind,
        values: Mapping[str, FieldValue],
        new: Mapping[str, RecordKind] = NO_NEW,
    ) -> list[Setting]:
        if not kind.can_be_new:
            raise EditError(f"a new {kind.name} cannot be made yet")
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
        self, kind: RecordKind, field: Field, given: FieldValue, new: Mapping[str, RecordKind]
    ) -> FieldValue | NewReference | Items:
        if field.type == LIST:
            return self._items(field, kind.lists.get(field.code), given, new)
        value = self._part(field, given, new)
        check_potential(field, value)
        return value

    def _items(
        self, field: Field, shape: ListShape | None, given: object, new: Mapping[str, RecordKind]
    ) -> Items:
        """Items to add to a list, by the codes of their parts."""
        if shape is None or not field.is_editable:
            raise EditError(f"{_called(field)} {refusal(field)}")
        parts = {part.code: part for part in field.items if part.code in shape.parts}
        items = tuple(self._item(field, parts, entry, new) for entry in _listed(field, given))
        for item in items:
            refers = any(parts[code].points_to is not None for code in item)
            if not refers and is_blank(field, shape, item):
                raise EditError(f"{_called(field)}: an item must set more than a new item has")
        return items

    def _item(
        self, field: Field, parts: Mapping[str, Field], given: object, new: Mapping[str, RecordKind]
    ) -> Item:
        if not isinstance(given, Mapping) or not given:
            raise EditError(f"{_called(field)}: an item has parts by code: {', '.join(parts)}")
        unknown = given.keys() - parts.keys()
        if unknown:
            known = ", ".join(parts)
            raise EditError(f"{_called(field)} has no {', '.join(sorted(unknown))}, only {known}")
        return {
            code: self._part(parts[code], value, new, in_list=True) for code, value in given.items()
        }

    def _part(
        self, field: Field, given: object, new: Mapping[str, RecordKind], *, in_list: bool = False
    ) -> FieldValue | NewReference:
        """A checked value of a field, or of a part of an item.

        A team in a list can be a national team, which has the uid of its nation.
        """
        reason = refusal(field, LIST_REFERENCE_TAGS if in_list else REFERENCE_TAGS)
        if reason is not None:
            raise EditError(f"{_called(field)} {reason}")
        if given is None:
            raise EditError(f"{_called(field)} needs a value")
        if in_list and field.points_to == "team" and not is_new_reference(given):
            check_exists(self._lookup, _called(field), given, "club", "nation")
            return given
        if field.points_to is not None:
            return self.refer(field.points_to, _called(field), given, new)
        value = _typed(field, given)
        stored_value(field, value)
        return value

    def refer(
        self, points_to: str, called: str, given: object, new: Mapping[str, RecordKind]
    ) -> int | NewReference:
        """A record that exists or is new, for something called `called` that points to it."""
        if is_new_reference(given):
            return _new_reference(points_to, called, given, new)
        table = LOOKUP_TABLES.get(points_to)
        if table is None:
            raise EditError(f"{called} points to a {points_to}, which the lookup does not hold")
        check_exists(self._lookup, called, given, table)
        return given


def _can_write(kind: RecordKind, field: Field) -> bool:
    if field.type == LIST:
        return field.is_editable and field.code in kind.lists
    return refusal(field) is None and field.points_to in (None, *LOOKUP_TABLES)


def _listed(field: Field, given: object) -> list:
    """Items as a list; a query gives them as JSON text."""
    if isinstance(given, str):
        try:
            given = read_json(given)
        except json.JSONDecodeError:
            pass  # not JSON, so refused below as no list
        except RepeatedNameError as error:
            raise EditError(f"{_called(field)}: {error}") from error
    if not isinstance(given, list):
        raise EditError(f"{_called(field)} needs a list of items, not {given!r}")
    return given


def _called(field: Field) -> str:
    return f"{field.name} ({field.code})"


def check_exists(lookup: sqlite3.Connection, called: str, uid: object, *tables: str) -> None:
    """Something called `called` points to a record of one of these tables of the lookup."""
    if not is_uid(uid) or all(record_name(lookup, table, uid) is None for table in tables):
        raise EditError(f"{called}: there is no {' or '.join(tables)} {uid!r}")


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
