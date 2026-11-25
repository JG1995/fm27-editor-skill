from pathlib import Path

import pytest

import synthetic
from fm27_editor import editor_file
from fm27_editor.editor_file import EditorFileError, load_editor_file, save_editor_file


def editor_file_bytes(new_value: int = 53_000) -> bytes:
    return synthetic.container(
        "Club Tweaks",
        [("Club Tweaks", ".dbc", synthetic.change_list(synthetic.capacity_change(new_value)))],
        folder=("_data", [("details", ".aom", b"details")]),
    )


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "Club Tweaks.fmf"
    path.write_bytes(editor_file_bytes())
    return path


def new_value(file) -> bytes:
    (change,) = file.changes.changes
    return next(item.value for item in change if item.tag == "nwvl")


def set_new_value(file, value: int) -> None:
    (change,) = file.changes.changes
    item = next(item for item in change if item.tag == "nwvl")
    item.value = value.to_bytes(4, "little")


def test_edited_file_saves_as_a_new_file_that_reads_back(source, tmp_path):
    edited = load_editor_file(source)
    set_new_value(edited, 53_123)

    save_editor_file(edited, tmp_path / "mcp test.fmf")

    saved = load_editor_file(tmp_path / "mcp test.fmf")
    assert new_value(saved) == (53_123).to_bytes(4, "little")
    assert saved.container.root.name == "mcp test"
    assert saved.container.root.members[0].name == "mcp test"


def test_a_file_with_an_added_change_saves_with_the_new_count(source, tmp_path):
    edited = load_editor_file(source)
    edited.changes.changes.append(list(edited.changes.changes[0]))

    save_editor_file(edited, tmp_path / "two changes.fmf")

    saved = load_editor_file(tmp_path / "two changes.fmf")
    count = next(item.value for item in saved.changes.general if item.tag == "dchc")
    assert count == (2).to_bytes(8, "little")
    assert saved.changes.changes == edited.changes.changes


def test_source_file_is_not_changed_by_loading_or_saving(source, tmp_path):
    before = source.read_bytes()
    edited = load_editor_file(source)
    set_new_value(edited, 1)

    save_editor_file(edited, tmp_path / "other.fmf")

    assert source.read_bytes() == before


def test_saving_over_an_existing_file_is_refused(source):
    edited = load_editor_file(source)
    set_new_value(edited, 1)

    with pytest.raises(EditorFileError, match="already exists"):
        save_editor_file(edited, source)

    assert source.read_bytes() == editor_file_bytes()


def test_a_file_that_does_not_read_back_the_same_is_not_kept(source, tmp_path, monkeypatch):
    edited = load_editor_file(source)
    set_new_value(edited, 53_123)
    monkeypatch.setattr(editor_file, "write_container", lambda container: editor_file_bytes(1))

    with pytest.raises(EditorFileError, match="read back"):
        save_editor_file(edited, tmp_path / "broken.fmf")

    assert list(tmp_path.iterdir()) == [source]


def test_an_fmf_without_a_change_list_is_reported(tmp_path):
    path = tmp_path / "shortlist.fmf"
    path.write_bytes(synthetic.container("List", [("List", ".slf", b"x")]))

    with pytest.raises(EditorFileError, match="change list"):
        load_editor_file(path)


def test_a_file_with_two_change_lists_is_refused(tmp_path):
    path = tmp_path / "two.fmf"
    change_list = synthetic.change_list(synthetic.capacity_change(1))
    path.write_bytes(
        synthetic.container("Two", [("Two", ".dbc", change_list), ("Other", ".dbc", change_list)])
    )

    with pytest.raises(EditorFileError, match="more than one change list"):
        load_editor_file(path)


def test_an_interrupted_write_leaves_no_file_behind(source, tmp_path, monkeypatch):
    edited = load_editor_file(source)
    set_new_value(edited, 53_123)
    real_open = Path.open

    class DiskFull:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            self.handle = real_open(self.path, "xb")
            return self

        def write(self, content):
            self.handle.write(content[:20])
            raise OSError("disk full")

        def __exit__(self, *_):
            self.handle.close()

    monkeypatch.setattr(
        Path,
        "open",
        lambda self, mode="r", *a, **k: (
            DiskFull(self) if mode == "xb" else real_open(self, mode, *a, **k)
        ),
    )

    with pytest.raises(OSError, match="disk full"):
        save_editor_file(edited, tmp_path / "broken.fmf")

    assert list(tmp_path.iterdir()) == [source]
