"""Turning a request into checked edits that can be shown, approved, and then written.

The plan holds what would be written and what the lookup says now. Its approval code stands for
exactly that, so a file is only made for the plan that was shown.
"""

import datetime
import hashlib
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fm27_editor.change_reading import Change, existing_record, read_change
from fm27_editor.editor_file import EditorFile, load_editor_file
from fm27_editor.new_file import new_editor_file
from fm27_editor.potential import ABILITY, POTENTIAL, has_more_ability_than_potential
from fm27_editor.record_changes import HIGHEST_UID, NewIds, stored_value
from fm27_editor.record_kinds import RecordGroup, RecordKind, kind_of
from fm27_editor.record_rules import NEW_MARK, NewReference, RecordRules, Setting
from fm27_editor.request import (
    RequestError,
    WantedEdit,
    WantedRecord,
    check_request,
    wanted_edits,
    wanted_records,
)
from fm27_editor.setting_changes import edit_record, new_record

CODE_LENGTH = 12


@dataclass(frozen=True)
class KnownRecord:
    """A record as the lookup describes it."""

    uid: int
    kind: RecordKind
    facts: Mapping[str, Any]

    @property
    def name(self) -> str:
        return self.facts["name"]


@dataclass(frozen=True)
class Edit:
    record: KnownRecord
    setting: Setting
    old: str | int | None
    """What the lookup says now; nothing when it does not know."""


@dataclass(frozen=True)
class Addition:
    kind: RecordKind
    name: str | None
    """What the request calls it, for other records to refer to."""
    settings: list[Setting]


@dataclass(frozen=True)
class StartingFile:
    path: Path
    file: EditorFile
    digest: str


@dataclass(frozen=True)
class Plan:
    start: StartingFile | None
    edits: list[Edit]
    additions: list[Addition]
    already_so: int
    """Requested values that records have already, which are left out."""
    replaced: int
    """Edits of a field that the starting file changes as well."""
    above_potential: int
    """People who would have more ability than potential."""


def make_plan(request: Any, rules: RecordRules, lookup: sqlite3.Connection) -> Plan:
    check_request(request)
    start = _starting_file(request.get("start_from"))
    additions = _additions(wanted_records(request), rules)
    new = {addition.name: addition.kind for addition in additions if addition.name is not None}
    planned = list(_planned(wanted_edits(request, lookup), new, rules, lookup))
    edits = [edit for edit in planned if edit.old != edit.setting.as_the_lookup_says]
    if not edits and not additions:
        raise RequestError("the request changes nothing")
    already_so = len(planned) - len(edits)
    above = _above_potential(edits, additions)
    return Plan(start, edits, additions, already_so, _replaced(start, edits), above)


def approval_code(plan: Plan) -> str:
    """Stands for everything the plan writes, leaving out the random numbers."""
    parts = ["" if plan.start is None else plan.start.digest]
    for addition in plan.additions:
        parts.append(f"{addition.kind.name} {addition.name}")
        parts += [_written(setting) for setting in addition.settings]
    parts += [f"{_address(edit.record)} {_written(edit.setting)}" for edit in plan.edits]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:CODE_LENGTH]


def build_file(plan: Plan, approved: str, today: datetime.date) -> EditorFile:
    """The file with the plan's changes, behind those of the file it starts from.

    Only for a plan whose approval code was given back.
    """
    code = approval_code(plan)
    if code != approved:
        raise RequestError(
            f"this plan ({code}) is not the one that was approved ({approved}); preview it again"
        )
    file = new_editor_file(today) if plan.start is None else _copy(plan.start.file)
    file.changes.changes += _changes(plan, NewIds(file.changes))
    return file


def _changes(plan: Plan, ids: NewIds) -> list[Change]:
    """New records first, in the order of the request, because what follows may refer to them."""
    changes, new = [], {}
    for addition in plan.additions:
        record = ids.record()
        if addition.name is not None:
            new[addition.name] = record
        changes += new_record(addition.kind, record, addition.settings, new, ids)
    for edit in plan.edits:
        changes += edit_record(edit.record.kind, edit.record.uid, [edit.setting], new, ids)
    return changes


