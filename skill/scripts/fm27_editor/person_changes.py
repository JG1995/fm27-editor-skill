"""The changes that create a person or edit one. Creating adds the record, then sets its fields."""

from fm27_editor.people import PersonKind
from fm27_editor.person_rules import Setting
from fm27_editor.record_changes import (
    Change,
    NewIds,
    Table,
    add_record,
    existing_record,
    field_change,
)


def new_person(kind: PersonKind, settings: list[Setting], ids: NewIds) -> list[Change]:
    record = ids.record()
    added = add_record(Table.PERSON, kind, record, ids)
    return [added, *_set_fields(record, settings, ids)]


def edit_person(uid: int, settings: list[Setting], ids: NewIds) -> list[Change]:
    return _set_fields(existing_record(uid), settings, ids)


def _set_fields(record: bytes, settings: list[Setting], ids: NewIds) -> list[Change]:
    return [
        field_change(Table.PERSON, record, setting.field, setting.value, ids)
        for setting in settings
    ]
