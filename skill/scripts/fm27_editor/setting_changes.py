"""The changes that create a record or edit one. Creating adds the record, then sets its fields."""

from collections.abc import Mapping

from fm27_editor.change_reading import Change, existing_record
from fm27_editor.record_changes import FieldValue, NewIds, add_record, field_change
from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import NewReference, Setting

type NewRecords = Mapping[str, bytes]
"""The IDs of the records a request creates, by the names it gives them."""


def new_record(
    kind: RecordKind, record: bytes, settings: list[Setting], new: NewRecords, ids: NewIds
) -> list[Change]:
    added = add_record(kind.group.table, kind.person_type, record, ids)
    return [added, *_set_fields(kind, record, settings, new, ids)]


def edit_record(
    kind: RecordKind, uid: int, settings: list[Setting], new: NewRecords, ids: NewIds
) -> list[Change]:
    return _set_fields(kind, existing_record(uid), settings, new, ids)


def _set_fields(
    kind: RecordKind, record: bytes, settings: list[Setting], new: NewRecords, ids: NewIds
) -> list[Change]:
    return [
        field_change(kind.group.table, record, setting.field, _value(setting, new), ids)
        for setting in settings
    ]


def _value(setting: Setting, new: NewRecords) -> FieldValue:
    value = setting.value
    return new[value.name] if isinstance(value, NewReference) else value
