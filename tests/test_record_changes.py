import datetime
import random

import pytest

from fm27_editor.change_list import ChangeList, Kind, Property
from fm27_editor.field_definitions import Field
from fm27_editor.record_changes import (
    EditError,
    NewIds,
    Table,
    add_record,
    existing_record,
    field_change,
    number,
)

RECORD = b"\x01\x02\x03\x04" * 2


def a_field(kind, **details):
    defaults = {
        "code": "Ztst",
        "name": "Test",
        "lowest": None,
        "highest": None,
        "choices": None,
        "points_to": None,
        "is_client_field": False,
        "is_language_field": False,
        "is_editable": True,
    }
    return Field(type=kind, **(defaults | details))


def a_number(**details):
    return a_field("integer", **({"lowest": 0, "highest": 20} | details))


def change_to(field, value):
    return field_change(Table.PERSON, RECORD, field, value, NewIds(ChangeList(), random.Random(1)))


def new_value(field, value):
    return next(item for item in change_to(field, value) if item.tag == "nwvl")


def tags(change):
    return [item.tag for item in change]


@pytest.mark.parametrize(
    ("value", "kind", "raw"),
    [
        (-1, Kind.INT8, b"\xff"),
        (-128, Kind.INT8, b"\x80"),
        (127, Kind.INT8, b"\x7f"),
        (128, Kind.INT16, b"\x80\x00"),
        (-129, Kind.INT16, b"\x7f\xff"),
        (32_767, Kind.INT16, b"\xff\x7f"),
        (32_768, Kind.INT32, b"\x00\x80\x00\x00"),
        (2_147_483_648, Kind.INT64, b"\x00\x00\x00\x80\x00\x00\x00\x00"),
    ],
)
def test_a_number_takes_the_smallest_signed_size(value, kind, raw):
    assert number("Zed ", value) == Property("Zed ", kind, raw)


def test_a_field_change_names_the_record_and_the_field():
    change = change_to(a_field("integer", code="Zjmp", lowest=0, highest=20), 7)

    assert change[:4] == [
        Property("dtty", Kind.INT8, b"\x01"),
        Property("duni", Kind.ID, RECORD),
        Property("prty", Kind.CODE, "Zjmp"),
        Property("nwvl", Kind.INT8, b"\x07"),
    ]
    assert change[4] == Property("vers", Kind.INT16, b"\xac\x0e")
    assert tags(change) == ["dtty", "duni", "prty", "nwvl", "vers", "rdui"]


def test_a_client_field_change_carries_the_client_marks():
    assert tags(change_to(a_number(is_client_field=True), 1))[6:] == ["ISCF", "DBCI"]


def test_a_language_field_change_carries_the_language_mark():
    assert tags(change_to(a_field("string", is_language_field=True), "a"))[6:] == ["ISLF"]


def test_a_client_and_language_field_change_carries_every_mark_in_order():
    field = a_field("string", is_client_field=True, is_language_field=True)

    assert tags(change_to(field, "a"))[6:] == ["ISCF", "ISLF", "DBCI"]


def test_text_is_stored_as_text():
    assert new_value(a_field("string"), "Zoë") == Property("nwvl", Kind.TEXT, "Zoë")


def test_an_attribute_is_stored_as_text_the_way_the_editor_does():
    assert new_value(a_field("attribute"), 14) == Property("nwvl", Kind.TEXT, "14")


def test_a_choice_is_stored_by_its_number():
    field = a_field("enum", choices={0: "Calm", 2: "Cross"})

    assert new_value(field, 2) == Property("nwvl", Kind.INT8, b"\x02")


def test_yes_or_no_is_stored_as_one_byte():
    assert new_value(a_field("boolean"), True) == Property("nwvl", Kind.BOOL, b"\x01")
    assert new_value(a_field("boolean"), False) == Property("nwvl", Kind.BOOL, b"\x00")


@pytest.mark.parametrize(
    ("day", "raw"),
    [
        (datetime.date(2027, 6, 30), "00b5d60f"),
        (datetime.date(2028, 6, 30), "00b6d80f"),  # a leap year: one day later in the year
        (datetime.date(1900, 1, 1), "0001d80e"),
        (datetime.date(2028, 12, 31), "006ed90f"),  # day 366 needs a ninth bit
    ],
)
def test_a_date_is_stored_as_year_and_day_of_the_year(day, raw):
    assert new_value(a_field("date"), day) == Property("nwvl", Kind.DATE, bytes.fromhex(raw))


@pytest.mark.parametrize(
    ("table", "tag"),
    [
        ("nation", "Nnat"),
        ("team", "Ttea"),
        ("city", "city"),
        ("language", "lang"),
        ("competition", "comp"),
        ("stadium", "stad"),
    ],
)
def test_a_reference_names_the_other_record(table, tag):
    field = a_field("database_record_unique_id", points_to=table)

    assert new_value(field, 776).value == [
        Property("id  ", Kind.CODE, "nwvl"),
        Property(tag, Kind.ID, b"\x08\x03\x00\x00" * 2),
        Property("DBID", Kind.INT16, b"\x08\x03"),
    ]


