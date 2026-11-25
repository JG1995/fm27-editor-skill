"""Checking the rules a request gives for the competitions of a nation.

What the Editor's definitions say about each rule is checked, and that the rules fit together: what
does not add up is an error, and what may be meant is a warning.
"""

import datetime
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from fm27_editor.change_reading import EditError
from fm27_editor.definition_files import FieldDefinitionError
from fm27_editor.record_rules import NEW_MARK, NewReference
from fm27_editor.rule_definitions import Rule, RuleDefinitions
from fm27_editor.rule_shapes import (
    CHOICES_LEFT_OUT,
    CUP,
    CUP_GROUP,
    DATE,
    DAYS,
    DIVISION_GROUP,
    MONTHS,
    NATION_GROUP,
    NATION_RULES,
    SUBSTITUTIONS,
    SUPER_CUP,
    Shape,
)

SUBSTITUTION_RULES, SUPER_CUP_TYPE = "subs_rules", "super_cup"
DAYS_IN_A_WEEK = 7

type Refer = Callable[[str, str, Any], int | NewReference]
"""The record a rule points to, from the kind of record, the name of the rule, and what is given."""
type Values = dict[str, Any]


@dataclass(frozen=True)
class NationRules:
    values: Values
    """Every rule that is stored, by its name: words, numbers, dates, and records."""
    warnings: list[str]
    definitions: RuleDefinitions = field(repr=False, compare=False)

    @property
    def nation(self) -> int:
        return self.values["nation"]

    @property
    def divisions(self) -> list[Values]:
        return self.values["league_comps"]

    @property
    def cups(self) -> list[Values]:
        return self.values["cup_comps"]

    @property
    def competitions(self) -> list[int | NewReference]:
        """Every competition that the rules make, with the parts of a division behind it."""
        found = []
        for division in self.divisions:
            found.append(division["competition"])
            found += [part["competition"] for part in division["child_competitions"] or []]
        return found + [cup["competition"] for cup in self.cups]


def check_nation_rules(given: Any, definitions: RuleDefinitions, refer: Refer) -> NationRules:
    rules = definitions.group(NATION_GROUP)
    checker = _Checker(definitions, refer)
    values = checker.shape("nation_rules", NATION_RULES, rules, given)
    if not values["league_comps"]:
        raise EditError("nation_rules needs a division in league_comps")
    _check_season(values)
    warnings = [*_league_warnings(values["league_comps"]), *_cup_warnings(values)]
    checked = NationRules(values, warnings, definitions)
    _check_once(checked.competitions)
    return checked


class _Checker:
    """Checks values against shapes and definitions, with defaults for what is not given."""

    def __init__(self, definitions: RuleDefinitions, refer: Refer):
        self._definitions = definitions
        self._refer = refer

    def shape(self, where: str, shape: Shape, rules: Mapping[str, Rule], given: Any) -> Values:
        if not isinstance(given, Mapping):
            raise EditError(f"{where} must have named parts: {', '.join(shape.offered)}")
        self._check_names(where, shape, rules, given)
        values = {**shape.defaults, **given, **shape.fixed}
        return {
            name: self._value(f"{where}: {name}", rules.get(name), values.get(name), shape)
            for name in shape.order
        }

    def _check_names(
        self, where: str, shape: Shape, rules: Mapping[str, Rule], given: Mapping[str, Any]
    ) -> None:
        for name, value in given.items():
            if name in shape.offered and value is None:
                raise EditError(f"{where}: {name} has no value")
            if name in shape.offered:
                continue
            if name in rules:
                raise EditError(f"{where}: {name} cannot be set yet")
            raise EditError(f"{where} has no rule {name}")
        missing = [name for name in shape.needed if name not in given]
        if missing:
            raise EditError(f"{where} needs {', '.join(missing)}")

    def _value(self, where: str, rule: Rule | None, value: Any, shape: Shape) -> Any:
        if value is None:
            return None
        if rule is None:
            raise FieldDefinitionError(f"the Editor does not define {where}")
        part = shape.parts.get(rule.name)
        match rule.type:
            case "record" if part is not None:
                return self.shape(where, part, rule.parts, value)
            case "list" if part is not None:
                return self._items(where, rule, value, part)
            case "list" if rule.choices is not None:
                return _words(where, rule, value)
            case "list" | "database_record_list" | "cash" if value in ([], 0):
                return value  # the shape always stores these as they are
            case "date_fields" if part is not None:
                return self.shape(where, part, _date_rules(), _as_date_parts(where, value))
            case "database_record_unique_id":
                return self._refer(rule.points_to or "", where, value)
        return _simple_value(where, rule, value)

    def _items(self, where: str, rule: Rule, value: Any, part: Shape) -> list[Values]:
        if not isinstance(value, list):
            raise EditError(f"{where} must be a list")
        found = []
        for number, item in enumerate(value, 1):
            called = f"{where} {number}"
            if rule.name == "league_comps":
                found.append(self._division(called, part, item))
            elif rule.name == "cup_comps":
                found.append(self._cup(called, item))
            else:
                found.append(self.shape(called, part, rule.parts, item))
        return found

    def _division(self, where: str, shape: Shape, given: Any) -> Values:
        values = self.shape(where, shape, self._definitions.group(DIVISION_GROUP), given)
        if values["minimum_number_teams"] > values["maximum_number_teams"]:
            raise EditError(f"{where}: minimum_number_teams is above maximum_number_teams")
        _check_order(where, values, "start_date", "end_date")
        parts, promoted = _parts(values), values["promotion_places"]
        if promoted % parts:
            raise EditError(
                f"{where}: promotion_places {promoted} does not divide over {parts} sub-divisions"
            )
        return values | {"has_sub_divisions": bool(values["child_competitions"])}

    def _cup(self, where: str, given: Any) -> Values:
        is_super_cup = isinstance(given, Mapping) and given.get("type") == SUPER_CUP_TYPE
        shape = SUPER_CUP if is_super_cup else CUP
        values = self.shape(where, shape, self._definitions.group(CUP_GROUP), given)
        if not is_super_cup:
            return _counted_cup(where, values)
        if values["comp_1"] == values["comp_2"]:
            raise EditError(f"{where}: comp_1 and comp_2 are the same competition")
        return values


