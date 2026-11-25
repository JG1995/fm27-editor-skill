"""An editor file with no changes yet, headed the way the Editor heads its own."""

import datetime

from fm27_editor.change_list import CHANGE_COUNT_TAG, ChangeList, Kind, Property
from fm27_editor.editor_file import EditorFile, start_editor_file
from fm27_editor.record_changes import EDITOR_DATA_VERSION, date_bytes, number

# The newest Editor whose files were read to learn the format.
EDITOR_BUILD = "fm27-rel-04-update1"
RULES_VERSION = 1687
DATABASE = "2700"


def new_editor_file(today: datetime.date) -> EditorFile:
    return start_editor_file(ChangeList(_general(), _editor(today)))


def _general() -> list[Property]:
    return [
        Property(CHANGE_COUNT_TAG, Kind.COUNT, bytes(8)),
        Property("desc", Kind.NULL, b""),
        Property("auth", Kind.NULL, b""),
        number("vers", EDITOR_DATA_VERSION),
        Property("beta", Kind.BOOL, b"\x00"),
    ]


def _editor(today: datetime.date) -> list[Property]:
    return [
        Property("verf", Kind.LIST, []),
        number("XSvC", 1),
        Property("EdBr", Kind.TEXT, EDITOR_BUILD),
        Property("EdDt", Kind.DATE, date_bytes(today)),
        number("vers", EDITOR_DATA_VERSION),
        number("RGvs", RULES_VERSION),
        Property("beta", Kind.BOOL, b"\x00"),
        Property("orvs", Kind.TEXT, DATABASE),
        Property("svvs", Kind.TEXT, DATABASE),
    ]
