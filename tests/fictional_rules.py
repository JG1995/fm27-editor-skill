"""Fictional definitions of competition rules, in the shape of the Editor's, built for tests."""

from pathlib import Path

import synthetic


def rule(name, kind, *extra, label=None):
    return (
        f'<record><flags id="field" value="{name}" />'
        f'<translation id="name" value="{label or name.replace("_", " ").title()}" />'
        f'<flags id="type" value="{kind}" />{"".join(extra)}</record>'
    )


def span(lowest, highest):
    return synthetic.number_range(lowest, highest)


def choices(**numbers):
    listed = "".join(
        f'<record enum="{word}" enum_id="{number}"><string id="name" value="{word}" /></record>'
        for word, number in numbers.items()
    )
    return f'<list id="enum_values">{listed}</list>'


def shared(name):
    return f'<flags id="enum_values" value="{name}" />'


def table(name):
    return f'<flags id="database_table_type" value="{name}" />'


def fields(*rules):
    return f'<list id="fields">{"".join(rules)}</list>'


def items(*rules):
    return f'<record id="list_item">{fields(*rules)}</record>'


def items_of(group):
    return f'<record id="list_item"><flags id="fields" value="{group}" /></record>'


def section(*rules):
    """A heading without a field of its own."""
    return f'<record><flags id="type" value="record" />{fields(*rules)}</record>'


def inserted(group):
    return f'<record insert_fields="{group}" />'


def group(name, *rules):
    return f'<record><record id="{name}">{fields(*rules)}</record></record>'.encode()


