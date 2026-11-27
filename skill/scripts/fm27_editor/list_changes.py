"""Storing lists the way the Editor stores them: whole, or by adding items to what is there.

In the lists of real files an item holds the parts that its definition names, with nothing in the
place of what it does not have, and references without a number beside the ID. The order of the
parts is the Editor's own for each list, and some lists hold fewer parts than their definition, so
each list is written in the shape that real files show.

A list whose whole content is known is stored whole. Otherwise items are added as the Editor adds
them: empty first, then one part at a time, each change naming the item by all it held before.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from fm27_editor.change_list import Kind, ListItem, Property
from fm27_editor.change_reading import Change, EditError, Table, existing_record, uid_of
from fm27_editor.field_definitions import Field
from fm27_editor.record_changes import (
    ID_TAG,
    MONEY,
    REFERENCE,
    REFERENCE_TAGS,
    FieldValue,
    NewIds,
    date_bytes,
    make_change,
    number,
)

# A person is referred to only in lists, as far as files were seen, and a club as a club only there.
LIST_REFERENCE_TAGS = REFERENCE_TAGS | {"person": "Pers", "club": "Cclu"}
NUMBERS = {"integer", "enum", "multiple_enum", MONEY}
# What a change does to a list, by the Editor's numbers for it.
ADD, CHANGE_PART, CLEAR = 0, 1, 3
NEW_VALUE, PART_VALUE, OLD_ITEM, OPERATION = "nwvl", "valu", "olvl", "lsop"

type Item = Mapping[str, FieldValue | None]
"""The parts of an item by code; what is not named has no value."""


@dataclass(frozen=True)
class ListShape:
    """How the items of one list are stored, as real files show it."""

    parts: tuple[str, ...]
    """The codes of the parts of an item, in the order they are stored."""
    empty: Mapping[str, FieldValue] = dataclass_field(default_factory=dict)
    """What an item that was just added holds; it has nothing in the other parts."""
    as_codes: frozenset[str] = frozenset()
    """Numbers that an item holds as four bytes, the highest first."""


def list_change(
    table: Table,
    record: bytes,
    field: Field,
    shape: ListShape,
    items: Iterable[Item],
    ids: NewIds,
) -> Change:
    """The change that gives a list these items. Their values are not checked here."""
    parts = _defined(field, shape)
    stored = []
    for item in items:
        _check_known(field, shape, item)
        stored.append(ListItem(Kind.NESTED, _stored_item(parts, shape, item)))
    return _list_change(table, record, field, Property(NEW_VALUE, Kind.LIST, stored), ids)


def item_changes(
    table: Table,
    record: bytes,
    field: Field,
    shape: ListShape,
    items: Sequence[Item],
    ids: NewIds,
) -> list[Change]:
    """The changes that add these items to what a list holds; with no items, it is cleared.

    Each item is complete before the next is added, so no two items look the same to the Editor
    while their parts are set. The values are not checked here.
    """
    parts = _defined(field, shape)
    if not items:
        return [_operation(table, record, field, ids, CLEAR)]
    changes = []
    for item in items:
        _check_known(field, shape, item)
        changes.append(_operation(table, record, field, ids, ADD))
        held = {code: shape.empty.get(code) for code in shape.parts}
        for code, part in parts.items():
            if code not in item or _is_same(part, shape, item[code], held[code]):
                continue
            old = _stored_item(parts, shape, held)
            new = _new_part(part, item[code])
            changes.append(_operation(table, record, field, ids, CHANGE_PART, code, new, old))
            held[code] = item[code]
    return changes


def _is_same(
    part: Field, shape: ListShape, value: FieldValue | None, other: FieldValue | None
) -> bool:
    """Whether an item holds two values alike, such as no and nothing for yes or no."""
    as_code = part.code in shape.as_codes
    return _part(part, value, as_code) == _part(part, other, as_code)


def _operation(
    table: Table,
    record: bytes,
    field: Field,
    ids: NewIds,
    operation: int,
    part: str = NEW_VALUE,
    new: Property | None = None,
    old: list[Property] | None = None,
) -> Change:
    described = [Property(ID_TAG, Kind.CODE, part)]
    if new is not None:
        described.append(new)
    described.append(number(OPERATION, operation))
    if old is not None:
        named = Property(ID_TAG, Kind.CODE, OLD_ITEM)
        described.append(Property(OLD_ITEM, Kind.NESTED, [named, *old]))
    return _list_change(table, record, field, Property(NEW_VALUE, Kind.NESTED, described), ids)


def _list_change(table: Table, record: bytes, field: Field, new: Property, ids: NewIds) -> Change:
    return make_change(
        table,
        record,
        field.code,
        new,
        ids,
        is_client_field=field.is_client_field,
        is_language_field=field.is_language_field,
    )


def _defined(field: Field, shape: ListShape) -> dict[str, Field]:
    """The definitions of the parts of an item, in the order of its shape."""
    defined = {part.code: part for part in field.items}
    missing = [code for code in shape.parts if code not in defined]
    if missing:
        raise EditError(f"the Editor does not define {', '.join(missing)} of {field.name}")
    return {code: defined[code] for code in shape.parts}


def _check_known(field: Field, shape: ListShape, item: Item) -> None:
    unknown = item.keys() - set(shape.parts)
    if unknown:
        raise EditError(f"{field.name} ({field.code}) has no {', '.join(sorted(unknown))}")


def _stored_item(parts: Mapping[str, Field], shape: ListShape, item: Item) -> list[Property]:
    return [_part(part, item.get(code), code in shape.as_codes) for code, part in parts.items()]


def _part(part: Field, value: FieldValue | None, as_code: bool) -> Property:
    """A part as an item holds it."""
    if value is not None and as_code:
        return Property(part.code, Kind.CODE, value.to_bytes(4, "big").decode("latin-1"))
    if value is not None and part.type == REFERENCE:
        return Property(part.code, Kind.NESTED, _reference(part, part.code, value))
    return _plain(part.code, part, value)


def _new_part(part: Field, value: FieldValue) -> Property:
    """A part as a change to it holds its new value: a reference with the number of the record."""
    if value is not None and part.type == REFERENCE:
        named, record = _reference(part, PART_VALUE, value)
        uid = number("DBID", uid_of(record.value))
        return Property(PART_VALUE, Kind.NESTED, [named, record, uid])
    return _plain(PART_VALUE, part, value)


def _plain(tag: str, part: Field, value: FieldValue | None) -> Property:
    match part.type:
        case "string":
            return Property(tag, Kind.TEXT, value or "")
        case "boolean":
            return Property(tag, Kind.BOOL, bytes([bool(value)]))
        case _ if value is None:
            return Property(tag, Kind.NULL, b"")
        case "date":
            return Property(tag, Kind.DATE, date_bytes(value))
        case _ if part.type in NUMBERS:
            return number(tag, value)
    raise EditError(f"{part.name} ({part.code}) cannot be written in a list yet")


def _reference(part: Field, tag: str, value: FieldValue) -> list[Property]:
    """A record by its uid, or a new one by its whole ID."""
    if part.points_to not in LIST_REFERENCE_TAGS:
        raise EditError(f"{part.name} ({part.code}) cannot be written in a list yet")
    record = value if isinstance(value, bytes) else existing_record(value)
    return [
        Property(ID_TAG, Kind.CODE, tag),
        Property(LIST_REFERENCE_TAGS[part.points_to], Kind.ID, record),
    ]
