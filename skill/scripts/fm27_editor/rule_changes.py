"""Writing the rules of a nation's competitions into a file, the way the Editor stores them."""

import datetime
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fm27_editor.change_list import ChangeList, Kind, ListItem, Property
from fm27_editor.change_reading import EditError, existing_record
from fm27_editor.nation_rules import NationRules, choices_of
from fm27_editor.record_changes import ID_TAG, date_bytes, number, reference
from fm27_editor.record_fields import NewReference
from fm27_editor.rule_definitions import Rule, RuleDefinitions
from fm27_editor.rule_shapes import CODES, CUP_GROUP, DAYS, DIVISION_GROUP, MONTHS, NATION_GROUP
from fm27_editor.setting_changes import NewRecords, resolved

RULES_TAG = "rlgr"
# The Editor lets a file have rules for a nation or one of these: for a continent, international
# competitions, or versus competitions.
OTHER_RULES_TAGS = {"cnrl", "inrl", "vrrl"}
ADVANCED_RULES_TAG = "fles"
# Rules without a value that the Editor stores as nothing; others are left out.
STORED_AS_NOTHING = {"number_teams"}


def add_rules(changes: ChangeList, rules: NationRules, new: NewRecords) -> None:
    """Put the rules among the file's properties, and the nation at its head as well."""
    check_has_no_rules(changes)
    writer = _Writer(rules.definitions, new)
    parts = writer.parts(rules.values, rules.definitions.group(NATION_GROUP))
    changes.general.insert(1, Property(RULES_TAG, Kind.NESTED, [_nation(rules.nation)]))
    changes.editor.append(_nested(RULES_TAG, parts))


def check_has_no_rules(changes: ChangeList) -> None:
    if read_rules(changes) != StoredRules():
        raise EditError("the file to start from has rules already, and a file has one kind of them")


@dataclass(frozen=True)
class StoredRules:
    """The rules that a file holds, as far as they are read."""

    nations: tuple[int | None, ...] = ()
    """The nation that there are rules for; nothing in its place when that cannot be read."""
    divisions: int = 0
    cups: int = 0
    others: int = 0
    """Rules for a continent, international competitions, or versus competitions."""
    advanced: int = 0


def read_rules(changes: ChangeList) -> StoredRules:
    """What is at the head of a file counts as well, but the rest of it is among the properties."""
    items = {item.tag: item for item in (*changes.general, *changes.editor)}
    parts = {item.tag: item for item in _inside(items.get(RULES_TAG))}
    return StoredRules(
        nations=(_read_nation(parts.get(CODES["nation"])),) if RULES_TAG in items else (),
        divisions=len(_inside(parts.get(CODES["league_comps"]))),
        cups=len(_inside(parts.get(CODES["cup_comps"]))),
        others=len(items.keys() & OTHER_RULES_TAGS),
        advanced=len(_inside(items.get(ADVANCED_RULES_TAG))),
    )


def _inside(item: Property | None) -> list:
    return item.value if item is not None and item.kind in (Kind.NESTED, Kind.LIST) else []


def _read_nation(item: Property | None) -> int | None:
    if item is None or item.kind is not Kind.CODE:
        return None
    return struct.unpack(">I", item.value.encode("latin-1"))[0]


class _Writer:
    def __init__(self, definitions: RuleDefinitions, new: NewRecords):
        self._new = new
        self._groups = {
            "league_comps": definitions.group(DIVISION_GROUP),
            "cup_comps": definitions.group(CUP_GROUP),
        }

    def parts(self, values: Mapping[str, Any], rules: Mapping[str, Rule]) -> list[Property]:
        stored = (self._property(rules.get(name), name, value) for name, value in values.items())
        return [item for item in stored if item is not None]

    def _property(self, rule: Rule | None, name: str, value: Any) -> Property | None:
        tag = CODES[name]
        if value is None:
            return Property(tag, Kind.NULL, b"") if name in STORED_AS_NOTHING else None
        if rule is None:
            return _undefined(tag, value)
        match rule.type:
            case "record":
                return _nested(tag, self.parts(value, rule.parts))
            case "date_fields":
                return _nested(tag, self.parts(value, {}))
            case "list" if rule.choices is not None:
                return Property(tag, Kind.LIST, _numbers(rule.choices[word] for word in value))
            case "list" | "database_record_list":
                return Property(tag, Kind.LIST, self._items(rule, value))
            case "database_record_unique_id" if name == "nation":
                return _nation(value)
            case "database_record_unique_id":
                return Property(tag, Kind.NESTED, self._reference(tag, rule, value))
        return _simple(tag, rule, value)

    def _items(self, rule: Rule, values: Sequence[Mapping[str, Any]]) -> list[ListItem]:
        rules = self._groups.get(rule.name, rule.parts)
        return [ListItem(Kind.NESTED, self.parts(value, rules)) for value in values]

    def _reference(self, tag: str, rule: Rule, value: int | NewReference) -> list[Property]:
        found = resolved(value, self._new)
        record = found if isinstance(found, bytes) else existing_record(found)
        return reference(tag, rule.points_to, record)


def _simple(tag: str, rule: Rule, value: Any) -> Property:
    match value:
        case bool():
            return Property(tag, Kind.BOOL, bytes([value]))
        case datetime.date():
            return Property(tag, Kind.DATE, date_bytes(value))
        case int():
            return number(tag, value)
        case list():
            return Property(tag, Kind.CODE, _code(sum(choices_of(rule)[word] for word in value)))
    if rule.type in ("month", "day_of_week"):
        return _undefined(tag, value)
    return number(tag, choices_of(rule)[value])


def _undefined(tag: str, value: str | int) -> Property:
    """A month, a day of the week, or a number, whose values the Editor has built in."""
    if isinstance(value, int):
        return number(tag, value)
    names = MONTHS if value in MONTHS else DAYS
    return number(tag, names.index(value) + 1)


def _nation(uid: int) -> Property:
    return Property(CODES["nation"], Kind.CODE, _code(uid))


def _code(value: int) -> str:
    """A number in the place of a code of four characters."""
    return struct.pack(">I", value).decode("latin-1")


def _nested(tag: str, parts: list[Property]) -> Property:
    return Property(tag, Kind.NESTED, [Property(ID_TAG, Kind.CODE, tag), *parts])


def _numbers(values) -> list[ListItem]:
    stored = (number("", value) for value in values)
    return [ListItem(item.kind, item.value) for item in stored]
