import contextlib
import datetime
import random
import sqlite3

import pytest

import synthetic
from fictional_editor import write_definitions
from fm27_editor.change_list import ChangeList, Kind, Property
from fm27_editor.record_changes import EditError, NewIds
from fm27_editor.record_kinds import PLAYER, STAFF
from fm27_editor.record_rules import RecordRules
from fm27_editor.setting_changes import edit_record, new_record

BASICS = {
    "Pfna": "Testy",
    "Psna": "McTestface",
    "birth_date": datetime.date(2008, 4, 25),
    "nation_uid": 9001,
}


@pytest.fixture
def editor(tmp_path):
    return write_definitions(tmp_path)


def lookup():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE nation(uid INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("CREATE TABLE club(uid INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("INSERT INTO nation VALUES (9001, 'Testland')")
    connection.execute("INSERT INTO club VALUES (9101, 'Test Town')")
    return contextlib.closing(connection)


def make(editor, kind=PLAYER, **values):
    return create(editor, kind, BASICS | values)


def create(editor, kind, values):
    with lookup() as database:
        settings = RecordRules(editor, database).new_record_settings(kind, values)
        return new_record(kind, settings, NewIds(ChangeList(), random.Random(1)))


def tagged(change):
    return {item.tag: item for item in change}


def values_by_code(changes):
    return {tagged(change)["prty"].value: tagged(change)["nwvl"] for change in changes}


def test_the_person_is_added_before_its_fields_are_set(editor):
    added, *fields = make(editor)

    assert tagged(added)["prty"].value == "ADDR"
    assert [tagged(change)["prty"].value for change in fields] == ["Pfna", "Psna", "Pdob", "Pnti"]


def test_an_existing_person_is_addressed_by_its_unique_id_twice(editor):
    with lookup() as database:
        settings = RecordRules(editor, database).settings(PLAYER, {"finishing": 17})
        changes = edit_record(PLAYER, 776, settings, NewIds(ChangeList(), random.Random(1)))

    (change,) = changes
    assert tagged(change)["duni"].value == b"\x08\x03\x00\x00" * 2
    assert tagged(change)["prty"].value == "PDfn"
    assert tagged(change)["nwvl"].value == "17"


def test_an_existing_person_needs_no_name_or_birth_date(editor):
    with lookup() as database:
        (setting,) = RecordRules(editor, database).settings(PLAYER, {"ca": 99})

    assert (setting.field.code, setting.value) == ("PCAB", 99)


def test_every_field_is_addressed_to_the_new_person(editor):
    added, *fields = make(editor)

    described = {item.tag: item.value for item in tagged(added)["nwvl"].value}
    assert {tagged(change)["duni"].value for change in fields} == {described["duni"]}
    assert {tagged(change)["dtty"].value for change in fields} == {b"\x01"}


@pytest.mark.parametrize(("kind", "code"), [(PLAYER, 2), (STAFF, 1)])
def test_the_record_type_says_what_kind_of_person_it_is(editor, kind, code):
    added, *_ = make(editor, kind)

    described = {item.tag: item.value for item in tagged(added)["nwvl"].value}
    assert described["dcty"] == "\x00\x00\x00" + chr(code)


def test_facts_are_given_by_the_names_the_lookup_uses(editor):
    values = values_by_code(make(editor, ca=120, finishing=17))

    assert values["PCAB"] == Property("nwvl", Kind.INT8, b"\x78")
    assert values["PDfn"] == Property("nwvl", Kind.TEXT, "17")


def test_ability_of_staff_has_its_own_field(editor):
    assert values_by_code(make(editor, STAFF, ca=120))["Ncra"].value == b"\x78"


def test_fields_the_lookup_does_not_name_are_given_by_code(editor):
    assert values_by_code(make(editor, Phes=182))["Phes"].value == (182).to_bytes(2, "little")


@pytest.mark.parametrize("name", list(BASICS))
def test_a_person_needs_a_name_a_birth_date_and_a_nation(editor, name):
    values = {key: value for key, value in BASICS.items() if key != name}

    with pytest.raises(EditError, match="needs"):
        create(editor, PLAYER, values)


def test_an_editor_without_a_required_field_is_reported(tmp_path):
    first_name = synthetic.field_definition("Pfna", "First Name", "string")
    editor = write_definitions(tmp_path, synthetic.definition_file("pers", first_name))

    with pytest.raises(EditError, match="Pdob"):
        create(editor, PLAYER, {"Pfna": "Testy"})


@pytest.mark.parametrize("name", ["nation_uid", "club_uid"])
def test_a_nation_or_club_that_does_not_exist_is_refused(editor, name):
    with pytest.raises(EditError, match="4242"):
        make(editor, **{name: 4242})


def test_a_club_that_exists_is_set(editor):
    assert "Pcti" in values_by_code(make(editor, club_uid=9101))


def test_a_record_the_lookup_cannot_confirm_is_refused(editor):
    with pytest.raises(EditError, match="city"):
        make(editor, Pcbi=5)


@pytest.mark.parametrize("pa", [-8, -95, 0, 150])
def test_a_potential_may_be_a_number_or_one_of_the_editors_ranges(editor, pa):
    assert "PPAB" in values_by_code(make(editor, pa=pa))


def test_a_negative_potential_that_is_no_range_is_refused(editor):
    with pytest.raises(EditError, match="-50"):
        make(editor, pa=-50)


def test_an_unknown_field_is_refused(editor):
    with pytest.raises(EditError, match="sprint"):
        make(editor, sprint=5)


def test_a_field_given_by_name_and_by_code_is_refused(editor):
    with pytest.raises(EditError, match="PDfn"):
        make(editor, finishing=17, PDfn=3)


def test_a_player_field_is_refused_for_staff(editor):
    with pytest.raises(EditError, match="finishing"):
        make(editor, STAFF, finishing=17)


@pytest.mark.parametrize("code", ["Ptyp", "Page", "PPAR"])
def test_what_the_editor_works_out_itself_cannot_be_set(editor, code):
    with pytest.raises(EditError, match=code):
        make(editor, **{code: 1})
