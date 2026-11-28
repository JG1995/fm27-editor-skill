import datetime
import re

import pytest

import synthetic
from fictional_editor import PEOPLE, STAFF_KIND, write_editor
from fm27_editor.base_database import open_database
from fm27_editor.binary import FormatError
from fm27_editor.editor_file import save_editor_file
from fm27_editor.plan import approval_code, build_file, make_plan
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
    yield lambda **request: make_plan(request, editor, lookup)
    lookup.close()


def by_hand(uid, of="people", **values):
    return {"of": of, "uid": uid, "set": values}


def asked(query, of="people"):
    return {"of": of, "query": query}


def edited(plan):
    return [(e.record.uid, e.setting.field.code, e.old, e.setting.value) for e in plan.edits]


def test_a_query_gives_each_person_the_values_of_its_columns(plan_for):
    query = "SELECT uid, min(pa + 5, 144) AS pa, 18 AS finishing FROM people WHERE kind = 'player'"

    plan = plan_for(edits=[asked(query)])

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
        ({"of": "people", "uid": 100, "set": 5}, "set"),
        ({"of": "moons", "uid": 100, "set": {}}, "moons"),
        ({"of": ["people"], "uid": 100, "set": {}}, "people"),
        ({"uid": 100, "set": {"finishing": 3}}, "of"),
        (asked(5), "query"),
        (asked("SELECT uid, 5 AS pa FROM people; SELECT 1"), "one statement"),
        (by_hand(100), "nothing"),
        (by_hand(100, sprint=3), "sprint"),
        (by_hand(100, finishing=21), "PDfn"),
        (by_hand(100, finishing=[3]), "PDfn"),
        (by_hand(9101, of="clubs", gender="both"), "PLgn"),
        (by_hand(100, birth_date="soon"), "soon"),
        (by_hand(103, finishing=3), "both"),
        ({"of": "people", "uid": 100}, "query"),
        ({"of": "people", "query": "SELECT 1", "uid": 100, "set": {}}, "query"),
        (asked("SELECT uid FROM people"), "nothing"),
        (asked("SELECT pa FROM people"), "uid"),
        (asked("SELECT uid, pa, ca AS pa FROM people"), "pa"),
        (asked("SELECT uid, pa * 1.5 AS pa FROM people"), "whole number"),
        (asked("SELECT uid, NULL AS pa FROM people"), "no value for pa"),
        (asked("SELECT uid, pa FROM nowhere"), "nowhere"),
        (asked("DELETE FROM person"), "readonly"),
        (asked("SELECT uid, 5 AS pa FROM people WHERE 0"), "finds nothing"),
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
        {"new": [{"kind": "player"}]},
        {"new": [{"kind": "player", "set": 5}]},
        {"new": [{"kind": "wizard", "set": {}}]},
        {"new": [NEW_PLAYER | {"extra": 1}]},
        {"new": [NEW_PLAYER | {"as": 5}]},
        {"new": [NEW_PLAYER | {"as": "two words"}]},
        {"new": [NEW_PLAYER | {"as": "One"}, NEW_PLAYER | {"as": "One"}]},
        {"new": [NEW_PLAYER | {"kind": ["player"]}]},
        {"new_people": [NEW_PLAYER]},
    ],
)
def test_a_request_that_is_empty_or_misspelt_is_refused(plan_for, request_):
    with pytest.raises(FormatError):
        plan_for(**request_)


def test_new_people_are_planned_with_their_settings(plan_for):
    (addition,) = plan_for(new=[NEW_PLAYER]).additions

    assert addition.kind.name == "player"
    assert [s.field.code for s in addition.settings] == ["Pfna", "Psna", "Pdob", "Pnti"]


# --- clubs and competitions ---------------------------------------------------------------

LEAGUE = {
    "kind": "competition",
    "as": "D1",
    "set": {"name": "Test League", "short_name": "League", "nation_uid": 9001, "dbty": 0},
}
ROVERS = {
    "kind": "club",
    "set": {
        "name": "Test Rovers",
        "short_name": "Rovers",
        "nation_uid": 9001,
        "division_uid": "@D1",
    },
}


def test_the_gender_of_a_club_is_given_and_compared_the_way_the_lookup_says_it(plan_for):
    edits = [by_hand(uid, of="clubs", gender="female") for uid in (9101, 9103)]

    plan = plan_for(edits=edits)

    assert edited(plan) == [(9101, "PLgn", "male", 1)]
    assert plan.already_so == 1


