"""Potential ability, which is a number or, below 0, one of the Editor's ranges."""

from collections.abc import Iterable
from dataclasses import replace

from fm27_editor.change_reading import EditError
from fm27_editor.field_definitions import Field
from fm27_editor.record_kinds import RecordKind

POTENTIAL, ABILITY = "pa", "ca"
PLAYER_POTENTIAL, POTENTIAL_RANGE = "PPAB", "PPAR"
POTENTIALS = {PLAYER_POTENTIAL, "Npta"}


def is_range(field: Field, value: object) -> bool:
    return field.code in POTENTIALS and isinstance(value, int) and value < 0


def with_ranges(fields: dict[str, Field]) -> dict[str, Field]:
    """The fields with the choice of ranges, which the Editor shows apart, on the number itself."""
    if PLAYER_POTENTIAL not in fields or POTENTIAL_RANGE not in fields:
        return fields
    ranges = fields[POTENTIAL_RANGE].choices
    return fields | {PLAYER_POTENTIAL: replace(fields[PLAYER_POTENTIAL], choices=ranges)}


def check_potential(field: Field, value: object) -> None:
    """A negative potential stands for a range, and only some numbers do."""
    is_listed = field.code == PLAYER_POTENTIAL
    if is_listed and is_range(field, value) and value not in (field.choices or {}):
        raise EditError(f"{value} is not one of the Editor's potential ranges")


def has_more_ability_than_potential(
    kind: RecordKind, set_to: Iterable[tuple[str, object]], ca: int | None, pa: int | None
) -> bool:
    """Whether values by code would leave a person, who has `ca` and `pa` now, above potential.

    A range is not compared, and neither is a potential that is not known.
    """
    values = dict(set_to)
    ca, pa = values.get(kind.codes.get(ABILITY), ca), values.get(kind.codes.get(POTENTIAL), pa)
    return ca is not None and pa is not None and 0 < pa < ca
