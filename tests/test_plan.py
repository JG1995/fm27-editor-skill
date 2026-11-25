import datetime

import pytest

import synthetic
from fictional_editor import PEOPLE, STAFF_KIND, write_editor
from fm27_editor.base_database import open_database
from fm27_editor.binary import FormatError
from fm27_editor.plan import approval_code, build_file, make_plan
from fm27_editor.record_rules import RecordRules
from fm27_editor.request import RequestError

TODAY = datetime.date(2026, 11, 12)
BOTH_KIND = 3
CROWD = [
    *PEOPLE,
    (2, 102, "Charlie Coach", 1980, 110, (41, 9001), (0, 9102), STAFF_KIND),
    (3, 103, "Delta Dual", 1985, 90, (41, 9001), (0, 9102), BOTH_KIND),
]
NEW_PLAYER = {
    "kind": "player",
    "set": {"Pfna": "Testy", "Psna": "New", "birth_date": "2008-04-25", "nation_uid": 9001},
}


@pytest.fixture
def editor(tmp_path):
    return write_editor(tmp_path / "editor", CROWD)


@pytest.fixture
def plan_for(editor, tmp_path):
    lookup = open_database(editor, tmp_path / "cache.sqlite")
    rules = RecordRules(editor, lookup)
    yield lambda **request: make_plan(request, rules, lookup)
    lookup.close()


def by_hand(uid, **values):
    return {"uid": uid, "set": values}


def edited(plan):
    return [(e.record.uid, e.setting.field.code, e.old, e.setting.value) for e in plan.edits]


def test_a_query_gives_each_person_the_values_of_its_columns(plan_for):
    query = "SELECT uid, min(pa + 5, 144) AS pa, 18 AS finishing FROM people WHERE kind = 'player'"

    plan = plan_for(edits=[{"query": query}])

    assert edited(plan) == [
        (100, "PPAB", 140, 144),
        (100, "PDfn", 15, 18),
        (101, "PPAB", 80, 85),
        (101, "PDfn", 15, 18),
    ]


def test_one_person_is_edited_by_unique_id(plan_for):
    assert edited(plan_for(edits=[by_hand(101, finishing=3)])) == [(101, "PDfn", 15, 3)]


def test_staff_are_edited_in_their_own_fields(plan_for):
    assert edited(plan_for(edits=[by_hand(102, ca=111)])) == [(102, "Ncra", 110, 111)]


def test_a_field_the_lookup_does_not_know_has_no_old_value(plan_for):
    assert edited(plan_for(edits=[by_hand(100, Phes=190)])) == [(100, "Phes", None, 190)]


def test_dates_are_given_as_text(plan_for):
    (edit,) = plan_for(edits=[by_hand(100, birth_date="2005-01-02")]).edits

    assert edit.old == "2004-02-29"
    assert edit.setting.value == datetime.date(2005, 1, 2)


def test_values_a_person_already_has_are_left_out(plan_for):
    plan = plan_for(edits=[by_hand(100, ca=120, birth_date="2004-02-29", finishing=9)])

    assert edited(plan) == [(100, "PDfn", 15, 9)]
    assert plan.already_so == 2


def test_people_are_described_the_way_the_lookup_knows_them(plan_for):
    (edit,) = plan_for(edits=[by_hand(100, finishing=3)]).edits

    facts = edit.record.facts
    assert (facts["name"], facts["birth_date"]) == ("Alfa Striker", "2004-02-29")
    assert (facts["nation"], facts["club"]) == ("Norwegia", "Fictional City")


@pytest.mark.parametrize(
    ("edit", "complaint"),
    [
        (by_hand(4242, finishing=3), "4242"),
        (by_hand("100", finishing=3), "'100'"),
        (by_hand(True, finishing=3), "True"),
        (by_hand(10**20, finishing=3), "100000000000000000000"),
        ({"uid": 100, "set": 5}, "set"),
        ({"query": 5}, "query"),
        ({"query": "SELECT uid, 5 AS pa FROM people; SELECT 1"}, "one statement"),
        (by_hand(100), "nothing"),
        (by_hand(100, sprint=3), "sprint"),
        (by_hand(100, finishing=21), "PDfn"),
        (by_hand(100, birth_date="soon"), "soon"),
        (by_hand(103, finishing=3), "both"),
        ({"uid": 100}, "query"),
        ({"query": "SELECT 1", "uid": 100, "set": {}}, "query"),
        ({"query": "SELECT uid FROM people"}, "nothing"),
        ({"query": "SELECT pa FROM people"}, "uid"),
        ({"query": "SELECT uid, pa, ca AS pa FROM people"}, "pa"),
        ({"query": "SELECT uid, pa * 1.5 AS pa FROM people"}, "whole number"),
        ({"query": "SELECT uid, NULL AS pa FROM people"}, "no value for pa"),
        ({"query": "SELECT uid, pa FROM nowhere"}, "nowhere"),
        ({"query": "DELETE FROM person"}, "readonly"),
        ({"query": "SELECT uid, 5 AS pa FROM people WHERE 0"}, "no one"),
    ],
)
def test_an_edit_that_cannot_be_made_is_refused_with_a_reason(plan_for, edit, complaint):
    with pytest.raises(FormatError, match=complaint):
        plan_for(edits=[edit])


