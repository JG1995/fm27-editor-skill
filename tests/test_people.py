import datetime

import pytest

import synthetic
from fm27_editor.people import PeopleError, PersonKind, iter_people, parse_basic_people
from fm27_editor.person_names import Names

NAMES = Names({1: "Testy"}, {2: "McTestface"}, {5: "Testo"})
STAFF_SAMPLE = [
    "working_with_youngsters",
    "determination",
    "coaching_goalkeeping",
    "coaching_attacking",
    "authority",
    "coaching_set_pieces",
    "negotiating",
]


def read_all(basic_records, people_records):
    basic = parse_basic_people(synthetic.basic_people(basic_records))
    return list(
        iter_people(basic, synthetic.people_stream(people_records, len(people_records)), NAMES)
    )


def test_basic_records_of_every_kind_are_read():
    records = [
        synthetic.basic_person(kind, index, 100 + index)
        for index, kind in enumerate([1, 2, 3, 4, 5, 2])
    ]

    people = parse_basic_people(synthetic.basic_people(records))

    assert [(p.index, p.uid, p.kind) for p in people] == [
        (0, 100, PersonKind.STAFF),
        (1, 101, PersonKind.PLAYER),
        (2, 102, PersonKind.BOTH),
        (3, 103, PersonKind.OFFICIAL),
        (4, 104, PersonKind.RETIRED),
        (5, 105, PersonKind.PLAYER),
    ]


def test_basic_record_carries_nation_club_ability_and_signed_potential():
    people = parse_basic_people(
        synthetic.basic_people(
            [synthetic.basic_person(2, 0, 100, ca=150, pa=-85, nation=(51, 9002), club=(61, 9101))]
        )
    )

    (person,) = people
    assert (person.nation_uid, person.club_uid, person.ca, person.pa) == (9002, 9101, 150, -85)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(synthetic.basic_people([synthetic.basic_person(2, 0, 100)])[:-4], id="short"),
        pytest.param(
            synthetic.basic_people([synthetic.basic_person(2, 0, 100)]) + b"\x00\x00", id="trailing"
        ),
        pytest.param(
            synthetic.basic_people([synthetic.basic_person(2, 3, 100)]), id="index out of order"
        ),
        pytest.param(synthetic.basic_people([b"\x11\x09" + b"\x00" * 40]), id="unknown kind"),
    ],
)
def test_rejects_basic_people_that_do_not_follow_the_layout(content):
    with pytest.raises(PeopleError):
        parse_basic_people(content)


def test_player_record_yields_name_birth_date_attributes_and_personality():
    attributes = {52: 17, 84: 20, 35: 1, 47: 20, 74: 8, 75: 20}
    record = synthetic.person_record(0, 100, attributes=attributes, day=100, year=1999)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert person.full_name == "Testy McTestface"
    assert person.birth_date == datetime.date(1999, 4, 10)
    assert person.fields["finishing"] == 17
    assert person.fields["acceleration"] == 20
    assert person.fields["position_st"] == 20
    assert person.fields["right_foot"] == 20
    assert person.fields["adaptability"] == 10
    assert person.fields["controversy"] == 17


def test_unresearched_values_are_missing_rather_than_zero():
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [synthetic.person_record(0, 100)])

    assert "finishing" not in person.fields
    assert person.fields["adaptability"] == 10


@pytest.mark.parametrize(
    ("common", "full", "name", "full_name"),
    [
        (0xFFFFFFFF, "Testy Long McTestface", "Testy McTestface", "Testy Long McTestface"),
        (0xFFFFFFFF, "", "Testy McTestface", None),
        (5, "Testy Long McTestface", "Testo", "Testy Long McTestface"),
    ],
)
def test_the_name_is_the_common_name_or_the_first_and_second_name(common, full, name, full_name):
    """As the game shows a person; the full name is the one written out in the record, if any."""
    record = synthetic.person_record(0, 100, common=common, full_name=full)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert (person.name, person.full_name) == (name, full_name)


@pytest.mark.parametrize(
    ("part", "expected"),
    [("first", "Ownly McTestface"), ("second", "Testy Ownly"), ("common", "Ownly")],
)
def test_a_name_that_the_name_tables_lack_is_read_from_the_record(part, expected):
    record = synthetic.person_record(0, 100, **{part: "Ownly"})
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert person.name == expected


