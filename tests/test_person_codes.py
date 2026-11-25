import pytest

from fm27_editor.people import PersonKind
from fm27_editor.person_codes import person_codes
from fm27_editor.person_fields import FIELD_NAMES
from fm27_editor.record_changes import EditError

WITHOUT_A_CODE = {"name", "position_sw"}


def test_every_fact_the_lookup_has_for_players_has_a_code_or_a_reason_not_to():
    facts = {"name", "full_name", "birth_date", "nation_uid", "club_uid", "ca", "pa", *FIELD_NAMES}

    assert set(person_codes(PersonKind.PLAYER)) == facts - WITHOUT_A_CODE


def test_no_two_facts_share_a_code():
    codes = list(person_codes(PersonKind.PLAYER).values())

    assert len(set(codes)) == len(codes)


@pytest.mark.parametrize("kind", [PersonKind.BOTH, PersonKind.OFFICIAL, PersonKind.RETIRED])
def test_kinds_whose_codes_are_not_known_are_refused(kind):
    with pytest.raises(EditError, match="not known"):
        person_codes(kind)