def test_clubs_are_edited_as_clubs_also_when_a_person_has_the_same_unique_id(plan_for):
    plan = plan_for(edits=[by_hand(9101, of="clubs", reputation=6_000)])

    assert edited(plan) == [(9101, "Crep", 5_000, 6_000)]
    assert plan.edits[0].record.kind.name == "club"


def test_competitions_are_edited_by_the_lookups_names(plan_for):
    plan = plan_for(edits=[by_hand(9203, of="competitions", level=3, parent_uid=9202)])

    assert edited(plan) == [(9203, "levl", 2, 3), (9203, "cpcm", 9201, 9202)]


def test_awards_are_edited_by_the_lookups_names(plan_for):
    values = {"previous_winner": 1, "AWxa": 21, "competition_uid": 9203}

    plan = plan_for(edits=[by_hand(9501, of="awards", **values)])

    assert edited(plan) == [
        (9501, "AWap", 3, 1),
        (9501, "AWxa", None, 21),
        (9501, "AWmi", 9201, 9203),
    ]


def test_stadiums_are_edited_by_the_lookups_names_and_their_codes(plan_for):
    plan = plan_for(edits=[by_hand(9401, of="stadiums", name="New Park", Scpy=30_000)])

    assert edited(plan) == [(9401, "Snam", "Test Park", "New Park"), (9401, "Scpy", None, 30_000)]


def test_nations_are_edited_by_the_lookups_names_and_their_codes(plan_for):
    plan = plan_for(edits=[by_hand(9002, of="nations", name="Norway", Necf=15, Nnsi=9401)])

    assert edited(plan) == [
        (9002, "Nnam", "Norwegia", "Norway"),
        (9002, "Necf", None, 15),
        (9002, "Nnsi", None, 9401),
    ]


def test_cities_are_edited_by_the_lookups_names_and_their_codes(plan_for):
    plan = plan_for(edits=[by_hand(9301, of="cities", name="Testbury", nation_uid=9002, Catt=12)])

    assert edited(plan) == [
        (9301, "Cnam", "Testby", "Testbury"),
        (9301, "Cnti", 9001, 9002),
        (9301, "Catt", None, 12),
    ]


def test_continents_injuries_and_weather_are_edited_by_name_and_code(plan_for):
    plan = plan_for(
        edits=[
            by_hand(3, of="continents", name="Europe", Crgs=0.85),
            by_hand(1, of="injuries", Iocr=1.5, Imip=0),
            by_hand(115052, of="weathers", name="Testish Upland", w0p0=40),
        ]
    )

    assert edited(plan) == [
        (3, "Cnam", "Europia", "Europe"),
        (3, "Crgs", None, 0.85),
        (1, "Iocr", None, 1.5),
        (1, "Imip", None, 0),
        (115052, "wnam", "Testish Inland", "Testish Upland"),
        (115052, "w0p0", None, 40),
    ]


def test_media_sources_derbies_and_stage_names_are_edited_by_name_and_code(plan_for):
    plan = plan_for(
        edits=[
            by_hand(18, of="media_sources", name="Testby Evening Echo", Mcyi=9302),
            by_hand(50, of="derbies", short_name="Derby Day", club_2_uid=9104, D1tw=12),
            by_hand(3, of="stage_names", name="Grand Final", SNpn="Grand Finals"),
        ]
    )

    assert edited(plan) == [
        (18, "Mnam", "Testby Echo", "Testby Evening Echo"),
        (18, "Mcyi", None, 9302),
        (50, "Dsnm", "Derby", "Derby Day"),
        (50, "Dtm2", 9102, 9104),
        (50, "D1tw", None, 12),
        (3, "SNna", "Final", "Grand Final"),
        (3, "SNpn", None, "Grand Finals"),
    ]


def test_local_regions_and_agreements_are_edited_by_name(plan_for):
    plan = plan_for(
        edits=[
            by_hand(9601, of="local_regions", name="Test County", nation_uid=9002),
            by_hand(9602, of="local_regions", population=12_000),
            by_hand(4, of="agreements", short_name="TA"),
        ]
    )

    assert edited(plan) == [
        (9601, "Lnam", "Testshire", "Test County"),
        (9601, "Lnat", 9001, 9002),
        (9602, "Lpop", None, 12_000),
        (4, "AGsn", "", "TA"),
    ]