def test_a_written_name_must_repeat_its_number_after_it():
    record = bytearray(synthetic.person_record(0, 100, second="Ownly"))
    after = record.index(b"Ownly") + len("Ownly")
    record[after : after + 4] = (901).to_bytes(4, "little")

    assert read_all([synthetic.basic_person(2, 0, 100)], [bytes(record)]) == []


def test_a_long_full_name_is_read():
    full = "Testy " + "Middle " * 25 + "McTestface"
    record = synthetic.person_record(0, 100, full_name=full)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert person.full_name == full


def test_people_are_matched_by_uid_not_by_order():
    basic = [synthetic.basic_person(2, i, 100 + i) for i in range(3)]
    records = [synthetic.person_record(i, 100 + i, full_name=f"Person {i}") for i in (2, 0, 1)]

    people = {p.uid: p.full_name for p in read_all(basic, records)}

    assert people == {100: "Person 0", 101: "Person 1", 102: "Person 2"}


def test_a_stray_nation_marker_is_not_mistaken_for_the_birth_date():
    record = synthetic.person_record(0, 100, decoy=True)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert person.full_name == "Testy McTestface"


def test_people_whose_names_cannot_be_found_are_skipped_not_guessed():
    unknown_name = synthetic.person_record(0, 100, first=99)
    assert read_all([synthetic.basic_person(2, 0, 100)], [unknown_name]) == []


def test_an_official_is_read_with_the_nation_of_the_short_record():
    basic = synthetic.basic_person(4, 0, 100, nation=(7, 9007))
    record = synthetic.person_record(0, 100, nation=(7, 9007), kind=4, attributes={52: 17})

    (person,) = read_all([basic], [record])

    assert (person.kind, person.name, person.nation_uid) == (
        PersonKind.OFFICIAL,
        "Testy McTestface",
        9007,
    )
    assert person.birth_date == datetime.date(2004, 2, 29)
    assert person.fields == {}


def test_a_retired_person_has_only_a_name():
    basic = [synthetic.basic_person(5, 0, 100)]

    (person,) = read_all(basic, [synthetic.retired_record(0, 100, "Old Testman")])

    assert (person.kind, person.name, person.full_name) == (
        PersonKind.RETIRED,
        "Old Testman",
        "Old Testman",
    )
    assert (person.birth_date, person.nation_uid, person.club_uid, person.fields) == (
        None,
        None,
        None,
        {},
    )


@pytest.mark.parametrize("at", [4, 5, -12 - 1])
def test_a_retired_person_outside_the_known_layout_is_skipped(at):
    """The kind, the four zero bytes before the name, and the eight after it are checked."""
    record = bytearray(synthetic.retired_record(0, 100, "Old Testman"))
    record[at] = 9

    assert read_all([synthetic.basic_person(5, 0, 100)], [bytes(record)]) == []


def test_a_retired_person_without_a_name_is_skipped():
    """A name is all such a record has."""
    record = synthetic.retired_record(0, 100, "")

    assert read_all([synthetic.basic_person(5, 0, 100)], [record]) == []


def test_staff_and_other_kinds_do_not_get_player_fields():
    """Players' byte positions were only checked on players, and personality on staff as well."""
    kinds = [1, 2, 3, 2]
    records = [
        synthetic.person_record(i, 100 + i, attributes={52: 17}, kind=kind)
        for i, kind in enumerate(kinds)
    ]
    basic = [synthetic.basic_person(kind, index, 100 + index) for index, kind in enumerate(kinds)]

    people = {p.uid: p.fields for p in read_all(basic, records)}

    assert "finishing" not in people[100]
    assert people[100]["adaptability"] == 10
    assert people[102] == {}
    assert people[101]["finishing"] == 17


@pytest.mark.parametrize("items", [0, 3])
def test_staff_attributes_count_from_the_end_of_the_list_at_the_start(items):
    staff = {32: 16, 33: 18, 47: 1, 54: 20, 68: 12, 71: 14}
    record = synthetic.person_record(0, 100, kind=1, staff_items=items, staff_attributes=staff)
    (person,) = read_all([synthetic.basic_person(1, 0, 100)], [record])

    assert {name: person.fields.get(name) for name in STAFF_SAMPLE} == {
        "working_with_youngsters": 16,
        "determination": 18,
        "coaching_goalkeeping": 1,
        "coaching_attacking": 20,
        "authority": 12,
        "coaching_set_pieces": 14,
        "negotiating": None,
    }
    assert person.fields["adaptability"] == 10


