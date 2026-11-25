"""Rules as part of a plan: the records they are for, and whether those fit the rules."""

import sqlite3
from collections.abc import Callable, Iterator, Sequence
from itertools import pairwise
from typing import Any

from fm27_editor.change_reading import EditError
from fm27_editor.nation_rules import NationRules, Refer, Values, check_nation_rules, parts_of
from fm27_editor.places import Gender
from fm27_editor.planned import Addition, Edit
from fm27_editor.record_kinds import CLUB, GENDER_CODE, GENDER_WORDS
from fm27_editor.record_rules import NewReference
from fm27_editor.rule_definitions import RuleDefinitions
from fm27_editor.words import counted, named, named_reference

DIVISION = "division_uid"
FEMALE = GENDER_WORDS[GENDER_CODE][Gender.FEMALE]
DAYS_IN_A_WEEK = 7

type Competition = int | NewReference
type Called = Callable[[Competition], str]


def plan_rules(
    given: Any,
    definitions: RuleDefinitions,
    refer: Refer,
    additions: Sequence[Addition],
    lookup: sqlite3.Connection,
) -> NationRules:
    rules = check_nation_rules(given, definitions, refer)
    if any(_is_for_women(competition, additions, lookup) for competition in rules.competitions):
        raise EditError("rules for women's competitions cannot be written yet")
    return rules


def rule_warnings(
    rules: NationRules,
    edits: Sequence[Edit],
    additions: Sequence[Addition],
    lookup: sqlite3.Connection,
) -> list[str]:
    def called(competition: Competition) -> str:
        return named_reference(lookup, "competition", competition)

    warnings = list(fit_warnings(rules, called))
    if rules.nation in rules.definitions.nations_in_the_game():
        nation = named(lookup, "nation", rules.nation)
        warnings.append(f"{nation} has competitions in the game, which these rules replace")
    for competition, division in rules.leagues.items():
        clubs, women = _clubs(competition, edits, additions, lookup)
        least, most = division["minimum_number_teams"], division["maximum_number_teams"]
        if not least <= clubs <= most:
            has = counted(clubs, "club", "clubs") if clubs else "no clubs"
            needs = f"{least}" if least == most else f"{least} to {most}"
            warnings.append(f"{called(competition)} has {has} in its division, and needs {needs}")
        if women:
            for_women = counted(women, "women's club", "women's clubs")
            warnings.append(f"{called(competition)} is for men, and gets {for_women}")
    return warnings


def fit_warnings(rules: NationRules, called: Called) -> Iterator[str]:
    """What may be meant, but does not fit together."""
    yield from _division_warnings(rules.divisions)
    for number, cup in enumerate(rules.cups, 1):
        yield from _entrant_warnings(number, cup, rules, called)
        for name in ("comp_1", "comp_2"):
            if name in cup and cup[name] not in rules.competitions:
                other = called(cup[name])
                yield f"cup {number} is for {other}, which these rules do not play"


def _division_warnings(divisions: list[Values]) -> Iterator[str]:
    for number, division in enumerate(divisions, 1):
        down, parts = division["relegation_places"], parts_of(division)
        if down % parts:
            yield f"{down} go down from the {parts} sub-divisions of division {number}"
        teams = division["maximum_number_teams"]
        match_days = (teams - 1 + teams % 2) * division["number_rounds"]
        weeks = (division["end_date"] - division["start_date"]).days // DAYS_IN_A_WEEK + 1
        if match_days > weeks * 2:
            yield f"division {number} has {match_days} match days in {weeks} weeks"
    for number, (upper, lower) in enumerate(pairwise(divisions), 1):
        down, up = upper["relegation_places"], lower["promotion_places"]
        if down != up:
            yield f"{down} go down from division {number}, but {up} come up to it"


def _entrant_warnings(
    number: int, cup: Values, rules: NationRules, called: Called
) -> Iterator[str]:
    for entrants in cup.get("teams", []):
        competition, teams = entrants["competition"], entrants["number_teams"]
        division = rules.leagues.get(competition)
        if division is None:
            yield f"cup {number} takes teams from {called(competition)}, where no clubs play"
        elif teams > division["maximum_number_teams"]:
            most = division["maximum_number_teams"]
            yield f"cup {number} takes {teams} teams from {called(competition)}, which has {most}"


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
