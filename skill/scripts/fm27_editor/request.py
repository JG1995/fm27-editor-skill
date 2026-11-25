"""Reading a request: which records to change, to what, and which to add."""

import json
import re
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fm27_editor.binary import FormatError
from fm27_editor.record_kinds import GROUPS, RecordGroup, RecordKind, kind_named

RULES_KEY = "nation_rules"
HISTORY_KEY = "award_history"
REQUEST_KEYS = {"start_from", "edits", "new", RULES_KEY, HISTORY_KEY}
QUERY_KEYS = {"of", "query"}
BY_HAND_KEYS = {"of", "uid", "set"}
NEW_KEYS = {"kind", "set"}
NAMED_NEW_KEYS = {"kind", "as", "set"}
UID = "uid"
NAME = re.compile(r"[\w-]+")

type Values = Mapping[str, Any]


class RequestError(FormatError):
    """The request cannot be carried out as it is."""


@dataclass(frozen=True)
class WantedEdit:
    group: RecordGroup
    uid: Any
    values: Values


@dataclass(frozen=True)
class WantedRecord:
    kind: RecordKind
    name: str | None
    """What the request calls it, for other records to refer to."""
    values: Values


@dataclass(frozen=True)
class Found:
    """What a query finds."""

    columns: list[str]
    rows: list[tuple]
    has_more: bool


def read_request(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_named_once)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RequestError(f"{path.name} is not a request: {error}") from error


def run_query(lookup: sqlite3.Connection, query: str, limit: int | None = None) -> Found:
    try:
        cursor = lookup.execute(query)
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchall() if limit is None else cursor.fetchmany(limit + 1)
    except sqlite3.Error as error:
        raise RequestError(f"the query cannot be run: {error}") from error
    has_more = limit is not None and len(rows) > limit
    return Found(columns, rows[:limit], has_more)


def check_request(request: Any) -> None:
    _check_keys(request, REQUEST_KEYS, "a request")
    for name in ("edits", "new"):
        if not isinstance(request.get(name, []), list):
            raise RequestError(f"{name} must be a list")
    if not isinstance(request.get("start_from", ""), str):
        raise RequestError("start_from must be the path of a file")


def wanted_edits(request: Any, lookup: sqlite3.Connection) -> Iterator[WantedEdit]:
    """The values each record is to have, for every edit asked for."""
    for entry in request.get("edits", []):
        keys = set(entry) if isinstance(entry, Mapping) else set()
        if keys not in (QUERY_KEYS, BY_HAND_KEYS):
            raise RequestError("an edit has of, and either a query, or a uid and what to set")
        group = _group(entry["of"])
        if keys == QUERY_KEYS:
            for uid, values in _asked_for(entry["query"], lookup):
                yield WantedEdit(group, uid, values)
        else:
            yield WantedEdit(group, entry["uid"], _values(entry))


def wanted_records(request: Any) -> Iterator[WantedRecord]:
    names = set()
    for entry in request.get("new", []):
        keys = set(entry) if isinstance(entry, Mapping) else set()
        if keys not in (NEW_KEYS, NAMED_NEW_KEYS):
            raise RequestError("a new record has a kind, what to set, and maybe a name as")
        name = entry.get("as")
        if name is not None and (not isinstance(name, str) or not NAME.fullmatch(name)):
            raise RequestError(f"{name!r} is not a name of letters, digits, and hyphens")
        if name in names:
            raise RequestError(f"two new records are called {name}")
        names |= {name} - {None}
        yield WantedRecord(kind_named(str(entry["kind"])), name, _values(entry))


def _named_once(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    names = [name for name, _ in pairs]
    repeated = {name for name in names if names.count(name) > 1}
    if repeated:
        raise RequestError(f"the request gives {', '.join(sorted(repeated))} twice in one place")
    return dict(pairs)


def _check_keys(entry: Any, known: set[str], what: str) -> None:
    if not isinstance(entry, Mapping):
        raise RequestError(f"{what} must have named parts: {', '.join(sorted(known))}")
    unknown = entry.keys() - known
    if unknown:
        raise RequestError(f"{what} has no part named {', '.join(sorted(unknown))}")


def _group(name: Any) -> RecordGroup:
    group = GROUPS.get(name) if isinstance(name, str) else None
    if group is None:
        raise RequestError(f"an edit is of {', '.join(GROUPS)}, not {name!r}")
    return group


def _values(entry: Mapping[str, Any]) -> Values:
    if not isinstance(entry["set"], Mapping):
        raise RequestError("what to set must be named values")
    return entry["set"]


def _asked_for(query: Any, lookup: sqlite3.Connection) -> Iterator[tuple[Any, Values]]:
    """Each row names a record, and the other columns are the values it is to have."""
    if not isinstance(query, str):
        raise RequestError("a query must be text")
    found = run_query(lookup, query)
    if UID not in found.columns:
        raise RequestError("the query has no column named uid")
    if len(set(found.columns)) != len(found.columns):
        raise RequestError(f"the query has two columns with one name: {', '.join(found.columns)}")
    if not found.rows:
        raise RequestError("the query finds nothing")
    for row in found.rows:
        values = dict(zip(found.columns, row, strict=True))
        yield values.pop(UID), values