# --- single values --------------------------------------------------------------------------


def _simple_value(where: str, rule: Rule, value: Any) -> Any:
    match rule.type:
        case "integer":
            return _number(where, value, rule.lowest, rule.highest)
        case "boolean":
            if not isinstance(value, bool):
                raise EditError(f"{where} must be true or false, not {value!r}")
            return value
        case "enum":
            return _word(where, choices_of(rule), value)
        case "multiple_enum":
            return _words(where, rule, value)
        case "date":
            return _date(where, value)
        case "month":
            return _word(where, MONTHS, value)
        case "day_of_week":
            return _word(where, DAYS, value)
        case "time":
            return _time(where, value)
    raise EditError(f"{where} cannot be set yet")


def choices_of(rule: Rule) -> Mapping[str, int]:
    """The choices that can be given, with their numbers."""
    if rule.name == SUBSTITUTION_RULES:
        return SUBSTITUTIONS
    left_out = CHOICES_LEFT_OUT.get(rule.name, set())
    choices = rule.choices or {}
    return {word: number for word, number in choices.items() if word not in left_out}


def _number(where: str, value: Any, lowest: int | None, highest: int | None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EditError(f"{where} needs a whole number, not {value!r}")
    if (lowest is not None and value < lowest) or (highest is not None and value > highest):
        raise EditError(f"{where} must be from {lowest} to {highest}, not {value}")
    return value


def _word(where: str, choices: Any, value: Any) -> str:
    if not isinstance(value, str) or value not in choices:
        raise EditError(f"{where} must be one of {', '.join(choices)}; not {value!r}")
    return value


def _words(where: str, rule: Rule, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise EditError(f"{where} must be a list")
    words = [_word(where, choices_of(rule), word) for word in value]
    if len(set(words)) < len(words):
        raise EditError(f"{where} gives a choice twice")
    return words


def _date(where: str, value: Any) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise EditError(f"{where} needs a date such as 2026-08-15, not {value!r}") from error


def _time(where: str, value: Any) -> int:
    """A time of day, such as 1500."""
    _number(where, value, 0, 2359)
    if value % 100 > 59:
        raise EditError(f"{where} must be a time such as 1500, not {value}")
    return value


def _as_date_parts(where: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    day = _date(where, value)
    return {"day_of_month": day.day, "month": MONTHS[day.month - 1], "year": day.year}


def _date_rules() -> dict[str, Rule]:
    """The Editor has these parts of a date built in."""
    limits = {"day_of_month": (1, 31), "month": (None, None), "year": (2000, 2100)}
    return {
        name: Rule(name, name, "month" if name == "month" else "integer", *limits[name], None, None)
        for name in DATE.order
    }


# --- whether the rules fit together ---------------------------------------------------------


def _counted_cup(where: str, values: Values) -> Values:
    """The cup with its teams counted; every round needs two teams for each match."""
    rounds, left = [], 0
    for number, given in enumerate(values["rounds"], 1):
        called = f"{where}: round {number}"
        teams = left + given["number_extra_teams"]
        if teams != 2 * given["number_matches"]:
            raise EditError(f"{called} has {given['number_matches']} matches for {teams} teams")
        left = given["number_matches"]
        rounds.append(_legs(called, given) | {"number_teams": teams})
    if left != 1:
        raise EditError(f"{where}: rounds must end with one match")
    for number, (earlier, later) in enumerate(pairwise(rounds), 2):
        if later["date"] <= (earlier["date_2"] or earlier["date"]):
            raise EditError(f"{where}: round {number} is not after the one before it")
    entering = sum(given["number_extra_teams"] for given in rounds)
    entrants = sum(given["number_teams"] for given in values["teams"])
    if entering != entrants:
        raise EditError(f"{where}: {entrants} teams are in teams, but {entering} enter the rounds")
    return values | {"rounds": rounds, "number_teams": entrants}


def _legs(where: str, values: Values) -> Values:
    if values["number_legs"] == 1:
        if values["date_2"] is not None or values["time_2"] is not None:
            raise EditError(f"{where}: date_2 and time_2 need number_legs 2")
        return values
    if values["date_2"] is None:
        raise EditError(f"{where} needs date_2")
    _check_order(where, values, "date", "date_2")
    second = values["time"] if values["time_2"] is None else values["time_2"]
    return values | {"time_2": second, "stadium_rules": None}


def _check_season(values: Values) -> None:
    _check_order("nation_rules", values, "start_date", "end_date")
    for number, division in enumerate(values["league_comps"], 1):
        _check_within(
            values, f"league_comps {number}", division["start_date"], division["end_date"]
        )
    for number, cup in enumerate(values["cup_comps"], 1):
        dates = [day for part in (cup, *cup.get("rounds", [])) for day in _dates(part)]
        _check_within(values, f"cup_comps {number}", min(dates), max(dates))
    for number, window in enumerate(values["transfer_windows"], 1):
        if _day(window["end_date"]) < _day(window["start_date"]):
            raise EditError(f"transfer_windows {number} ends before it starts")


def _dates(values: Values) -> list[datetime.date]:
    found = (values.get(name) for name in ("date", "date_2"))
    return [day for day in found if day is not None]


def _check_within(season: Values, what: str, first: datetime.date, last: datetime.date) -> None:
    if first < season["start_date"] or last > season["end_date"]:
        raise EditError(f"{what} is not played within the season")


def _day(parts: Values) -> tuple[int, int, int]:
    return parts["year"], MONTHS.index(parts["month"]), parts["day_of_month"]


def _check_order(where: str, values: Values, first: str, second: str) -> None:
    if values[second] <= values[first]:
        raise EditError(f"{where}: {second} is not after {first}")


def _check_once(competitions: list[int | NewReference]) -> None:
    for competition in competitions:
        if competitions.count(competition) > 1:
            raise EditError(f"nation_rules has competition {_called(competition)} twice")


def _called(competition: int | NewReference) -> str:
    is_new = isinstance(competition, NewReference)
    return f"{NEW_MARK}{competition.name}" if is_new else str(competition)


def _parts(division: Values) -> int:
    return len(division["child_competitions"] or []) or 1


def leagues(divisions: list[Values]) -> Iterator[tuple[int | NewReference, Values]]:
    """The competitions that clubs play in: the parts of a division that has any, or itself."""
    for division in divisions:
        for part in division["child_competitions"] or [division]:
            yield part["competition"], division


def _league_warnings(divisions: list[Values]) -> list[str]:
    warnings = []
    for number, division in enumerate(divisions, 1):
        down, parts = division["relegation_places"], _parts(division)
        if down % parts:
            warnings.append(f"{down} go down from the {parts} sub-divisions of division {number}")
        teams = division["maximum_number_teams"]
        match_days = (teams - 1 + teams % 2) * division["number_rounds"]
        weeks = (division["end_date"] - division["start_date"]).days // DAYS_IN_A_WEEK + 1
        if match_days > weeks * 2:
            warnings.append(f"division {number} has {match_days} match days in {weeks} weeks")
    for number, (upper, lower) in enumerate(pairwise(divisions), 1):
        down, up = upper["relegation_places"], lower["promotion_places"]
        if down != up:
            warnings.append(f"{down} go down from division {number}, but {up} come up to it")
    return warnings


def _cup_warnings(values: Values) -> list[str]:
    """Entrants that the divisions do not have, and super cups between other competitions."""
    warnings = []
    played_in = dict(leagues(values["league_comps"]))
    made = {*played_in, *(cup["competition"] for cup in values["cup_comps"])}
    made |= {division["competition"] for division in values["league_comps"]}
    for number, cup in enumerate(values["cup_comps"], 1):
        for entrants in cup.get("teams", []):
            competition, teams = entrants["competition"], entrants["number_teams"]
            called = _called(competition)
            if competition not in played_in:
                warnings.append(f"cup {number} takes teams from {called}, where no clubs play")
            elif teams > played_in[competition]["maximum_number_teams"]:
                most = played_in[competition]["maximum_number_teams"]
                warnings.append(f"cup {number} takes {teams} teams from {called}, which has {most}")
        others = [cup[name] for name in ("comp_1", "comp_2") if name in cup]
        warnings += [
            f"cup {number} is for {_called(other)}, which these rules do not play"
            for other in others
            if other not in made
        ]
    return warnings
