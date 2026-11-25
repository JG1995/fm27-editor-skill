"""The details member of an editor file: what kind of file it is, and its name.

The Editor offers a file to open only when this member says that it is editor data. Behind the name
come a description, an author, and sometimes the author's Steam ID. They are kept as they are.
"""

from fm27_editor.binary import FormatError, Reader, text_bytes

DETAILS_TAG = b"\x03\x01moa.\x04\x00"
EDITOR_DATA = "LEAGUE_DATA_UPDATE_TYPE_HANDLER"
# No description, unknown bytes that are the same in every file, no author, and no Steam ID.
NOBODYS = text_bytes("") + b"\x00" * 6 + b"\xff" * 16 + text_bytes("") + b"\x00\x00\x01\x00"


class DetailsError(FormatError):
    """The details do not describe an editor file."""


def new_details(name: str) -> bytes:
    return DETAILS_TAG + text_bytes(EDITOR_DATA) + text_bytes(name) + NOBODYS


def renamed_details(content: bytes, name: str) -> bytes:
    reader = Reader(content, DetailsError)
    if reader.take(len(DETAILS_TAG)) != DETAILS_TAG:
        raise DetailsError("the details have an unknown layout")
    kind = reader.text()
    if kind != EDITOR_DATA:
        raise DetailsError(f"the details say this is {kind}, not editor data")
    reader.text()
    rest = reader.take(len(content) - reader.position)
    return DETAILS_TAG + text_bytes(kind) + text_bytes(name) + rest
