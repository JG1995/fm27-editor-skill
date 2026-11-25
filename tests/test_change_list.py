import struct
from compression import zstd

import pytest

import synthetic
from fm27_editor.change_list import (
    ChangeListError,
    change_list_body,
    parse_change_list,
    serialise_change_list,
)


def every_verified_kind() -> bytes:
    prop, text = synthetic.prop, synthetic.text
    nested = prop(
        "nest", 0x0A, synthetic.props(prop("id  ", 0x02, b"lvwn"), prop("flag", 0x03, b"\x01"))
    )
    items = (
        struct.pack("<I", 3)
        + b"\x01\x1a"
        + text("24.0.0")
        + b"\x01\x11\x07"
        + b"\x01\x0a"
        + synthetic.props(prop("in  ", 0x11, b"\x09"))
    )
    return synthetic.change(
        prop("none", 0x00),
        prop("intg", 0x01, b"\x08\xcf\x00\x00"),
        prop("code", 0x02, b"yceS"),
        prop("bool", 0x03, b"\x01"),
        prop("colr", 0x04, b"\x01\x1d\x40\xff"),
        prop("long", 0x05, b"\x00" * 8),
        nested,
        prop("list", 0x0B, items),
        prop("col2", 0x0D, b"\xd0\x50\x00\xff"),
        prop("uniq", 0x0F, b"\x01\x02\x03\x04" * 2),
        prop("byte", 0x11, b"\x0a"),
        prop("word", 0x12, b"\xaa\x0e"),
        prop("sole", 0x13, b"\xff"),
        prop("pair", 0x14, b"\x67\x07"),
        prop("quad", 0x15, b"\x01\x02\x03\x04"),
        prop("wide", 0x18, b"\x01" * 8),
        prop("name", 0x1A, text("Ægir Þór")),
        prop("date", 0x20, b"\x00\xb6\xd2\x0f"),
    )


def test_every_value_kind_rebuilds_byte_for_byte():
    content = synthetic.change_list(every_verified_kind(), synthetic.capacity_change(53_123))

    changes = parse_change_list(content)

    assert len(changes.changes) == 2
    assert change_list_body(changes) == zstd.decompress(content[9:])
    assert parse_change_list(serialise_change_list(changes)) == changes


def test_reads_the_fields_of_a_change():
    changes = parse_change_list(synthetic.change_list(synthetic.capacity_change(53_123)))

    (first,) = changes.changes
    values = {item.tag: item for item in first}
    assert values["prty"].value == "Secy"
    assert values["nwvl"].value == struct.pack("<i", 53_123)
    assert values["duni"].value == b"\x01\x02\x03\x04" * 2


def test_text_values_are_text():
    content = synthetic.change_list(
        synthetic.change(synthetic.prop("nwvl", 0x1A, synthetic.text("-10")))
    )

    (change,) = parse_change_list(content).changes

    assert change[0].value == "-10"


def test_declared_change_count_follows_the_changes_when_written():
    changes = parse_change_list(
        synthetic.change_list(synthetic.capacity_change(1), synthetic.capacity_change(2))
    )
    changes.changes.pop()

    rebuilt = parse_change_list(serialise_change_list(changes))

    assert len(rebuilt.changes) == 1
    assert rebuilt.general[0].value == struct.pack("<Q", 1)


def test_unknown_value_kind_is_reported_with_its_field():
    content = synthetic.change_list(synthetic.change(synthetic.prop("what", 0x7E, b"\x01")))

    with pytest.raises(ChangeListError, match=r"what.*0x7e"):
        parse_change_list(content)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"\x03\x01zzz.\x06\x00\x00" + b"\x00" * 20, id="wrong tag"),
        pytest.param(b"\x03\x01cbd.\x06\x00\x00not a frame", id="not compressed"),
        pytest.param(b"\x03\x01cbd.", id="shorter than its header"),
        pytest.param(
            synthetic.change_list(synthetic.capacity_change(1), count=2),
            id="fewer changes than declared",
        ),
    ],
)
def test_rejects_files_that_are_not_readable_change_lists(content):
    with pytest.raises(ChangeListError):
        parse_change_list(content)


def test_bytes_after_the_last_change_are_an_error():
    good = synthetic.change_list(synthetic.capacity_change(1))
    body = zstd.decompress(good[9:]) + b"\x00\x00"

    with pytest.raises(ChangeListError):
        parse_change_list(good[:9] + synthetic.zstd_frame(body))


def test_a_change_list_that_is_cut_short_is_rejected():
    content = synthetic.change_list(synthetic.capacity_change(1))

    with pytest.raises(ChangeListError):
        parse_change_list(content[:-2])
