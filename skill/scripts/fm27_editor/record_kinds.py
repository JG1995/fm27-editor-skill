"""The kinds of records that can be set, and what sets each apart."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property

from fm27_editor import person_codes
from fm27_editor.change_reading import EditError, Table
from fm27_editor.list_changes import ListShape
from fm27_editor.people import PersonKind
from fm27_editor.person_lists import PERSON_LISTS
from fm27_editor.places import Gender


@dataclass(frozen=True, eq=False)
class RecordGroup:
    """Records that live in one table and are found in one view of the lookup."""

    one: str
    view: str
    table: Table
    details: Mapping[str, str]
    """What tells a record from others of its name: columns of the view, and how to say them."""
    name_codes: tuple[str, ...]
    """The fields a name is made of, in the order they are said."""


@dataclass(frozen=True)
class HeldList:
    """Where the lookup holds the items of a list: a table with a row for each item."""

    table: str
    owner: str
    """The column with the uid of the record whose list it is."""
    order: str
    parts: Mapping[str, str]
    """The Editor's codes of the parts by the lookup's names."""
    known_by: str | None = None
    """A fact of the record that is missing when the lookup could not read its list; without one,
    the lookup knows every record's list."""


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
    left_out_families: tuple[str, ...] = ()
    """What the codes of whole groups of fields start with that are not set by hand either."""
    person_type: int | None = None
    pointed_to_as: tuple[str, ...] = ()
    """What the Editor's definitions call a record of this kind that a field points to."""
    words: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    """The numbers of choices that the lookup holds as words, by code."""
    can_be_new: bool = True
    """Whether a file was seen that adds a record of this kind."""
    lists: Mapping[str, ListShape] = field(default_factory=dict)
    """The lists that can be given items, by code, in the shape real files show."""
    held_lists: Mapping[str, HeldList] = field(default_factory=dict)
    """The lists whose items the lookup holds, by code."""

    @cached_property
    def names(self) -> dict[str, str]:
        """The lookup's names by code."""
        return {code: name for name, code in self.codes.items()}

    def offers(self, code: str) -> bool:
        return code not in self.left_out and not code.startswith(self.left_out_families)


