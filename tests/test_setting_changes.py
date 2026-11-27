import contextlib
import datetime
import random
import sqlite3
import struct

import pytest

import synthetic
from fictional_editor import write_definitions
from fm27_editor.change_list import ChangeList, Kind, Property
from fm27_editor.record_changes import EditError, NewIds
from fm27_editor.record_kinds import CLUB, COMPETITION, PLAYER, STAFF
from fm27_editor.record_rules import ListItems, NewReference, RecordRules
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
    names = {
        "nation": 9001,
        "club": 9101,
        "competition": 9201,
        "city": 9301,
        "stadium": 9401,
        "language": 8,
    }
    for table, uid in names.items():
        connection.execute(f"CREATE TABLE {table}(uid INTEGER PRIMARY KEY, name TEXT)")
        connection.execute(f"INSERT INTO {table} VALUES ({uid}, 'Test {table}')")
    return contextlib.closing(connection)


def make(editor, kind=PLAYER, **values):
    return create(editor, kind, BASICS | values)


def create(editor, kind, values, new=None):
    with lookup() as database:
        settings = RecordRules(editor, database).new_record_settings(kind, values, new or {})
    ids = NewIds(ChangeList(), random.Random(1))
    records = {name: ids.record() for name in new or {}}
    return new_record(kind, ids.record(), settings, records, ids)


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
        changes = edit_record(PLAYER, 776, settings, {}, NewIds(ChangeList(), random.Random(1)))

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


@pytest.mark.parametrize("name", ["nation_uid", "club_uid", "dfln"])
def test_a_nation_club_or_language_that_does_not_exist_is_refused(editor, name):
    with pytest.raises(EditError, match="4242"):
        make(editor, **{name: 4242})


def test_a_club_that_exists_is_set(editor):
    assert "Pcti" in values_by_code(make(editor, club_uid=9101))


def test_a_city_that_exists_is_set(editor):
    assert "Pcbi" in values_by_code(make(editor, Pcbi=9301))


def test_a_language_that_exists_is_set(editor):
    reference = values_by_code(make(editor, dfln=8))["dfln"].value

    assert (reference[1].tag, reference[1].value) == ("lang", struct.pack("<II", 8, 8))


@pytest.mark.parametrize("points_to", ["continent", "moon"])
def test_a_record_the_lookup_cannot_confirm_is_refused(tmp_path, points_to):
    field = synthetic.field_definition("Plng", "Tongue", *synthetic.reference(points_to))
    editor = write_definitions(tmp_path, synthetic.definition_file("pers", field))

    with lookup() as database, pytest.raises(EditError, match=points_to):
        RecordRules(editor, database).settings(PLAYER, {"Plng": 5})


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


# --- clubs and competitions ----------------------------------------------------------------

CLUB_BASICS = {"name": "Test Rovers", "short_name": "Rovers", "nation_uid": 9001}
COMPETITION_BASICS = {"name": "Test League", "short_name": "League", "nation_uid": 9001, "dbty": 0}


@pytest.mark.parametrize(
    ("kind", "basics", "table", "name"),
    [(CLUB, CLUB_BASICS, 3, "Cnam"), (COMPETITION, COMPETITION_BASICS, 25, "cnam")],
    ids=["club", "competition"],
)
def test_clubs_and_competitions_are_added_to_their_own_table(editor, kind, basics, table, name):
    added, *fields = create(editor, kind, basics)

    described = {item.tag: item.value for item in tagged(added)["nwvl"].value}
    assert (described["dtty"], described["dcty"]) == (bytes([table]), b"\x00")
    assert {tagged(change)["dtty"].value for change in fields} == {bytes([table])}
    assert {tagged(change)["duni"].value for change in fields} == {described["duni"]}
    assert values_by_code(fields)[name].value == basics["name"]


