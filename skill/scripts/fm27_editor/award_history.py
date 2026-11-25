"""The past winners of awards: what a request says about some years, among all the others.

The history of an award is stored whole, so the years that a request does not name are taken from
the lookup as they are. Only what a request gives is checked, because the database holds values
that the Editor's own ranges would refuse.
"""

import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from dataclasses import fields as dataclass_fields
from typing import Any

from fm27_editor.awards import PLACES
from fm27_editor.base_database import record_name
from fm27_editor.change_reading import Change, EditError, Table, existing_record
from fm27_editor.definition_files import FieldDefinitionError
from fm27_editor.field_definitions import Field
from fm27_editor.list_changes import LIST_REFERENCE_TAGS, Item, list_change
from fm27_editor.record_changes import (
    REFERENCE,
    NewIds,
    checked_number,
    is_uid,
    refusal,
    stored_value,
)
from fm27_editor.record_rules import LOOKUP_TABLES, check_exists

HISTORY_CODE = "AWsh"
YEAR_CODE, NO_DATA_CODE, NOT_HELD_CODE = "AHye", "AHnd", "Ahnt"
# The codes of what is known of a place, with the number of the place in them.
PLACE_CODES = {
    "person_uid": "AH{}p",
    "name": "AH{}n",
    "team_uid": "AH{}t",
    "points": "AH{}i",
    "more_points": "A{}i2",
    "age": "A{}ag",
    "nation_uid": "AH{}c",
    "position": "AHp{}",
}
AWARD_UID, YEAR, PLACES_KEY, NOT_HELD, KEEP = "award_uid", "year", "places", "not_held", "keep"
ENTRY_KEYS = {AWARD_UID, YEAR, PLACES_KEY, NOT_HELD}
OFFERED = ("person_uid", "name", "team_uid", "points", "age", "nation_uid")
NAMING = {KEEP, "person_uid", "name", "team_uid"}


@dataclass(frozen=True)
class Place:
    """Who has a place, as far as it is known."""

    person_uid: int | None = None
    name: str | None = None
    team_uid: int | None = None
    """The uid of a club, or of a nation for its national team."""
    points: int | None = None
    more_points: int | None = None
    age: int | None = None
    nation_uid: int | None = None
    position: int | None = None


@dataclass(frozen=True)
class Year:
    year: int
    places: Mapping[int, Place]
    """By number, from the first. Some years have a second place and no first."""
    not_held: bool = False
    no_data: bool = False


@dataclass(frozen=True)
class AwardHistory:
    award_uid: int
    years: list[Year]
    """Every year, as it is to be stored."""
    changed: list[tuple[Year | None, Year]]
    """What is different: the year as it is in the database, if it is there, and as it is to be."""
    already_so: int
    """Years that were asked for and are so already."""
    field: Field = dataclass_field(repr=False, compare=False)


def check_award_history(
    given: Any, fields: Mapping[str, Field], lookup: sqlite3.Connection
) -> list[AwardHistory]:
    """The history of each award that a request gives years for."""
    if not isinstance(given, list):
        raise EditError("award_history must be a list of years")
    checker = _Checker(history_field(fields), lookup)
    wanted: dict[int, dict[int, Mapping[str, Any]]] = {}
    for entry in given:
        award, year = checker.entry(entry)
        years = wanted.setdefault(award, {})
        if year in years:
            raise EditError(f"{_called(award, year)} is given twice")
        years[year] = entry
    return [checker.history(award, years) for award, years in wanted.items()]


def history_field(fields: Mapping[str, Field]) -> Field:
    """The history among the fields of an award."""
    field = fields.get(HISTORY_CODE)
    if field is None or field.type != "list":
        raise FieldDefinitionError("the Editor does not define the history of awards")
    if not field.is_editable:
        raise EditError("the history of awards cannot be edited in the Editor")
    return field


def history_part(field: Field, code: str) -> Field:
    """A part of a year that can be given a value."""
    for part in field.items:
        if part.code == code:
            reason = refusal(part, LIST_REFERENCE_TAGS)
            if reason is not None:
                raise EditError(f"{part.name} ({code}) {reason}")
            return part
    raise FieldDefinitionError(f"the Editor does not define {code} of an award's history")


def history_change(history: AwardHistory, ids: NewIds) -> Change:
    """The change that stores a history."""
    record = existing_record(history.award_uid)
    items = map(_item, history.years)
    return list_change(Table.AWARD, record, history.field, items, ids)


def read_history(lookup: sqlite3.Connection, award_uid: int) -> Iterator[Year]:
    """The history that the database has; a year can be in it more than once."""
    columns = ", ".join(part.name for part in dataclass_fields(Place))
    years = lookup.execute(
        "SELECT uid, year, not_held, no_data FROM award_year WHERE award_uid = ?"
        " ORDER BY year, uid",
        (award_uid,),
    )
    for uid, year, not_held, no_data in years.fetchall():
        places = lookup.execute(
            f"SELECT place, {columns} FROM award_place WHERE year_uid = ? ORDER BY place", (uid,)
        )
        found = {number: Place(*values) for number, *values in places}
        yield Year(year, found, bool(not_held), bool(no_data))


