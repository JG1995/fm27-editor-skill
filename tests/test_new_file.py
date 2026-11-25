import datetime

import pytest

from fm27_editor.change_list import Kind, Property
from fm27_editor.editor_file import load_editor_file, save_editor_file
from fm27_editor.new_file import new_editor_file

TODAY = datetime.date(2026, 11, 12)


@pytest.fixture
def saved(tmp_path):
    path = tmp_path / "Brand new.fmf"
    save_editor_file(new_editor_file(TODAY), path)
    return load_editor_file(path)


def test_a_new_file_holds_an_empty_change_list_under_its_own_name(saved):
    root = saved.container.root

    assert root.name == "Brand new"
    assert [(m.name, m.extension) for m in root.members] == [("Brand new", ".dbc")]
    assert saved.changes.changes == []


def test_a_new_file_says_which_editor_and_database_it_is_for(saved):
    editor = {item.tag: item for item in saved.changes.editor}

    assert editor["EdBr"].value == "fm27-rel-04-update1"
    assert editor["vers"] == Property("vers", Kind.INT16, b"\xac\x0e")
    assert editor["svvs"].value == "2700"


def test_a_new_file_is_dated_today(saved):
    editor = {item.tag: item for item in saved.changes.editor}

    assert editor["EdDt"] == Property("EdDt", Kind.DATE, bytes.fromhex("003cd50f"))


def test_changes_can_be_added_to_a_new_file(tmp_path):
    file = new_editor_file(TODAY)
    file.changes.changes.append([Property("prty", Kind.CODE, "Ztst")])

    save_editor_file(file, tmp_path / "One change.fmf")

    assert len(load_editor_file(tmp_path / "One change.fmf").changes.changes) == 1