@pytest.mark.parametrize(
    ("kind", "basics"), [(CLUB, CLUB_BASICS), (COMPETITION, COMPETITION_BASICS)]
)
def test_clubs_and_competitions_need_every_basic(editor, kind, basics):
    for missing in basics:
        values = {name: value for name, value in basics.items() if name != missing}
        with pytest.raises(EditError, match="needs"):
            create(editor, kind, values)


def test_a_club_can_play_in_a_competition_that_is_new_as_well(editor):
    values = CLUB_BASICS | {"division_uid": "@D1"}

    added, *fields = create(editor, CLUB, values, {"D1": COMPETITION})

    record = NewIds(ChangeList(), random.Random(1)).record()
    (reference, number) = values_by_code(fields)["Cdvi"].value[1:]
    assert (reference.tag, reference.value) == ("comp", record)
    assert int.from_bytes(number.value, "little") == int.from_bytes(record[:4], "little")


def test_a_reference_to_a_new_record_keeps_its_name(editor):
    with lookup() as database:
        (setting,) = RecordRules(editor, database).settings(
            CLUB, {"division_uid": "@D1"}, {"D1": COMPETITION}
        )

    assert setting.value == NewReference("D1")


@pytest.mark.parametrize(
    ("values", "complaint"),
    [
        ({"division_uid": "@D2"}, "@D2"),
        ({"division_uid": "@Rovers"}, "club"),
        ({"division_uid": "D1"}, "'D1'"),
        ({"division_uid": 4242}, "4242"),
        ({"stadium_uid": 4242}, "4242"),
    ],
)
def test_a_reference_must_be_to_a_record_of_the_right_kind(editor, values, complaint):
    with pytest.raises(EditError, match=complaint):
        create(editor, CLUB, CLUB_BASICS | values, {"D1": COMPETITION, "Rovers": CLUB})


@pytest.mark.parametrize("code", ["dbnm", "Snam", "CHAa"])
def test_what_is_not_a_fact_of_the_club_itself_cannot_be_set(editor, code):
    with pytest.raises(EditError, match=code):
        create(editor, CLUB, CLUB_BASICS | {code: 1})


def edited(editor, values, uid=776):
    with lookup() as database:
        settings = RecordRules(editor, database).settings(PLAYER, values)
    return edit_record(PLAYER, uid, settings, {}, NewIds(ChangeList(), random.Random(1)))


def list_steps(changes):
    """What each change does to a list: the part it sets, or nwvl to add or clear."""
    return [
        (tagged(change)["prty"].value, tagged(change)["nwvl"].value[0].value) for change in changes
    ]


@pytest.mark.parametrize(
    "items", [[{"nati": 9001, "ntin": 85}], '[{"nati": 9001, "ntin": 85}]'], ids=["list", "text"]
)
def test_items_of_a_list_are_given_by_the_codes_of_their_parts(editor, items):
    with lookup() as database:
        (setting,) = RecordRules(editor, database).settings(PLAYER, {"PNRs": items})

    assert setting.value == ListItems(({"nati": 9001, "ntin": 85},))


def test_items_are_added_to_what_a_person_has_one_part_at_a_time(editor):
    changes = edited(editor, {"PNRs": [{"nati": 9001, "ntin": 85}]})

    assert {tagged(change)["duni"].value for change in changes} == {b"\x08\x03\x00\x00" * 2}
    assert list_steps(changes) == [("PNRs", "nwvl"), ("PNRs", "ntin"), ("PNRs", "nati")]


def test_a_replaced_list_is_cleared_before_its_items_are_added(editor):
    changes = edited(editor, {"PNRs": {"replace": [{"nati": 9001}]}})

    assert list_steps(changes) == [("PNRs", "nwvl"), ("PNRs", "nwvl"), ("PNRs", "nati")]
    assert tagged(changes[0])["nwvl"].value[-1] == Property("lsop", Kind.INT8, b"\x03")


