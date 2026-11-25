"""Storing a list whole, the way the Editor stores its lists.

In the lists of real files an item holds the parts that its definition names, with nothing in the
place of what it does not have, and references without a number beside the ID. Some lists hold more
or fewer parts than their definition, so a list is only written once the Editor has shown it right.
"""

from collections.abc import Iterable, Mapping

from fm27_editor.change_list import Kind, ListItem, Property
from fm27_editor.change_reading import Change, EditError, Table, existing_record
from fm27_editor.field_definitions import Field
from fm27_editor.record_changes import (
    ID_TAG,
    REFERENCE,
    REFERENCE_TAGS,
    FieldValue,
    NewIds,
    make_change,
    number,
)

# A person is referred to only in lists, as far as files were seen.
LIST_REFERENCE_TAGS = REFERENCE_TAGS | {"person": "Pers"}

type Item = Mapping[str, FieldValue | None]
"""The parts of an item by code; what is not named has no value."""


def list_change(
    table: Table, record: bytes, field: Field, items: Iterable[Item], ids: NewIds
) -> Change:
    """The change that gives a list these items. Their values are not checked here."""
    stored = [ListItem(Kind.NESTED, _parts(field, item)) for item in items]
    return make_change(
        table,
        record,
        field.code,
        Property("nwvl", Kind.LIST, stored),
        ids,
        is_client_field=field.is_client_field,
        is_language_field=field.is_language_field,
    )


def _parts(field: Field, item: Item) -> list[Property]:
    unknown = item.keys() - {part.code for part in field.items}
    if unknown:
        raise EditError(f"{field.name} ({field.code}) has no {', '.join(sorted(unknown))}")
    return [_part(part, item.get(part.code)) for part in field.items]


def _part(part: Field, value: FieldValue | None) -> Property:
    match part.type:
        case "string":
            return Property(part.code, Kind.TEXT, value or "")
        case "boolean":
            return Property(part.code, Kind.BOOL, bytes([bool(value)]))
        case _ if value is None:
            return Property(part.code, Kind.NULL, b"")
        case "integer" | "enum":
            return number(part.code, value)
        case _ if part.type == REFERENCE and part.points_to in LIST_REFERENCE_TAGS:
            return Property(part.code, Kind.NESTED, _reference(part, value))
    raise EditError(f"{part.name} ({part.code}) cannot be written in a list yet")


def _reference(part: Field, uid: int) -> list[Property]:
    return [
        Property(ID_TAG, Kind.CODE, part.code),
        Property(LIST_REFERENCE_TAGS[part.points_to], Kind.ID, existing_record(uid)),
    ]