class _Checker:
    """Checks what a request gives against the Editor's definitions and the lookup."""

    def __init__(self, field: Field, lookup: sqlite3.Connection):
        self._field = field
        self._lookup = lookup

    def entry(self, given: Any) -> tuple[int, int]:
        """The award and the year that are meant."""
        _check_keys("award_history", given, ENTRY_KEYS)
        missing = [name for name in (AWARD_UID, YEAR) if name not in given]
        if missing:
            raise EditError(f"a year of award_history needs {', '.join(missing)}")
        award = given[AWARD_UID]
        check_exists(self._lookup, "award_history", award, "award")
        part = history_part(self._field, YEAR_CODE)
        year = checked_number("year of award_history", given[YEAR], part.lowest, part.highest)
        if (PLACES_KEY in given) == (NOT_HELD in given):
            raise EditError(f"{_called(award, year)} needs either places or not_held")
        if given.get(NOT_HELD, True) is not True:
            raise EditError(f"{_called(award, year)}: not_held can only be true")
        return award, year

    def history(self, award: int, wanted: Mapping[int, Mapping[str, Any]]) -> AwardHistory:
        years = list(read_history(self._lookup, award))
        changed, already_so = [], 0
        for number, given in sorted(wanted.items()):
            old = _only(award, number, years)
            new = self._year(_called(award, number), number, given, old)
            if new == old:
                already_so += 1
                continue
            changed.append((old, new))
            years = [entry for entry in years if entry is not old] + [new]
        years.sort(key=lambda entry: entry.year)
        return AwardHistory(award, years, changed, already_so, self._field)

    def _year(self, where: str, number: int, given: Mapping[str, Any], old: Year | None) -> Year:
        if NOT_HELD in given:
            return Year(number, {}, not_held=True)
        places = given[PLACES_KEY]
        if not isinstance(places, list) or not 1 <= len(places) <= PLACES:
            raise EditError(f"{where}: places must be a list of one to three")
        return Year(
            number,
            {
                place: self._place(f"{where}, place {place}", place, entry, old)
                for place, entry in enumerate(places, 1)
            },
        )

    def _place(self, where: str, number: int, given: Any, old: Year | None) -> Place:
        _check_keys(where, given, {KEEP, *OFFERED})
        for name, value in given.items():
            if value is None:
                raise EditError(f"{where}: {name} has no value")
        if not NAMING & given.keys():
            raise EditError(f"{where} needs a name, a person_uid, or a team_uid")
        kept = _kept(where, given[KEEP], old) if KEEP in given else Place()
        values = {name: given[name] for name in OFFERED if name in given}
        for name, value in values.items():
            self._check_value(where, name, number, value)
        if "person_uid" in values and "name" not in values:
            values["name"] = self._person_name(values["person_uid"])
        return replace(kept, **values)

    def _check_value(self, where: str, name: str, number: int, value: Any) -> None:
        part = history_part(self._field, PLACE_CODES[name].format(number))
        if name == "person_uid":
            if not is_uid(value) or self._person_name(value) is None:
                raise EditError(f"{where}: there is no person {value!r}")
        elif name == "team_uid":
            check_exists(self._lookup, where, value, "club", "nation")
        elif part.type == REFERENCE:
            check_exists(self._lookup, where, value, LOOKUP_TABLES[part.points_to])
        else:
            try:
                stored_value(part, value)
            except EditError as error:
                raise EditError(f"{where}: {error}") from error

    def _person_name(self, uid: int) -> str | None:
        """The name that most awards use, which is often shorter than the lookup's own."""
        row = self._lookup.execute(
            "SELECT name FROM award_place WHERE person_uid = ? AND name IS NOT NULL"
            " GROUP BY name ORDER BY count(*) DESC, name LIMIT 1",
            (uid,),
        ).fetchone()
        return record_name(self._lookup, "person", uid) if row is None else row[0]


def _check_keys(where: str, given: Any, known: set[str]) -> None:
    if not isinstance(given, Mapping):
        raise EditError(f"{where} must have named parts: {', '.join(sorted(known))}")
    unknown = given.keys() - known
    if unknown:
        raise EditError(f"{where} has no part named {', '.join(sorted(unknown))}")


def _only(award: int, number: int, years: list[Year]) -> Year | None:
    found = [entry for entry in years if entry.year == number]
    if len(found) > 1:
        raise EditError(f"{_called(award, number)} has more than one entry, so none can be changed")
    return found[0] if found else None


def _kept(where: str, number: Any, old: Year | None) -> Place:
    checked_number(f"{where}: keep", number, 1, PLACES)
    if old is None or number not in old.places:
        raise EditError(f"{where}: the history has no place {number} in that year")
    return old.places[number]


def _called(award: int, year: int) -> str:
    return f"{year} of award {award}"


def _item(year: Year) -> Item:
    item: dict[str, Any] = {
        YEAR_CODE: year.year,
        NO_DATA_CODE: year.no_data,
        NOT_HELD_CODE: year.not_held,
    }
    for number, place in year.places.items():
        for name, code in PLACE_CODES.items():
            item[code.format(number)] = getattr(place, name)
    return item
