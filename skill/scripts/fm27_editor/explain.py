"""What an editor file does, in plain words."""

import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

from fm27_editor.change_list import Kind, ListItem, Property
from fm27_editor.change_reading import (
    ADD_RECORD,
    ID_SIZE,
    REMOVE_RECORD,
    EditError,
    ReadChange,
    Table,
    is_existing,
    read_change,
    read_number,
    read_plain,
    referred_to,
    says_nothing,
    uid_of,
)
from fm27_editor.definition_files import NoDefinitionsError
from fm27_editor.editor_file import EditorFile
from fm27_editor.field_definitions import (
    read_field_names,
    read_item_names,
    read_shared_choices,
)
from fm27_editor.list_changes import (
    ADD,
    CHANGE_PART,
    CLEAR,
    COPY,
    LIST_REFERENCE_TAGS,
    OPERATION,
    PART_VALUE,
    REMOVE,
)
from fm27_editor.record_changes import ID_TAG, REFERENCE_TAGS
from fm27_editor.record_fields import LOOKUP_TABLES
from fm27_editor.record_kinds import (
    COMPETITION,
    GROUPS,
    NATION,
    NATIONAL_TEAM,
    NATIONAL_TEAMS,
    NATIONS,
    PLAYER,
    STAFF,
)
from fm27_editor.rule_changes import read_rules
from fm27_editor.words import counted, named, named_team

KINDS_OF_RECORD = "dbts"
FIELDS_SHOWN = 12
KEPT_HALF = slice(4, ID_SIZE)
# Where the Editor's list of tables does not say all that a table holds: it calls the nations'
# table National Team, and it holds the nations as well (see place_lookup).
NATIONS_AND_TEAMS = "Nation or national team"
KIND_OF_TABLE = {Table.NATION: NATIONS_AND_TEAMS}
# Where the definition files are not called what the Editor calls the kind of record.
DEFINED_IN = {
    "Person": [*STAFF.defined_in, *PLAYER.defined_in],
    "Derby Name": ["derby"],
    "Competition": COMPETITION.defined_in,
    NATIONS_AND_TEAMS: [*NATION.defined_in, *NATIONAL_TEAM.defined_in],
}
# Where the lookup names a record: the view of its kind, by the table a change is about, and the
# lookup's table, by the tag of a reference. The national teams name every record of table 9, a
# women's team by its nation.
VIEW_OF_TABLE = {group.table: group.view for group in GROUPS.values() if group is not NATIONS} | {
    Table.NATION: NATIONAL_TEAMS.view
}
TABLE_OF_TAG = {tag: LOOKUP_TABLES.get(kind) for kind, tag in LIST_REFERENCE_TAGS.items()}
LIST_STEPS = {
    ADD: "an item is added",
    REMOVE: "an item is taken out",
    CLEAR: "cleared",
    COPY: "an item is copied",
}


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
        self._items: dict[str, dict[str, dict[str, str]]] = {}
        self._new_names = _names_of_new_records(changes)

    def kind(self, table: int) -> str:
        return KIND_OF_TABLE.get(table) or self._kinds.get(table, f"Table {table}")

    def field(self, kind: str, code: str) -> str:
        if kind not in self._fields:
            self._fields[kind] = self._read_fields(kind)
        return self._fields[kind].get(code, code)

    def part(self, kind: str, code: str, part: str) -> str:
        """A part of an item of a list."""
        if kind not in self._items:
            self._items[kind] = self._read_items(kind)
        return self._items[kind].get(code, {}).get(part, part)

    def record(self, table: str | None, record: bytes) -> str:
        """A record of one of the lookup's tables, or a new one, by name if that is known."""
        if is_existing(record):
            return named(self._lookup, table, uid_of(record))
        if len(record) < ID_SIZE:
            return record.hex()
        return f"{self._new_names.get(record[KEPT_HALF], uid_of(record))} (new)"

    def referred(self, tag: str, record: bytes) -> str:
        """A record that a value refers to."""
        if tag == REFERENCE_TAGS["team"] and is_existing(record):
            return named_team(self._lookup, uid_of(record))
        return self.record(TABLE_OF_TAG.get(tag), record)

    def _read_fields(self, kind: str) -> dict[str, str]:
        return self._read(kind, read_field_names)

    def _read_items(self, kind: str) -> dict[str, dict[str, str]]:
        return self._read(kind, read_item_names)

    def _read[T](self, kind: str, read: Callable[[Path, str], dict[str, T]]) -> dict[str, T]:
        names: dict[str, T] = {}
        for definitions in DEFINED_IN.get(kind, [kind.lower()]):
            try:
                names = read(self._editor_dir, definitions) | names
            except NoDefinitionsError:
                continue
        return names