def test_the_weather_of_a_local_region_cannot_be_set(plan_for):
    """No file shows a field that refers to a weather."""
    with pytest.raises(FormatError, match="Lwea"):
        plan_for(edits=[by_hand(9601, of="local_regions", Lwea=1)])


def test_how_often_an_injury_happens_is_stored_as_a_real_file_stores_it(plan_for):
    plan = plan_for(edits=[by_hand(1, of="injuries", Iocr=1.5)])

    (change,) = build_file(plan, approval_code(plan), TODAY).changes.changes

    assert [(item.tag, item.kind.name, item.value) for item in change[:4]] == [
        ("dtty", "INT8", b"\x06"),
        ("duni", "ID", bytes.fromhex("0100000001000000")),
        ("prty", "CODE", "Iocr"),
        ("nwvl", "REAL", bytes.fromhex("0000c03f")),
    ]


# Nations are table 9, which real files use, though the Editor's list calls it National Team.
@pytest.mark.parametrize(
    ("of", "uid", "code", "value", "table"),
    [
        ("stadiums", 9401, "Scti", 9302, 21),
        ("nations", 9002, "Necf", 15, 9),
        ("cities", 9301, "Catt", 12, 2),
        ("continents", 3, "Crgs", 0.85, 5),
        ("injuries", 6, "Imip", 50, 6),
        ("weathers", 1, "w0p0", 40, 27),
        ("media_sources", 19, "Mnam", "The Example Post", 7),
        ("derbies", 50, "D1tw", 12, 18),
        ("stage_names", 1, "SNpn", "Replays", 23),
        ("local_regions", 9601, "Lpop", 10, 47),
        ("agreements", 1, "AGna", "Union of Examples", 56),
    ],
)
def test_a_record_is_changed_in_its_own_table(plan_for, of, uid, code, value, table):
    plan = plan_for(edits=[by_hand(uid, of=of, **{code: value})])

    (change,) = build_file(plan, approval_code(plan), TODAY).changes.changes

    assert [(item.tag, item.value) for item in change[:3]] == [
        ("dtty", bytes([table])),
        ("duni", uid.to_bytes(4, "little") * 2),
        ("prty", code),
    ]


@pytest.mark.parametrize(
    "kind",
    [
        *("nation", "continent", "injury", "weather"),
        *("media_source", "derby", "stage_name", "local_region", "agreement"),
    ],
)
def test_a_kind_that_no_file_adds_cannot_be_made(plan_for, kind):
    with pytest.raises(FormatError, match=f"a new {kind} cannot be made"):
        plan_for(new=[{"kind": kind, "set": {"name": "Example"}}])


CITY = {"kind": "city", "as": "C", "set": {"name": "Testville", "nation_uid": 9001}}
STADIUM = {"kind": "stadium", "as": "S", "set": {"name": "Test Ground", "city_uid": "@C"}}


def added_tables(file):
    """The table of each record that the file adds, in order."""
    return [
        next(i for i in change if i.tag == "nwvl").value[1].value[0]
        for change in file.changes.changes
        if any(i.value == "ADDR" for i in change)
    ]


def new_id(file, index):
    return next(i.value for i in file.changes.changes[index] if i.tag == "nwvl")[-1].value


def test_a_new_stadium_can_be_in_a_new_city_and_a_new_club_can_play_there(plan_for):
    rovers = ROVERS | {"set": ROVERS["set"] | {"stadium_uid": "@S"}}

    plan = plan_for(new=[LEAGUE, CITY, STADIUM, rovers])
    file = build_file(plan, approval_code(plan), TODAY)

    assert added_tables(file) == [25, 2, 21, 3]
    adds = [index for index, code in enumerate(codes(file)) if code == "ADDR"]
    _, city, stadium, _ = (new_id(file, index) for index in adds)
    references = {
        code: next(i for i in change if i.tag == "nwvl").value[1].value
        for change in file.changes.changes
        if (code := next(i.value for i in change if i.tag == "prty")) in ("Scti", "Csti")
    }
    assert references == {"Scti": city, "Csti": stadium}


