"""Turning a request into checked edits that can be shown, approved, and then written.

The plan holds what would be written and what the lookup says now. Its approval code stands for
exactly that, so a file is only made for the plan that was shown.
"""

import datetime
import hashlib
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fm27_editor.change_reading import existing_record, read_change
from fm27_editor.editor_file import EditorFile, load_editor_file
from fm27_editor.new_file import new_editor_file
from fm27_editor.people import PersonKind
from fm27_editor.person_changes import edit_person, new_person
from fm27_editor.person_codes import names_by_code
from fm27_editor.person_rules import PersonRules, Setting, has_more_ability_than_potential
from fm27_editor.record_changes import HIGHEST_UID, NewIds, stored_value
from fm27_editor.request import (
    RequestError,
    Values,
    check_request,
    wanted_edits,
    wanted_people,
)

CODE_LENGTH = 12


@dataclass(frozen=True)
class KnownPerson:
    """A person as the lookup describes them."""

    uid: int
    kind: PersonKind
    name: str
    birth_date: str
    nation: str | None
    club: str | None
    ca: int | None
    pa: int | None


@dataclass(frozen=True)
class Edit:
    person: KnownPerson
    setting: Setting
    old: str | int | None
    """What the lookup says now; nothing when it does not know."""


@dataclass(frozen=True)
class Addition:
    kind: PersonKind
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
    """Requested values that people have already, which are left out."""
    replaced: int
    """Edits of a field that the starting file changes as well."""
    above_potential: int
    """People who would have more ability than potential."""


def make_plan(request: Any, rules: PersonRules, lookup: sqlite3.Connection) -> Plan:
    check_request(request)
    start = _starting_file(request.get("start_from"))
    wanted = list(wanted_edits(request, lookup))
    planned = list(_planned(wanted, rules, lookup))
    edits = [edit for edit in planned if edit.old != edit.setting.as_the_lookup_says]
    additions = [
        Addition(kind, rules.new_person_settings(kind, values))
        for kind, values in wanted_people(request)
    ]
    if not edits and not additions:
        raise RequestError("the request changes nothing")
    already_so = len(planned) - len(edits)
    above = _above_potential(edits, additions)
    return Plan(start, edits, additions, already_so, _replaced(start, edits), above)


def approval_code(plan: Plan) -> str:
    """Stands for everything the plan writes, leaving out the random numbers."""
    parts = ["" if plan.start is None else plan.start.digest]
    parts += [f"{edit.person.uid} {_written(edit.setting)}" for edit in plan.edits]
    for addition in plan.additions:
        parts.append(addition.kind.name)
        parts += [_written(setting) for setting in addition.settings]
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
    ids = NewIds(file.changes)
    for edit in plan.edits:
        file.changes.changes += edit_person(edit.person.uid, [edit.setting], ids)
    for addition in plan.additions:
        file.changes.changes += new_person(addition.kind, addition.settings, ids)
    return file


def _written(setting: Setting) -> str:
    return f"{setting.field.code} {stored_value(setting.field, setting.value)!r}"


def _starting_file(path: str | None) -> StartingFile | None:
    if path is None:
        return None
    source = Path(path)
    if not source.is_file():
        raise RequestError(f"there is no file {path}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return StartingFile(source, load_editor_file(source), digest)


def _planned(
    wanted: list[tuple[int, Values]], rules: PersonRules, lookup: sqlite3.Connection
) -> Iterator[Edit]:
    seen = set()
    for uid, values in wanted:
        person, facts = _known(uid, lookup)
        _check_values(person, values)
        settings = rules.settings(person.kind, values)
        names = names_by_code(person.kind)
        for setting in settings:
            code = setting.field.code
            if (uid, code) in seen:
                raise RequestError(f"{setting.field.name} of {person.name} ({uid}) is set twice")
            seen.add((uid, code))
            yield Edit(person, setting, facts.get(names.get(code, "")))


def _known(uid: Any, lookup: sqlite3.Connection) -> tuple[KnownPerson, dict[str, Any]]:
    cursor = lookup.cursor()
    cursor.row_factory = sqlite3.Row
    row = None
    if type(uid) is int and 0 < uid <= HIGHEST_UID:
        row = cursor.execute("SELECT * FROM people WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        raise RequestError(f"the lookup has no person with uid {uid!r}")
    kind = PersonKind[row["kind"].upper()]
    described = [row[name] for name in ("name", "birth_date", "nation", "club", "ca", "pa")]
    return KnownPerson(row["uid"], kind, *described), dict(row)


def _check_values(person: KnownPerson, values: Values) -> None:
    if not values:
        raise RequestError(f"nothing is set on {person.name} ({person.uid})")
    for name, value in values.items():
        if value is None:
            raise RequestError(
                f"there is no value for {name} of {person.name} ({person.uid}); "
                "leave out people whose value the lookup does not know"
            )


def _above_potential(edits: list[Edit], additions: list[Addition]) -> int:
    edited: dict[KnownPerson, list[Setting]] = {}
    for edit in edits:
        edited.setdefault(edit.person, []).append(edit.setting)
    above = [
        has_more_ability_than_potential(person.kind, settings, person.ca, person.pa)
        for person, settings in edited.items()
    ]
    above += [has_more_ability_than_potential(a.kind, a.settings, None, None) for a in additions]
    return sum(above)


def _replaced(start: StartingFile | None, edits: list[Edit]) -> int:
    if start is None:
        return 0
    changes = map(read_change, start.file.changes.changes)
    changed = {(change.record, change.code) for change in changes}
    wanted = ((existing_record(e.person.uid), e.setting.field.code) for e in edits)
    return sum(key in changed for key in wanted)


def _copy(file: EditorFile) -> EditorFile:
    changes = replace(file.changes, changes=list(file.changes.changes))
    return EditorFile(file.container, changes)