def _names_of_new_records(changes: list[ReadChange]) -> dict[bytes, str]:
    """Names by the half of the ID that stays the same when the Editor saves a file."""
    codes = {group.table: group.name_codes for group in GROUPS.values()}
    names: dict[bytes, tuple[int, dict[str, str]]] = {}
    for change in changes:
        new = change.new
        is_name = change.code in codes.get(change.table, ()) and new is not None
        if is_name and new.kind is Kind.TEXT and new.value and not is_existing(change.record):
            parts = names.setdefault(change.record[KEPT_HALF], (change.table, {}))[1]
            parts[change.code] = new.value
    return {
        record: " ".join(parts[code] for code in codes[table] if code in parts)
        for record, (table, parts) in names.items()
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
    rules = read_rules(file.changes)
    lines = []
    for nation in rules.nations:
        called = "a nation" if nation is None else named(lookup, "nation", nation)
        divisions = counted(rules.divisions, "division", "divisions")
        lines.append(f"Rules for {called}: {divisions}, {counted(rules.cups, 'cup', 'cups')}")
    if rules.others:
        lines.append("Rules for international or continental competitions, not spelled out")
    if rules.advanced:
        lines.append(f"Advanced rules: {counted(rules.advanced, 'set', 'sets')}, not spelled out")
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
        every = (line for item in items for line in _searched_lines(item, words))
        matching = [line for line in every if find.lower() in line.lower()]
        lines, total = matching[:examples], len(matching)
    if not lines:
        return [f"No change mentions {find!r}"] if find else []
    return [f"Changes, {len(lines)} of {total:,}:", *lines]


def _change_line(item: ReadChange, words: _Words) -> str:
    step = _list_step(item, words)
    if step is not None:
        return f"{_changed_field(item, words)}: {step}"
    return f"{_changed_field(item, words)} = {_value(item.new, words)}"


def _list_step(item: ReadChange, words: _Words) -> str | None:
    """What a change does to the items of a list, if it changes them one at a time."""
    if item.new is None or item.new.kind is not Kind.NESTED:
        return None
    parts = {part.tag: part for part in item.new.value}
    if OPERATION not in parts:
        return None
    operation = read_number(parts[OPERATION])
    if operation == CHANGE_PART and ID_TAG in parts:
        part = words.part(words.kind(item.table), item.code, str(parts[ID_TAG].value))
        return f"its {part} = {_value(parts.get(PART_VALUE), words)}"
    return LIST_STEPS.get(operation, f"list step {operation}")


def _searched_lines(item: ReadChange, words: _Words) -> Iterator[str]:
    """What a search looks through: each item of a list stands for itself."""
    if item.new is None or item.new.kind is not Kind.LIST or not item.new.value:
        yield _change_line(item, words)
        return
    called = _changed_field(item, words)
    for entry in item.new.value:
        yield f"{called}: {_list_item(item, entry, words)}"


def _changed_field(item: ReadChange, words: _Words) -> str:
    kind = words.kind(item.table)
    record = words.record(VIEW_OF_TABLE.get(item.table), item.record)
    return f"  {record}: {words.field(kind, item.code)}"


# --- values --------------------------------------------------------------------------------


def _list_item(item: ReadChange, entry: ListItem, words: _Words) -> str:
    """What an item has, without the parts that say nothing."""
    if entry.kind is not Kind.NESTED:
        return _value(entry, words)
    kind = words.kind(item.table)
    return ", ".join(
        f"{words.part(kind, item.code, part.tag)} {_value(part, words)}"
        for part in entry.value
        if not says_nothing(part)
    )


def _value(value: Property | ListItem | None, words: _Words) -> str:
    if value is None:
        return "nothing"
    if value.kind is Kind.LIST:
        return f"a list of {len(value.value)}"
    if value.kind is Kind.NESTED:
        reference = referred_to(value)
        if reference is None:
            return "a value of several parts"
        tag, record = reference
        return words.referred(tag, record)
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
