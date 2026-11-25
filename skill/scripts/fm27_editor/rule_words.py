"""The rules of a nation's competitions in plain words, named the way a request names them."""

import datetime
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from fm27_editor.nation_rules import NationRules, choices_of
from fm27_editor.rule_definitions import Rule, RuleDefinitions
from fm27_editor.rule_shapes import (
    CUP,
    CUP_GROUP,
    DAYS,
    DIVISION,
    DIVISION_GROUP,
    MONTHS,
    NATION_GROUP,
    NATION_RULES,
    ROUND,
    SUPER_CUP,
    Shape,
)
from fm27_editor.words import named, named_reference

# What a request can be told the rules of, by the name that is asked for.
RULES_OF = {
    "nation_rules": (NATION_RULES, NATION_GROUP),
    "division": (DIVISION, DIVISION_GROUP),
    "cup": (CUP, CUP_GROUP),
    "super_cup": (SUPER_CUP, CUP_GROUP),
}
COMPETITIONS = {"competition", "comp_1", "comp_2"}
SUB_DIVISIONS = "child_competitions"
ON_LINES_OF_THEIR_OWN = {"nation", "transfer_windows", "league_comps", "cup_comps"}
# The divisions and cups of a nation are asked for by themselves.
ASKED_FOR_APART = {"league_comps": "division", "cup_comps": "cup or super_cup"}


def offered_lines(name: str, definitions: RuleDefinitions) -> list[str]:
    """What can be given for each rule, and what is stored when it is not."""
    shape, group = RULES_OF[name]
    rules = definitions.group(group)
    return [
        f"{rule}: {rules[rule].label}, {_accepted(rules[rule], shape)}" for rule in shape.offered
    ]


def _accepted(rule: Rule, shape: Shape) -> str:
    if rule.name in shape.needed:
        return f"{_values(rule, shape.parts.get(rule.name))}, needed"
    default = shape.defaults.get(rule.name)
    otherwise = "" if default is None else f", otherwise {_default(default)}"
    return f"{_values(rule, shape.parts.get(rule.name))}{otherwise}"


def _values(rule: Rule, part: Shape | None) -> str:
    if rule.name in ASKED_FOR_APART:
        return f"a list; ask for the rules of a {ASKED_FOR_APART[rule.name]}"
    match rule.type:
        case "integer":
            return f"{rule.lowest} to {rule.highest}"
        case "boolean":
            return "true or false"
        case "date" | "date_fields":
            return "a date such as 2026-08-15"
        case "time":
            return "a time such as 1500"
        case "month":
            return f"one of {', '.join(MONTHS)}"
        case "day_of_week":
            return f"one of {', '.join(DAYS)}"
        case "enum":
            return f"one of {', '.join(choices_of(rule))}"
        case "multiple_enum":
            return f"a list of {', '.join(choices_of(rule))}"
        case "database_record_unique_id":
            new = " or new name" if rule.points_to == "competition" else ""
            return f"the uid{new} of a {rule.points_to}"
        case "list" if part is None:
            return f"a list of {', '.join(choices_of(rule))}"
    described = "; ".join(f"{name}: {_accepted(rule.parts[name], part)}" for name in part.offered)
    return f"a list of ({described})" if rule.type == "list" else f"({described})"


def _default(value: Any) -> str:
    return _Words(None).value("", value) if value or isinstance(value, bool | int) else "none"


def rule_lines(rules: NationRules, lookup: sqlite3.Connection) -> list[str]:
    words = _Words(lookup)
    values = rules.values
    lines = [f"Nation rules: {named(lookup, 'nation', rules.nation)}"]
    lines += [
        f"  {name}: {words.value(name, values[name])}"
        for name in NATION_RULES.offered
        if name not in ON_LINES_OF_THEIR_OWN
    ]
    for number, window in enumerate(values["transfer_windows"], 1):
        lines.append(f"  transfer_windows {number}: {words.listed(window, window)}")
    for number, division in enumerate(rules.divisions, 1):
        lines.append(f"  Division {number}: {words.listed(division, DIVISION.offered)}")
    for number, cup in enumerate(rules.cups, 1):
        lines += _cup_lines(number, cup, words)
    return lines


def _cup_lines(number: int, cup: Mapping[str, Any], words: _Words) -> list[str]:
    rounds = cup.get("rounds", [])
    offered = CUP.offered if rounds else SUPER_CUP.offered
    names = [name for name in offered if name != "rounds"]
    lines = [f"  Cup {number}: {words.listed(cup, names)}"]
    return lines + [
        f"  Cup {number}, round {index}: {words.listed(given, ROUND.offered)}"
        for index, given in enumerate(rounds, 1)
    ]


class _Words:
    def __init__(self, lookup: sqlite3.Connection | None):
        self._lookup = lookup

    def listed(self, values: Mapping[str, Any], names: Sequence[str] | Mapping[str, Any]) -> str:
        said = [(name, values[name]) for name in names if values[name] is not None]
        return ", ".join(f"{name} {self._inside(name, value)}" for name, value in said)

    def value(self, name: str, value: Any) -> str:
        if name == SUB_DIVISIONS:
            return " and ".join(self.value("competition", part["competition"]) for part in value)
        match value:
            case bool():
                return "yes" if value else "no"
            case datetime.date():
                return value.isoformat()
            case Mapping():
                return self.listed(value, value)
            case list():
                return " and ".join(self._inside(name, item) for item in value) or "none"
        if name in COMPETITIONS:
            return named_reference(self._lookup, "competition", value)
        return str(value)

    def _inside(self, name: str, value: Any) -> str:
        """A value among others; one with parts of its own stands in brackets."""
        said = self.value(name, value)
        return f"({said})" if isinstance(value, Mapping) else said