@pytest.mark.parametrize(
    ("new", "missing"),
    [
        ({"kind": "stadium", "set": {"name": "Test Ground"}}, "City (Scti)"),
        ({"kind": "city", "set": {"name": "Testville"}}, "Nation (Cnti)"),
    ],
)
def test_a_new_stadium_needs_a_city_and_a_new_city_a_nation(plan_for, new, missing):
    with pytest.raises(FormatError, match=re.escape(missing)):
        plan_for(new=[new])


def test_an_award_cannot_be_made(plan_for):
    with pytest.raises(FormatError, match="a new award cannot be made"):
        plan_for(new=[{"kind": "award", "set": {"name": "Example Award"}}])


PAST = {"award_uid": 9501, "year": 2024, "places": [{"keep": 2}, {"keep": 1}]}


def test_past_winners_alone_are_a_request(plan_for):
    (edit,) = plan_for(award_history=[PAST]).histories

    assert (edit.award.uid, edit.award.name) == (9501, "Example Player of the Year")
    assert [new.year for _, new in edit.history.changed] == [2024]


def test_the_history_is_written_behind_the_settings(plan_for):
    edits = [by_hand(9501, of="awards", previous_winner=1)]
    plan = plan_for(edits=edits, award_history=[PAST])

    file = build_file(plan, approval_code(plan), TODAY)

    changes = [{part.tag: part for part in change} for change in file.changes.changes]
    assert [change["prty"].value for change in changes] == ["AWap", "AWsh"]
    assert [change["duni"].value for change in changes] == [b"\x1d\x25\x00\x00" * 2] * 2
    assert len(changes[1]["nwvl"].value) == 3


def test_past_winners_that_are_so_already_change_nothing(plan_for):
    so_already = {"award_uid": 9501, "year": 2023, "places": [{"keep": 1}]}

    with pytest.raises(RequestError, match="changes nothing"):
        plan_for(award_history=[so_already])


def test_the_code_covers_the_history(plan_for):
    other = PAST | {"places": [{"keep": 2}, {"keep": 1, "points": 8}]}

    codes = {approval_code(plan_for(award_history=[past])) for past in (PAST, other)}

    assert len(codes) == 2


def test_the_code_covers_the_items_of_a_list(plan_for):
    lists = (
        [{"nati": 9001}],
        [{"nati": 9002}],
        [{"nati": 9002, "ntin": 85}],
        {"replace": [{"nati": 9002}]},
        {"replace": []},
    )

    codes = {approval_code(plan_for(edits=[by_hand(100, PNRs=items)])) for items in lists}

    assert len(codes) == 5


def test_a_history_that_the_starting_file_changes_cannot_be_changed_again(plan_for, tmp_path):
    plan = plan_for(award_history=[PAST])
    path = tmp_path / "History.fmf"
    save_editor_file(build_file(plan, approval_code(plan), TODAY), path)
    other_award = {"award_uid": 9502, "year": 2025, "places": [{"name": "New Star"}]}

    so_already = {"award_uid": 9501, "year": 2023, "places": [{"keep": 1}]}
    plan = plan_for(start_from=str(path), award_history=[other_award, so_already])

    assert [edit.award.uid for edit in plan.histories] == [9502]
    with pytest.raises(RequestError, match="history of Example Player of the Year"):
        plan_for(start_from=str(path), award_history=[PAST])


@pytest.mark.parametrize(
    ("places", "complaint"),
    [
        ([{"name": "A", "points": 5}, {"name": "B", "points": 6}], "more points in 2024"),
        ([{"name": "A"}, {"name": "B"}, {"name": "A"}], "placed twice in 2024"),
        ([{"person_uid": 100}, {"person_uid": 100, "name": "Other Name"}], "placed twice in 2024"),
    ],
)
def test_places_that_look_wrong_are_pointed_out(plan_for, places, complaint):
    plan = plan_for(award_history=[PAST | {"places": places}])

    (warning,) = plan.warnings
    assert re.search(complaint, warning)


def test_places_without_points_are_not_compared(plan_for):
    places = [{"name": "A"}, {"name": "B", "points": 6}, {"name": "C", "points": 6}]

    assert plan_for(award_history=[PAST | {"places": places}]).warnings == []


def test_a_query_can_move_clubs_to_a_division(plan_for):
    plan = plan_for(edits=[asked("SELECT uid, 9203 AS division_uid FROM clubs", of="clubs")])

    assert [(uid, new) for uid, _, _, new in edited(plan)] == [
        (9101, 9203),
        (9103, 9203),
        (9104, 9203),
    ]
    assert plan.already_so == 1


