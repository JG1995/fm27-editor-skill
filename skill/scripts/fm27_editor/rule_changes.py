"""Writing the rules of a nation's competitions into a file, the way the Editor stores them."""

import datetime
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from fm27_editor.change_list import ChangeList, Kind, ListItem, Property
from fm27_editor.change_reading import EditError, existing_record, uid_of
from fm27_editor.nation_rules import NationRules, choices_of
from fm27_editor.record_changes import date_bytes, number
from fm27_editor.record_rules import NewReference
from fm27_editor.rule_definitions import Rule, RuleDefinitions
from fm27_editor.rule_shapes import CODES, CUP_GROUP, DAYS, DIVISION_GROUP, MONTHS, NATION_GROUP
from fm27_editor.setting_changes import NewRecords

RULES_TAG = "rlgr"
ID_TAG = "id  "
COMPETITION_TAG = "comp"
# Rules without a value that the Editor stores as nothing; others are left out.
STORED_AS_NOTHING = {"number_teams"}


def add_rules(changes: ChangeList, rules: NationRules, new: NewRecords) -> None:
    """Put the rules among the file's properties, and the nation at its head as well."""
    if has_rules(changes):
        raise EditError("the file to start from has rules already; a file has rules for one nation")
    writer = _Writer(rules.definitions, new)
    parts = writer.parts(rules.values, rules.definitions.group(NATION_GROUP))
    changes.general.insert(1, Property(RULES_TAG, Kind.NESTED, [_nation(rules.nation)]))
    changes.editor.append(_nested(RULES_TAG, parts))


def has_rules(changes: ChangeList) -> bool:
    return any(item.tag == RULES_TAG for item in (*changes.general, *changes.editor))


def nation_of(rules: Property) -> int | None:
    """The nation that stored rules are for."""
    for item in rules.value:
        if item.tag == CODES["nation"] and item.kind is Kind.CODE:
            return struct.unpack(">I", item.value.encode("latin-1"))[0]
    return None


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
                return _nested(tag, self._reference(value))
        return _simple(tag, rule, value)

    def _items(self, rule: Rule, values: Sequence[Mapping[str, Any]]) -> list[ListItem]:
        rules = self._groups.get(rule.name, rule.parts)
        return [ListItem(Kind.NESTED, self.parts(value, rules)) for value in values]

    def _reference(self, value: int | NewReference) -> list[Property]:
        if isinstance(value, NewReference):
            record = self._new[value.name]
        else:
            record = existing_record(value)
        return [Property(COMPETITION_TAG, Kind.ID, record), number("DBID", uid_of(record))]


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
