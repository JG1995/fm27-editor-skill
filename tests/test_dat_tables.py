import pytest

import synthetic
from fm27_editor.dat_tables import (
    DatError,
    Record,
    open_table,
    read_records,
    read_stream,
    read_string_table,
    read_tables,
)


def test_reads_a_single_stream_file(tmp_path):
    path = tmp_path / "people_db.dat"
    path.write_bytes(synthetic.dat_file(b"people bytes" * 50))

    assert read_stream(path) == b"people bytes" * 50


def test_reads_the_tables_of_a_container_file(tmp_path):
    path = tmp_path / "client_db.dat"
    path.write_bytes(synthetic.dat_container("client_db", [("table_3", b"clubs"), ("x", b"y")]))

    assert read_tables(path, {"table_3"}) == {"table_3": b"clubs"}


def test_a_missing_table_is_named(tmp_path):
    path = tmp_path / "client_db.dat"
    path.write_bytes(synthetic.dat_container("client_db", [("table_3", b"clubs")]))

    with pytest.raises(DatError, match="table_9"):
        read_tables(path, {"table_3", "table_9"})


def test_reads_a_string_table():
    table = synthetic.string_table({0: "Žofia", 7: "Åse Ægir"})

    assert read_string_table(table) == {0: "Žofia", 7: "Åse Ægir"}


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"\x03\x01xxx." + b"\x00" * 30, id="wrong tag"),
        pytest.param(synthetic.dat_file(b"abc")[:15], id="truncated"),
    ],
)
def test_rejects_files_that_are_not_database_files(tmp_path, content):
    path = tmp_path / "people_db.dat"
    path.write_bytes(content)

    with pytest.raises(DatError):
        read_stream(path)


def test_a_string_table_that_ends_early_is_an_error():
    with pytest.raises(DatError):
        read_string_table(synthetic.string_table({1: "Name"})[:-2])


def test_an_unknown_database_version_is_refused_with_the_version(tmp_path):
    path = tmp_path / "people_db.dat"
    path.write_bytes(b"\x03\x01tad.\xa1\x0f\xa9\x0e\x09\x00" + synthetic.zstd_frame(b"x"))

    with pytest.raises(DatError, match="4001"):
        read_stream(path)


def test_opening_a_table_returns_its_count_and_a_reader_behind_it():
    reader, count = open_table(synthetic.string_table({1: "a", 2: "b"}))

    assert count == 2
    assert reader.u32() == 1


def test_a_table_without_its_tag_is_refused():
    with pytest.raises(DatError):
        open_table(b"\x00" * 12)


def test_reads_the_records_of_a_table():
    table = synthetic.record_table([(9101, b"first"), (9102, b"\x00" * 5_000), (9103, b"")])

    assert list(read_records(table)) == [
        Record(9101, b"first"),
        Record(9102, b"\x00" * 5_000),
        Record(9103, b""),
    ]


@pytest.mark.parametrize("uid", [5, 9101, 2_000_000_001])
def test_zeros_before_the_first_id_are_not_read_as_part_of_it(uid):
    table = synthetic.record_table([(uid, b"\x07\x00\x00\x00\x00"), (9102, b"second")])

    assert [record.uid for record in read_records(table)] == [uid, 9102]


def test_records_that_do_not_fill_the_table_are_an_error():
    with pytest.raises(DatError, match="follow"):
        list(read_records(synthetic.record_table([(9101, b"only")]) + b"\x00\x00"))


def test_a_record_without_an_end_is_an_error():
    table = synthetic.record_table([(9101, b"first"), (9102, b"second")])

    with pytest.raises(DatError, match="record 1"):
        list(read_records(table[:-20]))
