import copy
import datetime
import re

import pytest

from fictional_rules import write_rules
from fm27_editor.binary import FormatError
from fm27_editor.change_list import ChangeList, Kind, ListItem, Property
from fm27_editor.change_reading import EditError
from fm27_editor.nation_rules import check_nation_rules
from fm27_editor.record_fields import NewReference
from fm27_editor.rule_changes import add_rules
from fm27_editor.rule_definitions import RuleDefinitions
from fm27_editor.rule_plan import fit_warnings

D1, D2, CUP = b"\x01\0\0\0\x0a\0\0\0", b"\x02\0\0\0\x0b\0\0\0", b"\x03\0\0\0\x0c\0\0\0"
NEW = {"D1": D1, "D2": D2, "CUP": CUP}
RULES = {
    "nation": 9001,
    "season_update_day": {"day_of_month": 20, "month": "jun"},
    "start_date": "2026-08-01",
    "end_date": "2027-05-31",
    "transfer_windows": [{"start_date": "2026-07-01", "end_date": "2026-08-31"}],
    "league_comps": [
        {
            "competition": "@D1",
            "minimum_number_teams": 4,
            "maximum_number_teams": 4,
            "relegation_places": 1,
            "start_date": "2026-08-15",
            "end_date": "2027-05-15",
        },
        {
            "competition": "@D2",
            "minimum_number_teams": 4,
            "maximum_number_teams": 4,
            "promotion_places": 1,
            "start_date": "2026-08-15",
            "end_date": "2027-05-15",
        },
    ],
    "cup_comps": [
        {
            "competition": "@CUP",
            "type": "main_cup",
            "teams": [
                {"competition": "@D1", "number_teams": 4},
                {"competition": "@D2", "number_teams": 2},
            ],
            "rounds": [
                {"number_matches": 2, "number_extra_teams": 4, "date": "2026-09-23"},
                {"number_matches": 2, "number_extra_teams": 2, "date": "2026-10-28"},
                {"number_matches": 1, "date": "2027-05-22", "stadium_rules": "neutral"},
            ],
        }
    ],
}
SUPER_CUP = {
    "competition": 9204,
    "type": "super_cup",
    "comp_1": "@D1",
    "comp_2": "@CUP",
    "date": "2026-08-08",
}


@pytest.fixture
def definitions(tmp_path):
    return RuleDefinitions(write_rules(tmp_path))


def refer(points_to, what, given):
    """Stands for the lookup: every uid from 9000 exists, and so do the new records."""
    if isinstance(given, str) and given.removeprefix("@") in NEW:
        return NewReference(given.removeprefix("@"))
    if isinstance(given, int) and given >= 9000:
        return given
    raise EditError(f"{what}: there is no {points_to} {given!r}")


@pytest.fixture
def checked(definitions):
    return lambda given: check_nation_rules(given, definitions, refer)


def warned(rules):
    return list(fit_warnings(rules, str))


def changed(**parts):
    return copy.deepcopy(RULES) | parts


def with_division(**values):
    rules = copy.deepcopy(RULES)
    rules["league_comps"][0] |= values
    return rules


def with_cup(**values):
    rules = copy.deepcopy(RULES)
    rules["cup_comps"][0] |= values
    return rules


def with_round(number, **values):
    rules = copy.deepcopy(RULES)
    rules["cup_comps"][0]["rounds"][number] |= values
    return rules


def stored(rules):
    changes = ChangeList(general=[Property("dchc", Kind.COUNT, bytes(8))])
    add_rules(changes, rules, NEW)
    return changes


def tagged(parts):
    return {part.tag: part for part in parts}


# --- what is accepted -----------------------------------------------------------------------


def test_rules_that_are_not_given_get_a_value_that_is_shown(checked):
    division = checked(RULES).values["league_comps"][0]

    assert division["number_rounds"] == 2
    assert division["subs_rules"] == "five_from_nine_max_three_stoppages"
    assert division["match_days"] == {"day_of_week": "sat", "time": 1500}


def test_dates_are_given_as_text(checked):
    rules = checked(RULES).values

    assert rules["start_date"] == datetime.date(2026, 8, 1)
    assert rules["transfer_windows"][0]["start_date"] == {
        "day_of_month": 1,
        "month": "jul",
        "year": 2026,
    }


def test_competitions_are_existing_or_new_ones(checked):
    rules = checked(with_division(competition=9201)).values

    assert [d["competition"] for d in rules["league_comps"]] == [9201, NewReference("D2")]