@pytest.mark.parametrize("replaced", [{"replace": []}, '{"replace": []}'], ids=["list", "text"])
def test_a_list_replaced_by_no_items_is_cleared(editor, replaced):
    (change,) = edited(editor, {"PNRs": replaced})

    assert tagged(change)["nwvl"].value[-1] == Property("lsop", Kind.INT8, b"\x03")


def test_a_language_is_added_with_how_well_it_is_spoken(editor):
    changes = edited(editor, {"PElg": [{"lang": 8, "prof": 5}]})

    assert list_steps(changes) == [("PElg", "nwvl"), ("PElg", "lang"), ("PElg", "prof")]


def test_a_new_person_is_given_items_after_being_added(editor):
    added, *fields = make(editor, PNRs=[{"nati": 9001}])

    assert tagged(added)["prty"].value == "ADDR"
    assert list_steps(fields[-2:]) == [("PNRs", "nwvl"), ("PNRs", "nati")]


def test_an_item_can_refer_to_a_club_that_is_new_as_well(editor):
    values = BASICS | {"Pfvc": [{"club": "@Rovers", "rrea": 1}]}

    *_, club_set = create(editor, PLAYER, values, {"Rovers": CLUB})

    record = NewIds(ChangeList(), random.Random(1)).record()
    reference = tagged(club_set)["nwvl"].value[1].value[1]
    assert (reference.tag, reference.value) == ("Cclu", record)


def test_an_item_can_refer_to_a_person_that_is_new_as_well(editor):
    values = BASICS | {"Pfvp": [{"pers": "@Mentor", "rrea": 1}]}

    *_, person_set = create(editor, PLAYER, values, {"Mentor": STAFF})

    reference = tagged(person_set)["nwvl"].value[1].value[1]
    assert reference.tag == "Pers"


@pytest.mark.parametrize("team", [9101, 9001], ids=["club", "nation"])
def test_a_team_in_a_list_can_be_a_club_or_a_national_team(editor, team):
    _, team_set, _ = edited(editor, {"Pdcn": [{"Ttea": team, "days": 900}]})

    assert tagged(team_set)["nwvl"].value[1].value[1].value == struct.pack("<II", team, team)


@pytest.mark.parametrize(
    ("values", "complaint"),
    [
        ({"PNRs": [{"ntin": 80}]}, "more than a new item"),
        ({"Pdcn": [{"days": 1, "bfat": False}]}, "more than a new item"),
        ({"Pdcn": [{"Ttea": 4242}]}, "4242"),
        ({"PNRs": [{"nati": 4242}]}, "4242"),
        ({"PNRs": [{"ntin": 81}]}, "ntin"),
        ({"PNRs": [{"moon": 1}]}, "moon"),
        ({"PNRs": []}, "no items to add"),
        ({"PNRs": {"add": []}}, "replace"),
        ({"PNRs": {"replace": [], "add": []}}, "replace"),
        ({"PNRs": {"replace": 9001}}, "list"),
        ({"PElg": [{"lang": 8, "proe": 3}]}, "no proe, only lang, prof"),
        ({"PElg": [{"lang": 4242}]}, "4242"),
        ({"PElg": [{"prof": 5}]}, "an item needs lang"),
        ({"PNRs": [{"nati": None}]}, "nati"),
        ({"PNRs": [{}]}, "an item"),
        ({"PNRs": [9001]}, "an item"),
        ({"PNRs": 9001}, "list"),
        ({"PNRs": "[{"}, "list"),
        ({"PNRs": '[{"nati": 9001, "nati": 9002}]'}, "Second Nations .*nati is given twice"),
        ({"Pfvc": [{"club": 4242}]}, "4242"),
        ({"Pfvc": [{"leve": 101}]}, "leve"),
        ({"Pbnl": []}, "Pbnl"),
    ],
)
def test_items_the_editor_would_not_accept_are_refused(editor, values, complaint):
    with pytest.raises(EditError, match=complaint):
        edited(editor, values)
