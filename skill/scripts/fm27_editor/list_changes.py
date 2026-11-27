"""Storing a list whole, the way the Editor stores its lists.

In the lists of real files an item holds the parts that its definition names, with nothing in the
place of what it does not have, and references without a number beside the ID. The order of the
parts is the Editor's own for each list, and some lists hold fewer parts than their definition, so
each list is written in the shape that real files show.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

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


@dataclass(frozen=True)
class ListShape:
    """How the items of one list are stored, as real files show it."""

    parts: tuple[str, ...]
    """The codes of the parts of an item, in the order they are stored."""


def list_change(
    table: Table,
    record: bytes,
    field: Field,
    shape: ListShape,
    items: Iterable[Item],
    ids: NewIds,
) -> Change:
    """The change that gives a list these items. Their values are not checked here."""
    stored = [ListItem(Kind.NESTED, _parts(field, shape, item)) for item in items]
    return make_change(
        table,
        record,
        field.code,
        Property("nwvl", Kind.LIST, stored),
        ids,
        is_client_field=field.is_client_field,
        is_language_field=field.is_language_field,
    )


def _parts(field: Field, shape: ListShape, item: Item) -> list[Property]:
    unknown = item.keys() - set(shape.parts)
    if unknown:
        raise EditError(f"{field.name} ({field.code}) has no {', '.join(sorted(unknown))}")
    defined = {part.code: part for part in field.items}
    missing = [code for code in shape.parts if code not in defined]
    if missing:
        raise EditError(f"the Editor does not define {', '.join(missing)} of {field.name}")
    return [_part(defined[code], item.get(code)) for code in shape.parts]


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
