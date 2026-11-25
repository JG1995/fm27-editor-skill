from fm27_editor.people import PersonKind
from fm27_editor.person_codes import person_codes
from fm27_editor.person_fields import FIELD_NAMES

NO_LONGER_IN_THE_EDITOR = {"position_sw"}


def test_every_fact_the_lookup_has_for_players_has_a_code():
    names = {"birth_date", "nation_uid", "club_uid", "ca", "pa", *FIELD_NAMES}

    assert set(person_codes(PersonKind.PLAYER)) == names - NO_LONGER_IN_THE_EDITOR


def test_no_two_facts_share_a_code():
    codes = list(person_codes(PersonKind.PLAYER).values())

    assert len(set(codes)) == len(codes)
