import datetime
import random

import pytest

from fm27_editor.change_list import ChangeList, Kind, ListItem, Property
from fm27_editor.field_definitions import Field
from fm27_editor.list_changes import ListShape, item_changes, list_change
from fm27_editor.record_changes import EditError, NewIds, Table

RECORD = b"\x01\x02\x03\x04" * 2


def a_field(code, kind, *, points_to=None, choices=None, items=()):
    return Field(
        code=code,
        name="Test",
        type=kind,
        lowest=None,
        highest=None,
        choices=choices,
        points_to=points_to,
        is_client_field=False,
        is_language_field=False,
        is_editable=True,
        items=tuple(items),
    )


PARTS = [
    a_field("Zheld", "boolean"),
    a_field("Zpos", "enum", choices={64: "Left"}),
    a_field("Ztea", "database_record_unique_id", points_to="team"),
    a_field("Znam", "string"),
    a_field("Zwho", "database_record_unique_id", points_to="person"),
    a_field("Zyer", "integer"),
]
SHAPE = ListShape(("Zyer", "Zwho", "Znam", "Ztea", "Zpos", "Zheld"))


def stored(*items, parts=PARTS, shape=SHAPE):
    field = a_field("Zlst", "list", items=parts)
    ids = NewIds(ChangeList(), random.Random(1))
    return list_change(Table.AWARD, RECORD, field, shape, items, ids)


def inside(change):
    (new,) = [part for part in change if part.tag == "nwvl"]
    assert new.kind is Kind.LIST
    return new.value


def test_every_part_of_an_item_is_stored_in_the_order_of_its_shape():
    given = {"Zheld": True, "Zpos": 64, "Znam": "Zoë", "Ztea": 776, "Zwho": 100, "Zyer": 1973}

    assert inside(stored(given)) == [
        ListItem(
            Kind.NESTED,
            [
                Property("Zyer", Kind.INT16, b"\xb5\x07"),
                Property(
                    "Zwho",
                    Kind.NESTED,
                    [
                        Property("id  ", Kind.CODE, "Zwho"),
                        Property("Pers", Kind.ID, b"\x64\x00\x00\x00" * 2),
                    ],
                ),
                Property("Znam", Kind.TEXT, "Zoë"),
                Property(
                    "Ztea",
                    Kind.NESTED,
                    [
                        Property("id  ", Kind.CODE, "Ztea"),
                        Property("Ttea", Kind.ID, b"\x08\x03\x00\x00" * 2),
                    ],
                ),
                Property("Zpos", Kind.INT8, b"\x40"),
                Property("Zheld", Kind.BOOL, b"\x01"),
            ],
        )
    ]


def test_what_has_no_value_is_stored_as_nothing_but_a_text_as_empty():
    (item,) = inside(stored({"Zheld": False}))

    assert [(part.tag, part.kind, part.value) for part in item.value] == [
        ("Zyer", Kind.NULL, b""),
        ("Zwho", Kind.NULL, b""),
        ("Znam", Kind.TEXT, ""),
        ("Ztea", Kind.NULL, b""),
        ("Zpos", Kind.NULL, b""),
        ("Zheld", Kind.BOOL, b"\x00"),
    ]


def test_the_change_names_the_record_and_the_list():
    change = stored({"Zyer": 1973}, {"Zyer": 1974})

    assert change[:3] == [
        Property("dtty", Kind.INT8, b"\x00"),
        Property("duni", Kind.ID, RECORD),
        Property("prty", Kind.CODE, "Zlst"),
    ]
    assert [part.tag for part in change] == ["dtty", "duni", "prty", "nwvl", "vers", "rdui"]
    assert len(inside(change)) == 2


# Modelled on Second Nations: an added item has Nationality Info 80 and no nation.
NATIONS = [
    a_field("nati", "database_record_unique_id", points_to="nation"),
    a_field("ntin", "enum", choices={80: "Eligible", 85: "Born"}),
]
NATIONS_SHAPE = ListShape(("ntin", "nati"), empty={"ntin": 80})


def operations(*items, parts=NATIONS, shape=NATIONS_SHAPE, replace=False):
    field = a_field("Zlst", "list", items=parts)
    ids = NewIds(ChangeList(), random.Random(1))
    changes = item_changes(Table.PERSON, RECORD, field, shape, items, ids, replace=replace)
    return [_new_value(change) for change in changes]


def _new_value(change):
    assert [part.tag for part in change] == ["dtty", "duni", "prty", "nwvl", "vers", "rdui"]
    assert change[2] == Property("prty", Kind.CODE, "Zlst")
    (new,) = [part for part in change if part.tag == "nwvl"]
    return new


def an_operation(number, part="nwvl"):
    return [Property("id  ", Kind.CODE, part), Property("lsop", Kind.INT8, bytes([number]))]


