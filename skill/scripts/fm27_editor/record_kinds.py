"""The kinds of records that can be set, and what sets each apart."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property

from fm27_editor import person_codes
from fm27_editor.change_reading import EditError, Table
from fm27_editor.people import PersonKind


@dataclass(frozen=True, eq=False)
class RecordGroup:
    """Records that live in one table and are found in one view of the lookup."""

    one: str
    view: str
    table: Table
    details: Mapping[str, str]
    """What tells a record from others of its name: columns of the view, and how to say them."""


@dataclass(frozen=True, eq=False)
class RecordKind:
    name: str
    group: RecordGroup
    defined_in: tuple[str, ...]
    """The Editor's definition files for its fields."""
    codes: Mapping[str, str]
    """The Editor's codes by the lookup's names."""
    needed: Mapping[str, str]
    """What a new record cannot be without: names by code."""
    left_out: frozenset[str]
    """Codes that are not set by hand."""
    person_type: int | None = None

    @cached_property
    def names(self) -> dict[str, str]:
        """The lookup's names by code."""
        return {code: name for name, code in self.codes.items()}


PEOPLE = RecordGroup(
    one="person",
    view="people",
    table=Table.PERSON,
    details={"birth_date": "born {}", "nation": "{}", "club": "{}"},
)
PERSON_NEEDS = {
    "Pfna": "First Name",
    "Psna": "Second Name",
    "Pdob": "Date Of Birth",
    "Pnti": "Nation",
}
# The record itself says the person type, and potential covers its ranges. The Editor works out the
# others, or shows them only in the game, though its definitions do not mark them.
PERSON_LEFT_OUT = frozenset(
    {
        *("Ptyp", "PPAR", "Page", "PnRV", "PShN", "dbnm", "Pbrl", "ERCL", "Pnhs", "NpCw"),
        *("PcHC", "Pion", "Phij", "Phbn"),
        *("PCRI", "PHRI", "PWRI", "NcrI", "NhmI", "NwrI"),
        *(f"BR{position:02}" for position in range(1, 15)),
    }
)
PLAYER = RecordKind(
    name="player",
    group=PEOPLE,
    defined_in=("player", "person"),
    codes=person_codes.COMMON | person_codes.PLAYER,
    needed=PERSON_NEEDS,
    left_out=PERSON_LEFT_OUT,
    person_type=PersonKind.PLAYER,
)
STAFF = RecordKind(
    name="staff",
    group=PEOPLE,
    defined_in=("non player", "person"),
    codes=person_codes.COMMON | person_codes.STAFF,
    needed=PERSON_NEEDS,
    left_out=PERSON_LEFT_OUT,
    person_type=PersonKind.STAFF,
)
KINDS = {kind.name: kind for kind in (PLAYER, STAFF)}


def kind_named(name: str) -> RecordKind:
    kind = KINDS.get(name)
    if kind is None:
        raise EditError(f"only {', '.join(KINDS)} can be set, not {name}")
    return kind
