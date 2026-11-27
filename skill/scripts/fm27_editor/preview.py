"""A plan in plain words, for the user to approve."""

import sqlite3
from collections.abc import Iterable, Sequence

from fm27_editor.history_words import history_heading, year_lines
from fm27_editor.list_changes import LIST
from fm27_editor.plan import Plan, approval_code
from fm27_editor.planned import Addition, Edit, KnownRecord
from fm27_editor.potential import is_range
from fm27_editor.record_changes import MONEY
from fm27_editor.record_kinds import GROUPS, RecordGroup
from fm27_editor.record_rules import NewReference, Setting
from fm27_editor.rule_words import rule_lines
from fm27_editor.words import amount, counted, shown


def preview_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    return [
        *_starting_lines(plan),
        *_edit_lines(plan, lookup, examples),
        *_history_lines(plan, lookup, examples),
        *_left_out_lines(plan),
        *_addition_lines(plan, lookup, examples),
        *([] if plan.rules is None else rule_lines(plan.rules, lookup)),
        *(f"Warning: {warning}" for warning in plan.warnings),
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
    lines = []
    for group in GROUPS.values():
        edits = [edit for edit in plan.edits if edit.record.kind.group is group]
        lines += _group_lines(group, edits)
    chosen = _spread(plan.edits, examples)
    lines.append(f"Examples, {len(chosen)} of {len(plan.edits):,}:")
    return lines + [_example_line(edit, lookup) for edit in chosen]


def _group_lines(group: RecordGroup, edits: list[Edit]) -> list[str]:
    if not edits:
        return []
    records = len({edit.record.uid for edit in edits})
    changes = counted(len(edits), "change", "changes")
    heading = f"Edits: {changes} to {counted(records, group.one, group.view)}"
    return [heading, *(_field_line(group, alike) for alike in _by_field(edits))]


def _by_field(edits: Iterable[Edit]) -> list[list[Edit]]:
    by_code: dict[str, list[Edit]] = {}
    for edit in edits:
        by_code.setdefault(edit.setting.field.code, []).append(edit)
    return list(by_code.values())


def _field_line(group: RecordGroup, edits: list[Edit]) -> str:
    field = edits[0].setting.field
    parts = [counted(len(edits), group.one, group.view)]
    if field.type in ("integer", "attribute", MONEY):
        parts += _direction(edits)
        numbers = [edit.setting.value for edit in edits if not _has_range(edit)]
        if numbers:
            lowest, highest = amount(field, min(numbers)), amount(field, max(numbers))
            parts.append(f"new values {lowest} to {highest}")
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


def _spread[T](items: Sequence[T], count: int) -> Sequence[T]:
    """Up to `count` items from first to last, so that no part of a long list stays unseen."""
    if len(items) <= count:
        return items
    if count < 2:
        return items[:count]
    return [items[step * (len(items) - 1) // (count - 1)] for step in range(count)]


def _example_line(edit: Edit, lookup: sqlite3.Connection) -> str:
    """The old value and the new one; a list is not known, so only what is done to it is said."""
    field = edit.setting.field
    new = shown(field, edit.setting.value, lookup)
    if field.type == LIST:
        return f"  {_described(edit.record)}: {field.name} {new}"
    old = "unknown" if edit.old is None else shown(field, edit.old, lookup)
    return f"  {_described(edit.record)}: {field.name} {old} -> {new}"


def _described(record: KnownRecord) -> str:
    said = {
        column: words.format(record.facts[column])
        for column, words in record.kind.group.details.items()
        if record.facts[column] is not None
    }
    return ", ".join([f"{record.name} ({record.uid})", *said.values()])


def _left_out_lines(plan: Plan) -> list[str]:
    counts = [
        (plan.already_so, "value that is", "values that are"),
        (plan.years_already_so, "year that is", "years that are"),
    ]
    return [f"Left out: {counted(n, one, many)} so already" for n, one, many in counts if n]


def _history_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    lines = []
    for edit in plan.histories:
        changed = edit.history.changed
        shown_years = _spread(changed, examples)
        lines.append(history_heading(_described(edit.award), edit.history))
        lines += year_lines(shown_years, edit.history.field, lookup)
        if len(changed) > len(shown_years):
            more = len(changed) - len(shown_years)
            lines.append(f"  and {counted(more, 'more year', 'more years')}")
    return lines


def _addition_lines(plan: Plan, lookup: sqlite3.Connection, examples: int) -> list[str]:
    lines = []
    for group in GROUPS.values():
        additions = [new for new in plan.additions if new.kind.group is group]
        if not additions:
            continue
        lines.append(f"New {group.view}: {len(additions):,}")
        lines += [_addition_line(addition, lookup) for addition in additions[:examples]]
        if len(additions) > examples:
            lines.append(f"  and {len(additions) - examples:,} more")
    return lines


def _addition_line(addition: Addition, lookup: sqlite3.Connection) -> str:
    name = "" if addition.name is None else f" {NewReference(addition.name)}"
    settings = "; ".join(_setting(setting, lookup) for setting in addition.settings)
    return f"  {addition.kind.name}{name}: {settings}"


def _setting(setting: Setting, lookup: sqlite3.Connection) -> str:
    return f"{setting.field.name} {shown(setting.field, setting.value, lookup)}"
