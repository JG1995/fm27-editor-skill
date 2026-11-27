import datetime

import pytest

import synthetic
from fm27_editor.people import PeopleError, PersonKind, iter_people, parse_basic_people
from fm27_editor.person_names import Names

NAMES = Names({1: "Testy"}, {2: "McTestface"}, {5: "Testo"})


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
        (0xFFFFFFFF, "", "Testy McTestface", "Testy McTestface"),
        (5, "Testy Long McTestface", "Testo", "Testy Long McTestface"),
    ],
)
def test_the_name_is_the_common_name_or_the_first_and_second_name(common, full, name, full_name):
    """As the game shows a person; the full name is the one written out in the record."""
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


def test_records_without_player_details_are_skipped():
    records = [synthetic.person_record(1, 101)]
    basic = [synthetic.basic_person(5, 0, 100), synthetic.basic_person(2, 1, 101)]

    assert [p.uid for p in read_all(basic, records)] == [101]


def test_staff_and_other_kinds_do_not_get_player_fields():
    """The byte positions were only checked on players."""
    records = [synthetic.person_record(i, 100 + i, attributes={52: 17}) for i in range(4)]
    basic = [
        synthetic.basic_person(kind, index, 100 + index) for index, kind in enumerate([1, 2, 3, 2])
    ]

    people = {p.uid: p.fields for p in read_all(basic, records)}

    assert people[100] == people[102] == {}
    assert people[101]["finishing"] == 17


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


@pytest.mark.parametrize(("year", "found"), [(2004, True), (2005, False)])
def test_day_366_only_exists_in_leap_years(year, found):
    record = synthetic.person_record(0, 100, day=366, year=year)

    assert bool(read_all([synthetic.basic_person(2, 0, 100)], [record])) is found
