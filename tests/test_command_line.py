import json

import pytest

from fictional_editor import STAFF_KIND, write_editor
from fm27_editor.command_line import main
from fm27_editor.editor_file import load_editor_file

TEAM = [
    (0, 100, "Alfa Striker", 2004, 120, (51, 9002), (1, 9101)),
    (1, 101, "Bravo Keeper", 2008, 60, (41, 9001), (0, 9102)),
    (2, 102, "Charlie Coach", 1980, 110, (41, 9001), (0, 9102), STAFF_KIND),
]
REQUEST = {"edits": [{"of": "people", "uid": 100, "set": {"finishing": 17}}]}


@pytest.fixture
def run(tmp_path, capsys):
    """Run a command; gives the exit status, the lines printed, and the error."""
    editor = write_editor(tmp_path / "editor", TEAM)
    places = ["--editor", str(editor), "--cache", str(tmp_path / "cache.sqlite")]

    def command(*arguments):
        status = main([*places, *map(str, arguments)])
        printed = capsys.readouterr()
        return status, printed.out.splitlines(), printed.err

    return command


@pytest.fixture
def request_file(tmp_path):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(REQUEST))
    return path


def code_in(lines):
    return lines[-1].removeprefix("Approval code: ")


def test_find_prints_the_columns_and_rows(run):
    status, lines, _ = run("find", "SELECT uid, name, club FROM people WHERE kind = 'player'")

    assert status == 0
    assert lines == [
        "uid\tname\tclub",
        "100\tAlfa Striker\tFictional City",
        "101\tBravo Keeper\tExample United",
        "2 rows",
    ]


def test_find_says_when_there_is_more(run):
    _, lines, _ = run("find", "SELECT uid FROM people ORDER BY uid", "--limit", 2)

    assert lines == ["uid", "100", "101", "The first 2 rows; there are more"]


def test_find_shows_what_the_lookup_does_not_know_as_null(run):
    _, lines, _ = run("find", "SELECT finishing FROM people WHERE uid = 102")

    assert lines[1] == "NULL"


def test_a_query_that_cannot_be_run_is_an_error(run):
    status, lines, error = run("find", "SELECT uid FROM nowhere")

    assert (status, lines) == (1, [])
    assert "nowhere" in error


def test_fields_are_listed_with_name_code_and_range(run):
    _, lines, _ = run("fields", "player")

    assert "finishing (PDfn): Finishing, 0 to 20" in lines
    assert "Phes: Height, 0 to 210" in lines
    assert "birth_date (Pdob): Date Of Birth, a date such as 2008-04-25" in lines
    assert "nation_uid (Pnti): Nation, the uid of a nation" in lines
    assert "Pfna: First Name, a text" in lines


def test_fields_that_cannot_be_written_are_not_listed(run):
    _, lines, _ = run("fields", "player")

    assert not [line for line in lines if "Ptyp" in line or "Page" in line]


def test_the_fields_of_clubs_and_competitions_are_listed_by_the_lookups_names(run):
    _, clubs, _ = run("fields", "club", "division")
    _, competitions, _ = run("fields", "competition", "type")

    assert clubs == ["division_uid (Cdvi): Division, the uid of a competition"]
    assert competitions == ["dbty: Type, one of 0 Top Division, 2 Main Cup"]


def test_the_rules_that_can_be_set_are_listed_with_what_is_set_otherwise(run):
    _, rounds, _ = run("fields", "division", "number_rounds")
    _, division, _ = run("fields", "division")
    _, cup, _ = run("fields", "cup", "rounds")
    _, nation, _ = run("fields", "nation_rules", "transfer_windows")

    assert rounds == ["number_rounds: Number Rounds, 1 to 40, otherwise 2"]
    assert "competition: Competition, the uid or new name of a competition, needed" in division
    assert "subs_rules" in "\n".join(division) and "use_game_rules" not in "\n".join(division)
    assert cup[0].startswith("rounds: Rounds, a list of (number_matches: 1 to 500, needed; ")
    assert nation == [
        "transfer_windows: Transfer Windows, a list of (start_date: a date such as 2026-08-15, "
        "needed; end_date: a date such as 2026-08-15, needed; window_type: one of normal, "
        "free_transfers_only, otherwise normal), otherwise none"
    ]


def test_fields_can_be_searched_by_name_or_code(run):
    _, by_name, _ = run("fields", "staff", "ability")
    _, by_code, _ = run("fields", "staff", "ncra")

    assert by_name == by_code == ["ca (Ncra): Current Ability, 0 to 200"]