def test_the_same_field_of_one_person_cannot_be_set_twice(plan_for):
    with pytest.raises(FormatError, match="Alfa Striker"):
        plan_for(edits=[by_hand(100, finishing=3), by_hand(100, finishing=4)])


@pytest.mark.parametrize(
    "request_",
    [
        {},
        {"edits": []},
        {"edits": [by_hand(100, ca=120)]},
        {"edit": [by_hand(100, finishing=3)]},
        {"edits": by_hand(100, finishing=3)},
        {"start_from": 5, "edits": [by_hand(100, finishing=3)]},
        {"new_people": [{"kind": "player"}]},
        {"new_people": [{"kind": "player", "set": 5}]},
        {"new_people": [{"kind": "wizard", "set": {}}]},
        {"new_people": [NEW_PLAYER | {"extra": 1}]},
    ],
)
def test_a_request_that_is_empty_or_misspelt_is_refused(plan_for, request_):
    with pytest.raises(FormatError):
        plan_for(**request_)


def test_new_people_are_planned_with_their_settings(plan_for):
    (addition,) = plan_for(new_people=[NEW_PLAYER]).additions

    assert addition.kind.name == "player"
    assert [s.field.code for s in addition.settings] == ["Pfna", "Psna", "Pdob", "Pnti"]


# --- the file -----------------------------------------------------------------------------


@pytest.fixture
def started(tmp_path):
    """A file that already changes the height of person 100."""
    path = tmp_path / "Started.fmf"
    change = synthetic.change(
        synthetic.prop("dtty", 0x11, b"\x01"),
        synthetic.prop("duni", 0x0F, (100).to_bytes(4, "little") * 2),
        synthetic.prop("prty", 0x02, b"sehP"),
        synthetic.prop("nwvl", 0x11, b"\x64"),
    )
    path.write_bytes(
        synthetic.container(
            "Started",
            [("Started", ".dbc", synthetic.change_list(change))],
            folder=("_data", [("details", ".aom", synthetic.details("Started"))]),
        )
    )
    return path


def codes(file):
    return [next(i.value for i in change if i.tag == "prty") for change in file.changes.changes]


def test_the_file_holds_the_planned_changes(plan_for):
    plan = plan_for(edits=[by_hand(100, finishing=3)], new_people=[NEW_PLAYER])

    file = build_file(plan, approval_code(plan), TODAY)

    assert codes(file) == ["PDfn", "ADDR", "Pfna", "Psna", "Pdob", "Pnti"]


def test_changes_are_added_behind_those_of_the_file_to_start_from(plan_for, started):
    plan = plan_for(start_from=str(started), edits=[by_hand(100, finishing=3)])

    assert codes(build_file(plan, approval_code(plan), TODAY)) == ["Phes", "PDfn"]


def test_fields_the_starting_file_changes_already_are_counted(plan_for, started):
    plan = plan_for(start_from=str(started), edits=[by_hand(100, Phes=190, finishing=3)])

    assert plan.replaced == 1


def test_a_starting_file_that_does_not_exist_is_reported(plan_for, tmp_path):
    with pytest.raises(FormatError, match="Nowhere.fmf"):
        plan_for(start_from=str(tmp_path / "Nowhere.fmf"), edits=[by_hand(100, finishing=3)])


def test_building_twice_gives_the_new_person_different_ids_but_the_same_code(plan_for):
    plan = plan_for(new_people=[NEW_PLAYER])
    code = approval_code(plan)

    first, second = build_file(plan, code, TODAY), build_file(plan, code, TODAY)

    assert first.changes.changes != second.changes.changes
    assert approval_code(plan) == code


def test_a_file_is_only_built_for_the_plan_that_was_approved(plan_for):
    shown = plan_for(edits=[by_hand(100, finishing=3)])
    other = plan_for(edits=[by_hand(100, finishing=4)])

    with pytest.raises(RequestError, match="approved"):
        build_file(other, approval_code(shown), TODAY)


def test_the_same_request_has_the_same_code_each_time(plan_for):
    request = {"edits": [by_hand(100, finishing=3)], "new_people": [NEW_PLAYER]}

    assert approval_code(plan_for(**request)) == approval_code(plan_for(**request))


def test_any_difference_in_what_is_written_changes_the_code(plan_for, started):
    other_player = NEW_PLAYER | {"set": NEW_PLAYER["set"] | {"Psna": "Other"}}
    plans = [
        plan_for(edits=[by_hand(100, finishing=3)]),
        plan_for(edits=[by_hand(100, finishing=4)]),
        plan_for(edits=[by_hand(101, finishing=3)]),
        plan_for(edits=[by_hand(100, ca=3)]),
        plan_for(new_people=[NEW_PLAYER]),
        plan_for(new_people=[other_player]),
        plan_for(start_from=str(started), edits=[by_hand(100, finishing=3)]),
    ]

    assert len({approval_code(plan) for plan in plans}) == len(plans)


def test_a_changed_starting_file_changes_the_code(plan_for, started):
    request = {"start_from": str(started), "edits": [by_hand(100, finishing=3)]}
    before = approval_code(plan_for(**request))
    other = synthetic.change_list(synthetic.capacity_change(1))
    started.write_bytes(
        synthetic.container(
            "Started",
            [("Started", ".dbc", other)],
            folder=("_data", [("details", ".aom", synthetic.details("Started"))]),
        )
    )

    assert approval_code(plan_for(**request)) != before
