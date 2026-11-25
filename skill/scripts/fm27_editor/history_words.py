"""The past winners of awards in plain words."""

import sqlite3
from collections.abc import Sequence

from fm27_editor.award_history import (
    AWARD_UID,
    KEEP,
    NOT_HELD,
    OFFERED,
    PLACE_CODES,
    PLACES_KEY,
    YEAR,
    YEAR_CODE,
    AwardHistory,
    Place,
    Year,
    history_field,
    history_part,
)
from fm27_editor.awards import PLACES
from fm27_editor.field_definitions import Field
from fm27_editor.record_kinds import AWARD
from fm27_editor.record_rules import RecordRules
from fm27_editor.words import accepted, counted, named, named_team

# What can be given where the Editor's definition does not say it all.
IN_WORDS = {
    "person_uid": "the uid of a person, whose name is then known",
    "team_uid": "the uid of a club, or of a nation for its national team",
}


def offered_history_lines(rules: RecordRules) -> list[str]:
    """What can be given for a year of an award."""
    field = history_field(rules.fields(AWARD))
    offered = "; ".join(f"{name}: {_accepted(name, field)}" for name in OFFERED)
    return [
        f"{AWARD_UID}: the uid of an award, needed",
        f"{YEAR}: {accepted(history_part(field, YEAR_CODE))}, needed",
        f"{PLACES_KEY}: a list of one to three, the first first, each of ({KEEP}: 1 to {PLACES}, "
        f"the place of who stands in the history of that year; {offered})",
        f"{NOT_HELD}: true, instead of {PLACES_KEY}",
    ]


def history_heading(described: str, history: AwardHistory) -> str:
    changed = len(history.changed)
    says = [
        f"{changed} of {counted(len(history.years), 'year', 'years')} "
        f"{'changes' if changed == 1 else 'change'}"
    ]
    other = sum(old is not None and _winner(old) != _winner(new) for old, new in history.changed)
    added = sum(old is None for old, _ in history.changed)
    if other:
        says.append(f"{other} with another winner")
    if added:
        says.append(f"{added} new")
    others = "; the others stay as they are" if changed < len(history.years) else ""
    return f"History of {described}: {', '.join(says)}{others}"


def year_lines(
    changed: Sequence[tuple[Year | None, Year]], field: Field, lookup: sqlite3.Connection
) -> list[str]:
    """Each changed year with everything that is stored for it, and as it was."""
    words = _Words(field, lookup)
    lines = []
    for old, new in changed:
        before = "not in the history" if old is None else words.year(old)
        lines += [f"  {new.year}: {words.year(new)}", f"    was: {before}"]
    return lines


def _winner(year: Year) -> tuple[int | None, str | None, int | None]:
    first = year.places.get(1, Place())
    if first.person_uid is not None:
        return first.person_uid, None, None
    return None, first.name, None if first.name is not None else first.team_uid


class _Words:
    def __init__(self, field: Field, lookup: sqlite3.Connection):
        self._lookup = lookup
        self._field = field

    def year(self, year: Year) -> str:
        said = [f"{number} {self._place(number, place)}" for number, place in year.places.items()]
        if year.not_held:
            said.append("not held")
        if year.no_data:
            said.append("no data")
        return "; ".join(said) or "nothing"

    def _place(self, number: int, place: Place) -> str:
        said = []
        if place.name is not None or place.person_uid is not None:
            person = "no person" if place.person_uid is None else place.person_uid
            said.append(f"{place.name or ''} ({person})".strip())
        if place.team_uid is not None:
            said.append(named_team(self._lookup, place.team_uid))
        if place.nation_uid is not None:
            said.append(named(self._lookup, "nation", place.nation_uid))
        if place.points is not None:
            said.append(counted(place.points, "point", "points"))
        if place.more_points is not None:
            said.append(f"then {place.more_points:,}")
        if place.age is not None:
            said.append(f"age {place.age}")
        if place.position is not None:
            said.append(self._position(number, place.position))
        return ", ".join(said)

    def _position(self, number: int, position: int) -> str:
        part = history_part(self._field, PLACE_CODES["position"].format(number))
        return (part.choices or {}).get(position, f"position {position}")


def _accepted(name: str, field: Field) -> str:
    part = history_part(field, PLACE_CODES[name].format(1))
    return IN_WORDS.get(name) or accepted(part)
