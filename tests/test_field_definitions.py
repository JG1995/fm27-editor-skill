import pytest

import synthetic
from fm27_editor.definition_files import FieldDefinitionError
from fm27_editor.field_definitions import read_field_names, read_fields, read_shared_choices

ENUMS = synthetic.enum_file(mood={0: "Calm", 2: "Cross", -1: "Unknown"})


def editor_folder(tmp_path, *fields, enums=ENUMS):
    files = {"person": synthetic.definition_file("pers", *fields)}
    path = tmp_path / "shared" / "data" / "editor.fmf"
    path.parent.mkdir(parents=True)
    path.write_bytes(synthetic.definitions_container(files, enums))
    return tmp_path


def read_one(tmp_path, *parts):
    folder = editor_folder(tmp_path, synthetic.field_definition(*parts))
    (field,) = read_fields(folder, "person").values()
    return field


def test_a_number_field_has_its_name_and_range(tmp_path):
    field = read_one(tmp_path, "Zjmp", "Jump", "integer", synthetic.number_range(-5, 20))

    assert (field.code, field.name, field.type) == ("Zjmp", "Jump", "integer")
    assert (field.lowest, field.highest) == (-5, 20)


def test_a_note_to_translators_is_not_part_of_the_name(tmp_path):
    field = read_one(tmp_path, "Zjmp", "Jump[COMMENT: how high; CHARLIMIT: None]", "string")

    assert field.name == "Jump"


def test_choices_listed_in_the_field_are_read_by_number(tmp_path):
    listed = (
        '<list id="enum_values">'
        '<record enum="3"><translation id="name" value="Three" /></record>'
        '<record enum="-2"><string id="name" value="Minus two" /></record></list>'
    )

    field = read_one(tmp_path, "Zenm", "Pick", "enum", listed)

    assert field.choices == {3: "Three", -2: "Minus two"}


@pytest.mark.parametrize("element", ["flags", "string"])
def test_choices_shared_between_fields_are_found_by_name(tmp_path, element):
    field = read_one(
        tmp_path, "Zmod", "Mood", "enum", f'<{element} id="enum_values" value="mood" />'
    )

    assert field.choices == {0: "Calm", 2: "Cross", -1: "Unknown"}


def test_a_choice_whose_value_is_a_word_uses_its_number(tmp_path):
    listed = (
        '<list id="enum_values">'
        '<record enum="false" enum_id="0"><string id="name" value="No" /></record>'
        '<record enum="true" enum_id="1"><string id="name" value="Yes" /></record></list>'
    )

    field = read_one(tmp_path, "Zyes", "Yes or no", "enum", listed)

    assert field.choices == {0: "No", 1: "Yes"}


def test_choices_without_numbers_are_left_out(tmp_path):
    listed = '<list id="enum_values"><record enum="reserves"></record></list>'

    assert read_one(tmp_path, "Zwrd", "Word", "enum", listed).choices is None


def test_the_kind_of_record_a_field_points_to_is_read(tmp_path):
    table = '<flags id="database_table_type" value="nation" />'

    field = read_one(tmp_path, "Znat", "Nation", "database_record_unique_id", table)

    assert field.points_to == "nation"


def test_a_list_has_the_fields_of_its_items_in_order(tmp_path):
    items = synthetic.list_items(
        synthetic.field_definition("Zyer", "Year", "integer", synthetic.number_range(1800, 2100)),
        synthetic.field_definition("Znat", "Nation", *synthetic.reference("nation")),
        synthetic.field_definition(
            "Zmod", "Mood", "enum", '<flags id="enum_values" value="mood" />'
        ),
    )

    field = read_one(tmp_path, "Zlst", "Past", "list", items)

    assert [(item.code, item.type, item.highest) for item in field.items] == [
        ("Zyer", "integer", 2100),
        ("Znat", "database_record_unique_id", None),
        ("Zmod", "enum", None),
    ]
    assert field.items[1].points_to == "nation"
    assert field.items[2].choices == {0: "Calm", 2: "Cross", -1: "Unknown"}


def test_a_field_that_is_no_list_has_no_items(tmp_path):
    assert read_one(tmp_path, "Zjmp", "Jump", "string").items == ()


def test_client_and_language_fields_are_marked(tmp_path):
    folder = editor_folder(
        tmp_path,
        synthetic.field_definition("Zcli", "A", "string", synthetic.flag("is_client_field")),
        synthetic.field_definition("Zlan", "B", "string", synthetic.flag("is_language_field")),
        synthetic.field_definition("Zpln", "C", "string"),
    )

    fields = read_fields(folder, "person")

    assert [f.is_client_field for f in fields.values()] == [True, False, False]
    assert [f.is_language_field for f in fields.values()] == [False, True, False]


