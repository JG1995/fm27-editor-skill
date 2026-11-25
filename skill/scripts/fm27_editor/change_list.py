"""The list of edits inside a .dbc member.

A change list is a 9-byte tag and a compressed body: two groups of properties, a change count, and
the changes. Each change is a group of properties. Tags and codes are stored with their four
characters reversed.

Scalar values stay as raw bytes: their meaning depends on the field, and raw bytes rebuild exactly.
"""

import struct
from compression import zstd
from dataclasses import dataclass, field
from enum import IntEnum

from fm27_editor.binary import FormatError, Reader, text_bytes, unpack_frame

LIST_TAG = b"\x03\x01cbd.\x06\x00\x00"
CHANGE_COUNT_TAG = "dchc"
MAX_BODY_SIZE = 1024 * 1024 * 1024


class ChangeListError(FormatError):
    """The bytes are not a change list this library can read."""


class Kind(IntEnum):
    """Value kinds seen in FM24 and FM27 files; any other kind is an error."""

    NULL = 0x00
    INT32 = 0x01
    CODE = 0x02
    BOOL = 0x03
    COLOUR = 0x04
    INT64 = 0x05
    NESTED = 0x0A
    LIST = 0x0B
    COLOUR_2 = 0x0D
    ID = 0x0F
    INT8 = 0x11
    INT16 = 0x12
    INT8_2 = 0x13  # seen once, in one file
    INT16_2 = 0x14
    INT32_2 = 0x15
    COUNT = 0x18
    TEXT = 0x1A
    DATE = 0x20


SCALAR_SIZES = {
    Kind.NULL: 0,
    Kind.INT32: 4,
    Kind.BOOL: 1,
    Kind.COLOUR: 4,
    Kind.INT64: 8,
    Kind.COLOUR_2: 4,
    Kind.ID: 8,
    Kind.INT8: 1,
    Kind.INT16: 2,
    Kind.INT8_2: 1,
    Kind.INT16_2: 2,
    Kind.INT32_2: 4,
    Kind.COUNT: 8,
    Kind.DATE: 4,
}

type Value = bytes | str | list["Property"] | list["ListItem"]


@dataclass
class Property:
    tag: str
    kind: Kind
    value: Value
    flag: int = 1


@dataclass
class ListItem:
    kind: Kind
    value: Value
    flag: int = 1


@dataclass
class ChangeList:
    general: list[Property] = field(default_factory=list)
    editor: list[Property] = field(default_factory=list)
    changes: list[list[Property]] = field(default_factory=list)


def parse_change_list(content: bytes) -> ChangeList:
    reader = Reader(read_body(content), ChangeListError)
    changes = ChangeList(_read_group(reader), _read_group(reader))
    for _ in range(reader.u32()):
        changes.changes.append(_read_group(reader))
    if not reader.at_end:
        raise ChangeListError(f"{len(reader.content) - reader.position} bytes follow the changes")
    return changes


def serialise_change_list(changes: ChangeList) -> bytes:
    compressor = zstd.ZstdCompressor(options={zstd.CompressionParameter.checksum_flag: 1})
    return LIST_TAG + compressor.compress(change_list_body(changes)) + compressor.flush()


def read_body(content: bytes) -> bytes:
    """The uncompressed body."""
    if content[: len(LIST_TAG)] != LIST_TAG:
        raise ChangeListError("not an editor change list")
    return unpack_frame(content[len(LIST_TAG) :], "the change list", ChangeListError, MAX_BODY_SIZE)


def change_list_body(changes: ChangeList) -> bytes:
    general = [_with_change_count(item, len(changes.changes)) for item in changes.general]
    body = _group_bytes(general) + _group_bytes(changes.editor)
    body += struct.pack("<I", len(changes.changes))
    return body + b"".join(_group_bytes(change) for change in changes.changes)


def _with_change_count(item: Property, count: int) -> Property:
    if item.tag != CHANGE_COUNT_TAG:
        return item
    return Property(item.tag, item.kind, struct.pack("<Q", count), item.flag)


def _read_group(reader: Reader) -> list[Property]:
    return [_read_property(reader) for _ in range(reader.u32())]


def _read_property(reader: Reader) -> Property:
    start = reader.position
    tag = reader.take(4)[::-1].decode("latin-1")
    flag, kind = reader.take(2)
    return Property(tag, *_read_value(reader, kind, tag, start), flag)


def _read_value(reader: Reader, kind: int, tag: str, start: int) -> tuple[Kind, Value]:
    try:
        known = Kind(kind)
    except ValueError as error:
        raise ChangeListError(f"field {tag!r} at {start} has unknown kind {kind:#x}") from error
    if known is Kind.TEXT:
        return known, reader.text()
    if known is Kind.CODE:
        return known, reader.take(4)[::-1].decode("latin-1")
    if known is Kind.NESTED:
        return known, _read_group(reader)
    if known is Kind.LIST:
        return known, [_read_list_item(reader, tag, start) for _ in range(reader.u32())]
    return known, reader.take(SCALAR_SIZES[known])


def _read_list_item(reader: Reader, tag: str, start: int) -> ListItem:
    flag, kind = reader.take(2)
    known, value = _read_value(reader, kind, tag, start)
    return ListItem(known, value, flag)


def _group_bytes(group: list[Property]) -> bytes:
    return struct.pack("<I", len(group)) + b"".join(
        item.tag.encode("latin-1")[::-1] + bytes([item.flag, item.kind]) + _value_bytes(item)
        for item in group
    )


def _value_bytes(item: Property | ListItem) -> bytes:
    if item.kind is Kind.TEXT:
        return text_bytes(item.value)
    if item.kind is Kind.CODE:
        return item.value.encode("latin-1")[::-1]
    if item.kind is Kind.NESTED:
        return _group_bytes(item.value)
    if item.kind is Kind.LIST:
        return struct.pack("<I", len(item.value)) + b"".join(
            bytes([entry.flag, entry.kind]) + _value_bytes(entry) for entry in item.value
        )
    return item.value
