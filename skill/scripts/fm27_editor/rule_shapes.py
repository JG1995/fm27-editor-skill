"""What the rules of a nation's competitions consist of when a file sets them.

Names are the Editor's own words for its rules. The codes, and which rules a file holds, were read
from a file with a complete set of basic rules, and the FM27 Editor opened a file written this way
and saved it with the same rules. A rule that was not seen in a file is not offered.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

CODES = {
    "nation": "nati",
    "competition": "comp",
    "use_game_rules": "usgr",
    "season_update_day": "updy",
    "day_of_month": "dyom",
    "day_of_week": "dyow",
    "month": "mont",
    "year": "year",
    "time": "time",
    "start_date": "stdt",
    "end_date": "endt",
    "transfer_windows": "trwi",
    "window_type": "wnty",
    "uses_bosman_rules": "usbs",
    "bosman_number_days": "tbnd",
    "free_transfers_can_join_outside_window": "frtj",
    "loan_players_can_join_outside_window": "lpow",
    "discipline_rules": "dsrl",
    "accumulative_method": "accm",
    "sequence": "sequ",
    "games_banned": "gmsb",
    "red_card_info": "rdci",
    "red_card_rule": "rdcr",
    "work_permit_rules": "wkpm",
    "league_comps": "lgcs",
    "secondary_league_comps": "slgc",
    "cup_comps": "cpcs",
    "has_sub_divisions": "hsdv",
    "child_competitions": "chdc",
    "type": "type",
    "minimum_number_teams": "mntm",
    "maximum_number_teams": "mxtm",
    "number_rounds": "nrds",
    "priority": "prio",
    "promotion_places": "prpl",
    "relegation_places": "rlpl",
    "b_teams_cannot_be_promoted": "btnp",
    "c_teams_cannot_be_promoted": "ctnp",
    "b_teams_cannot_be_promoted_if_main_team_is_2_divisions_above": "bt2l",
    "sort_rules": "sort",
    "initial_tv_money": "itvm",
    "parachute_money": "prcm",
    "use_specified_fixtures": "ussf",
    "league_fixtures": "lgfx",
    "opening_league_fixtures": "oplf",
    "closing_league_fixtures": "cllf",
    "prize_money": "przm",
    "match_days": "mtdy",
    "can_play_on_xmas_day": "CpXD",
    "tv_dates": "tvds",
    "subs_rules": "subr",
    "match_fixture_rules": "mtfr",
    "squad_fixture_rules": "sqfr",
    "format": "fmat",
    "number_teams": "ntms",
    "teams": "tems",
    "id": "id  ",
    "requirements": "strq",
    "seeding_method": "semt",
    "match_rules": "mtrl",
    "qualifying_rounds": "qurn",
    "rounds": "rnds",
    "number_matches": "nmmt",
    "number_extra_teams": "nmxt",
    "number_legs": "nmlg",
    "date": "date",
    "date_2": "dat2",
    "time_2": "tim2",
    "stadium_rules": "strl",
    "comp_1": "cmp1",
    "comp_2": "cmp2",
}
# The Editor has these built in. Each was matched between its templates, which name them, and its
# own rules, which number them, for at least three competitions.
SUBSTITUTIONS = {
    "three_from_five_and_extra_time_sub": 11,
    "five_from_seven": 20,
    "five_from_nine": 17,
    "five_from_ten": 66,
    "five_from_seven_max_three_stoppages": 56,
    "five_from_seven_max_three_stoppages_and_extra_time_sub": 62,
    "five_from_nine_max_three_stoppages": 58,
    "five_from_nine_max_three_stoppages_and_extra_time_sub": 63,
    "five_from_ten_max_three_stoppages": 59,
    "five_from_ten_max_three_stoppages_and_extra_time_sub": 60,
    "five_from_eleven_max_three_stoppages": 69,
    "five_from_eleven_max_three_stoppages_and_extra_time_sub": 79,
    "five_from_twelve_max_three_stoppages": 61,
    "five_from_twelve_max_three_stoppages_and_extra_time_sub": 67,
}
# Choices that need a rule whose code is not known, such as which stadium, or do without a number of
# teams.
CHOICES_LEFT_OUT = {
    "stadium_rules": {"specific"},
    "id": {"get_specific_team", "get_last_winner", "get_last_runnerup"},
}
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
DAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
NOTHING: Mapping[str, Any] = {}


@dataclass(frozen=True)
class Shape:
    """The rules of one thing, such as a division."""

    order: tuple[str, ...]
    """Every rule that is stored, in the order of the files seen."""
    needed: tuple[str, ...] = ()
    defaults: Mapping[str, Any] = field(default_factory=dict)
    """What is stored for a rule that the request does not give."""
    fixed: Mapping[str, Any] = field(default_factory=dict)
    """What is always stored, and cannot be given."""
    parts: Mapping[str, Shape] = field(default_factory=dict)
    """The shapes of records and of the items of lists."""

    @property
    def offered(self) -> list[str]:
        return [name for name in self.order if name not in self.fixed]


DAY = Shape(("day_of_month", "month"), needed=("day_of_month", "month"))
DATE = Shape(("day_of_month", "month", "year"), needed=("day_of_month", "month", "year"))
WINDOW = Shape(
    ("start_date", "end_date", "window_type"),
    needed=("start_date", "end_date"),
    defaults={"window_type": "normal"},
    parts={"start_date": DATE, "end_date": DATE},
)
YELLOW_CARDS = Shape(
    ("sequence", "games_banned", "start_date"),
    defaults={"sequence": "5_10_15", "games_banned": 1, "start_date": "immediate"},
)
RED_CARDS = Shape(
    ("red_card_rule", "games_banned"),
    defaults={"red_card_rule": "x_match_per_red_card", "games_banned": 1},
)
DISCIPLINE = Shape(
    ("accumulative_method", "red_card_info"),
    defaults={"accumulative_method": NOTHING, "red_card_info": NOTHING},
    parts={"accumulative_method": YELLOW_CARDS, "red_card_info": RED_CARDS},
)
MATCH_DAY = Shape(("day_of_week", "time"), needed=("day_of_week", "time"))
FIXTURE_LISTS = {
    "league_fixtures": [],
    "opening_league_fixtures": [],
    "closing_league_fixtures": [],
    "prize_money": [],
}
SUB_DIVISION = Shape(
    ("competition", "use_game_rules", *FIXTURE_LISTS),
    needed=("competition",),
    fixed={"use_game_rules": "not_in_game"} | FIXTURE_LISTS,
)
DIVISION = Shape(
    (
        *("competition", "use_game_rules", "has_sub_divisions", "type"),
        *("minimum_number_teams", "maximum_number_teams", "use_specified_fixtures"),
        *("start_date", "end_date", *FIXTURE_LISTS),
        *("match_fixture_rules", "squad_fixture_rules", "number_rounds", "priority"),
        *("promotion_places", "relegation_places", "b_teams_cannot_be_promoted"),
        "c_teams_cannot_be_promoted",
        "b_teams_cannot_be_promoted_if_main_team_is_2_divisions_above",
        *("sort_rules", "initial_tv_money", "parachute_money", "match_days"),
        *("can_play_on_xmas_day", "tv_dates", "subs_rules", "child_competitions"),
    ),
    needed=(
        *("competition", "minimum_number_teams", "maximum_number_teams"),
        *("start_date", "end_date"),
    ),
    defaults={
        "number_rounds": 2,
        "priority": "league_low",
        "promotion_places": 0,
        "relegation_places": 0,
        "b_teams_cannot_be_promoted": False,
        "c_teams_cannot_be_promoted": False,
        "b_teams_cannot_be_promoted_if_main_team_is_2_divisions_above": False,
        "sort_rules": ["goal_difference", "goals_for"],
        "match_days": {"day_of_week": "sat", "time": 1500},
        "can_play_on_xmas_day": False,
        "subs_rules": "five_from_nine_max_three_stoppages",
        "child_competitions": None,
    },
    fixed={
        "use_game_rules": "not_in_game",
        "has_sub_divisions": False,
        "type": "league",
        "use_specified_fixtures": False,
        "match_fixture_rules": [],
        "squad_fixture_rules": [],
        "initial_tv_money": 0,
        "parachute_money": 0,
        "tv_dates": [],
    }
    | FIXTURE_LISTS,
    parts={"match_days": MATCH_DAY, "child_competitions": SUB_DIVISION},
)
ENTRANTS = Shape(
    ("competition", "number_teams", "id"),
    needed=("competition", "number_teams"),
    defaults={"id": "get_best_division_teams"},
)
ROUND = Shape(
    (
        *("number_matches", "number_teams", "number_extra_teams", "number_legs"),
        *("date", "date_2", "stadium_rules", "time", "time_2"),
    ),
    needed=("number_matches", "date"),
    defaults={
        "number_extra_teams": 0,
        "number_legs": 1,
        "date_2": None,
        "stadium_rules": "home",
        "time": 1500,
        "time_2": None,
    },
    fixed={"number_teams": None},
)
TWO_LEGS = {"date_2", "time_2"}
CUP_FIXTURE_RULES = {
    "subs_rules": "five_from_nine_max_three_stoppages_and_extra_time_sub",
    "match_rules": ["extra_time", "pen"],
}
CUP = Shape(
    (
        *("use_game_rules", "type", "qualifying_rounds", "match_fixture_rules", "format"),
        *("number_teams", "teams", "requirements", "seeding_method", "rounds", "competition"),
        *("subs_rules", "match_rules"),
    ),
    needed=("type", "competition", "teams", "rounds"),
    defaults=CUP_FIXTURE_RULES | {"seeding_method": "0"},
    fixed={
        "use_game_rules": "not_in_game",
        "qualifying_rounds": 0,
        "match_fixture_rules": [],
        "format": "cup",
        "number_teams": None,
        "requirements": [],
    },
    parts={"teams": ENTRANTS, "rounds": ROUND},
)
SUPER_CUP = Shape(
    (
        *("use_game_rules", "type", "match_fixture_rules", "number_teams", "requirements"),
        *("competition", "subs_rules", "match_rules", "comp_1", "comp_2", "date", "stadium_rules"),
    ),
    needed=("type", "competition", "comp_1", "comp_2", "date"),
    defaults=CUP_FIXTURE_RULES | {"stadium_rules": "neutral"},
    fixed={
        "use_game_rules": "not_in_game",
        "match_fixture_rules": [],
        "number_teams": None,
        "requirements": [],
    },
)
NATION_RULES = Shape(
    (
        *("use_game_rules", "season_update_day", "start_date", "end_date", "bosman_number_days"),
        *("nation", "transfer_windows", "discipline_rules", "work_permit_rules"),
        *("league_comps", "secondary_league_comps", "cup_comps", "uses_bosman_rules"),
        "free_transfers_can_join_outside_window",
        "loan_players_can_join_outside_window",
    ),
    needed=("nation", "season_update_day", "start_date", "end_date", "league_comps"),
    defaults={
        "bosman_number_days": 183,
        "transfer_windows": [],
        "discipline_rules": NOTHING,
        "cup_comps": [],
        "uses_bosman_rules": True,
        "free_transfers_can_join_outside_window": True,
        "loan_players_can_join_outside_window": False,
    },
    fixed={"use_game_rules": False, "work_permit_rules": NOTHING, "secondary_league_comps": []},
    parts={
        "season_update_day": DAY,
        "transfer_windows": WINDOW,
        "discipline_rules": DISCIPLINE,
        "work_permit_rules": Shape(()),
        "league_comps": DIVISION,
        "cup_comps": CUP,
    },
)
# Where the Editor defines what each shape holds; parts are defined inside.
NATION_GROUP, DIVISION_GROUP, CUP_GROUP = "bscn", "bslg", "bscp"
