"""What stands out in the history that a request gives an award."""

from collections.abc import Iterable, Iterator
from itertools import pairwise

from fm27_editor.award_history import Year
from fm27_editor.planned import HistoryEdit


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
