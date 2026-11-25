"""What an editor file does, in plain words."""

import sqlite3
from collections import Counter
from pathlib import Path

from fm27_editor.change_list import Kind, Property
from fm27_editor.change_reading import (
    ADD_RECORD,
    ID_SIZE,
    REMOVE_RECORD,
    EditError,
    ReadChange,
    is_existing,
    read_change,
    read_plain,
    referred_to,
    uid_of,
)
from fm27_editor.definition_files import NoDefinitionsError
from fm27_editor.editor_file import EditorFile
from fm27_editor.field_definitions import read_field_names, read_shared_choices
from fm27_editor.record_changes import REFERENCE_TAGS
from fm27_editor.record_kinds import GROUPS
from fm27_editor.record_rules import LOOKUP_TABLES
from fm27_editor.rule_changes import RULES_TAG, nation_of
from fm27_editor.rule_shapes import CODES
from fm27_editor.words import counted, named

KINDS_OF_RECORD = "dbts"
FIELDS_SHOWN = 12
ADVANCED_RULES = "fles"
KEPT_HALF = slice(4, ID_SIZE)
# Where the definition files are not called what the Editor calls the kind of record.
DEFINED_IN = {
    "Person": ["person", "player", "non player"],
    "National Team": ["national team container"],
    "Derby Name": ["derby"],
    "Competition": ["comp"],
}
# The lookup's tables, by the Editor's kind of record and by the tag of a reference.
TABLE_OF_KIND = {
    "Person": "person",
    "Club": "club",
    "Competition": "competition",
    "Nation": "nation",
    "City": "city",
    "Stadium": "stadium",
}
TABLE_OF_TAG = {tag: LOOKUP_TABLES.get(kind) for kind, tag in REFERENCE_TAGS.items()}


def explain_lines(
    file: EditorFile, editor_dir: Path, lookup: sqlite3.Connection, *, find: str, examples: int
) -> list[str]:
    changes = [read_change(change) for change in file.changes.changes]
    words = _Words(changes, editor_dir, lookup)
    added = [change for change in changes if change.code == ADD_RECORD]
    removed = [change for change in changes if change.code == REMOVE_RECORD]
    changed = [change for change in changes if change.code not in (ADD_RECORD, REMOVE_RECORD)]
    return [
        _heading(file),
        *_rule_lines(file, lookup),
        *_record_lines("Adds", added, words),
        *_record_lines("Removes", removed, words),
        *_table_lines(changed, words),
        *_change_lines(changed, words, find, examples),
    ]


class _Words:
    """Names for kinds of records, fields, and records."""

    def __init__(self, changes: list[ReadChange], editor_dir: Path, lookup: sqlite3.Connection):
        self._lookup = lookup
        self._editor_dir = editor_dir
        self._kinds = read_shared_choices(editor_dir, KINDS_OF_RECORD)
        self._fields: dict[str, dict[str, str]] = {}
        self._new_names = _names_of_new_records(changes)

    def kind(self, table: int) -> str:
        return self._kinds.get(table, f"Table {table}")

    def field(self, kind: str, code: str) -> str:
        if kind not in self._fields:
            self._fields[kind] = self._read_fields(kind)
        return self._fields[kind].get(code, code)

    def record(self, table: str | None, record: bytes) -> str:
        """A record of one of the lookup's tables, or a new one, by name if that is known."""
        if is_existing(record):
            return named(self._lookup, table, uid_of(record))
        if len(record) < ID_SIZE:
            return record.hex()
        return f"{self._new_names.get(record[KEPT_HALF], uid_of(record))} (new)"

    def _read_fields(self, kind: str) -> dict[str, str]:
        names: dict[str, str] = {}
        for definitions in DEFINED_IN.get(kind, [kind.lower()]):
            try:
                names = read_field_names(self._editor_dir, definitions) | names
            except NoDefinitionsError:
                continue
        return names


def _names_of_new_records(changes: list[ReadChange]) -> dict[bytes, str]:
    """Names by the half of the ID that stays the same when the Editor saves a file."""
    codes = {group.table: group.name_codes for group in GROUPS.values()}
    names: dict[bytes, dict[str, str]] = {}
    for change in changes:
        new = change.new
        is_name = change.code in codes.get(change.table, ()) and new is not None
        if is_name and new.kind is Kind.TEXT and new.value and not is_existing(change.record):
            names.setdefault(change.record[KEPT_HALF], {})[change.code] = new.value
    order = [code for group in codes.values() for code in group]
    return {
        record: " ".join(parts[code] for code in order if code in parts)
        for record, parts in names.items()
    }