def test_potential_lists_the_ranges_it_may_be(run):
    _, lines, _ = run("fields", "player", "PPAB")

    assert lines == ["pa (PPAB): Potential Ability, 0 to 200, or a range: -8 130-160, -95 160-190"]
    assert run("fields", "player", "PPAR")[1] == ["No field matches 'PPAR'"]


def test_a_field_with_choices_lists_them(run):
    _, lines, _ = run("fields", "player", "Zmod")

    assert lines == ["Zmod: Mood, one of 0 Calm, 2 Cross"]


def test_preview_writes_nothing(run, request_file, tmp_path):
    before = set(tmp_path.rglob("*.fmf"))

    status, lines, _ = run("preview", request_file)

    assert status == 0
    assert "Edits: 1 change to 1 person" in lines
    assert set(tmp_path.rglob("*.fmf")) == before


def test_write_makes_the_file_that_was_previewed(run, request_file, tmp_path):
    _, preview, _ = run("preview", request_file)
    target = tmp_path / "Sharper.fmf"

    status, lines, _ = run("write", request_file, target, "--approved", code_in(preview))

    assert status == 0
    assert lines[0] == f"Wrote {target}: 1 change, read back and compared"
    (change,) = load_editor_file(target).changes.changes
    assert next(item.value for item in change if item.tag == "nwvl") == "17"


def test_write_refuses_a_request_that_is_not_the_one_previewed(run, request_file, tmp_path):
    _, preview, _ = run("preview", request_file)
    request_file.write_text(
        json.dumps({"edits": [{"of": "people", "uid": 100, "set": {"finishing": 20}}]})
    )
    target = tmp_path / "Sharper.fmf"

    status, _, error = run("write", request_file, target, "--approved", code_in(preview))

    assert status == 1
    assert "not the one that was approved" in error
    assert not target.exists()


def test_write_never_replaces_a_file(run, request_file, tmp_path):
    _, preview, _ = run("preview", request_file)
    target = tmp_path / "Mine.fmf"
    target.write_bytes(b"hours of work")

    status, _, error = run("write", request_file, target, "--approved", code_in(preview))

    assert (status, target.read_bytes()) == (1, b"hours of work")
    assert "already exists" in error


def test_write_wants_the_ending_the_editor_looks_for(run, request_file, tmp_path):
    _, preview, _ = run("preview", request_file)

    status, _, error = run(
        "write", request_file, tmp_path / "Mine.dat", "--approved", code_in(preview)
    )

    assert status == 1
    assert ".fmf" in error


def test_write_needs_an_approval_code(run, request_file, tmp_path):
    with pytest.raises(SystemExit):
        run("write", request_file, tmp_path / "Mine.fmf")


def test_explain_says_what_a_file_does(run, request_file, tmp_path):
    _, preview, _ = run("preview", request_file)
    target = tmp_path / "Sharper.fmf"
    run("write", request_file, target, "--approved", code_in(preview))

    _, lines, _ = run("explain", target)
    _, found, _ = run("explain", target, "--find", "bravo")

    assert "Person: 1 change to 1 record" in lines
    assert "  Alfa Striker (100): Finishing = 17" in lines
    assert found[-1] == "No change mentions 'bravo'"


@pytest.mark.parametrize(
    "content", ["{", "[]", '{"edits": [{"of": "people", "uid": 4242, "set": {"finishing": 3}}]}']
)
def test_a_request_that_cannot_be_used_is_an_error(run, request_file, content):
    request_file.write_text(content)

    status, lines, error = run("preview", request_file)

    assert (status, lines) == (1, [])
    assert error.startswith("error: ")


def test_a_name_given_twice_in_a_request_is_an_error(run, request_file):
    request_file.write_text(
        '{"edits": [{"of": "people", "uid": 100, "set": {"finishing": 3, "finishing": 4}}]}'
    )

    status, _, error = run("preview", request_file)

    assert status == 1
    assert "finishing" in error


@pytest.mark.parametrize("limit", ["0", "-1", "many"])
def test_limits_are_one_or_more(run, request_file, limit):
    with pytest.raises(SystemExit):
        run("find", "SELECT 1", "--limit", limit)
    with pytest.raises(SystemExit):
        run("preview", request_file, "--examples", limit)


def test_a_file_that_does_not_exist_is_an_error(run, tmp_path):
    status, _, error = run("explain", tmp_path / "Nowhere.fmf")

    assert status == 1
    assert "Nowhere.fmf" in error


def test_an_editor_that_is_not_there_is_an_error(tmp_path, capsys):
    status = main(
        ["--editor", str(tmp_path), "--cache", str(tmp_path / "c.sqlite"), "find", "SELECT 1"]
    )

    assert status == 1
    assert "error: " in capsys.readouterr().err