def test_the_number_of_teams_in_a_cup_is_counted(checked):
    cup = checked(RULES).values["cup_comps"][0]

    assert cup["number_teams"] == 6
    assert [r["number_teams"] for r in cup["rounds"]] == [4, 4, 2]


def test_sub_divisions_are_noticed(checked):
    plain, divided = (
        checked(with_division(**values)).values["league_comps"][0]
        for values in ({}, {"child_competitions": [{"competition": 9205}]})
    )

    assert (plain["has_sub_divisions"], divided["has_sub_divisions"]) == (False, True)


def test_places_of_a_division_count_for_all_its_sub_divisions_together(checked):
    """The Editor: promoted teams "should be divisible by number of sub-competitions"."""
    rules = changed(cup_comps=[])
    rules["league_comps"][0]["relegation_places"] = 2
    rules["league_comps"][1] |= {
        "promotion_places": 2,
        "child_competitions": [{"competition": 9205}, {"competition": 9206}],
    }
    assert warned(checked(rules)) == []

    rules["league_comps"][0]["relegation_places"] = 1
    rules["league_comps"][1]["promotion_places"] = 1
    with pytest.raises(EditError, match="promotion_places 1.*2 sub-divisions"):
        checked(rules)


def test_a_round_of_two_legs_has_two_dates_and_no_stadium(checked):
    rules = with_round(0, number_legs=2, date_2="2026-09-30")

    first = checked(rules).values["cup_comps"][0]["rounds"][0]

    assert (first["date_2"], first["time_2"]) == (datetime.date(2026, 9, 30), 1500)
    assert first["stadium_rules"] is None


@pytest.mark.parametrize(
    ("rules", "complaint"),
    [
        (5, "nation_rules"),
        (changed(league_comps=[]), "division"),
        (changed(league_comps=5), "list"),
        (changed(extra=1), "extra"),
        (changed(use_game_rules=True), "use_game_rules"),
        (changed(youth_regen_min_age=16), "youth_regen_min_age.*yet"),
        (changed(nation=5), "nation 5"),
        (changed(start_date="soon"), "soon"),
        (changed(start_date="2027-06-01"), "end_date"),
        (changed(season_update_day={"day_of_month": 32, "month": "jun"}), "32"),
        (changed(season_update_day={"day_of_month": 1, "month": "june"}), "june"),
        (changed(season_update_day={"day_of_month": 1}), "month"),
        (changed(uses_bosman_rules=1), "true or false"),
        (changed(transfer_windows=[{"start_date": "2026-07-01"}]), "end_date"),
        (
            changed(transfer_windows=[{"start_date": "2026-07-02", "end_date": "2026-07-01"}]),
            "transfer_windows",
        ),
        (with_division(competition="@D9"), "@D9"),
        (with_division(competition="@D2"), "twice"),
        (with_division(number_rounds=41), "41"),
        (with_division(number_rounds="2"), "whole number"),
        (with_division(priority="urgent"), "urgent"),
        (with_division(priority=["league_low"]), "league_low"),
        (with_division(subs_rules="six_from_six"), "six_from_six"),
        (with_division(sort_rules=["luck"]), "luck"),
        (with_division(sort_rules="goals_for"), "list"),
        (with_division(sort_rules=["goals_for", "goals_for"]), "twice"),
        (with_division(match_days={"day_of_week": "caturday", "time": 1500}), "caturday"),
        (with_division(match_days={"day_of_week": "sat", "time": 1575}), "1575"),
        (with_division(minimum_number_teams=5), "minimum_number_teams"),
        (with_division(end_date="2027-06-02"), "season"),
        (with_division(top_playoff={}), "top_playoff.*yet"),
        (with_division(initial_tv_money=5), "initial_tv_money.*yet"),
        (with_cup(type="friendly"), "friendly"),
        (with_cup(type=["cup"]), "cup"),
        (with_cup(match_rules=["golden_goal"]), "golden_goal"),
        (with_cup(teams=[{"competition": "@D1", "number_teams": 5}]), "5 teams.*6"),
        (with_cup(teams=[]), "teams"),
        (
            with_cup(teams=[{"competition": "@D1", "number_teams": 6, "id": "get_specific_team"}]),
            "get_specific_team",
        ),
        (with_round(0, stadium_rules="specific"), "specific"),
        (changed(cup_comps=None), "cup_comps has no value"),
        (with_division(promotion_places=None), "promotion_places has no value"),
        (with_round(0, number_extra_teams=None), "number_extra_teams has no value"),
        (with_round(0, number_legs=2, date_2="2026-10-28"), "round 2.*before"),
        (with_round(0, date="2026-07-31"), "cup_comps 1.*season"),
        (with_round(2, date="2029-05-22"), "cup_comps 1.*season"),
        (changed(cup_comps=[SUPER_CUP | {"date": "2025-08-08"}]), "cup_comps 1.*season"),
        (with_cup(rounds=[]), "rounds"),
        (with_round(1, number_matches=3), "round 2"),
        (with_round(2, number_matches=2, number_extra_teams=2), "one match"),
        (with_round(1, date="2026-09-01"), "round 2.*before"),
        (with_round(0, number_legs=2), "date_2"),
        (with_round(0, date_2="2026-09-30"), "number_legs"),
        (with_round(0, number_legs=2, date_2="2026-09-22"), "date_2"),
        (changed(cup_comps=[SUPER_CUP | {"comp_2": "@D1"}]), "comp_2"),
        (changed(cup_comps=[SUPER_CUP | {"rounds": []}]), "rounds"),
    ],
)
def test_rules_the_editor_would_not_accept_are_refused_with_a_reason(checked, rules, complaint):
    with pytest.raises(FormatError, match=complaint):
        checked(rules)


