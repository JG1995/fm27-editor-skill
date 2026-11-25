"""Turning a request into checked edits that can be shown, approved, and then written.

A request says which people to change, by a query over the lookup or by unique ID, and which people
to add. The plan holds what would be written and what the lookup says now. Its approval code stands
for exactly that, so a file is only written for the plan that was shown.
"""

import datetime
import hashlib
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fm27_editor.change_list import ChangeList
from fm27_editor.editor_file import EditorFile, load_editor_file
from fm27_editor.new_file import new_editor_file
from fm27_editor.people import PersonKind
from fm27_editor.person_changes import edit_person, new_person
from fm27_editor.person_codes import person_codes
from fm27_editor.person_rules import PersonRules, Setting
from fm27_editor.record_changes import (
    HIGHEST_UID,
    EditError,
    NewIds,
    existing_record,
    stored_value,
)

REQUEST_KEYS = {"start_from", "edits", "new_people"}
QUERY_KEYS = {"query"}
BY_HAND_KEYS = {"uid", "set"}
NEW_PERSON_KEYS = {"kind", "set"}
UID = "uid"
CODE_LENGTH = 12

type Request = Mapping[str, Any]
type Values = Mapping[str, Any]


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


def make_plan(request: Request, rules: PersonRules, lookup: sqlite3.Connection) -> Plan:
    _check_keys(request, REQUEST_KEYS, "a request")
    start = _starting_file(request.get("start_from"))
    wanted = list(_wanted(_listed(request, "edits"), lookup))
    planned = list(_planned(wanted, rules, lookup))
    edits = [edit for edit in planned if edit.old != _as_the_lookup_says(edit.setting)]
    additions = [_addition(entry, rules) for entry in _listed(request, "new_people")]
    if not edits and not additions:
        raise EditError("the request changes nothing")
    already_so = len(planned) - len(edits)
    above = _above_potential(edits, additions)
    return Plan(start, edits, additions, already_so, _replaced(start, edits), above)


def build_file(plan: Plan, today: datetime.date) -> EditorFile:
    """The file with the plan's changes, behind those of the file it starts from."""
    file = new_editor_file(today) if plan.start is None else _copy(plan.start.file)
    ids = NewIds(file.changes)
    for edit in plan.edits:
        file.changes.changes += edit_person(edit.person.uid, [edit.setting], ids)
    for addition in plan.additions:
        file.changes.changes += new_person(addition.kind, addition.settings, ids)
    return file


def approval_code(plan: Plan) -> str:
    """Stands for everything the plan writes, leaving out the random numbers."""
    parts = ["" if plan.start is None else plan.start.digest]
    parts += [f"{edit.person.uid} {_written(edit.setting)}" for edit in plan.edits]
    for addition in plan.additions:
        parts.append(addition.kind.name)
        parts += [_written(setting) for setting in addition.settings]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:CODE_LENGTH]


def _written(setting: Setting) -> str:
    return f"{setting.field.code} {stored_value(setting.field, setting.value)!r}"


# --- reading the request ------------------------------------------------------------------


def _check_keys(entry: Any, known: set[str], what: str) -> None:
    if not isinstance(entry, Mapping):
        raise EditError(f"{what} must have named parts: {', '.join(sorted(known))}")
    unknown = entry.keys() - known
    if unknown:
        raise EditError(f"{what} has no part named {', '.join(sorted(unknown))}")


def _listed(request: Request, name: str) -> list[Any]:
    entries = request.get(name, [])
    if not isinstance(entries, list):
        raise EditError(f"{name} must be a list")
    return entries


