"""The examples in the skill's instructions are requests that the code accepts."""

import json
import re
from pathlib import Path

import pytest

from fictional_rules import write_rules
from fm27_editor.nation_rules import check_nation_rules
from fm27_editor.record_rules import NewReference
from fm27_editor.request import check_request, wanted_records
from fm27_editor.rule_definitions import RuleDefinitions

INSTRUCTIONS = Path(__file__).parents[1] / "skill" / "SKILL.md"
REQUEST, RULES = (
    json.loads(block)
    for block in re.findall("```json\n(.*?)```", INSTRUCTIONS.read_text(encoding="utf-8"), re.S)
)


def test_the_example_request_has_known_parts():
    check_request(REQUEST)

    assert [record.name for record in wanted_records(REQUEST)] == ["D1", None]


def test_the_example_rules_fit_together(tmp_path):
    definitions = RuleDefinitions(write_rules(tmp_path))

    rules = check_nation_rules(
        RULES,
        definitions,
        lambda points_to, called, given: (
            NewReference(given[1:]) if isinstance(given, str) else given
        ),
    )

    assert rules.warnings == []


@pytest.mark.parametrize("kind", ["player", "staff", "club", "competition", "nation_rules"])
def test_every_kind_of_fields_is_named(kind):
    assert f"`{kind}`" in INSTRUCTIONS.read_text(encoding="utf-8")