# --- what is pointed out --------------------------------------------------------------------


def test_rules_that_fit_together_have_no_warnings(checked):
    assert warned(checked(RULES)) == []


def test_unequal_promotion_and_relegation_is_pointed_out(checked):
    (warning,) = warned(checked(with_division(relegation_places=2)))

    assert "2 go down" in warning and "1 come up" in warning


def test_relegation_that_does_not_divide_over_the_sub_divisions_is_pointed_out(checked):
    parts = [{"competition": 9205}, {"competition": 9206}]

    (warning,) = warned(checked(with_division(child_competitions=parts) | {"cup_comps": []}))

    assert "1 go down" in warning and "2 sub-divisions" in warning


@pytest.mark.parametrize(
    ("entrants", "complaint"),
    [
        ([("@D1", 5), ("@D2", 1)], "5 teams.*@D1.*4"),
        ([("@D1", 4), (9207, 2)], "9207"),
    ],
    ids=["more than there are", "from elsewhere"],
)
def test_entrants_that_the_divisions_do_not_have_are_pointed_out(checked, entrants, complaint):
    teams = [{"competition": c, "number_teams": number} for c, number in entrants]

    (warning,) = warned(checked(with_cup(teams=teams)))

    assert re.search(complaint, warning)


def test_entrants_come_from_the_parts_of_a_division(checked):
    rules = with_division(child_competitions=[{"competition": 9205}])

    (warning,) = warned(checked(rules))

    assert "@D1" in warning


def test_a_super_cup_between_competitions_of_other_rules_is_pointed_out(checked):
    (warning,) = warned(checked(changed(cup_comps=[SUPER_CUP | {"comp_2": 9208}])))

    assert "9208" in warning


def test_a_second_leg_can_start_at_midnight(checked):
    rules = with_round(0, number_legs=2, date_2="2026-09-30", time_2=0)

    assert checked(rules).values["cup_comps"][0]["rounds"][0]["time_2"] == 0


def test_a_season_too_short_for_its_matches_is_pointed_out(checked):
    (warning,) = warned(checked(with_division(number_rounds=40)))

    assert "120 match days" in warning


# --- how they are stored --------------------------------------------------------------------


def test_a_file_says_twice_which_nation_it_has_rules_for(checked):
    changes = stored(checked(RULES))

    nation = Property("nati", Kind.CODE, "\x00\x00\x23\x29")
    assert changes.general[1] == Property("rlgr", Kind.NESTED, [nation])
    assert tagged(changes.editor)["rlgr"].value[0] == Property("id  ", Kind.CODE, "rlgr")
    assert nation in tagged(changes.editor)["rlgr"].value


