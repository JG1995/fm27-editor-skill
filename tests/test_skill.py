"""The examples in the skill's instructions are requests that the code accepts."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from fictional_editor import write_editor
from fictional_rules import write_rules
from fm27_editor import award_lookup, place_lookup
from fm27_editor.award_history import check_award_history
from fm27_editor.nation_rules import check_nation_rules
from fm27_editor.record_fields import NewReference, RecordFields
from fm27_editor.record_kinds import AWARD, KINDS
from fm27_editor.request import HISTORY_KEY, check_request, wanted_records
from fm27_editor.rule_definitions import RuleDefinitions
from fm27_editor.rule_plan import fit_warnings
from fm27_editor.rule_words import RULES_OF

INSTRUCTIONS = Path(__file__).parents[1] / "skill" / "SKILL.md"
REQUEST, RULES, HISTORY = (
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

    assert list(fit_warnings(rules, str)) == []


def test_the_example_history_fits(tmp_path):
    editor = write_editor(tmp_path / "editor")
    with closing(sqlite3.connect(":memory:")) as lookup:
        lookup.executescript(place_lookup.SCHEMA + award_lookup.SCHEMA)
        lookup.execute("CREATE TABLE person(uid INTEGER PRIMARY KEY, name TEXT)")
        lookup.execute("INSERT INTO person VALUES (1234567, 'Testy McTestface')")
        lookup.execute("INSERT INTO nation VALUES (12345, 'Testland')")
        lookup.execute("INSERT INTO club (uid, name) VALUES (67890, 'Testby')")
        lookup.execute("INSERT INTO award (uid, name) VALUES (24680, 'Example Award')")
        lookup.execute("INSERT INTO award_year VALUES (1, 24680, 1973, 0, 0)")
        lookup.execute("INSERT INTO award_place (year_uid, place, name) VALUES (1, 2, 'Runner-up')")

        fields = RecordFields(editor, lookup).fields(AWARD)
        (history,) = check_award_history(HISTORY, fields, lookup)

    assert [new.year for _, new in history.changed] == [1973, 2020]


@pytest.mark.parametrize("kind", [*KINDS, *RULES_OF, HISTORY_KEY])
def test_every_kind_of_fields_is_named(kind):
    assert f"`{kind}`" in INSTRUCTIONS.read_text(encoding="utf-8")


def test_the_example_wage_is_converted_without_losing_part_of_a_pound():
    instructions = INSTRUCTIONS.read_text(encoding="utf-8")
    (conversion,) = re.findall(r"`(CAST\(round\([^`]*per_pound\) AS INTEGER\))`", instructions)

    with closing(sqlite3.connect(":memory:")) as lookup:
        (pounds,) = lookup.execute(f"SELECT {conversion} FROM (SELECT 2.5 AS per_pound)").fetchone()

    assert pounds == round(100_000 * 12 / 52 / 2.5)