def test_a_new_club_and_an_existing_one_can_play_in_a_new_competition(plan_for):
    query = "SELECT uid, '@D1' AS division_uid FROM clubs WHERE uid = 9102"
    plan = plan_for(new=[LEAGUE, ROVERS], edits=[asked(query, of="clubs")])

    file = build_file(plan, approval_code(plan), TODAY)

    league = next(i.value for i in file.changes.changes[0] if i.tag == "nwvl")[-1].value
    divisions = [
        next(i for i in change if i.tag == "nwvl").value[1].value
        for change in file.changes.changes
        if any(i.value == "Cdvi" for i in change)
    ]
    assert divisions == [league, league]


def test_a_new_record_is_named_before_it_is_referred_to(plan_for):
    with pytest.raises(FormatError, match="@D1"):
        plan_for(new=[ROVERS, LEAGUE])


def test_the_code_covers_which_new_record_is_meant(plan_for):
    second = LEAGUE | {"as": "D2"}
    to_second = ROVERS | {"set": ROVERS["set"] | {"division_uid": "@D2"}}

    plans = [plan_for(new=[LEAGUE, second, club]) for club in (ROVERS, to_second)]

    assert len({approval_code(plan) for plan in plans}) == 2


# --- nation rules -------------------------------------------------------------------------

NATION_RULES = {
    "nation": 9001,
    "season_update_day": {"day_of_month": 20, "month": "jun"},
    "start_date": "2026-08-01",
    "end_date": "2027-05-31",
    "league_comps": [
        {
            "competition": "@D1",
            "minimum_number_teams": 2,
            "maximum_number_teams": 2,
            "start_date": "2026-08-15",
            "end_date": "2027-05-15",
        }
    ],
}


def rules_for(competition):
    division = NATION_RULES["league_comps"][0] | {"competition": competition}
    return NATION_RULES | {"league_comps": [division]}


def test_rules_are_written_with_the_records_they_are_for(plan_for):
    plan = plan_for(new=[LEAGUE, ROVERS, ROVERS], nation_rules=NATION_RULES)

    file = build_file(plan, approval_code(plan), TODAY)

    league = next(i.value for i in file.changes.changes[0] if i.tag == "nwvl")[-1].value
    (rules,) = [item for item in file.changes.editor if item.tag == "rlgr"]
    (divisions,) = [item for item in rules.value if item.tag == "lgcs"]
    assert divisions.value[0].value[0].value[1].value == league
    assert plan.warnings == []


def test_rules_alone_are_a_request(plan_for):
    assert plan_for(nation_rules=rules_for(9201)).rules is not None


def test_the_code_covers_the_rules(plan_for):
    plans = [
        plan_for(new=[LEAGUE]),
        plan_for(new=[LEAGUE], nation_rules=NATION_RULES),
        plan_for(new=[LEAGUE], nation_rules=NATION_RULES | {"end_date": "2027-06-01"}),
    ]

    assert len({approval_code(plan) for plan in plans}) == 3


@pytest.mark.parametrize(
    ("clubs", "has"),
    [([], "no clubs"), ([ROVERS], "1 club"), ([ROVERS] * 3, "3 clubs")],
    ids=["none", "too few", "too many"],
)
def test_a_division_without_the_right_number_of_clubs_is_pointed_out(plan_for, clubs, has):
    (warning,) = plan_for(new=[LEAGUE, *clubs], nation_rules=NATION_RULES).warnings

    assert "@D1" in warning and has in warning and "needs 2" in warning


def test_clubs_that_are_moved_in_and_out_count(plan_for):
    """9101 is in 9201 and 9102 in 9203; one is moved in, the other out."""
    moves = [
        by_hand(9102, of="clubs", division_uid=9201),
        by_hand(9104, of="clubs", division_uid=9201),
        by_hand(9101, of="clubs", division_uid=9203),
    ]

    assert plan_for(edits=moves, nation_rules=rules_for(9201)).warnings == []


