"""The Editor's own definitions of the rules of a nation's competitions.

Rules are named by words, such as number_rounds, and so are their choices. The four-letter codes a
file stores them under are not in the definitions.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree.ElementTree import Element

from fm27_editor.definition_files import (
    DefinitionFolder,
    FieldDefinitionError,
    child,
    name_of,
    open_definitions,
    value_of,
    whole_number,
)

RULES_FILE = Path("data", "format.fmf")
RULES_FOLDER = "rule group"
SHARED_CHOICES = "enums"
GAME_RULES_FILE = Path("data", "basic comps.fmf")
GAME_RULES = "rule_group"

type Choices = Mapping[str, int]


@dataclass(frozen=True)
class Rule:
    name: str
    label: str
    type: str
    lowest: int | None
    highest: int | None
    choices: Choices | None
    points_to: str | None
    parts: Mapping[str, Rule] = field(default_factory=dict)
    """The rules inside a record, or inside each item of a list."""


class RuleDefinitions:
    def __init__(self, editor_dir: Path):
        self._editor_dir = editor_dir
        folder = open_definitions(editor_dir / RULES_FILE).subfolder(RULES_FOLDER)
        self._groups = _groups(folder)
        self._shared = {
            record.get("id", ""): _choices(record)
            for record in folder.parse(SHARED_CHOICES).findall("record")
        }

    def group(self, name: str) -> dict[str, Rule]:
        """The rules of a group by name. Of two with one name, the first counts."""
        return self._rules(self._group(name), (name,))

    def nations_in_the_game(self) -> set[int]:
        """The nations whose competitions the game has rules for."""
        folder = open_definitions(self._editor_dir / GAME_RULES_FILE)
        nations = set()
        for name in folder.names:
            rules = child(folder.parse(name), GAME_RULES)
            nation = None if rules is None else whole_number(rules, "nation")
            if nation is not None:
                nations.add(nation)
        return nations

    def _group(self, name: str) -> list[Element]:
        if name not in self._groups:
            raise FieldDefinitionError(f"{RULES_FILE.name} has no rules {name}")
        return self._groups[name]

    def _rules(self, elements: Iterable[Element], inside: tuple[str, ...]) -> dict[str, Rule]:
        rules: dict[str, Rule] = {}
        for element in elements:
            name, inserted = value_of(element, "field"), element.get("insert_fields")
            if name is not None:
                found = {name: self._rule(name, element, inside)}
            elif inserted is not None:
                found = self._inserted(inserted, inside)
            else:
                found = self._rules(_listed(element), inside)
            rules |= {name: rule for name, rule in found.items() if name not in rules}
        return rules

    def _inserted(self, name: str, inside: tuple[str, ...]) -> dict[str, Rule]:
        """The rules of another group; one that is being read already is left out."""
        if name in inside:
            return {}
        return self._rules(self._group(name), (*inside, name))

    def _rule(self, name: str, element: Element, inside: tuple[str, ...]) -> Rule:
        item = child(element, "list_item")
        described = element if item is None else item
        return Rule(
            name=name,
            label=name_of(element),
            type=value_of(element, "type") or "",
            lowest=whole_number(element, "min_value"),
            highest=whole_number(element, "max_value"),
            choices=self._choices(described),
            points_to=value_of(element, "database_table_type"),
            parts=self._parts(described, inside),
        )

    def _choices(self, element: Element) -> Choices | None:
        """The choices of a rule, or of the items of a list, which are an entry without a name."""
        found = _choices(element) or self._shared.get(value_of(element, "enum_values") or "")
        unnamed = [entry for entry in _listed(element) if value_of(entry, "field") is None]
        if found is None and len(unnamed) == 1:
            return self._choices(unnamed[0])
        return found

    def _parts(self, element: Element, inside: tuple[str, ...]) -> dict[str, Rule]:
        named = value_of(element, "fields")
        return self._rules(_listed(element), inside) | (
            {} if named is None else self._inserted(named, inside)
        )


def _groups(folder: DefinitionFolder) -> dict[str, list[Element]]:
    groups = {}
    for name in folder.names:
        for record in folder.parse(name).findall("record[@id]"):
            listed = child(record, "fields")
            if listed is not None and listed.tag == "list":
                groups[record.get("id", "")] = list(listed)
    return groups


def _listed(element: Element) -> list[Element]:
    listed = child(element, "fields")
    return [] if listed is None or listed.tag != "list" else list(listed)


def _choices(element: Element) -> Choices | None:
    """Numbers by word; a choice without a word is named by its number."""
    listed = element.find("list[@id='enum_values']")
    if listed is None:
        return None
    choices = {}
    for record in listed.findall("record"):
        word = record.get("enum", "")
        try:
            choices[word] = int(record.get("enum_id", word))
        except ValueError:
            return None
    return choices
