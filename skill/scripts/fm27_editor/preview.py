"""A plan in plain words, for the user to approve."""

import sqlite3
from collections.abc import Iterable

from fm27_editor.plan import Edit, KnownRecord, Plan, approval_code
from fm27_editor.potential import is_range
from fm27_editor.record_rules import Setting
from fm27_editor.words import counted, shown


def preview_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    return [
        *_starting_lines(plan),
        *_edit_lines(plan, lookup, examples),
        *_addition_lines(plan, lookup, examples),
        *_warning_lines(plan),
        f"Approval code: {approval_code(plan)}",
    ]


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
    people = len({edit.record.uid for edit in plan.edits})
    changes = counted(len(plan.edits), "change", "changes")
    lines = [f"Edits: {changes} to {counted(people, 'person', 'people')}"]
    lines += [_field_line(edits) for edits in _by_field(plan.edits)]
    if plan.already_so:
        values = counted(plan.already_so, "value", "values")
        lines.append(f"Left out: {values} that people have already")
    chosen = _spread(plan.edits, examples)
    lines.append(f"Examples, {len(chosen)} of {len(plan.edits):,}:")
    return lines + [_example_line(edit, lookup) for edit in chosen]


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
    field = edit.setting.field
    return is_range(field, edit.old) or is_range(field, edit.setting.value)


def _spread(edits: list[Edit], count: int) -> list[Edit]:
    """Up to `count` edits from first to last, so that no part of a long list stays unseen."""
    if len(edits) <= count:
        return edits
    if count < 2:
        return edits[:count]
    return [edits[step * (len(edits) - 1) // (count - 1)] for step in range(count)]


def _example_line(edit: Edit, lookup: sqlite3.Connection) -> str:
    field = edit.setting.field
    old = "unknown" if edit.old is None else shown(field, edit.old, lookup)
    new = shown(field, edit.setting.value, lookup)
    return f"  {_described(edit.record)}: {field.name} {old} -> {new}"


def _described(record: KnownRecord) -> str:
    said = {
        column: words.format(record.facts[column])
        for column, words in record.kind.group.details.items()
        if record.facts[column] is not None
    }
    return ", ".join([f"{record.name} ({record.uid})", *said.values()])


def _addition_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    if not plan.additions:
        return []
    lines = [f"New people: {len(plan.additions):,}"]
    for addition in plan.additions[:examples]:
        settings = "; ".join(_setting(setting, lookup) for setting in addition.settings)
        lines.append(f"  {addition.kind.name}: {settings}")
    if len(plan.additions) > examples:
        lines.append(f"  and {len(plan.additions) - examples:,} more")
    return lines


def _warning_lines(plan: Plan) -> list[str]:
    if not plan.above_potential:
        return []
    people = counted(plan.above_potential, "person", "people")
    return [f"Warning: {people} would have more ability than potential"]


def _setting(setting: Setting, lookup: sqlite3.Connection) -> str:
    return f"{setting.field.name} {shown(setting.field, setting.value, lookup)}"
