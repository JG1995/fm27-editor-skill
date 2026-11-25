"""The changes that create a record or edit one. Creating adds the record, then sets its fields."""

from fm27_editor.change_reading import Change, existing_record
from fm27_editor.record_changes import NewIds, add_record, field_change
from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import Setting


def new_record(kind: RecordKind, settings: list[Setting], ids: NewIds) -> list[Change]:
    record = ids.record()
    added = add_record(kind.group.table, kind.person_type, record, ids)
    return [added, *_set_fields(kind, record, settings, ids)]


def edit_record(kind: RecordKind, uid: int, settings: list[Setting], ids: NewIds) -> list[Change]:
    return _set_fields(kind, existing_record(uid), settings, ids)


def _set_fields(
    kind: RecordKind, record: bytes, settings: list[Setting], ids: NewIds
) -> list[Change]:
    return [
        field_change(kind.group.table, record, setting.field, setting.value, ids)
        for setting in settings
    ]