def test_a_division_is_stored_the_way_the_editor_does(checked):
    rules = tagged(tagged(stored(checked(RULES)).editor)["rlgr"].value)

    division = rules["lgcs"].value[0].value
    assert division[0] == Property(
        "comp",
        Kind.NESTED,
        [
            Property("id  ", Kind.CODE, "comp"),
            Property("comp", Kind.ID, D1),
            Property("DBID", Kind.INT8, b"\x01"),
        ],
    )
    parts = tagged(division)
    assert parts["usgr"].value == b"\x02"
    assert parts["mntm"] == Property("mntm", Kind.INT8, b"\x04")
    assert parts["stdt"] == Property("stdt", Kind.DATE, bytes.fromhex("00e3d40f"))
    assert parts["subr"].value == b"\x3a"
    assert [(item.kind, item.value) for item in parts["sort"].value] == [
        (Kind.INT8, b"\x00"),
        (Kind.INT8, b"\x01"),
    ]
    assert parts["mtdy"].value == [
        Property("id  ", Kind.CODE, "mtdy"),
        Property("dyow", Kind.INT8, b"\x07"),
        Property("time", Kind.INT16, b"\xdc\x05"),
    ]
    assert (parts["lgfx"].value, parts["itvm"].value) == ([], b"\x00")
    assert "chdc" not in parts


def test_rules_of_the_nation_are_stored_in_full(checked):
    rules = tagged(tagged(stored(checked(RULES)).editor)["rlgr"].value)

    assert rules["updy"].value[1:] == [
        Property("dyom", Kind.INT8, b"\x14"),
        Property("mont", Kind.INT8, b"\x06"),
    ]
    window = tagged(rules["trwi"].value[0].value)
    assert [part.value for part in window["stdt"].value[1:]] == [b"\x01", b"\x07", b"\xea\x07"]
    assert window["wnty"].value == b"\x01"
    assert rules["usgr"] == Property("usgr", Kind.BOOL, b"\x00")
    assert tagged(tagged(rules["dsrl"].value)["accm"].value)["sequ"].value == b"\x03"


def test_a_cup_is_stored_with_its_rounds_and_entrants(checked):
    rules = tagged(tagged(stored(checked(RULES)).editor)["rlgr"].value)

    cup = tagged(rules["cpcs"].value[0].value)
    assert (cup["type"].value, cup["ntms"].value) == (b"\x02", b"\x06")
    assert cup["mtrl"] == Property("mtrl", Kind.CODE, "\x00\x00\x00\x03")
    entrants = tagged(cup["tems"].value[0].value)
    assert (entrants["ntms"].value, entrants["id  "].value) == (b"\x04", b"\x04")
    first, *_, final = (tagged(item.value) for item in cup["rnds"].value)
    assert (first["nmmt"].value, first["ntms"].value, first["nmxt"].value) == (
        b"\x02",
        b"\x04",
        b"\x04",
    )
    assert final["strl"].value == b"\x03"
    assert "dat2" not in first


def test_a_super_cup_is_stored_with_its_two_competitions(checked):
    rules = changed(cup_comps=[SUPER_CUP])

    stored_rules = tagged(tagged(stored(checked(rules)).editor)["rlgr"].value)

    cup = tagged(stored_rules["cpcs"].value[0].value)
    assert cup["comp"].value[1].value == (9204).to_bytes(4, "little") * 2
    assert cup["cmp1"].value[:2] == [
        Property("id  ", Kind.CODE, "cmp1"),
        Property("comp", Kind.ID, D1),
    ]
    assert cup["ntms"] == Property("ntms", Kind.NULL, b"")


@pytest.mark.parametrize(
    "other",
    [
        Property("cnrl", Kind.NESTED, []),
        Property("inrl", Kind.NESTED, []),
        Property("vrrl", Kind.NESTED, []),
        Property("fles", Kind.LIST, [ListItem(Kind.NESTED, [])]),
    ],
    ids=lambda item: item.tag,
)
def test_a_file_with_other_kinds_of_rules_is_refused(checked, other):
    changes = ChangeList(general=[Property("dchc", Kind.COUNT, bytes(8))], editor=[other])

    with pytest.raises(FormatError, match="rules already"):
        add_rules(changes, checked(RULES), NEW)


def test_an_empty_list_of_advanced_rules_does_not_matter(checked):
    changes = ChangeList(
        general=[Property("dchc", Kind.COUNT, bytes(8))], editor=[Property("fles", Kind.LIST, [])]
    )

    add_rules(changes, checked(RULES), NEW)


def test_a_file_has_rules_for_one_nation(checked):
    changes = stored(checked(RULES))

    with pytest.raises(FormatError, match="rules already"):
        add_rules(changes, checked(RULES), NEW)
