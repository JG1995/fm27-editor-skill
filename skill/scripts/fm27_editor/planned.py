"""What a plan consists of: records to edit, and records to add."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fm27_editor.record_kinds import RecordKind
from fm27_editor.record_rules import Setting


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
