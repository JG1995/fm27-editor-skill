"""Fields, values, and counts in plain words."""

import datetime
import sqlite3

from fm27_editor.base_database import record_name
from fm27_editor.field_definitions import Field
from fm27_editor.list_changes import LIST, LIST_REFERENCE_TAGS, ListShape
from fm27_editor.record_changes import (
    HIGHEST_ATTRIBUTE,
    LOWEST_ATTRIBUTE,
    MONEY,
    REFERENCE,
    money_range,
    refusal,
)
from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import LOOKUP_TABLES, Items, NewReference, RecordRules


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
        case _ if field.type == MONEY:
            lowest, highest = money_range(field)
            return f"pounds from {lowest:,} to {highest:,}"
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
        if field.type == LIST:
            given = _accepted_items(field, kind.lists[field.code])
        elif words is None:
            given = accepted(field)
        else:
            given = f"one of {', '.join(words)}"
        lines.append(f"{called}: {field.name}, {given}")
    return lines


def _accepted_items(field: Field, shape: ListShape) -> str:
    """What the items of a list can be given: the parts that can be written, in definition order."""
    parts = [
        part
        for part in field.items
        if part.code in shape.parts and refusal(part, LIST_REFERENCE_TAGS) is None
    ]
    return "items of " + "; ".join(f"{part.code} ({part.name}, {accepted(part)})" for part in parts)


def shown(field: Field, value: object, lookup: sqlite3.Connection) -> str:
    if field.type == LIST:
        return _shown_items(field, value, lookup)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if field.points_to is not None:
        return named_reference(lookup, LOOKUP_TABLES[field.points_to], value)
    if field.choices and value in field.choices:
        return f"{field.choices[value]} ({value})"
    return amount(field, value)


def amount(field: Field, value: object) -> str:
    """A number as its field means it: money is in pounds."""
    return f"£{value:,}" if field.type == MONEY else str(value)


def _shown_items(field: Field, items: Items, lookup: sqlite3.Connection) -> str:
    """Items that are added, each after a plus; no items clear the list."""
    if not items:
        return "cleared"
    parts = {part.code: part for part in field.items}
    return " ".join(
        "+ "
        + ", ".join(
            f"{parts[code].name} {shown(parts[code], value, lookup)}"
            for code, value in item.items()
        )
        for item in items
    )


def named(lookup: sqlite3.Connection, table: str | None, uid: int) -> str:
    """A record by name and uid, or by uid alone when the lookup has no name for it."""
    name = None if table is None else record_name(lookup, table, uid)
    return str(uid) if name is None else f"{name} ({uid})"


def named_team(lookup: sqlite3.Connection, uid: int) -> str:
    """A club, or a national team, which has the uid of its nation."""
    is_club = record_name(lookup, "club", uid) is not None
    return named(lookup, "club" if is_club else "nation", uid)


def named_reference(
    lookup: sqlite3.Connection, table: str | None, record: int | NewReference
) -> str:
    """A record by name, or a new one by its name in the request."""
    return str(record) if isinstance(record, NewReference) else named(lookup, table, record)


def _listed(choices: dict[int, str]) -> str:
    return ", ".join(f"{number} {name}".strip() for number, name in choices.items())
