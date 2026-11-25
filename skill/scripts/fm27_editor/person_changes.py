"""The changes that create a person: one that adds the record, then one for each field."""

from fm27_editor.people import PersonKind
from fm27_editor.person_rules import Setting
from fm27_editor.record_changes import Change, NewIds, Table, add_record, field_change


def new_person(kind: PersonKind, settings: list[Setting], ids: NewIds) -> list[Change]:
    record = ids.record()
    added = add_record(Table.PERSON, kind, record, ids)
    return [added, *_set_fields(record, settings, ids)]


def _set_fields(record: bytes, settings: list[Setting], ids: NewIds) -> list[Change]:
    return [
        field_change(Table.PERSON, record, setting.field, setting.value, ids)
        for setting in settings
    ]
