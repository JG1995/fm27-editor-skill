"""The Editor's own definitions of its fields: names, types, ranges, and choices.

They are read from the user's Editor install, so what the skill knows about a field is what that
Editor accepts.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree.ElementTree import Element

from fm27_editor.definition_files import (
    DefinitionFolder,
    FieldDefinitionError,
    is_set,
    name_of,
    open_definitions,
    value_of,
    whole_number,
)

DEFINITIONS_FILE = Path("shared", "data", "editor.fmf")
FORMAT_FOLDER = "format"
DATABASE_FOLDER = "database"
SHARED_CHOICES = "db enums"
NOT_OFFERED = ("is_read_only", "is_ige_only", "debug_only")


@dataclass(frozen=True)
class Field:
    code: str
    name: str
    type: str
    lowest: int | None
    highest: int | None
    choices: dict[int, str] | None
    points_to: str | None
    is_client_field: bool
    is_language_field: bool
    is_editable: bool
    items: tuple[Field, ...] = ()
    """The fields that each item of a list has."""


def read_fields(editor_dir: Path, record_kind: str) -> dict[str, Field]:
    """The fields of one kind of record, such as "person" or "player", by their code."""
    format_folder = _format_folder(editor_dir)
    shared = _shared_choices(format_folder.parse(SHARED_CHOICES))
    fields = {}
    for element in _field_elements(format_folder.subfolder(DATABASE_FOLDER).parse(record_kind)):
        field = _field(element, shared)
        if field is None:
            continue
        known = fields.get(field.code)
        if known is not None and not _is_same(known, field):
            raise FieldDefinitionError(f"{record_kind}.xml defines {field.code} in two ways")
        fields[field.code] = field if known is None else _joined(known, field)
    return fields


def read_field_names(editor_dir: Path, record_kind: str) -> dict[str, str]:
    """The names of the fields of one kind of record, without codes that have several names."""
    names: dict[str, set[str]] = {}
    folder = _format_folder(editor_dir).subfolder(DATABASE_FOLDER)
    for element in _field_elements(folder.parse(record_kind)):
        code, name = value_of(element, "field"), name_of(element)
        if code is not None and name:
            names.setdefault(code, set()).add(name)
    return {code: found.pop() for code, found in names.items() if len(found) == 1}


def read_shared_choices(editor_dir: Path, name: str) -> dict[int, str]:
    """Choices that several fields use, such as the kinds of records, by number."""
    choices = _shared_choices(_format_folder(editor_dir).parse(SHARED_CHOICES)).get(name)
    if choices is None:
        raise FieldDefinitionError(f"{SHARED_CHOICES}.xml has no numbered choices {name}")
    return choices


def _format_folder(editor_dir: Path) -> DefinitionFolder:
    return open_definitions(editor_dir / DEFINITIONS_FILE).subfolder(FORMAT_FOLDER)


def _field_elements(root: Element) -> list[Element]:
    return root.findall("record/list[@id='fields']/record")


def _field(element: Element, shared: dict[str, dict[int, str] | None]) -> Field | None:
    """The field an entry describes; headings and other entries without a code are not fields."""
    code, kind = value_of(element, "field"), value_of(element, "type")
    if code is None or kind is None:
        return None
    return Field(
        code=code,
        name=name_of(element),
        type=kind,
        lowest=whole_number(element, "min_value"),
        highest=whole_number(element, "max_value"),
        choices=_field_choices(element, shared),
        points_to=value_of(element, "database_table_type"),
        is_client_field=is_set(element, "is_client_field"),
        is_language_field=is_set(element, "is_language_field"),
        is_editable=not any(is_set(element, mark) for mark in NOT_OFFERED),
        items=_items(element, shared),
    )


def _items(element: Element, shared: dict[str, dict[int, str] | None]) -> tuple[Field, ...]:
    entries = element.findall("record[@id='list_item']/list[@id='fields']/record")
    found = (_field(entry, shared) for entry in entries)
    return tuple(field for field in found if field is not None)


def _is_same(first: Field, second: Field) -> bool:
    """Whether two definitions differ at most in their names and in the marks of a change."""
    return first == replace(
        second,
        name=first.name,
        is_client_field=first.is_client_field,
        is_language_field=first.is_language_field,
    )


def _joined(first: Field, second: Field) -> Field:
    """The colours of a club are defined twice, and real changes to them carry the client mark."""
    return replace(
        first,
        is_client_field=first.is_client_field or second.is_client_field,
        is_language_field=first.is_language_field or second.is_language_field,
    )


def _field_choices(
    element: Element, shared: dict[str, dict[int, str] | None]
) -> dict[int, str] | None:
    listed = element.find("list[@id='enum_values']")
    if listed is not None:
        return _choices(listed)
    return shared.get(value_of(element, "enum_values") or "")


def _shared_choices(root: Element) -> dict[str, dict[int, str] | None]:
    """Choices that several fields use, by the name those fields give."""
    shared = {}
    for record in root.findall("record"):
        listed = record.find("list[@id='enum_values']")
        if listed is not None:
            shared[record.get("id", "")] = _choices(listed)
    return shared


def _choices(listed: Element) -> dict[int, str] | None:
    """Names by number, or nothing when the values are words without numbers."""
    choices = {}
    for record in listed.findall("record"):
        number = record.get("enum_id", record.get("enum", ""))
        try:
            choices[int(number)] = name_of(record)
        except ValueError:
            return None
    return choices
