"""Rules as part of a plan: the records they are for, and whether those fit the rules."""

import sqlite3
from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any

from fm27_editor.change_reading import EditError
from fm27_editor.nation_rules import NationRules, check_nation_rules, leagues
from fm27_editor.places import Gender
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
    for competition, division in leagues(rules.divisions):
        called = named_reference(lookup, "competition", competition)
        clubs, women = _clubs(competition, edits, additions, lookup)
        least, most = division["minimum_number_teams"], division["maximum_number_teams"]
        if not least <= clubs <= most:
            has = counted(clubs, "club", "clubs") if clubs else "no clubs"
            needs = f"{least}" if least == most else f"{least} to {most}"
            warnings.append(f"{called} has {has} in its division, and needs {needs}")
        if women:
            clubs_for_women = counted(women, "women's club", "women's clubs")
            warnings.append(f"{called} is for men, and gets {clubs_for_women}")
    return warnings


def _clubs(
    competition: Competition,
    edits: Sequence[Edit],
    additions: Sequence[Addition],
    lookup: sqlite3.Connection,
) -> tuple[int, int]:
    """How many clubs have the competition as their division once the plan is carried out, and how
    many women's clubs the plan puts there."""
    code = CLUB.codes[DIVISION]
    clubs = women = 0
    if not isinstance(competition, NewReference):
        query = "SELECT clubs FROM competitions WHERE uid = ?"
        (clubs,) = lookup.execute(query, (competition,)).fetchone()
    for edit in edits:
        if edit.record.kind is CLUB and edit.setting.field.code == code:
            comes = edit.setting.value == competition
            clubs += comes - (edit.old == competition)
            women += comes and edit.record.facts["gender"] == Gender.FEMALE
    for addition in additions:
        values = _values(addition)
        if addition.kind is CLUB and values.get(code) == competition:
            clubs += 1
            women += values.get(GENDER_CODE) == FEMALE
    return clubs, women


def _values(addition: Addition) -> dict[str, object]:
    return {setting.field.code: setting.value for setting in addition.settings}


def _is_for_women(
    competition: Competition, additions: Sequence[Addition], lookup: sqlite3.Connection
) -> bool:
    if isinstance(competition, NewReference):
        (addition,) = [new for new in additions if new.name == competition.name]
        return _values(addition).get(GENDER_CODE) == FEMALE
    query = "SELECT gender FROM competition WHERE uid = ?"
    return lookup.execute(query, (competition,)).fetchone() == (Gender.FEMALE,)
