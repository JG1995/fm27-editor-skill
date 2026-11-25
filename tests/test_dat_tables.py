import pytest

import synthetic
from fm27_editor.dat_tables import (
    DatError,
    open_table,
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
