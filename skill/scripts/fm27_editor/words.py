"""Fields, values, and counts in plain words."""

import datetime
import sqlite3
from collections.abc import Mapping, Sequence

from fm27_editor.base_database import record_name
from fm27_editor.field_definitions import Field
from fm27_editor.list_changes import LIST, LIST_REFERENCE_TAGS, ListShape
from fm27_editor.record_changes import (
    HIGHEST_ATTRIBUTE,
    LOWEST_ATTRIBUTE,
    MONEY,
    REAL,
    REFERENCE,
    money_range,
    refusal,
)
from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import LOOKUP_TABLES, ListItems, NewReference, RecordRules


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
        case _ if field.type == REAL:
            bounds = [(field.lowest, "from"), (field.highest, "to")]
            return " ".join(
                ["a number", *(f"{word} {end}" for end, word in bounds if end is not None)]
            )
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
        if part.code in shape.given and refusal(part, LIST_REFERENCE_TAGS) is None
    ]
    return "items of " + "; ".join(f"{part.code} ({part.name}, {accepted(part)})" for part in parts)


def shown(field: Field, value: object, lookup: sqlite3.Connection) -> str:
    """A value in words; a list's are items added to a new record, which holds none."""
    if field.type == LIST:
        return shown_list(field, value, (), lookup)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if field.points_to == "team" and isinstance(value, int):
        return named_team(lookup, value)
    if field.points_to is not None:
        return named_reference(lookup, LOOKUP_TABLES[field.points_to], value)
    if field.choices and value in field.choices:
        return f"{field.choices[value]} ({value})"
    if field.type == "multiple_enum" and field.choices and isinstance(value, int):
        chosen = [f"{name} ({number})" for number, name in field.choices.items() if number & value]
        return " and ".join(chosen)
    return amount(field, value)


def amount(field: Field, value: object) -> str:
    """A number as its field means it: money is in pounds."""
    return f"£{value:,}" if field.type == MONEY else str(value)


def shown_list(
    field: Field,
    value: ListItems,
    held: Sequence[Mapping[str, object]] | None,
    lookup: sqlite3.Connection,
) -> str:
    """Items that are added, each after a plus, behind those that replacing the list takes out,
    each after a minus; `held` is what the list holds now, or None when that is not known."""
    added = _items("+", field, value.items, lookup)
    if not value.replace:
        return added
    if held is None:
        cleared = "cleared of what it holds, which is not known"
    else:
        cleared = f"cleared of {_items('-', field, held, lookup) or 'nothing'}"
    return f"{cleared}, then {added}" if added else cleared


def _items(
    mark: str, field: Field, items: Sequence[Mapping[str, object]], lookup: sqlite3.Connection
) -> str:
    parts = {part.code: part for part in field.items}
    return " ".join(
        f"{mark} "
        + ", ".join(
            _part(parts[code], value, lookup)
            for code, value in item.items()
            if value or parts[code].type != "boolean"
        )
        for item in items
    )


def _part(part: Field, value: object, lookup: sqlite3.Connection) -> str:
    """A part of an item; a box is named only when it is ticked, and left out when it is not."""
    if part.type == "boolean":
        return part.name
    return f"{part.name} {shown(part, value, lookup)}"


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
