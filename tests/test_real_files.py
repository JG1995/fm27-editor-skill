"""Optional check against the user's own editor files; they never enter the repository."""

import os
from pathlib import Path

import pytest

from fm27_editor.change_list import change_list_body, parse_change_list, read_body
from fm27_editor.container import read_container, write_container
from fm27_editor.editor_file import load_editor_file

FILES = sorted(Path(os.environ.get("FM27_EDITOR_FILES", "/nonexistent")).glob("*.fmf"))


@pytest.mark.skipif(not FILES, reason="set FM27_EDITOR_FILES to a folder of editor files")
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_real_file_rebuilds_without_loss(path):
    loaded = load_editor_file(path)
    rebuilt = read_container(write_container(loaded.container))

    assert rebuilt == loaded.container
    for member in loaded.container.root.members:
        if member.extension == ".dbc":
            assert change_list_body(parse_change_list(member.data)) == read_body(member.data)
