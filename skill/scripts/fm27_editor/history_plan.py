"""Planning the histories that a request gives awards, and what stands out in them."""

import sqlite3
from collections.abc import Iterable, Iterator
from itertools import pairwise
from typing import Any

from fm27_editor.award_history import HISTORY_CODE, Year, check_award_history
from fm27_editor.planned import HistoryEdit, StartingFile, known_record
from fm27_editor.record_fields import RecordFields
from fm27_editor.record_kinds import AWARD
from fm27_editor.request import RequestError


def plan_histories(
    given: Any, record_fields: RecordFields, lookup: sqlite3.Connection, start: StartingFile | None
) -> list[HistoryEdit]:
    """The history of each award that is asked for, also when nothing in it is to change."""
    edits = [
        HistoryEdit(known_record(AWARD.group, history.award_uid, lookup), history)
        for history in check_award_history(given, record_fields.fields(AWARD), lookup)
    ]
    for edit in edits:
        _check_not_changed_before(edit, start)
    return edits


def _check_not_changed_before(edit: HistoryEdit, start: StartingFile | None) -> None:
    """A history is stored whole, so the one in the starting file would be lost."""
    if start is None or not edit.history.changed:
        return
    if (edit.award.address, HISTORY_CODE) in start.changed:
        raise RequestError(
            f"the file to start from changes the history of {edit.award.name} already"
        )


def history_warnings(edits: Iterable[HistoryEdit]) -> Iterator[str]:
    for edit in edits:
        years = [new for _, new in edit.history.changed]
        rising = [str(year.year) for year in years if _has_rising_points(year)]
        if rising:
            yield f"{edit.award.name}: a lower place has more points in {', '.join(rising)}"
        twice = [str(year.year) for year in years if _has_someone_twice(year)]
        if twice:
            yield f"{edit.award.name}: someone is placed twice in {', '.join(twice)}"


def _has_rising_points(year: Year) -> bool:
    points = [place.points for place in year.places.values() if place.points is not None]
    return any(higher < lower for higher, lower in pairwise(points))


def _has_someone_twice(year: Year) -> bool:
    people = [place.person_uid for place in year.places.values() if place.person_uid is not None]
    unlinked = [
        place.name
        for place in year.places.values()
        if place.person_uid is None and place.name is not None
    ]
    return len(set(people)) < len(people) or len(set(unlinked)) < len(unlinked)