COMPETITION = ("database_record_unique_id", table("competition"))
NATION_RULES = group(
    "bscn",
    section(
        rule("nation", "database_record_unique_id", table("nation")),
        rule("use_game_rules", "boolean"),
        rule(
            "season_update_day",
            "record",
            fields(rule("day_of_month", "integer", span(1, 31)), rule("month", "month")),
        ),
        rule("start_date", "date"),
        rule("end_date", "date"),
        rule(
            "transfer_windows",
            "list",
            items(
                rule("start_date", "date_fields"),
                rule("end_date", "date_fields"),
                rule("window_type", "enum", choices(normal=1, free_transfers_only=9)),
            ),
        ),
        section(
            rule("uses_bosman_rules", "boolean"),
            rule("bosman_number_days", "integer", span(1, 2000)),
            rule("free_transfers_can_join_outside_window", "boolean"),
            rule("loan_players_can_join_outside_window", "boolean"),
            rule("youth_regen_min_age", "integer", span(14, 25)),
        ),
        inserted("bscr"),
        rule("work_permit_rules", "record", fields()),
    ),
    rule("league_comps", "list", items_of("bslg")),
    rule("secondary_league_comps", "list", items_of("bslg")),
    rule("cup_comps", "list", items_of("bscp")),
)
DISCIPLINE = group(
    "bscr",
    rule(
        "discipline_rules",
        "record",
        fields(
            rule(
                "accumulative_method",
                "record",
                fields(
                    rule("sequence", "enum", choices(**{"5_10_15": 3, "3_6_9": 2})),
                    rule("games_banned", "integer", span(1, 20)),
                    rule("start_date", "enum", choices(immediate=0)),
                ),
            ),
            rule(
                "red_card_info",
                "record",
                fields(
                    rule("red_card_rule", "enum", choices(x_match_per_red_card=0)),
                    rule("games_banned", "integer", span(1, 20)),
                ),
            ),
        ),
    ),
)
MATCH_DAY = fields(rule("day_of_week", "day_of_week"), rule("time", "time"))
DIVISION = group(
    "bslg",
    section(
        rule("competition", *COMPETITION),
        rule("use_game_rules", "enum", choices(active_comp=0, not_in_game=2)),
        rule("has_sub_divisions", "boolean"),
        inserted("bslf"),
    ),
    rule("child_competitions", "list", items_of("bscc")),
    section(
        rule("start_date", "date"),
        rule("end_date", "date"),
        rule("match_days", "record", MATCH_DAY),
        rule("can_play_on_xmas_day", "boolean"),
        rule("tv_dates", "list", items()),
        rule("league_fixtures", "list", items()),
        rule("opening_league_fixtures", "list", items()),
        rule("closing_league_fixtures", "list", items()),
        rule("prize_money", "list", items()),
        rule("subs_rules", "enum", shared("subs")),
        rule("match_fixture_rules", "list", items()),
        rule("squad_fixture_rules", "list", items()),
        rule("top_playoff", "record", fields()),
    ),
)
SUB_DIVISION = group(
    "bscc",
    rule("competition", *COMPETITION),
    rule("use_game_rules", "enum", choices(active_comp=0, not_in_game=2)),
    rule("league_fixtures", "list", items()),
    rule("opening_league_fixtures", "list", items()),
    rule("closing_league_fixtures", "list", items()),
    rule("prize_money", "list", items()),
)
LEAGUE_FORMAT = group(
    "bslf",
    rule("type", "enum", choices(league=0, groups=1)),
    rule("minimum_number_teams", "integer", span(2, 500)),
    rule("maximum_number_teams", "integer", span(2, 500)),
    rule("number_rounds", "integer", span(1, 40)),
    rule("number_rounds", "integer", span(1, 8)),
    rule("priority", "enum", shared("prio")),
    rule("promotion_places", "integer", span(0, 60)),
    rule("relegation_places", "integer", span(0, 60)),
    rule("b_teams_cannot_be_promoted", "boolean"),
    rule("c_teams_cannot_be_promoted", "boolean"),
    rule("b_teams_cannot_be_promoted_if_main_team_is_2_divisions_above", "boolean"),
    rule(
        "sort_rules",
        "list",
        '<record id="list_item"><list id="fields"><record><flags id="type" value="enum" />'
        '<flags id="enum_values" value="srrl" /></record></list></record>',
    ),
    rule("initial_tv_money", "cash"),
    rule("parachute_money", "cash"),
    rule("use_specified_fixtures", "boolean"),
)
STADIUMS = choices(home=1, national=2, neutral=3, specific=22)
CUP = group(
    "bscp",
    rule("competition", *COMPETITION),
    rule("use_game_rules", "enum", choices(active_comp=0, not_in_game=2)),
    rule("type", "enum", choices(main_cup=2, cup=4, super_cup=5)),
    rule("format", "enum", choices(cup=0, grcp=1)),
    rule("number_teams", "integer", span(2, 2048)),
    rule(
        "teams",
        "list",
        items(
            rule("id", "enum", choices(get_best_division_teams=4, get_specific_team=5)),
            rule("competition", *COMPETITION),
            rule("number_teams", "integer", span(1, 1000)),
        ),
    ),
    rule("requirements", "database_record_list", table("competition")),
    rule(
        "seeding_method",
        "enum",
        '<list id="enum_values"><record enum="0"><string id="name" value="Seeded" /></record>'
        '<record enum="1"><string id="name" value="Random" /></record></list>',
    ),
    rule("qualifying_rounds", "integer", span(0, 4)),
    rule(
        "rounds",
        "list",
        items(
            rule("number_matches", "integer", span(1, 500)),
            rule("number_extra_teams", "integer", span(0, 1000)),
            rule("number_legs", "integer", span(1, 2)),
            rule("date", "date"),
            rule("time", "time"),
            rule("date_2", "date"),
            rule("time_2", "time"),
            rule("stadium_rules", "enum", STADIUMS),
        ),
    ),
    rule("match_rules", "multiple_enum", shared("smtr")),
    rule("subs_rules", "enum", shared("subs")),
    rule("match_fixture_rules", "list", items()),
    rule("comp_1", *COMPETITION),
    rule("comp_2", *COMPETITION),
    rule("date", "date"),
    rule("stadium_rules", "enum", STADIUMS),
)
ENUMS = (
    "<record>"
    f'<record id="prio">{choices(league_low=2, league_high=4)}</record>'
    f'<record id="srrl">{choices(goal_difference=0, goals_for=1, own_match=3)}</record>'
    f'<record id="smtr">{choices(extra_time=1, pen=2, away_goals=12)}</record>'
    "</record>"
).encode()
FILES = {
    "basic nation rules": NATION_RULES,
    "basic discipline rules": DISCIPLINE,
    "basic league settings": DIVISION,
    "basic child comp": SUB_DIVISION,
    "basic league format": LEAGUE_FORMAT,
    "basic cup settings": CUP,
    "enums": ENUMS,
}


def write_rules(folder: Path, files: dict[str, bytes] = FILES, nations=(9002,)) -> Path:
    """The definitions, and the rules the game has for some nations."""
    data = folder / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "format.fmf").write_bytes(
        synthetic.container(
            "format",
            [],
            folder=("rule group", [(name, ".xml", content) for name, content in files.items()]),
            encrypted=False,
        )
    )
    templates = [
        (
            f"nation{uid}",
            ".xml",
            f'<record><record id="rule_group"><integer id="nation" value="{uid}"/>'
            '<list id="league_comps"><record><integer id="nation" value="-1"/></record></list>'
            "</record></record>".encode(),
        )
        for uid in nations
    ]
    templates += [("config", ".xml", b"<record/>"), ("NOTES", ".md", b"# Not a definition")]
    (data / "basic comps.fmf").write_bytes(
        synthetic.container("basic comps", templates, encrypted=False)
    )
    return folder
