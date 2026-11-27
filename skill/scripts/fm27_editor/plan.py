"""Turning a request into checked edits that can be shown, approved, and then written.

The plan holds what would be written and what the lookup says now. Its approval code stands for
exactly that, so a file is only made for the plan that was shown.
"""

import datetime
import hashlib
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from fm27_editor.award_history import history_change
from fm27_editor.change_list import ChangeList
from fm27_editor.editor_file import EditorFile, load_editor_file
from fm27_editor.history_plan import history_warnings, plan_histories
from fm27_editor.list_changes import LIST
from fm27_editor.nation_rules import NationRules
from fm27_editor.new_file import new_editor_file
from fm27_editor.planned import (
    Addition,
    Edit,
    HistoryEdit,
    KnownRecord,
    StartingFile,
    known_record,
)
from fm27_editor.potential import ABILITY, POTENTIAL, has_more_ability_than_potential
from fm27_editor.record_changes import NewIds, stored_value
from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import NewReference, RecordRules, Setting
from fm27_editor.request import (
    HISTORY_KEY,
    RULES_KEY,
    RequestError,
    WantedEdit,
    WantedRecord,
    check_request,
    wanted_edits,
    wanted_records,
)
from fm27_editor.rule_changes import add_rules, check_has_no_rules
from fm27_editor.rule_definitions import RuleDefinitions
from fm27_editor.rule_plan import plan_rules, rule_warnings
from fm27_editor.setting_changes import edit_record, new_record
from fm27_editor.words import counted

CODE_LENGTH = 12


@dataclass(frozen=True)
class Plan:
    start: StartingFile | None
    edits: list[Edit]
    additions: list[Addition]
    histories: list[HistoryEdit]
    already_so: int
    """Requested values that records have already, which are left out."""
    years_already_so: int
    """Requested years of a history that are so already."""
    replaced: int
    """Edits of a field that the starting file changes as well."""
    rules: NationRules | None
    warnings: list[str]


def make_plan(request: Any, editor_dir: Path, lookup: sqlite3.Connection) -> Plan:
    check_request(request)
    rules = RecordRules(editor_dir, lookup)
    start = _starting_file(request.get("start_from"))
    additions = _additions(wanted_records(request), rules)
    new = {addition.name: addition.kind for addition in additions if addition.name is not None}
    planned = list(_planned(wanted_edits(request, lookup), new, rules, lookup))
    edits = [edit for edit in planned if edit.old != edit.setting.as_the_lookup_says]
    found = []
    if HISTORY_KEY in request:
        found = plan_histories(request[HISTORY_KEY], rules, lookup, start)
    histories = [edit for edit in found if edit.history.changed]
    nation_rules = None
    if RULES_KEY in request:
        if start is not None:
            check_has_no_rules(start.file.changes)
        definitions = RuleDefinitions(editor_dir)
        nation_rules = plan_rules(
            request[RULES_KEY], definitions, partial(rules.refer, new=new), additions, lookup
        )
    if not edits and not additions and not histories and nation_rules is None:
        raise RequestError("the request changes nothing")
    return Plan(
        start,
        edits,
        additions,
        histories,
        already_so=len(planned) - len(edits),
        years_already_so=sum(edit.history.already_so for edit in found),
        replaced=_replaced(start, edits),
        rules=nation_rules,
        warnings=[
            *(
                []
                if nation_rules is None
                else rule_warnings(nation_rules, edits, additions, lookup)
            ),
            *_potential_warnings(edits, additions),
            *history_warnings(histories),
        ],
    )


def approval_code(plan: Plan) -> str:
    """Stands for everything the plan writes, leaving out the random numbers."""
    parts = ["" if plan.start is None else plan.start.digest]
    for addition in plan.additions:
        parts.append(f"{addition.kind.name} {addition.name}")
        parts += [_written(setting) for setting in addition.settings]
    parts += [f"{edit.record.address} {_written(edit.setting)}" for edit in plan.edits]
    parts += [f"{edit.award.address} {edit.history.years!r}" for edit in plan.histories]
    parts.append("" if plan.rules is None else repr(plan.rules.values))
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
    _add_changes(file.changes, plan)
    return file


def _add_changes(file: ChangeList, plan: Plan) -> None:
    """New records first, in the order of the request, because what follows may refer to them."""
    ids, new = NewIds(file), {}
    for addition in plan.additions:
        record = ids.record()
        if addition.name is not None:
            new[addition.name] = record
        file.changes += new_record(addition.kind, record, addition.settings, new, ids)
    for edit in plan.edits:
        file.changes += edit_record(edit.record.kind, edit.record.uid, [edit.setting], new, ids)
    file.changes += [history_change(edit.history, ids) for edit in plan.histories]
    if plan.rules is not None:
        add_rules(file, plan.rules, new)


def _written(setting: Setting) -> str:
    if isinstance(setting.value, NewReference) or setting.field.type == LIST:
        return f"{setting.field.code} {setting.value!r}"
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
        record = known_record(edit.group, edit.uid, lookup)
        _check_values(record, edit.values)
        for setting in rules.settings(record.kind, edit.values, new):
            field = setting.field
            if (record.address, field.code) in seen:
                raise RequestError(f"{field.name} of {record.name} ({record.uid}) is set twice")
            seen.add((record.address, field.code))
            yield Edit(record, setting, record.facts.get(record.kind.names.get(field.code, "")))


def _check_values(record: KnownRecord, values: Mapping[str, Any]) -> None:
    if not values:
        raise RequestError(f"nothing is set on {record.name} ({record.uid})")
    for name, value in values.items():
        if value is None:
            raise RequestError(
                f"there is no value for {name} of {record.name} ({record.uid}); "
                f"leave out {record.kind.group.view} whose value the lookup does not know"
            )


def _potential_warnings(edits: list[Edit], additions: list[Addition]) -> list[str]:
    edited: dict[tuple[int, int], list[Edit]] = {}
    for edit in edits:
        edited.setdefault(edit.record.address, []).append(edit)
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
    if not any(above):
        return []
    people = counted(sum(above), "person", "people")
    return [f"{people} would have more ability than potential"]


def _by_code(settings: Iterable[Setting]) -> list[tuple[str, object]]:
    return [(setting.field.code, setting.value) for setting in settings]


def _replaced(start: StartingFile | None, edits: list[Edit]) -> int:
    if start is None:
        return 0
    wanted = ((edit.record.address, edit.setting.field.code) for edit in edits)
    return sum(key in start.changed for key in wanted)


def _copy(file: EditorFile) -> EditorFile:
    given = file.changes
    changes = ChangeList(list(given.general), list(given.editor), list(given.changes))
    return EditorFile(file.container, changes)
