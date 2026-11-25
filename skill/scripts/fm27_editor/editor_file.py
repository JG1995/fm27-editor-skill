"""Load an editor file, and save a changed copy as a new file that is checked before it is kept."""

from dataclasses import dataclass, replace
from pathlib import Path

from fm27_editor.binary import FormatError
from fm27_editor.change_list import ChangeList, parse_change_list, serialise_change_list
from fm27_editor.container import Container, Folder, Member, read_container, write_container

CHANGE_LIST_EXTENSION = ".dbc"


class EditorFileError(FormatError):
    """The editor file cannot be loaded, or the changed copy cannot be saved."""


@dataclass
class EditorFile:
    container: Container
    changes: ChangeList


def load_editor_file(path: Path) -> EditorFile:
    container = read_container(path.read_bytes())
    return EditorFile(container, parse_change_list(_change_list_member(container).data))


def save_editor_file(file: EditorFile, path: Path) -> None:
    """Write `file` as a new file at `path`.

    The bytes are decoded again and compared first, so a file that does not read back as intended
    never reaches the disk. A write that fails partway removes what it wrote.
    """
    if path.exists():
        raise EditorFileError(f"{path.name} already exists")
    container = _container_to_save(file, path.stem)
    content = write_container(container)
    _check_reads_back(content, container, file.changes)
    try:
        with path.open("xb") as target:
            target.write(content)
    except FileExistsError as error:
        raise EditorFileError(f"{path.name} already exists") from error
    except OSError:
        path.unlink(missing_ok=True)
        raise


def _change_list_member(container: Container) -> Member:
    found = [m for m in container.root.members if m.extension == CHANGE_LIST_EXTENSION]
    if not found:
        raise EditorFileError("this .fmf has no change list, so it is not an editor file")
    if len(found) > 1:
        raise EditorFileError("this .fmf has more than one change list, which is not supported")
    return found[0]


def _container_to_save(file: EditorFile, name: str) -> Container:
    """The container with the changes applied and the file's own name inside.

    The Editor opened a rewritten file whose internal name matched its file name.
    """
    root = file.container.root
    change_list = replace(
        _change_list_member(file.container), name=name, data=serialise_change_list(file.changes)
    )
    members = [change_list if m.extension == CHANGE_LIST_EXTENSION else m for m in root.members]
    return Container(file.container.storage, Folder(name, members, root.folders))


def _check_reads_back(content: bytes, container: Container, changes: ChangeList) -> None:
    again = read_container(content)
    if again != container or parse_change_list(_change_list_member(again).data) != changes:
        raise EditorFileError("the new file does not read back as it was written")