# --- lines ---------------------------------------------------------------------------------


def _heading(file: EditorFile) -> str:
    editor = {item.tag: item for item in file.changes.editor}
    heading = counted(len(file.changes.changes), "change", "changes")
    if "EdBr" in editor:
        heading += f", saved by {editor['EdBr'].value}"
    if "EdDt" in editor and editor["EdDt"].kind is Kind.DATE:
        heading += f" on {read_plain(editor['EdDt'])}"
    return heading


def _rule_lines(file: EditorFile, lookup: sqlite3.Connection) -> list[str]:
    editor = {item.tag: item for item in file.changes.editor}
    lines = []
    if RULES_TAG in editor and editor[RULES_TAG].kind is Kind.NESTED:
        rules = {item.tag: item for item in editor[RULES_TAG].value}
        counts = [
            counted(len(rules[CODES[name]].value) if CODES[name] in rules else 0, one, many)
            for name, one, many in (
                ("league_comps", "division", "divisions"),
                ("cup_comps", "cup", "cups"),
            )
        ]
        nation = nation_of(editor[RULES_TAG])
        called = "a nation" if nation is None else named(lookup, "nation", nation)
        lines.append(f"Rules for {called}: {', '.join(counts)}")
    if ADVANCED_RULES in editor and editor[ADVANCED_RULES].value:
        files = counted(len(editor[ADVANCED_RULES].value), "set", "sets")
        lines.append(f"Advanced rules: {files}, which are not spelled out")
    return lines


def _record_lines(verb: str, items: list[ReadChange], words: _Words) -> list[str]:
    if not items:
        return []
    kinds = Counter(words.kind(item.table) for item in items).most_common()
    listed = ", ".join(f"{kind} {count:,}" for kind, count in kinds)
    return [f"{verb} {counted(len(items), 'record', 'records')}: {listed}"]


def _table_lines(items: list[ReadChange], words: _Words) -> list[str]:
    lines = []
    for table, count in Counter(item.table for item in items).most_common():
        of_kind = [item for item in items if item.table == table]
        kind = words.kind(table)
        records = counted(len({item.record for item in of_kind}), "record", "records")
        lines.append(f"{kind}: {counted(count, 'change', 'changes')} to {records}")
        fields = Counter(item.code for item in of_kind).most_common()
        lines += [f"  {_field(kind, code, words)}: {n:,}" for code, n in fields[:FIELDS_SHOWN]]
        if len(fields) > FIELDS_SHOWN:
            lines.append(f"  and {len(fields) - FIELDS_SHOWN} more fields")
    return lines


def _field(kind: str, code: str, words: _Words) -> str:
    name = words.field(kind, code)
    return code if name == code else f"{name} ({code})"


def _change_lines(items: list[ReadChange], words: _Words, find: str, examples: int) -> list[str]:
    if not find:
        lines, total = [_change_line(item, words) for item in items[:examples]], len(items)
    else:
        every = (_change_line(item, words) for item in items)
        matching = [line for line in every if find.lower() in line.lower()]
        lines, total = matching[:examples], len(matching)
    if not lines:
        return [f"No change mentions {find!r}"] if find else []
    return [f"Changes, {len(lines)} of {total:,}:", *lines]


def _change_line(item: ReadChange, words: _Words) -> str:
    kind = words.kind(item.table)
    record = words.record(TABLE_OF_KIND.get(kind), item.record)
    return f"  {record}: {words.field(kind, item.code)} = {_value(item.new, words)}"


# --- values --------------------------------------------------------------------------------


def _value(value: Property | None, words: _Words) -> str:
    if value is None:
        return "nothing"
    if value.kind is Kind.LIST:
        return "a whole list"
    if value.kind is Kind.NESTED:
        reference = referred_to(value)
        if reference is None:
            return "a change to a list"
        tag, record = reference
        return words.record(TABLE_OF_TAG.get(tag), record)
    try:
        plain = read_plain(value)
    except EditError:
        return value.value if isinstance(value.value, str) else value.value.hex()
    return _plain(plain)


def _plain(value: object) -> str:
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:g}"
    return '""' if value == "" else str(value)
