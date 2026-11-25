import contextlib
import datetime
import random
import sqlite3

import pytest

import synthetic
from fm27_editor.change_list import ChangeList, Kind, Property
from fm27_editor.new_person import new_person, person_fields
from fm27_editor.people import PersonKind
from fm27_editor.record_changes import EditError, NewIds

PERSON = synthetic.definition_file(
    "pers",
    synthetic.field_definition("Ptyp", "Person Type", "enum"),
    synthetic.field_definition("Pfna", "First Name", "string"),
    synthetic.field_definition("Psna", "Second Name", "string"),
    synthetic.field_definition("Pdob", "Date Of Birth", "date"),
    synthetic.field_definition(
        "Pnti",
        "Nation",
        "database_record_unique_id",
        '<flags id="database_table_type" value="nation" />',
    ),
    synthetic.field_definition(
        "Pcti",
        "Club",
        "database_record_unique_id",
        '<flags id="database_table_type" value="team" />',
    ),
    synthetic.field_definition(
        "Pcbi",
        "City Of Birth",
        "database_record_unique_id",
        '<flags id="database_table_type" value="city" />',
    ),
    synthetic.field_definition("Page", "Age", "integer", synthetic.number_range(0, 99)),
    synthetic.field_definition("Phes", "Height", "integer", synthetic.number_range(0, 210)),
)
PLAYER = synthetic.definition_file(
    "play",
    synthetic.field_definition(
        "PCAB", "Current Ability", "integer", synthetic.number_range(0, 200)
    ),
    synthetic.field_definition(
        "PPAB", "Potential Ability", "integer", synthetic.number_range(-100, 200)
    ),
    synthetic.field_definition(
        "PPAR",
        "Potential Ability Range",
        "enum",
        '<list id="enum_values"><record enum="-8" /><record enum="-95" /></list>',
    ),
    synthetic.field_definition("PDfn", "Finishing", "attribute"),
)
NON_PLAYER = synthetic.definition_file(
    "nnpl",
    synthetic.field_definition(
        "Ncra", "Current Ability", "integer", synthetic.number_range(0, 200)
    ),
)
BASICS = {
    "Pfna": "Testy",
    "Psna": "McTestface",
    "birth_date": datetime.date(2008, 4, 25),
    "nation_uid": 9001,
}


@pytest.fixture
def editor(tmp_path):
    path = tmp_path / "shared" / "data" / "editor.fmf"
    path.parent.mkdir(parents=True)
    files = {"person": PERSON, "player": PLAYER, "non player": NON_PLAYER}
    path.write_bytes(synthetic.definitions_container(files, synthetic.enum_file()))
    return tmp_path


def lookup():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE nation(uid INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("CREATE TABLE club(uid INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("INSERT INTO nation VALUES (9001, 'Testland')")
    connection.execute("INSERT INTO club VALUES (9101, 'Test Town')")
    return contextlib.closing(connection)


def make(editor, kind=PersonKind.PLAYER, **values):
    return create(kind, BASICS | values, person_fields(editor, kind))


def create(kind, values, fields):
    with lookup() as database:
        return new_person(kind, values, fields, NewIds(ChangeList(), random.Random(1)), database)


def tagged(change):
    return {item.tag: item for item in change}


def values_by_code(changes):
    return {tagged(change)["prty"].value: tagged(change)["nwvl"] for change in changes}


def test_the_person_is_added_before_its_fields_are_set(editor):
    added, *fields = make(editor)

    assert tagged(added)["prty"].value == "ADDR"
    assert [tagged(change)["prty"].value for change in fields] == ["Pfna", "Psna", "Pdob", "Pnti"]


def test_every_field_is_addressed_to_the_new_person(editor):
    added, *fields = make(editor)

    described = {item.tag: item.value for item in tagged(added)["nwvl"].value}
    assert {tagged(change)["duni"].value for change in fields} == {described["duni"]}
    assert {tagged(change)["dtty"].value for change in fields} == {b"\x01"}


@pytest.mark.parametrize(("kind", "code"), [(PersonKind.PLAYER, 2), (PersonKind.STAFF, 1)])
def test_the_record_type_says_what_kind_of_person_it_is(editor, kind, code):
    added, *_ = make(editor, kind)

    described = {item.tag: item.value for item in tagged(added)["nwvl"].value}
    assert described["dcty"] == "\x00\x00\x00" + chr(code)


def test_facts_are_given_by_the_names_the_lookup_uses(editor):
    values = values_by_code(make(editor, ca=120, finishing=17))

    assert values["PCAB"] == Property("nwvl", Kind.INT8, b"\x78")
    assert values["PDfn"] == Property("nwvl", Kind.TEXT, "17")


def test_ability_of_staff_has_its_own_field(editor):
    assert values_by_code(make(editor, PersonKind.STAFF, ca=120))["Ncra"].value == b"\x78"


def test_fields_the_lookup_does_not_name_are_given_by_code(editor):
    assert values_by_code(make(editor, Phes=182))["Phes"].value == (182).to_bytes(2, "little")


@pytest.mark.parametrize("name", list(BASICS))
def test_a_person_needs_a_name_a_birth_date_and_a_nation(editor, name):
    values = {key: value for key, value in BASICS.items() if key != name}

    with pytest.raises(EditError, match="needs"):
        create(PersonKind.PLAYER, values, person_fields(editor, PersonKind.PLAYER))


def test_an_editor_without_a_required_field_is_reported(editor):
    fields = person_fields(editor, PersonKind.PLAYER)
    del fields["Pdob"]
    values = {key: value for key, value in BASICS.items() if key != "birth_date"}

    with pytest.raises(EditError, match="Pdob"):
        create(PersonKind.PLAYER, values, fields)


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
        make(editor, PersonKind.STAFF, finishing=17)


@pytest.mark.parametrize("code", ["Ptyp", "Page"])
def test_what_the_editor_works_out_itself_cannot_be_set(editor, code):
    with pytest.raises(EditError, match=code):
        make(editor, **{code: 1})


@pytest.mark.parametrize("kind", [PersonKind.BOTH, PersonKind.OFFICIAL, PersonKind.RETIRED])
def test_kinds_of_people_not_seen_created_are_refused(editor, kind):
    with pytest.raises(EditError, match="player or staff"):
        person_fields(editor, kind)
