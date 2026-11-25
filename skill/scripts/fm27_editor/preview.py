"""A plan in plain words, for the user to approve."""

import datetime
import sqlite3
from collections.abc import Iterable

from fm27_editor.field_definitions import Field
from fm27_editor.person_codes import POTENTIALS
from fm27_editor.person_rules import LOOKUP_TABLES, Setting
from fm27_editor.plan import Edit, KnownPerson, Plan, approval_code


def preview_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    return [
        *_starting_lines(plan),
        *_edit_lines(plan, lookup, examples),
        *_addition_lines(plan, lookup, examples),
        *_warning_lines(plan),
        f"Approval code: {approval_code(plan)}",
    ]


def counted(number: int, one: str, many: str) -> str:
    return f"{number:,} {one if number == 1 else many}"


def _starting_lines(plan: Plan) -> list[str]:
    if plan.start is None:
        return ["A new file"]
    changes = counted(len(plan.start.file.changes.changes), "change", "changes")
    lines = [f"Starts from {plan.start.path.name}, which has {changes}"]
    if plan.replaced:
        fields = counted(plan.replaced, "field", "fields")
        lines.append(f"{fields} set by that file will get the new value instead")
    return lines


def _edit_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    if not plan.edits:
        return []
    people = len({edit.person.uid for edit in plan.edits})
    changes = counted(len(plan.edits), "change", "changes")
    lines = [f"Edits: {changes} to {counted(people, 'person', 'people')}"]
    lines += [_field_line(edits) for edits in _by_field(plan.edits)]
    if plan.already_so:
        values = counted(plan.already_so, "value", "values")
        lines.append(f"Left out: {values} that people have already")
    shown = _spread(plan.edits, examples)
    lines.append(f"Examples, {len(shown)} of {len(plan.edits):,}:")
    return lines + [_example_line(edit, lookup) for edit in shown]


def _by_field(edits: Iterable[Edit]) -> list[list[Edit]]:
    by_code: dict[str, list[Edit]] = {}
    for edit in edits:
        by_code.setdefault(edit.setting.field.code, []).append(edit)
    return list(by_code.values())


def _field_line(edits: list[Edit]) -> str:
    field = edits[0].setting.field
    parts = [counted(len(edits), "person", "people")]
    if field.type in ("integer", "attribute"):
        parts += _direction(edits)
        numbers = [edit.setting.value for edit in edits if not _has_range(edit)]
        if numbers:
            parts.append(f"new values {min(numbers)} to {max(numbers)}")
    return f"  {field.name} ({field.code}): {', '.join(parts)}"


def _direction(edits: list[Edit]) -> list[str]:
    ranges = sum(map(_has_range, edits))
    numbers = [edit for edit in edits if not _has_range(edit)]
    known = [(edit.old, edit.setting.value) for edit in numbers if edit.old is not None]
    up = sum(new > old for old, new in known)
    counts = [
        (up, "up"),
        (len(known) - up, "down"),
        (ranges, "to or from a range"),
        (len(numbers) - len(known), "from an unknown value"),
    ]
    return [f"{count:,} {what}" for count, what in counts if count]


def _has_range(edit: Edit) -> bool:
    """Whether the old or new value is a potential that stands for a range."""
    values = (edit.old, edit.setting.value)
    return edit.setting.field.code in POTENTIALS and any(v is not None and v < 0 for v in values)


def _spread(edits: list[Edit], count: int) -> list[Edit]:
    """Up to `count` edits from first to last, so that no part of a long list stays unseen."""
    if len(edits) <= count:
        return edits
    if count < 2:
        return edits[:count]
    return [edits[step * (len(edits) - 1) // (count - 1)] for step in range(count)]


def _example_line(edit: Edit, lookup: sqlite3.Connection) -> str:
    field = edit.setting.field
    old = "unknown" if edit.old is None else _shown(field, edit.old, lookup)
    new = _shown(field, edit.setting.value, lookup)
    return f"  {_described(edit.person)}: {field.name} {old} -> {new}"


def _described(person: KnownPerson) -> str:
    known = [f"born {person.birth_date}", person.nation, person.club]
    return f"{person.name} ({person.uid}), {', '.join(part for part in known if part)}"


def _addition_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    if not plan.additions:
        return []
    lines = [f"New people: {len(plan.additions):,}"]
    for addition in plan.additions[:examples]:
        settings = "; ".join(_setting(setting, lookup) for setting in addition.settings)
        lines.append(f"  {addition.kind.name.lower()}: {settings}")
    if len(plan.additions) > examples:
        lines.append(f"  and {len(plan.additions) - examples:,} more")
    return lines


def _warning_lines(plan: Plan) -> list[str]:
    if not plan.above_potential:
        return []
    people = counted(plan.above_potential, "person", "people")
    return [f"Warning: {people} would have more ability than potential"]


def _setting(setting: Setting, lookup: sqlite3.Connection) -> str:
    return f"{setting.field.name} {_shown(setting.field, setting.value, lookup)}"


def _shown(field: Field, value: object, lookup: sqlite3.Connection) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    if field.points_to is not None:
        table = LOOKUP_TABLES[field.points_to]
        row = lookup.execute(f"SELECT name FROM {table} WHERE uid = ?", (value,)).fetchone()
        return f"{row[0]} ({value})" if row else str(value)
    if field.choices and value in field.choices:
        return f"{field.choices[value]} ({value})"
    return str(value)
