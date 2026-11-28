"""Reading the XML files in which the Editor defines its fields and rules."""

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element

from fm27_editor.binary import FormatError
from fm27_editor.container import ContainerError, Folder, read_container

TRANSLATOR_NOTE = "[COMMENT"
# Where a name says [%number#1], the Editor puts the first of the numbers the definition lists.
NUMBER_IN_NAME = re.compile(r"\[%number#(\d+)\]")
NAME_NUMBERS = "list[@id='translation_variables']/record"
DEFINITION_ENDING = ".xml"


class FieldDefinitionError(FormatError):
    """The Editor's definitions are missing or do not follow the known layout."""


class NoDefinitionsError(FieldDefinitionError):
    """The Editor has no definitions for this kind of record."""


@dataclass(frozen=True)
class DefinitionFolder:
    """A folder of definitions, and the file of the Editor that holds it."""

    source: str
    folder: Folder

    @property
    def names(self) -> list[str]:
        """Definitions only; the Editor's folders also hold notes for its developers."""
        members = self.folder.members
        return [member.name for member in members if member.extension == DEFINITION_ENDING]

    def subfolder(self, name: str) -> DefinitionFolder:
        for folder in self.folder.folders:
            if folder.name == name:
                return DefinitionFolder(self.source, folder)
        raise FieldDefinitionError(f"{self.source} has no folder {name}")

    def parse(self, name: str) -> Element:
        for member in self.folder.members:
            if member.name == name:
                try:
                    return ElementTree.fromstring(member.data)
                except ElementTree.ParseError as error:
                    raise FieldDefinitionError(f"{name}.xml cannot be read: {error}") from error
        raise NoDefinitionsError(f"{self.source} has no {name}.xml")


def open_definitions(path: Path) -> DefinitionFolder:
    """The top folder of one of the Editor's files."""
    if not path.is_file():
        raise FieldDefinitionError(f"the Editor folder has no {path.name}")
    try:
        container = read_container(path.read_bytes())
    except ContainerError as error:
        raise FieldDefinitionError(f"{path.name}: {error}") from error
    return DefinitionFolder(path.name, container.root)


def child(element: Element, name: str) -> Element | None:
    return element.find(f"*[@id='{name}']")


def value_of(element: Element, name: str) -> str | None:
    found = child(element, name)
    return None if found is None else found.get("value")


def name_of(element: Element) -> str:
    """The name as the Editor shows it, with its numbers filled in."""
    name = (value_of(element, "name") or "").split(TRANSLATOR_NOTE)[0].strip()
    numbers = {
        record.get("number"): value_of(record, "valu") for record in element.findall(NAME_NUMBERS)
    }
    return NUMBER_IN_NAME.sub(lambda found: numbers.get(found[1]) or found[0], name)


def whole_number(element: Element, name: str) -> int | None:
    found = child(element, name)
    if found is None or found.tag != "integer":
        return None
    try:
        return int(found.get("value", ""))
    except ValueError as error:
        raise FieldDefinitionError(f"a field has a {name} that is not a number") from error


def is_set(element: Element, name: str) -> bool:
    return value_of(element, name) == "true"