def test_staff_whose_first_list_is_not_in_the_known_layout_get_no_staff_attributes():
    record = bytearray(
        synthetic.person_record(0, 100, kind=1, staff_items=1, staff_attributes={32: 16})
    )
    record[7] = 2
    (person,) = read_all([synthetic.basic_person(1, 0, 100)], [bytes(record)])

    assert "working_with_youngsters" not in person.fields
    assert person.fields["adaptability"] == 10


def test_a_record_that_does_not_start_with_its_own_index_gets_no_fields():
    record = bytearray(synthetic.person_record(0, 100, attributes={52: 17}))
    record[0:4] = (9).to_bytes(4, "little")
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [bytes(record)])

    assert person.fields == {}
    assert person.full_name == "Testy McTestface"


def test_attribute_values_outside_one_to_twenty_are_missing():
    attributes = {52: 20, 84: 21, 88: 255, 67: 1}
    record = synthetic.person_record(0, 100, attributes=attributes)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert person.fields["finishing"] == 20
    assert person.fields["anticipation"] == 1
    assert "acceleration" not in person.fields and "pace" not in person.fields


def test_ability_of_zero_and_no_club_are_missing():
    basic = synthetic.basic_person(2, 0, 100, ca=0, pa=0, club=(0xFFFFFFFF, 0xFFFFFFFF))

    (person,) = parse_basic_people(synthetic.basic_people([basic]))

    assert (person.ca, person.pa, person.club_uid) == (None, None, None)


@pytest.mark.parametrize("kind", [1, 2])
def test_the_contract_with_the_club_gives_the_wage_and_when_it_expires(kind):
    record = synthetic.person_record(0, 100, kind=kind, contract=synthetic.contract_block(0))
    (person,) = read_all([synthetic.basic_person(kind, 0, 100)], [record])

    assert (person.wage, person.contract_expires) == (25_000, datetime.date(2029, 6, 30))


def test_a_wage_of_0_and_the_first_day_of_1900_are_missing():
    contract = synthetic.contract_block(0, wage=0, expires=(1, 1900))
    record = synthetic.person_record(0, 100, contract=contract)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert (person.wage, person.contract_expires) == (None, None)


@pytest.mark.parametrize(
    "contract",
    [
        pytest.param(synthetic.contract_block(0, (8, 9102)), id="another club"),
        pytest.param(synthetic.contract_block(1), id="another person"),
        pytest.param(
            synthetic.contract_block(0, before=b"\xff\xff\xff\xff\x05\x05"), id="not after a date"
        ),
        pytest.param(synthetic.contract_block(0, expires=(0, 0)), id="no date where it expires"),
        pytest.param(synthetic.contract_block(0) * 2, id="twice"),
    ],
)
def test_only_one_contract_with_the_persons_club_after_a_date_is_read(contract):
    """Staff have another block with the index and the club, which follows no date."""
    record = synthetic.person_record(0, 100, contract=contract)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert (person.wage, person.contract_expires) == (None, None)


def test_a_person_without_a_club_has_no_contract():
    basic = synthetic.basic_person(2, 0, 100, club=(0xFFFFFFFF, 0xFFFFFFFF))
    record = synthetic.person_record(0, 100, contract=synthetic.contract_block(0))
    (person,) = read_all([basic], [record])

    assert (person.wage, person.contract_expires) == (None, None)


def test_a_birth_date_on_the_first_day_of_1900_is_missing():
    """The Editor's date for no date."""
    record = synthetic.person_record(0, 100, day=1, year=1900)
    (person,) = read_all([synthetic.basic_person(2, 0, 100)], [record])

    assert person.birth_date is None


@pytest.mark.parametrize(("year", "found"), [(2004, True), (2005, False)])
def test_day_366_only_exists_in_leap_years(year, found):
    record = synthetic.person_record(0, 100, day=366, year=year)

    assert bool(read_all([synthetic.basic_person(2, 0, 100)], [record])) is found
