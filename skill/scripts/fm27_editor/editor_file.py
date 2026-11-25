"""Load or start an editor file, and save it as a new file that is checked before it is kept."""

from dataclasses import dataclass, replace
from pathlib import Path

from fm27_editor.binary import FormatError
from fm27_editor.change_list import (
    ChangeList,
    parse_change_list,
    serialise_change_list,
    with_current_count,
)
from fm27_editor.container import (
    Container,
    Folder,
    Member,
    Storage,
    read_container,
    write_container,
)
from fm27_editor.details import new_details, renamed_details

CHANGE_LIST_EXTENSION = ".dbc"
DETAILS_FOLDER = "_data"
DETAILS_NAME = "details"
DETAILS_EXTENSION = ".aom"


class EditorFileError(FormatError):
    """The editor file cannot be loaded, or the changed copy cannot be saved."""


@dataclass
class EditorFile:
    container: Container
    changes: ChangeList


def start_editor_file(changes: ChangeList) -> EditorFile:
    """A file made from nothing; it takes its name, inside as well, from the path it is saved to."""
    details = Member(DETAILS_NAME, DETAILS_EXTENSION, new_details())
    root = Folder("", [Member("", CHANGE_LIST_EXTENSION, b"")], [Folder(DETAILS_FOLDER, [details])])
    return EditorFile(Container(Storage.ZSTD, root), changes)


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
    """The container with the changes applied and the file's own name inside."""
    root = file.container.root
    change_list = replace(
        _change_list_member(file.container), name=name, data=serialise_change_list(file.changes)
    )
    members = [change_list if m.extension == CHANGE_LIST_EXTENSION else m for m in root.members]
    folders = _folders_with_renamed_details(root.folders, name)
    return Container(file.container.storage, Folder(name, members, folders))


def _folders_with_renamed_details(folders: list[Folder], name: str) -> list[Folder]:
    if not any(_is_details(folder, member) for folder in folders for member in folder.members):
        raise EditorFileError("this file has no details, so the Editor would not list it")
    return [
        replace(
            folder,
            members=[
                replace(member, data=renamed_details(member.data, name))
                if _is_details(folder, member)
                else member
                for member in folder.members
            ],
        )
        for folder in folders
    ]


def _is_details(folder: Folder, member: Member) -> bool:
    found = (folder.name, member.name, member.extension)
    return found == (DETAILS_FOLDER, DETAILS_NAME, DETAILS_EXTENSION)


def _check_reads_back(content: bytes, container: Container, changes: ChangeList) -> None:
    again = read_container(content)
    saved = parse_change_list(_change_list_member(again).data)
    if again != container or saved != with_current_count(changes):
        raise EditorFileError("the new file does not read back as it was written")
