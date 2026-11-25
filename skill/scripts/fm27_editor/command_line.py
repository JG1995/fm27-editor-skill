"""The commands of the skill: arguments in, short text out."""

import argparse
import datetime
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from fm27_editor.base_database import open_database
from fm27_editor.binary import FormatError
from fm27_editor.editor_file import load_editor_file, save_editor_file
from fm27_editor.explain import explain_lines
from fm27_editor.people import PersonKind
from fm27_editor.person_codes import names_by_code
from fm27_editor.person_rules import SETTABLE_KINDS, PersonRules
from fm27_editor.plan import Plan, build_file, make_plan
from fm27_editor.preview import preview_lines
from fm27_editor.request import read_request, run_query
from fm27_editor.words import accepted, counted

EDITOR_VARIABLE = "FM27_EDITOR_DIR"
EDITOR_DIR = Path("/mnt/c/Program Files (x86)/Steam/steamapps/common/Football Manager 27 Editor")


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
    find.add_argument("--limit", type=_one_or_more, default=40)
    find.set_defaults(command=_find)

    fields = commands.add_parser("fields", help="list the fields that can be set on a person")
    fields.add_argument("kind", choices=[kind.name.lower() for kind in SETTABLE_KINDS])
    fields.add_argument("text", nargs="?", default="", help="part of a name or code")
    fields.set_defaults(command=_fields)

    explain = commands.add_parser("explain", help="say what an editor file does")
    explain.add_argument("file", type=Path)
    explain.add_argument("--find", default="", help="show only changes that mention this")
    explain.add_argument("--limit", type=_one_or_more, default=20)
    explain.set_defaults(command=_explain)

    preview = commands.add_parser("preview", help="show what a request would write")
    preview.add_argument("request", type=Path)
    preview.add_argument("--examples", type=_one_or_more, default=10)
    preview.set_defaults(command=_preview)

    write = commands.add_parser("write", help="write a new file for an approved request")
    write.add_argument("request", type=Path)
    write.add_argument("output", type=Path)
    write.add_argument("--approved", required=True, metavar="CODE", help="from the preview")
    write.set_defaults(command=_write)
    return parser


def _one_or_more(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _editor_dir() -> Path:
    return Path(os.environ.get(EDITOR_VARIABLE, EDITOR_DIR))


def _cache_path() -> Path:
    caches = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return caches / "fm27-editor" / "lookup.sqlite"


def _find(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    found = run_query(lookup, options.query, options.limit)
    rows = counted(len(found.rows), "row", "rows")
    end = f"The first {rows}; there are more" if found.has_more else rows
    return ["\t".join(found.columns), *("\t".join(map(_cell, row)) for row in found.rows), end]


def _cell(value: object) -> str:
    return "NULL" if value is None else str(value)


def _fields(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    kind = PersonKind[options.kind.upper()]
    names = names_by_code(kind)
    lines = []
    for field in PersonRules(options.editor, lookup).writable_fields(kind):
        called = f"{names[field.code]} ({field.code})" if field.code in names else field.code
        lines.append(f"{called}: {field.name}, {accepted(field)}")
    matching = [line for line in lines if options.text.lower() in line.lower()]
    return matching or [f"No field matches {options.text!r}"]


def _explain(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    file = load_editor_file(options.file)
    return explain_lines(file, options.editor, lookup, find=options.find, examples=options.limit)


def _preview(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    return preview_lines(_plan(options, lookup), lookup, options.examples)


def _write(options: argparse.Namespace, lookup: sqlite3.Connection) -> list[str]:
    file = build_file(_plan(options, lookup), options.approved, datetime.date.today())
    save_editor_file(file, options.output)
    changes = counted(len(file.changes.changes), "change", "changes")
    return [f"Wrote {options.output}: {changes}, read back and compared"]


def _plan(options: argparse.Namespace, lookup: sqlite3.Connection) -> Plan:
    request = read_request(options.request)
    return make_plan(request, PersonRules(options.editor, lookup), lookup)
