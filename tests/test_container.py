import struct

import pytest

import synthetic
from fm27_editor.container import ContainerError, read_container, write_container

FILES = [("Club Tweaks", ".dbc", b"change data " * 40), ("picture", ".jpg", b"\xff\xd8 pixels")]
FOLDER = ("_data", [("details", ".aom", b"author details")])


def test_reads_members_of_compressed_and_raw_containers_including_folders():
    for storage in (3, 0):
        container = read_container(
            synthetic.container("Club Tweaks", FILES, storage=storage, folder=FOLDER)
        )

        assert container.root.name == "Club Tweaks"
        assert [(m.name, m.extension, m.data) for m in container.root.members] == FILES
        (folder,) = container.root.folders
        assert folder.name == "_data"
        assert [(m.name, m.extension, m.data) for m in folder.members] == FOLDER[1]


def test_reads_the_variant_with_a_size_before_each_compressed_frame():
    container = read_container(
        synthetic.container("Updated Transfers", FILES, folder=FOLDER, size_prefix=True)
    )

    assert [m.data for m in container.root.members] == [data for _, _, data in FILES]


@pytest.mark.parametrize("storage", [3, 0])
def test_written_file_reads_back_with_the_same_members(storage):
    original = read_container(
        synthetic.container("Club Tweaks", FILES, storage=storage, folder=FOLDER)
    )

    rewritten = read_container(write_container(original))

    assert rewritten == original


def test_written_storage_flag_matches_how_members_are_stored():
    """The Editor refused a file whose header said compressed while a member was raw."""
    for storage in (3, 0):
        written = write_container(
            read_container(synthetic.container("Club Tweaks", FILES, storage=storage))
        )
        assert written[25] == storage
        key, iv = written[34:50], written[50:66]
        plain = synthetic.aes_ctr(written[66:130], key, iv)
        assert (plain[:4] == b"\x28\xb5\x2f\xfd") == (storage == 3)


def test_each_write_uses_a_fresh_key():
    container = read_container(synthetic.container("Club Tweaks", FILES))

    assert write_container(container) != write_container(container)


GOOD = synthetic.container("T", FILES)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(synthetic.container("T", FILES, magic=b"\x02\x01xxx."), id="wrong magic"),
        pytest.param(synthetic.container("T", FILES, version=7), id="unsupported version"),
        pytest.param(GOOD[:25] + b"\x01" + GOOD[26:], id="unknown storage flag"),
        pytest.param(
            synthetic.container("T", FILES, declared_unpacked=5), id="wrong unpacked size"
        ),
        pytest.param(GOOD[:200], id="truncated"),
        pytest.param(b"\x02\x01afe.", id="shorter than the header"),
    ],
)
def test_rejects_files_that_are_not_readable_containers(content):
    with pytest.raises(ContainerError):
        read_container(content)


def test_rejects_an_index_offset_past_the_end():
    content = bytearray(synthetic.container("T", FILES))
    struct.pack_into("<Q", content, 9, len(content) + 1000)

    with pytest.raises(ContainerError):
        read_container(bytes(content))


def test_a_frame_that_is_cut_short_is_rejected_even_when_the_size_fits():
    """The checksum ends a frame; without its last bytes, damage would go unnoticed."""
    content = synthetic.container("T", FILES)
    cut = read_container(content)
    frame = write_container(cut)
    index_at = struct.unpack_from("<Q", frame, 9)[0] + 9
    with pytest.raises(ContainerError):
        read_container(frame[:-3])
    assert index_at < len(frame)


def test_bytes_after_the_last_frame_are_an_error():
    with pytest.raises(ContainerError):
        read_container(synthetic.container("T", FILES) + b"\x00\x00\x00\x00")
