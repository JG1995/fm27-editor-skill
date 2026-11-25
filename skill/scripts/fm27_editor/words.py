"""Fields, values, and counts in plain words."""

import datetime
import sqlite3

from fm27_editor.base_database import record_name
from fm27_editor.field_definitions import Field
from fm27_editor.record_changes import HIGHEST_ATTRIBUTE, LOWEST_ATTRIBUTE, REFERENCE
from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import LOOKUP_TABLES, NewReference, RecordRules


def counted(number: int, one: str, many: str) -> str:
    return f"{number:,} {one if number == 1 else many}"


def accepted(field: Field) -> str:
    """What can be given for a field that can be written."""
    match field.type:
        case "string":
            return "a text"
        case "attribute":
            return f"{LOWEST_ATTRIBUTE} to {HIGHEST_ATTRIBUTE}"
        case "integer" if field.choices:
            return f"0 to {field.highest}, or a range: {_listed(field.choices)}"
        case "integer":
            return f"{field.lowest} to {field.highest}"
        case "boolean":
            return "true or false"
        case "date":
            return "a date such as 2008-04-25"
        case "colour":
            return "a colour such as #480024, red first"
        case "enum":
            return f"one of {_listed(field.choices)}"
        case _ if field.type == REFERENCE:
            return f"the uid of a {field.points_to}"
    raise ValueError(f"no words for a field of type {field.type}")


def field_lines(kind: RecordKind, rules: RecordRules) -> list[str]:
    """What can be given for each field of a kind of record."""
    lines = []
    for field in rules.writable_fields(kind):
        name = kind.names.get(field.code)
        called = field.code if name is None else f"{name} ({field.code})"
        words = kind.words.get(field.code)
        given = accepted(field) if words is None else f"one of {', '.join(words)}"
        lines.append(f"{called}: {field.name}, {given}")
    return lines


def shown(field: Field, value: object, lookup: sqlite3.Connection) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    if field.points_to is not None:
        return named_reference(lookup, LOOKUP_TABLES[field.points_to], value)
    if field.choices and value in field.choices:
        return f"{field.choices[value]} ({value})"
    return str(value)


def named(lookup: sqlite3.Connection, table: str | None, uid: int) -> str:
    """A record by name and uid, or by uid alone when the lookup has no name for it."""
    name = None if table is None else record_name(lookup, table, uid)
    return str(uid) if name is None else f"{name} ({uid})"


def named_reference(
    lookup: sqlite3.Connection, table: str | None, record: int | NewReference
) -> str:
    """A record by name, or a new one by its name in the request."""
    return str(record) if isinstance(record, NewReference) else named(lookup, table, record)


def _listed(choices: dict[int, str]) -> str:
    return ", ".join(f"{number} {name}".strip() for number, name in choices.items())
