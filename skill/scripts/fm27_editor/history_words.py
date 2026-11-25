"""The past winners of awards in plain words."""

import sqlite3
from collections.abc import Sequence

from fm27_editor.award_history import (
    AWARD,
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
)
from fm27_editor.awards import PLACES
from fm27_editor.base_database import record_name
from fm27_editor.definition_files import FieldDefinitionError
from fm27_editor.field_definitions import Field
from fm27_editor.words import accepted, counted

# What can be given where the Editor's definition does not say it all.
IN_WORDS = {
    "person_uid": "the uid of a person, whose name is then known",
    "team_uid": "the uid of a club, or of a nation for its national team",
}


def offered_history_lines(field: Field) -> list[str]:
    """What can be given for a year of an award."""
    parts = {part.code: part for part in field.items}
    offered = "; ".join(f"{name}: {_accepted(name, parts)}" for name in OFFERED)
    return [
        f"{AWARD}: the uid of an award, needed",
        f"{YEAR}: {accepted(_part(YEAR_CODE, parts))}, needed",
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
    if history.already_so:
        says.append(f"{history.already_so} asked for and so already")
    return f"History of {described}: {', '.join(says)}; the others stay as they are"


def year_lines(
    changed: Sequence[tuple[Year | None, Year]], lookup: sqlite3.Connection
) -> list[str]:
    lines = []
    for old, new in changed:
        before = "not in the history" if old is None else _year(old, lookup)
        lines += [f"  {new.year}: {_year(new, lookup)}", f"    was: {before}"]
    return lines


def _winner(year: Year) -> tuple[int | None, str | None, int | None]:
    first = year.places.get(1, Place())
    if first.person_uid is not None:
        return first.person_uid, None, None
    return None, first.name, None if first.name is not None else first.team_uid


def _year(year: Year, lookup: sqlite3.Connection) -> str:
    said = [f"{number} {_place(place, lookup)}" for number, place in year.places.items()]
    if year.not_held:
        said.append("not held")
    if year.no_data:
        said.append("no data")
    return "; ".join(said) or "nothing"


def _place(place: Place, lookup: sqlite3.Connection) -> str:
    said = []
    if place.name is not None or place.person_uid is not None:
        person = "no person" if place.person_uid is None else place.person_uid
        said.append(f"{place.name or ''} ({person})".strip())
    if place.team_uid is not None:
        said.append(_named(lookup, place.team_uid, "club", "nation"))
    if place.nation_uid is not None:
        said.append(_named(lookup, place.nation_uid, "nation"))
    if place.points is not None:
        said.append(counted(place.points, "point", "points"))
    if place.age is not None:
        said.append(f"age {place.age}")
    return ", ".join(said)


def _named(lookup: sqlite3.Connection, uid: int, *tables: str) -> str:
    names = (record_name(lookup, table, uid) for table in tables)
    return next((name for name in names if name is not None), str(uid))


def _accepted(name: str, parts: dict[str, Field]) -> str:
    part = _part(PLACE_CODES[name].format(1), parts)
    return IN_WORDS.get(name) or accepted(part)


def _part(code: str, parts: dict[str, Field]) -> Field:
    if code not in parts:
        raise FieldDefinitionError(f"the Editor does not define {code} of an award's history")
    return parts[code]
