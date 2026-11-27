import random

import pytest

from fm27_editor.change_list import ChangeList, Kind, ListItem, Property
from fm27_editor.field_definitions import Field
from fm27_editor.list_changes import ListShape, list_change
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


@pytest.mark.parametrize(
    ("part", "value"),
    [
        (a_field("Zmon", "cash"), 5),
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