def _starting_file(path: Any) -> StartingFile | None:
    if path is None:
        return None
    if not isinstance(path, str):
        raise EditError("start_from must be the path of a file")
    source = Path(path)
    if not source.is_file():
        raise EditError(f"there is no file {path}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return StartingFile(source, load_editor_file(source), digest)


def _wanted(entries: list[Any], lookup: sqlite3.Connection) -> Iterator[tuple[int, Values]]:
    for entry in entries:
        keys = set(entry) if isinstance(entry, Mapping) else set()
        if keys == QUERY_KEYS:
            yield from _asked_for(entry["query"], lookup)
        elif keys == BY_HAND_KEYS:
            yield entry["uid"], _values(entry)
        else:
            raise EditError("an edit has either a query, or a uid and what to set")


def _values(entry: Mapping[str, Any]) -> Values:
    if not isinstance(entry["set"], Mapping):
        raise EditError("what to set must be named values")
    return entry["set"]


def _asked_for(query: Any, lookup: sqlite3.Connection) -> Iterator[tuple[int, Values]]:
    """Each row names a person, and the other columns are the values they are to have."""
    if not isinstance(query, str):
        raise EditError("a query must be text")
    try:
        found = lookup.execute(query)
        columns = [column[0] for column in found.description or []]
        rows = found.fetchall()
    except sqlite3.Error as error:
        raise EditError(f"the query cannot be run: {error}") from error
    if UID not in columns:
        raise EditError("the query has no column named uid")
    if len(set(columns)) != len(columns):
        raise EditError(f"the query has two columns with one name: {', '.join(columns)}")
    if not rows:
        raise EditError("the query finds no one")
    for row in rows:
        values = dict(zip(columns, row, strict=True))
        yield values.pop(UID), values


def _addition(entry: Any, rules: PersonRules) -> Addition:
    _check_keys(entry, NEW_PERSON_KEYS, "a new person")
    if set(entry) != NEW_PERSON_KEYS:
        raise EditError("a new person has a kind and what to set")
    try:
        kind = PersonKind[str(entry["kind"]).upper()]
    except KeyError as error:
        raise EditError(f"{entry['kind']} is not a kind of person") from error
    return Addition(kind, rules.new_person_settings(kind, _values(entry)))


# --- checking it against the lookup --------------------------------------------------------


def _planned(
    wanted: list[tuple[int, Values]], rules: PersonRules, lookup: sqlite3.Connection
) -> Iterator[Edit]:
    names = {kind: _names_by_code(kind) for kind in (PersonKind.PLAYER, PersonKind.STAFF)}
    seen = set()
    for uid, values in wanted:
        person, facts = _known(uid, lookup)
        _check_values(person, values)
        for setting in rules.settings(person.kind, values):
            code = setting.field.code
            if (uid, code) in seen:
                raise EditError(f"{setting.field.name} of {person.name} ({uid}) is set twice")
            seen.add((uid, code))
            yield Edit(person, setting, facts.get(names[person.kind].get(code, "")))


def _names_by_code(kind: PersonKind) -> dict[str, str]:
    return {code: name for name, code in person_codes(kind).items()}


def _known(uid: Any, lookup: sqlite3.Connection) -> tuple[KnownPerson, dict[str, Any]]:
    cursor = lookup.cursor()
    cursor.row_factory = sqlite3.Row
    row = None
    if type(uid) is int and 0 < uid <= HIGHEST_UID:
        row = cursor.execute("SELECT * FROM people WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        raise EditError(f"the lookup has no person with uid {uid!r}")
    kind = PersonKind[row["kind"].upper()]
    described = [row[name] for name in ("name", "birth_date", "nation", "club", "ca", "pa")]
    return KnownPerson(row["uid"], kind, *described), dict(row)


def _check_values(person: KnownPerson, values: Values) -> None:
    if not values:
        raise EditError(f"nothing is set on {person.name} ({person.uid})")
    for name, value in values.items():
        if value is None:
            raise EditError(
                f"there is no value for {name} of {person.name} ({person.uid}); "
                "leave out people whose value the lookup does not know"
            )


def _as_the_lookup_says(setting: Setting) -> str | int:
    value = setting.value
    return value.isoformat() if isinstance(value, datetime.date) else value


def _above_potential(edits: list[Edit], additions: list[Addition]) -> int:
    edited: dict[KnownPerson, list[Setting]] = {}
    for edit in edits:
        edited.setdefault(edit.person, []).append(edit.setting)
    outcomes = [
        _outcome(person.kind, settings, {"ca": person.ca, "pa": person.pa})
        for person, settings in edited.items()
    ]
    outcomes += [_outcome(new.kind, new.settings, {}) for new in additions]
    return sum(ca is not None and pa is not None and 0 < pa < ca for ca, pa in outcomes)


def _outcome(
    kind: PersonKind, settings: list[Setting], now: Mapping[str, int | None]
) -> tuple[int | None, int | None]:
    """Ability and potential as they would be; a potential below 0 stands for a range."""
    codes = person_codes(kind)
    set_to = {setting.field.code: setting.value for setting in settings}
    return tuple(set_to.get(codes[name], now.get(name)) for name in ("ca", "pa"))


def _replaced(start: StartingFile | None, edits: list[Edit]) -> int:
    if start is None:
        return 0
    changed = set()
    for change in start.file.changes.changes:
        items = {item.tag: item.value for item in change}
        changed.add((items.get("duni"), items.get("prty")))
    wanted = ((existing_record(e.person.uid), e.setting.field.code) for e in edits)
    return sum(key in changed for key in wanted)


def _copy(file: EditorFile) -> EditorFile:
    changes: ChangeList = replace(file.changes, changes=list(file.changes.changes))
    return EditorFile(file.container, changes)
