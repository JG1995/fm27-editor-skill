import pytest

import fictional_rules
from fictional_rules import write_rules
from fm27_editor.definition_files import FieldDefinitionError
from fm27_editor.rule_definitions import RuleDefinitions


@pytest.fixture
def definitions(tmp_path):
    return RuleDefinitions(write_rules(tmp_path))


def test_rules_are_found_under_headings_and_in_inserted_groups(definitions):
    division = definitions.group("bslg")

    teams = division["minimum_number_teams"]
    assert (teams.label, teams.type) == ("Minimum Number Teams", "integer")
    assert (teams.lowest, teams.highest) == (2, 500)
    assert division["competition"].points_to == "competition"


def test_the_first_of_two_definitions_counts(definitions):
    assert definitions.group("bslg")["number_rounds"].highest == 40


def test_choices_are_words_with_numbers(definitions):
    division, cup = definitions.group("bslg"), definitions.group("bscp")

    assert division["priority"].choices == {"league_low": 2, "league_high": 4}
    assert cup["type"].choices == {"main_cup": 2, "cup": 4, "super_cup": 5}
    assert cup["seeding_method"].choices == {"0": 0, "1": 1}


def test_records_and_lists_have_rules_of_their_own(definitions):
    nation, division = definitions.group("bscn"), definitions.group("bslg")

    assert set(nation["season_update_day"].parts) == {"day_of_month", "month"}
    assert "competition" in nation["league_comps"].parts
    assert nation["discipline_rules"].parts["red_card_info"].parts["games_banned"].highest == 20
    assert division["sort_rules"].choices == {"goal_difference": 0, "goals_for": 1, "own_match": 3}


def test_a_missing_group_is_reported(tmp_path):
    files = {name: xml for name, xml in fictional_rules.FILES.items() if "league" not in name}
    definitions = RuleDefinitions(write_rules(tmp_path, files))

    with pytest.raises(FieldDefinitionError, match="bslg"):
        definitions.group("bscn")


def test_the_nations_with_rules_in_the_game_are_known(definitions):
    assert definitions.nations_in_the_game() == {9002}