def test_a_reference_to_a_new_record_carries_its_whole_id():
    field = a_field("database_record_unique_id", points_to="competition")

    assert new_value(field, b"\x08\x03\x00\x00\x09\x09\x09\x09").value[1:] == [
        Property("comp", Kind.ID, b"\x08\x03\x00\x00\x09\x09\x09\x09"),
        Property("DBID", Kind.INT16, b"\x08\x03"),
    ]


def test_a_colour_is_stored_blue_first():
    stored = new_value(a_field("colour"), "#480024")

    assert (stored.kind, stored.value) == (Kind.COLOUR_2, b"\x24\x00\x48\xff")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (a_field("colour"), "claret"),
        (a_field("colour"), "#48002"),
        (a_field("colour"), "480024"),
        (a_field("colour"), "#48002g"),
        (a_field("colour"), 5),
        (a_field("database_record_unique_id", points_to="competition"), b"\x08\x03"),
        (a_field("integer", lowest=0, highest=20), 21),
        (a_field("integer", lowest=0, highest=20), -1),
        (a_field("integer"), 5),
        (a_field("integer", lowest=0), 5),
        (a_field("attribute"), 21),
        (a_field("attribute"), -1),
        (a_field("enum", choices={0: "Calm"}), 1),
        (a_field("enum", choices=None), 1),
        (a_field("string"), ""),
        (a_field("string"), "  "),
        (a_field("string"), "two\nlines"),
        (a_field("string"), "zero\0byte"),
        (a_field("string"), "broken \ud800"),
        (a_field("string"), 5),
        (a_number(), "5"),
        (a_number(), True),
        (a_number(), 1.5),
        (a_field("boolean"), 1),
        (a_field("date"), "2027-06-30"),
        (a_field("date"), datetime.datetime(2027, 6, 30)),
        (a_field("database_record_unique_id", points_to="nation"), 0),
        (a_field("database_record_unique_id", points_to="nation"), 2**31),
        (a_field("database_record_unique_id", points_to="moon"), 5),
        (a_field("list"), 5),
        (a_field("cash"), 5),
        (a_number(is_editable=False), 5),
    ],
)
def test_a_value_the_editor_would_not_accept_is_refused_with_the_field_named(field, value):
    with pytest.raises(EditError, match="Ztst"):
        change_to(field, value)


def test_an_existing_record_is_its_unique_id_twice():
    assert existing_record(776) == b"\x08\x03\x00\x00" * 2


def test_a_new_record_is_added_to_the_table_of_everything():
    ids = NewIds(ChangeList(), random.Random(1))

    change = add_record(Table.PERSON, 2, RECORD, ids)

    assert change[:4] == [
        Property("dtty", Kind.INT8, b"\x37"),
        Property("duni", Kind.ID, b"\x01\x00\x00\x00" * 2),
        Property("prty", Kind.CODE, "ADDR"),
        Property(
            "nwvl",
            Kind.NESTED,
            [
                Property("id  ", Kind.CODE, "nwvl"),
                Property("dtty", Kind.INT8, b"\x01"),
                Property("dcty", Kind.CODE, "\x00\x00\x00\x02"),
                Property("duni", Kind.ID, RECORD),
            ],
        ),
    ]
    assert tags(change)[4:] == ["vers", "rdui", "ISCF", "DBCI"]


def test_a_record_that_is_not_a_person_has_no_type():
    change = add_record(Table.CLUB, None, RECORD, NewIds(ChangeList(), random.Random(1)))

    (described,) = [item.value for item in change if item.tag == "nwvl"]
    assert described[1:3] == [
        Property("dtty", Kind.INT8, b"\x03"),
        Property("dcty", Kind.INT8, b"\x00"),
    ]


def test_new_record_ids_lie_between_those_of_the_database_and_those_of_the_editor():
    ids = NewIds(ChangeList(), random.Random(1))

    uids = [int.from_bytes(ids.record()[:4], "little") for _ in range(1000)]

    assert min(uids) >= 100_000_000 and max(uids) < 2_000_000_000
    assert len(set(uids)) == 1000


def test_a_new_record_id_is_not_one_the_file_already_uses():
    first = NewIds(ChangeList(), random.Random(1)).record()
    changes = ChangeList(changes=[add_record(Table.PERSON, 2, first, NewIds(ChangeList()))])

    assert NewIds(changes, random.Random(1)).record() != first


@pytest.mark.parametrize(
    "change",
    [
        [Property("prty", Kind.CODE, "ADDR")],
        [Property("prty", Kind.CODE, "ADDR"), Property("nwvl", Kind.BOOL, b"\x01")],
        [
            Property("prty", Kind.CODE, "ADDR"),
            Property("nwvl", Kind.NESTED, [Property("duni", Kind.INT8_2, b"\xff")]),
        ],
    ],
    ids=["no new value", "not a record", "a short ID"],
)
def test_an_added_record_of_unknown_shape_is_reported(change):
    with pytest.raises(EditError, match="adds a record"):
        NewIds(ChangeList(changes=[change]))


def test_changes_that_add_nothing_do_not_matter_for_new_ids():
    changes = ChangeList(changes=[[], [Property("prty", Kind.CODE, "Ztst")]])

    assert NewIds(changes, random.Random(1)).record()