def test_womens_clubs_in_a_mens_division_are_pointed_out(plan_for):
    """9103 is a women's club."""
    moves = [by_hand(9102, of="clubs", division_uid="@D1")]
    women = [by_hand(9103, of="clubs", division_uid="@D1")]
    new_women = ROVERS | {"set": ROVERS["set"] | {"gender": "female"}}

    assert plan_for(new=[LEAGUE, ROVERS], edits=moves, nation_rules=NATION_RULES).warnings == []
    (moved,) = plan_for(new=[LEAGUE, ROVERS], edits=women, nation_rules=NATION_RULES).warnings
    (made,) = plan_for(new=[LEAGUE, new_women], edits=moves, nation_rules=NATION_RULES).warnings

    assert "1 women's club" in moved and "1 women's club" in made


def test_sub_divisions_hold_the_clubs_of_a_division(plan_for):
    rules = rules_for("@D1")
    rules["league_comps"][0]["child_competitions"] = [{"competition": "@D2"}]
    second = LEAGUE | {"as": "D2"}
    in_second = ROVERS | {"set": ROVERS["set"] | {"division_uid": "@D2"}}

    plan = plan_for(new=[LEAGUE, second, in_second, in_second], nation_rules=rules)

    assert plan.warnings == []


@pytest.mark.parametrize(
    ("request_", "complaint"),
    [
        ({"nation_rules": rules_for(9202)}, "women"),
        (
            {
                "new": [LEAGUE | {"set": LEAGUE["set"] | {"gender": "female"}}],
                "nation_rules": rules_for("@D1"),
            },
            "women",
        ),
        ({"nation_rules": rules_for(True)}, "True"),
        ({"nation_rules": rules_for(10**20)}, "100000000000000000000"),
        ({"nation_rules": rules_for("@D1")}, "@D1"),
        ({"new": [LEAGUE, ROVERS | {"as": "R"}], "nation_rules": rules_for("@R")}, "club"),
    ],
    ids=["existing", "new", "true", "huge", "unknown", "not a competition"],
)
def test_rules_that_cannot_be_written_are_refused(plan_for, request_, complaint):
    with pytest.raises(FormatError, match=complaint):
        plan_for(**request_)


def test_a_file_with_rules_cannot_be_started_from_for_other_rules(plan_for, tmp_path):
    plan = plan_for(nation_rules=rules_for(9201))
    path = tmp_path / "Rules.fmf"
    save_editor_file(build_file(plan, approval_code(plan), TODAY), path)

    with pytest.raises(FormatError, match="rules already"):
        plan_for(start_from=str(path), nation_rules=rules_for(9201))


def test_rules_that_replace_those_of_the_game_are_pointed_out(plan_for):
    (warning, *_) = plan_for(nation_rules=rules_for(9201) | {"nation": 9002}).warnings

    assert "Norwegia" in warning and "replace" in warning


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
    plan = plan_for(edits=[by_hand(100, finishing=3)], new=[NEW_PLAYER])

    file = build_file(plan, approval_code(plan), TODAY)

    assert codes(file) == ["ADDR", "Pfna", "Psna", "Pdob", "Pnti", "PDfn"]


def test_changes_are_added_behind_those_of_the_file_to_start_from(plan_for, started):
    plan = plan_for(start_from=str(started), edits=[by_hand(100, finishing=3)])

    assert codes(build_file(plan, approval_code(plan), TODAY)) == ["Phes", "PDfn"]


def test_fields_the_starting_file_changes_already_are_counted(plan_for, started):
    plan = plan_for(start_from=str(started), edits=[by_hand(100, Phes=190, finishing=3)])

    assert plan.replaced == 1


def test_items_added_behind_those_of_the_starting_file_replace_nothing(plan_for, tmp_path):
    plan = plan_for(edits=[by_hand(100, PNRs=[{"nati": 9001}])])
    path = tmp_path / "Lists.fmf"
    save_editor_file(build_file(plan, approval_code(plan), TODAY), path)

    plan = plan_for(start_from=str(path), edits=[by_hand(100, PNRs=[{"nati": 9002}])])

    assert plan.replaced == 0


# A season's boxes that are not ticked, as the old value holds them.
NOT_TICKED = {"onln": 0, "ytht": 0, "trib": 0}
# The boxes of days at a club, and the one ticked for Alfa Striker's days in Norwegia.
DAYS_BOXES = dict.fromkeys(("0t21", "bfat", "etto", "0t19", "d152", "d021"), 0)


