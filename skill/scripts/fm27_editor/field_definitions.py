"""The Editor's own definitions of its fields: names, types, ranges, and choices.

They are read from the user's Editor install, so what the skill knows about a field is what that
Editor accepts.
"""

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element

from fm27_editor.binary import FormatError
from fm27_editor.container import ContainerError, Folder, read_container

DEFINITIONS_FILE = Path("shared", "data", "editor.fmf")
FORMAT_FOLDER = "format"
DATABASE_FOLDER = "database"
SHARED_CHOICES = "db enums"
TRANSLATOR_NOTE = "[COMMENT"
NOT_OFFERED = ("is_read_only", "is_ige_only", "debug_only")


class FieldDefinitionError(FormatError):
    """The Editor's field definitions are missing or do not follow the known layout."""


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


def read_fields(editor_dir: Path, record_kind: str) -> dict[str, Field]:
    """The fields of one kind of record, such as "person" or "player", by their code."""
    format_folder = _format_folder(editor_dir)
    shared = _shared_choices(_parse(format_folder, SHARED_CHOICES))
    fields = {}
    for element in _field_elements(_parse(_folder(format_folder, DATABASE_FOLDER), record_kind)):
        field = _field(element, shared)
        if field is None:
            continue
        if field.code in fields:
            raise FieldDefinitionError(f"{record_kind}.xml defines {field.code} twice")
        fields[field.code] = field
    return fields


def _format_folder(editor_dir: Path) -> Folder:
    path = editor_dir / DEFINITIONS_FILE
    if not path.is_file():
        raise FieldDefinitionError(f"the Editor folder has no {DEFINITIONS_FILE.name}")
    try:
        container = read_container(path.read_bytes())
    except ContainerError as error:
        raise FieldDefinitionError(f"{path.name}: {error}") from error
    return _folder(container.root, FORMAT_FOLDER)


def _folder(parent: Folder, name: str) -> Folder:
    for folder in parent.folders:
        if folder.name == name:
            return folder
    raise FieldDefinitionError(f"{DEFINITIONS_FILE.name} has no folder {name}")


def _parse(folder: Folder, name: str) -> Element:
    for member in folder.members:
        if member.name == name:
            try:
                return ElementTree.fromstring(member.data)
            except ElementTree.ParseError as error:
                raise FieldDefinitionError(f"{name}.xml cannot be read: {error}") from error
    raise FieldDefinitionError(f"{DEFINITIONS_FILE.name} has no {name}.xml")


def _field_elements(root: Element) -> list[Element]:
    return root.findall("record/list[@id='fields']/record")


def _field(element: Element, shared: dict[str, dict[int, str] | None]) -> Field | None:
    """The field an entry describes; headings and other entries without a code are not fields."""
    code, kind = _value(element, "field"), _value(element, "type")
    if code is None or kind is None:
        return None
    return Field(
        code=code,
        name=_name(element),
        type=kind,
        lowest=_whole_number(element, "min_value"),
        highest=_whole_number(element, "max_value"),
        choices=_field_choices(element, shared),
        points_to=_value(element, "database_table_type"),
        is_client_field=_is_set(element, "is_client_field"),
        is_language_field=_is_set(element, "is_language_field"),
        is_editable=not any(_is_set(element, mark) for mark in NOT_OFFERED),
    )


def _field_choices(
    element: Element, shared: dict[str, dict[int, str] | None]
) -> dict[int, str] | None:
    listed = element.find("list[@id='enum_values']")
    if listed is not None:
        return _choices(listed)
    return shared.get(_value(element, "enum_values") or "")


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
            choices[int(number)] = _name(record)
        except ValueError:
            return None
    return choices


def _name(element: Element) -> str:
    return (_value(element, "name") or "").split(TRANSLATOR_NOTE)[0].strip()


def _child(element: Element, name: str) -> Element | None:
    return element.find(f"*[@id='{name}']")


def _value(element: Element, name: str) -> str | None:
    child = _child(element, name)
    return None if child is None else child.get("value")


def _whole_number(element: Element, name: str) -> int | None:
    child = _child(element, name)
    if child is None or child.tag != "integer":
        return None
    try:
        return int(child.get("value", ""))
    except ValueError as error:
        raise FieldDefinitionError(f"a field has a {name} that is not a number") from error


def _is_set(element: Element, name: str) -> bool:
    return _value(element, name) == "true"
