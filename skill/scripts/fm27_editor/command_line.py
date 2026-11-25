"""The commands of the skill: arguments in, short text out."""

import argparse
import datetime
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from fm27_editor.base_database import open_database
from fm27_editor.binary import FormatError
from fm27_editor.editor_file import load_editor_file, save_editor_file
from fm27_editor.explain import explain_lines
from fm27_editor.field_definitions import Field
from fm27_editor.people import PersonKind
from fm27_editor.person_codes import person_codes
from fm27_editor.person_rules import PersonRules
from fm27_editor.plan import Plan, approval_code, build_file, make_plan
from fm27_editor.preview import counted, preview_lines
from fm27_editor.record_changes import (
    HIGHEST_ATTRIBUTE,
    LOWEST_ATTRIBUTE,
    REFERENCE,
    EditError,
)

EDITOR_VARIABLE = "FM27_EDITOR_DIR"
EDITOR_DIR = Path("/mnt/c/Program Files (x86)/Steam/steamapps/common/Football Manager 27 Editor")
EDITOR_FILE_ENDING = ".fmf"


def main(arguments: list[str]) -> int:
    options = _parser().parse_args(arguments)
    try:
        with closing(open_database(options.editor, options.cache)) as lookup:
            lines = options.command(options, lookup)
    except (FormatError, OSError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fm27.py", description=__doc__)
    parser.add_argument("--editor", type=Path, default=_editor_dir(), help="Editor folder")
    parser.add_argument("--cache", type=Path, default=_cache_path(), help="lookup cache file")
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    find = commands.add_parser("find", help="run an SQL query over the lookup")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=40)
    find.set_defaults(command=_find)

    fields = commands.add_parser("fields", help="list the fields that can be set on a person")
    fields.add_argument("kind", choices=["player", "staff"])
    fields.add_argument("text", nargs="?", default="", help="part of a name or code")
    fields.set_defaults(command=_fields)

    explain = commands.add_parser("explain", help="say what an editor file does")
    explain.add_argument("file", type=Path)
    explain.add_argument("--find", default="", help="show only changes that mention this")
    explain.add_argument("--limit", type=int, default=20)
    explain.set_defaults(command=_explain)

    preview = commands.add_parser("preview", help="show what a request would write")
    preview.add_argument("request", type=Path)
    preview.add_argument("--examples", type=int, default=10)
    preview.set_defaults(command=_preview)

    write = commands.add_parser("write", help="write a new file for an approved request")
    write.add_argument("request", type=Path)
    write.add_argument("output", type=Path)
    write.add_argument("--approved", required=True, metavar="CODE", help="from the preview")
    write.set_defaults(command=_write)
    return parser


def _editor_dir() -> Path:
    return Path(os.environ.get(EDITOR_VARIABLE, EDITOR_DIR))


def _cache_path() -> Path:
    caches = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return caches / "fm27-editor" / "lookup.sqlite"


def _find(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    found = lookup.execute(options.query)
    columns = [column[0] for column in found.description or []]
    rows = found.fetchmany(options.limit + 1)
    shown = rows[: options.limit]
    if len(rows) > options.limit:
        end = f"The first {counted(len(shown), 'row', 'rows')}; there are more"
    else:
        end = counted(len(shown), "row", "rows")
    return ["\t".join(columns), *("\t".join(map(_cell, row)) for row in shown), end]


def _cell(value: object) -> str:
    return "NULL" if value is None else str(value)


def _fields(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    kind = PersonKind[options.kind.upper()]
    names = {code: name for name, code in person_codes(kind).items()}
    fields = PersonRules(options.editor, lookup).writable_fields(kind)
    lines = [_field_line(field, names.get(field.code)) for field in fields]
    return [line for line in lines if options.text.lower() in line.lower()]


def _field_line(field: Field, name: str | None) -> str:
    called = field.code if name is None else f"{name} ({field.code})"
    return f"{called}: {field.name}, {_accepted(field)}"


def _accepted(field: Field) -> str:
    match field.type:
        case "attribute":
            return f"{LOWEST_ATTRIBUTE} to {HIGHEST_ATTRIBUTE}"
        case "integer":
            return f"{field.lowest} to {field.highest}"
        case "boolean":
            return "true or false"
        case "date":
            return "a date such as 2008-04-25"
        case "enum":
            return f"one of {', '.join(_choice(*item) for item in field.choices.items())}"
        case _ if field.type == REFERENCE:
            return f"the uid of a {field.points_to}"
    return "a text"


def _choice(number: int, name: str) -> str:
    return f"{number} {name}".strip()


def _explain(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    file = load_editor_file(options.file)
    return explain_lines(file, options.editor, lookup, find=options.find, examples=options.limit)


def _preview(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    return preview_lines(_plan(options, lookup), lookup, options.examples)


def _write(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    if options.output.suffix != EDITOR_FILE_ENDING:
        raise EditError(f"the name of an editor file ends in {EDITOR_FILE_ENDING}")
    plan = _plan(options, lookup)
    code = approval_code(plan)
    if code != options.approved:
        raise EditError(
            f"this plan ({code}) is not the one that was approved ({options.approved}); "
            "preview it again"
        )
    file = build_file(plan, datetime.date.today())
    save_editor_file(file, options.output)
    changes = counted(len(file.changes.changes), "change", "changes")
    return [f"Wrote {options.output}: {changes}, read back and compared"]


def _plan(options: argparse.Namespace, lookup: sqlite3.Connection) -> Plan:
    rules = PersonRules(options.editor, lookup)
    return make_plan(_request(options.request), rules, lookup)


def _request(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise EditError(f"{path.name} is not a request: {error}") from error