def olvl(*parts):
    return Property("olvl", Kind.NESTED, [Property("id  ", Kind.CODE, "olvl"), *parts])


def test_a_list_that_is_replaced_is_cleared_before_items_are_added():
    cleared, added, _ = operations({"nati": 1403}, replace=True)

    assert cleared == Property("nwvl", Kind.NESTED, an_operation(3))
    assert added == Property("nwvl", Kind.NESTED, an_operation(0))


def test_a_list_that_is_replaced_by_no_items_is_cleared():
    assert operations(replace=True) == [Property("nwvl", Kind.NESTED, an_operation(3))]


def test_adding_no_items_is_refused():
    with pytest.raises(EditError, match="no items"):
        operations()


def test_an_item_is_added_empty_and_then_given_each_part_with_what_it_held_before():
    nation = b"\x7b\x05\x00\x00" * 2

    added, info, nation_set = operations({"nati": 1403, "ntin": 85})

    assert added == Property("nwvl", Kind.NESTED, an_operation(0))
    assert info.value == [
        Property("id  ", Kind.CODE, "ntin"),
        Property("valu", Kind.INT8, b"\x55"),
        Property("lsop", Kind.INT8, b"\x01"),
        olvl(Property("ntin", Kind.INT8, b"\x50"), Property("nati", Kind.NULL, b"")),
    ]
    assert nation_set.value == [
        Property("id  ", Kind.CODE, "nati"),
        Property(
            "valu",
            Kind.NESTED,
            [
                Property("id  ", Kind.CODE, "valu"),
                Property("Nnat", Kind.ID, nation),
                Property("DBID", Kind.INT16, b"\x7b\x05"),
            ],
        ),
        Property("lsop", Kind.INT8, b"\x01"),
        olvl(Property("ntin", Kind.INT8, b"\x55"), Property("nati", Kind.NULL, b"")),
    ]


def test_a_part_that_an_added_item_has_already_is_not_set_again():
    changes = operations({"nati": 1403, "ntin": 80})

    assert [change.value[0].value for change in changes] == ["nwvl", "nati"]


def test_each_item_is_added_and_completed_before_the_next():
    changes = operations({"nati": 1403}, {"nati": 1404})

    assert [change.value[0].value for change in changes] == ["nwvl", "nati", "nwvl", "nati"]


def test_some_numbers_are_held_in_an_item_as_four_bytes_highest_first():
    parts = [a_field("apps", "integer"), a_field("join", "date")]
    shape = ListShape(("apps", "join"), empty={"apps": 0}, as_codes=frozenset({"apps"}))

    _, apps, _ = operations(
        {"apps": 20, "join": datetime.date(1900, 1, 1)}, parts=parts, shape=shape
    )
    *_, joined = operations(
        {"apps": 20, "join": datetime.date(2001, 7, 1)}, parts=parts, shape=shape
    )

    assert apps.value[1] == Property("valu", Kind.INT8, b"\x14")
    assert joined.value[-1] == olvl(
        Property("apps", Kind.CODE, "\x00\x00\x00\x14"), Property("join", Kind.NULL, b"")
    )


def test_a_club_is_referred_to_by_its_own_tag():
    club = [a_field("club", "database_record_unique_id", points_to="club")]

    _, chosen = operations({"club": 992}, parts=club, shape=ListShape(("club",)))

    assert chosen.value[1].value[1] == Property("Cclu", Kind.ID, b"\xe0\x03\x00\x00" * 2)


def test_an_item_with_a_part_that_the_list_does_not_have_is_refused():
    with pytest.raises(EditError, match="Zelse"):
        operations({"Zelse": 5})


def test_a_part_that_the_list_keeps_as_an_added_item_has_it_cannot_be_given():
    shape = ListShape(("Zyer", "Zheld"), kept=frozenset({"Zheld"}))

    with pytest.raises(EditError, match="Zheld"):
        operations({"Zyer": 1973, "Zheld": True}, parts=PARTS, shape=shape)


@pytest.mark.parametrize(
    ("part", "value"),
    [
        (a_field("Zcol", "colour"), "#480024"),
        (a_field("Zref", "database_record_unique_id", points_to="moon"), 5),
    ],
)
def test_a_part_of_a_kind_not_seen_in_a_list_is_refused(part, value):
    with pytest.raises(EditError, match=part.code):
        stored({part.code: value}, parts=[part], shape=ListShape((part.code,)))


def test_a_part_that_the_list_does_not_have_is_refused():
    with pytest.raises(EditError, match="Zelse"):
        stored({"Zelse": 5})


def test_a_shape_with_a_part_that_the_editor_does_not_define_is_refused():
    with pytest.raises(EditError, match="Zgon"):
        stored({"Zyer": 1973}, shape=ListShape(("Zyer", "Zgon")))
