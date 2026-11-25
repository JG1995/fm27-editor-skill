"""Rules as part of a plan: the records they are for, and whether those fit the rules."""

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from functools import partial
from typing import Any

from fm27_editor.change_reading import EditError
from fm27_editor.nation_rules import NationRules, Values, check_nation_rules
from fm27_editor.planned import Addition, Edit
from fm27_editor.record_kinds import CLUB, RecordKind
from fm27_editor.record_rules import NewReference, RecordRules
from fm27_editor.rule_definitions import RuleDefinitions
from fm27_editor.words import counted, named, named_reference

DIVISION = "division_uid"
GENDER_CODE, FEMALE = "PLgn", 1

type Competition = int | NewReference


def plan_rules(
    given: Any, additions: Sequence[Addition], rules: RecordRules, definitions: RuleDefinitions
) -> NationRules:
    new: Mapping[str, RecordKind] = {
        addition.name: addition.kind for addition in additions if addition.name is not None
    }
    checked = check_nation_rules(given, definitions, partial(rules.refer, new=new))
    for competition in checked.competitions:
        if _is_for_women(competition, additions, rules.lookup):
            raise EditError("rules for women's competitions cannot be written yet")
    return checked


def rule_warnings(
    rules: NationRules,
    edits: Sequence[Edit],
    additions: Sequence[Addition],
    lookup: sqlite3.Connection,
) -> list[str]:
    warnings = list(rules.warnings)
    if rules.nation in rules.definitions.nations_in_the_game():
        nation = named(lookup, "nation", rules.nation)
        warnings.append(f"{nation} has competitions in the game, which these rules replace")
    for competition, division in _leagues(rules):
        clubs = _clubs(competition, edits, additions, lookup)
        least, most = division["minimum_number_teams"], division["maximum_number_teams"]
        if not least <= clubs <= most:
            has = counted(clubs, "club", "clubs") if clubs else "no clubs"
            needs = f"{least}" if least == most else f"{least} to {most}"
            called = named_reference(lookup, "competition", competition)
            warnings.append(f"{called} has {has} in its division, and needs {needs}")
    return warnings


def _leagues(rules: NationRules) -> Iterator[tuple[Competition, Values]]:
    """The competitions that clubs play in: the parts of a division that has any, or itself."""
    for division in rules.divisions:
        for part in division["child_competitions"] or [division]:
            yield part["competition"], division


def _clubs(
    competition: Competition,
    edits: Sequence[Edit],
    additions: Sequence[Addition],
    lookup: sqlite3.Connection,
) -> int:
    """How many clubs have the competition as their division once the plan is carried out."""
    code = CLUB.codes[DIVISION]
    clubs = 0
    if not isinstance(competition, NewReference):
        query = "SELECT clubs FROM competitions WHERE uid = ?"
        (clubs,) = lookup.execute(query, (competition,)).fetchone()
    for edit in edits:
        if edit.record.kind is CLUB and edit.setting.field.code == code:
            clubs += (edit.setting.value == competition) - (edit.old == competition)
    for addition in additions:
        if addition.kind is CLUB:
            clubs += sum(
                setting.field.code == code and setting.value == competition
                for setting in addition.settings
            )
    return clubs


def _is_for_women(
    competition: Competition, additions: Sequence[Addition], lookup: sqlite3.Connection
) -> bool:
    if isinstance(competition, NewReference):
        (addition,) = [new for new in additions if new.name == competition.name]
        values = {setting.field.code: setting.value for setting in addition.settings}
        return values.get(GENDER_CODE) == FEMALE
    query = "SELECT gender FROM competition WHERE uid = ?"
    return lookup.execute(query, (competition,)).fetchone() == ("female",)