def test_the_items_a_list_holds_now_are_its_old_value_where_the_lookup_has_them(plan_for):
    plan = plan_for(edits=[by_hand(100, Plhs={"replace": []}), by_hand(101, PNRs={"replace": []})])

    history, nations = plan.edits
    assert history.old == (
        {
            "year": 2021,
            "yror": 0,
            "clid": 9102,
            "divi": 9203,
            "apps": 30,
            "gols": 12,
            "join": "2021-07-01",
            **NOT_TICKED,
        },
        {
            "year": 2022,
            "yror": 1,
            "clid": 9102,
            "divi": 9203,
            "apps": 12,
            "gols": 4,
            "cash": 2_500_000,
            "leav": "2023-01-31",
            **NOT_TICKED,
        },
        {
            **{"year": 2022, "yror": 2, "clid": 9101, "divi": 9201, "info": -2},
            **{"onln": 1, "ytht": 0, "trib": 0, "hsfl": 12},
        },
    )
    assert nations.old is None


def test_the_days_at_clubs_a_person_has_are_their_old_value_unless_they_are_not_known(plan_for):
    """Charlie Coach's days at clubs cannot be read."""
    plan = plan_for(edits=[by_hand(uid, Pdcn={"replace": []}) for uid in (100, 101, 102)])

    assert [edit.old for edit in plan.edits] == [
        (
            {"Ttea": 9101, "days": 400, **DAYS_BOXES},
            {"Ttea": 9002, "days": 6000, **DAYS_BOXES, "0t19": 1},
        ),
        (),
        None,
    ]


def test_a_value_the_starting_file_changes_is_set_back_though_the_lookup_has_it(plan_for, tmp_path):
    """Alfa Striker's finishing is 15 in the database."""
    plan = plan_for(edits=[by_hand(100, finishing=3)])
    path = tmp_path / "Changed.fmf"
    save_editor_file(build_file(plan, approval_code(plan), TODAY), path)

    plan = plan_for(start_from=str(path), edits=[by_hand(100, finishing=15)])

    assert [(edit.old, edit.setting.value) for edit in plan.edits] == [(None, 15)]
    assert plan.already_so == 0


def test_the_items_of_a_list_the_starting_file_changes_are_not_known(plan_for, tmp_path):
    plan = plan_for(edits=[by_hand(100, Pdcn=[{"Ttea": 9102, "days": 30}])])
    path = tmp_path / "Lists.fmf"
    save_editor_file(build_file(plan, approval_code(plan), TODAY), path)

    plan = plan_for(start_from=str(path), edits=[by_hand(100, Pdcn={"replace": []})])

    assert [edit.old for edit in plan.edits] == [None]


def test_a_list_that_replaces_one_the_starting_file_adds_to_is_counted(plan_for, tmp_path):
    plan = plan_for(edits=[by_hand(100, PNRs=[{"nati": 9001}])])
    path = tmp_path / "Lists.fmf"
    save_editor_file(build_file(plan, approval_code(plan), TODAY), path)

    replaced = {"replace": [{"nati": 9002}]}
    plan = plan_for(start_from=str(path), edits=[by_hand(100, PNRs=replaced)])

    assert plan.replaced == 1


def test_a_starting_file_that_does_not_exist_is_reported(plan_for, tmp_path):
    with pytest.raises(FormatError, match="Nowhere.fmf"):
        plan_for(start_from=str(tmp_path / "Nowhere.fmf"), edits=[by_hand(100, finishing=3)])


def test_building_twice_gives_the_new_person_different_ids_but_the_same_code(plan_for):
    plan = plan_for(new=[NEW_PLAYER])
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
    request = {"edits": [by_hand(100, finishing=3)], "new": [NEW_PLAYER]}

    assert approval_code(plan_for(**request)) == approval_code(plan_for(**request))


def test_any_difference_in_what_is_written_changes_the_code(plan_for, started):
    other_player = NEW_PLAYER | {"set": NEW_PLAYER["set"] | {"Psna": "Other"}}
    plans = [
        plan_for(edits=[by_hand(100, finishing=3)]),
        plan_for(edits=[by_hand(100, finishing=4)]),
        plan_for(edits=[by_hand(101, finishing=3)]),
        plan_for(edits=[by_hand(100, ca=3)]),
        plan_for(new=[NEW_PLAYER]),
        plan_for(new=[other_player]),
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