def _address(record: KnownRecord) -> tuple[int, int]:
    return record.kind.group.table, record.uid


def _written(setting: Setting) -> str:
    if isinstance(setting.value, NewReference):
        return f"{setting.field.code} {NEW_MARK}{setting.value.name}"
    return f"{setting.field.code} {stored_value(setting.field, setting.value)!r}"


def _starting_file(path: str | None) -> StartingFile | None:
    if path is None:
        return None
    source = Path(path)
    if not source.is_file():
        raise RequestError(f"there is no file {path}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return StartingFile(source, load_editor_file(source), digest)


def _additions(wanted: Iterable[WantedRecord], rules: RecordRules) -> list[Addition]:
    additions: list[Addition] = []
    new: dict[str, RecordKind] = {}
    for record in wanted:
        settings = rules.new_record_settings(record.kind, record.values, new)
        additions.append(Addition(record.kind, record.name, settings))
        if record.name is not None:
            new[record.name] = record.kind
    return additions


def _planned(
    wanted: Iterable[WantedEdit],
    new: Mapping[str, RecordKind],
    rules: RecordRules,
    lookup: sqlite3.Connection,
) -> Iterator[Edit]:
    seen = set()
    for edit in wanted:
        record = _known(edit.group, edit.uid, lookup)
        _check_values(record, edit.values)
        for setting in rules.settings(record.kind, edit.values, new):
            field = setting.field
            if (_address(record), field.code) in seen:
                raise RequestError(f"{field.name} of {record.name} ({record.uid}) is set twice")
            seen.add((_address(record), field.code))
            yield Edit(record, setting, record.facts.get(record.kind.names.get(field.code, "")))


def _known(group: RecordGroup, uid: Any, lookup: sqlite3.Connection) -> KnownRecord:
    cursor = lookup.cursor()
    cursor.row_factory = sqlite3.Row
    row = None
    if type(uid) is int and 0 < uid <= HIGHEST_UID:
        row = cursor.execute(f"SELECT * FROM {group.view} WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        raise RequestError(f"the lookup has no {group.one} with uid {uid!r}")
    facts = dict(row)
    return KnownRecord(facts["uid"], kind_of(group, facts), facts)


def _check_values(record: KnownRecord, values: Mapping[str, Any]) -> None:
    if not values:
        raise RequestError(f"nothing is set on {record.name} ({record.uid})")
    for name, value in values.items():
        if value is None:
            raise RequestError(
                f"there is no value for {name} of {record.name} ({record.uid}); "
                f"leave out {record.kind.group.view} whose value the lookup does not know"
            )


def _above_potential(edits: list[Edit], additions: list[Addition]) -> int:
    edited: dict[tuple[int, int], list[Edit]] = {}
    for edit in edits:
        edited.setdefault(_address(edit.record), []).append(edit)
    above = []
    for of_one in edited.values():
        kind, facts = of_one[0].record.kind, of_one[0].record.facts
        settings = _by_code(edit.setting for edit in of_one)
        ability, potential = facts.get(ABILITY), facts.get(POTENTIAL)
        above.append(has_more_ability_than_potential(kind, settings, ability, potential))
    above += [
        has_more_ability_than_potential(new.kind, _by_code(new.settings), None, None)
        for new in additions
    ]
    return sum(above)


def _by_code(settings: Iterable[Setting]) -> list[tuple[str, object]]:
    return [(setting.field.code, setting.value) for setting in settings]


def _replaced(start: StartingFile | None, edits: list[Edit]) -> int:
    if start is None:
        return 0
    changes = map(read_change, start.file.changes.changes)
    changed = {(change.table, change.record, change.code) for change in changes}
    wanted = (
        (edit.record.kind.group.table, existing_record(edit.record.uid), edit.setting.field.code)
        for edit in edits
    )
    return sum(key in changed for key in wanted)


def _copy(file: EditorFile) -> EditorFile:
    changes = replace(file.changes, changes=list(file.changes.changes))
    return EditorFile(file.container, changes)