@pytest.mark.parametrize("mark", ["is_read_only", "is_ige_only", "debug_only"])
def test_a_field_the_editor_does_not_offer_cannot_be_edited(tmp_path, mark):
    assert not read_one(tmp_path, "Zhid", "Hidden", "integer", synthetic.flag(mark)).is_editable


def test_an_ordinary_field_can_be_edited(tmp_path):
    off = '<boolean id="is_read_only" value="false" />'

    assert read_one(tmp_path, "Zord", "Ordinary", "integer", off).is_editable


def test_entries_without_a_code_or_type_are_skipped(tmp_path):
    button = '<record><string id="name" value="A heading" /></record>'
    folder = editor_folder(tmp_path, button, synthetic.field_definition("Zord", "A", "string"))

    assert list(read_fields(folder, "person")) == ["Zord"]


def test_a_code_defined_twice_alike_is_one_field_with_the_marks_of_both(tmp_path):
    first = synthetic.field_definition(
        "Ztwo", "Colour", "colour", synthetic.flag("is_client_field")
    )
    second = synthetic.field_definition("Ztwo", "Title Colour", "colour")

    for number, fields in enumerate([(first, second), (second, first)]):
        (field,) = read_fields(editor_folder(tmp_path / str(number), *fields), "person").values()
        assert field.is_client_field


def test_a_code_defined_twice_differently_is_refused(tmp_path):
    folder = editor_folder(
        tmp_path,
        synthetic.field_definition("Ztwo", "Twice", "string"),
        synthetic.field_definition("Ztwo", "Twice", "integer"),
    )

    with pytest.raises(FieldDefinitionError, match="Ztwo"):
        read_fields(folder, "person")


def test_a_missing_definition_file_is_reported(tmp_path):
    folder = editor_folder(tmp_path)

    with pytest.raises(FieldDefinitionError, match="stadium"):
        read_fields(folder, "stadium")


def test_an_editor_folder_without_definitions_is_reported(tmp_path):
    with pytest.raises(FieldDefinitionError, match="editor.fmf"):
        read_fields(tmp_path, "person")


def test_unreadable_definitions_are_reported(tmp_path):
    folder = editor_folder(tmp_path, "<record>")

    with pytest.raises(FieldDefinitionError, match="person.xml"):
        read_fields(folder, "person")


def test_a_range_that_is_not_a_number_is_reported(tmp_path):
    with pytest.raises(FieldDefinitionError, match="min_value"):
        read_one(tmp_path, "Zjmp", "Jump", "integer", '<integer id="min_value" value="low" />')


def test_a_range_of_fractions_is_not_read_as_whole_numbers(tmp_path):
    field = read_one(tmp_path, "Zfrc", "Share", "real", '<real id="min_value" value="0.5" />')

    assert field.lowest is None


def test_a_definitions_file_of_another_version_is_reported_by_name(tmp_path):
    path = tmp_path / "shared" / "data" / "editor.fmf"
    path.parent.mkdir(parents=True)
    path.write_bytes(synthetic.container("editor", [], encrypted=False, version=9))

    with pytest.raises(FieldDefinitionError, match="editor.fmf: .*version 9"):
        read_fields(tmp_path, "person")


def test_names_leave_out_a_code_that_has_two_of_them(tmp_path):
    folder = editor_folder(
        tmp_path,
        synthetic.field_definition("Ztwo", "First", "string"),
        synthetic.field_definition("Ztwo", "Second", "string"),
        synthetic.field_definition("Zone", "Single", "string"),
        synthetic.field_definition("Zone", "Single", "string"),
    )

    assert read_field_names(folder, "person") == {"Zone": "Single"}


def a_job(tmp_path, jobs):
    enums = synthetic.enum_file("mdbj", "mdjz", "mdnj", ftjn={5: "Boss", 9: "Spotter"})
    job = synthetic.field_definition(
        "Zjob", "Job", "enum", f'<flags id="enum_values" value="{jobs}" />'
    )
    (field,) = read_fields(editor_folder(tmp_path, job, enums=enums), "person").values()
    return field


@pytest.mark.parametrize("jobs", ["mdbj", "mdjz"])
def test_jobs_the_editor_fills_in_itself_are_those_it_names_for_responsibilities(tmp_path, jobs):
    assert a_job(tmp_path, jobs).choices == {5: "Boss", 9: "Spotter"}


def test_jobs_at_a_nation_have_no_choices(tmp_path):
    assert a_job(tmp_path, "mdnj").choices is None


def test_shared_choices_are_read_by_name(tmp_path):
    assert read_shared_choices(editor_folder(tmp_path), "mood") == {
        0: "Calm",
        2: "Cross",
        -1: "Unknown",
    }


def test_shared_choices_that_do_not_exist_are_reported(tmp_path):
    with pytest.raises(FieldDefinitionError, match="weather"):
        read_shared_choices(editor_folder(tmp_path), "weather")