PEOPLE = RecordGroup(
    one="person",
    view="people",
    table=Table.PERSON,
    details={"birth_date": "born {}", "nation": "{}", "club": "{}"},
    name_codes=person_codes.NAME_CODES,
)
CLUBS = RecordGroup(
    one="club",
    view="clubs",
    table=Table.CLUB,
    details={"nation": "{}", "gender": "{}", "division": "{}"},
    name_codes=("Cnam",),
)
COMPETITIONS = RecordGroup(
    one="competition",
    view="competitions",
    table=Table.COMPETITION,
    details={"nation": "{}", "gender": "{}", "level": "level {}"},
    name_codes=("cnam",),
)
AWARDS = RecordGroup(
    one="award",
    view="awards",
    table=Table.AWARD,
    details={"nation": "{}", "gender": "{}", "competition": "{}"},
    name_codes=("AWna",),
)
STADIUMS = RecordGroup(
    one="stadium",
    view="stadiums",
    table=Table.STADIUM,
    details={"city": "{}", "nation": "{}"},
    name_codes=("Snam",),
)
NATIONS = RecordGroup(
    one="nation",
    view="nations",
    table=Table.NATION,
    details={},
    name_codes=("Nnam",),
)
CITIES = RecordGroup(
    one="city",
    view="cities",
    table=Table.CITY,
    details={"nation": "{}"},
    name_codes=("Cnam",),
)
CONTINENTS = RecordGroup(
    one="continent",
    view="continents",
    table=Table.CONTINENT,
    details={},
    name_codes=("Cnam",),
)
INJURIES = RecordGroup(
    one="injury",
    view="injuries",
    table=Table.INJURY,
    details={},
    name_codes=("Inam",),
)
WEATHERS = RecordGroup(
    one="weather",
    view="weathers",
    table=Table.WEATHER,
    details={},
    name_codes=("wnam",),
)
MEDIA_SOURCES = RecordGroup(
    one="media source",
    view="media_sources",
    table=Table.MEDIA_SOURCE,
    details={},
    name_codes=("Mnam",),
)
DERBIES = RecordGroup(
    one="derby",
    view="derbies",
    table=Table.DERBY,
    details={"club_1": "{}", "club_2": "{}"},
    name_codes=("Dnam",),
)
STAGE_NAMES = RecordGroup(
    one="stage name",
    view="stage_names",
    table=Table.STAGE_NAME,
    details={},
    name_codes=("SNna",),
)
GROUPS = {
    group.view: group
    for group in (
        *(PEOPLE, CLUBS, COMPETITIONS, AWARDS, STADIUMS, NATIONS, CITIES),
        *(CONTINENTS, INJURIES, WEATHERS, MEDIA_SOURCES, DERBIES, STAGE_NAMES),
    )
}
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
PERSON_HELD_LISTS = {
    "Plhs": HeldList("history_season", "person_uid", "item", person_codes.PLAYING_HISTORY),
    "Pdcn": HeldList(
        "club_or_nation_days",
        "person_uid",
        "item",
        person_codes.DAYS_AT_CLUB_OR_NATION,
        known_by="clubs_and_nations",
    ),
}
PLAYER = RecordKind(
    name="player",
    group=PEOPLE,
    defined_in=("player", "person"),
    codes=person_codes.COMMON | person_codes.PLAYER,
    needed=PERSON_NEEDS,
    left_out=PERSON_LEFT_OUT,
    person_type=PersonKind.PLAYER,
    pointed_to_as=("person",),
    lists=PERSON_LISTS,
    held_lists=PERSON_HELD_LISTS,
)
STAFF = RecordKind(
    name="staff",
    group=PEOPLE,
    defined_in=("non player", "person"),
    codes=person_codes.COMMON | person_codes.STAFF,
    needed=PERSON_NEEDS,
    left_out=PERSON_LEFT_OUT,
    person_type=PersonKind.STAFF,
    pointed_to_as=("person",),
    lists=PERSON_LISTS,
    held_lists=PERSON_HELD_LISTS,
)
GENDER = "gender"
GENDER_CODE = "PLgn"
GENDER_WORDS = {GENDER_CODE: {Gender.MALE: 0, Gender.FEMALE: 1}}
COMPUTED_NAMES = ("dbnm", "dAPw")
# The record books: highest attendance, biggest win, and so on.
CLUB_RECORDS = (
    *("CAA", "CBD", "CBW", "CFG", "CGL", "CGM", "CHA", "CHF", "CHG", "CHL", "CHR", "CHS", "CLA"),
    *("CLR", "CMA", "CMC", "CMG", "CMO", "COP", "COS", "CWC", "CWL", "CWR", "CWS", "CWW", "CYP"),
    "CYS",
)
CLUB = RecordKind(
    name="club",
    group=CLUBS,
    defined_in=("club",),
    codes={
        "name": "Cnam",
        "short_name": "Csnm",
        GENDER: GENDER_CODE,
        "is_extinct": "Cext",
        "nation_uid": "Cnti",
        "based_nation_uid": "Cbni",
        "city_uid": "Ccty",
        "stadium_uid": "Csti",
        "reputation": "Crep",
        "division_uid": "Cdvi",
        "last_division_uid": "Cldi",
        "last_position": "Clps",
    },
    needed={"Cnam": "Name", "Csnm": "Short Name", "Cnti": "Nation"},
    # The Editor shows facts of the stadium and whether there is a list among those of the club.
    # Crkt is called a yes or no, and holds other numbers in 305 real changes.
    left_out=frozenset(
        {
            *COMPUTED_NAMES,
            *("Snam", "Scpy", "Sscy", "Scas", "Secy", "Sucy", "Sdcy", "Spty", "Scov", "Sush"),
            "Sscl",
            *("Chrd", "CrcS", "Cmls", "Crkt"),
        }
    ),
    left_out_families=CLUB_RECORDS,
    pointed_to_as=("club", "team"),
    words=GENDER_WORDS,
)
COMPETITION = RecordKind(
    name="competition",
    group=COMPETITIONS,
    defined_in=("comp",),
    codes={
        "name": "cnam",
        "short_name": "csnm",
        GENDER: GENDER_CODE,
        "level": "levl",
        "nation_uid": "cnti",
        "parent_uid": "cpcm",
    },
    needed={"cnam": "Name", "csnm": "Short Name", "cnti": "Nation", "dbty": "Type"},
    left_out=frozenset({*COMPUTED_NAMES, "DBvw"}),
    left_out_families=(*CLUB_RECORDS, "HCA", "LCA"),
    pointed_to_as=("competition",),
    words=GENDER_WORDS,
)
AWARD = RecordKind(
    name="award",
    group=AWARDS,
    defined_in=("award",),
    codes={
        "name": "AWna",
        "short_name": "AWsn",
        "nation_uid": "AWni",
        "competition_uid": "AWmi",
        "previous_winner": "AWap",
    },
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
STADIUM = RecordKind(
    name="stadium",
    group=STADIUMS,
    defined_in=("stadium",),
    codes={"name": "Snam", "city_uid": "Scti"},
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
NATION = RecordKind(
    name="nation",
    group=NATIONS,
    defined_in=("nation",),
    codes={"name": "Nnam"},
    needed={},
    left_out=frozenset({*COMPUTED_NAMES, "DBvw"}),
    can_be_new=False,
)
CITY = RecordKind(
    name="city",
    group=CITIES,
    defined_in=("city",),
    codes={"name": "Cnam", "nation_uid": "Cnti"},
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
CONTINENT = RecordKind(
    name="continent",
    group=CONTINENTS,
    defined_in=("continent",),
    codes={"name": "Cnam"},
    needed={},
    left_out=frozenset({*COMPUTED_NAMES, "DBvw"}),
    can_be_new=False,
)
INJURY = RecordKind(
    name="injury",
    group=INJURIES,
    defined_in=("injury",),
    codes={"name": "Inam"},
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
WEATHER = RecordKind(
    name="weather",
    group=WEATHERS,
    defined_in=("weather",),
    codes={"name": "wnam"},
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
MEDIA_SOURCE = RecordKind(
    name="media_source",
    group=MEDIA_SOURCES,
    defined_in=("media source",),
    codes={"name": "Mnam"},
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
DERBY = RecordKind(
    name="derby",
    group=DERBIES,
    defined_in=("derby",),
    codes={
        "name": "Dnam",
        "short_name": "Dsnm",
        "club_1_uid": "Dtm1",
        "club_2_uid": "Dtm2",
    },
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
STAGE_NAME = RecordKind(
    name="stage_name",
    group=STAGE_NAMES,
    defined_in=("stage name",),
    codes={"name": "SNna"},
    needed={},
    left_out=frozenset(COMPUTED_NAMES),
    can_be_new=False,
)
KINDS = {
    kind.name: kind
    for kind in (
        *(PLAYER, STAFF, CLUB, COMPETITION, AWARD, STADIUM, NATION, CITY),
        *(CONTINENT, INJURY, WEATHER, MEDIA_SOURCE, DERBY, STAGE_NAME),
    )
}


def kind_of(group: RecordGroup, facts: Mapping[str, object]) -> RecordKind:
    """The kind of a record that the lookup describes."""
    kinds = [kind for kind in KINDS.values() if kind.group is group]
    return kinds[0] if len(kinds) == 1 else kind_named(str(facts["kind"]))


def kind_named(name: str) -> RecordKind:
    kind = KINDS.get(name)
    if kind is None:
        raise EditError(f"only {', '.join(KINDS)} can be set, not {name}")
    return kind
