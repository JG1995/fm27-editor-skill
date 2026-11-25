"""A fictional Editor install: a small base database and field definitions, built for tests."""

from pathlib import Path

import synthetic

PEOPLE = [
    (0, 100, "Alfa Striker", 2004, 120, (51, 9002), (1, 9101)),
    (1, 101, "Bravo Keeper", 2008, 60, (41, 9001), (0, 9102)),
]
PLAYER_KIND, STAFF_KIND = 2, 1

PERSON = synthetic.definition_file(
    "pers",
    synthetic.field_definition("Ptyp", "Person Type", "enum"),
    synthetic.field_definition("Pfna", "First Name", "string"),
    synthetic.field_definition("Psna", "Second Name", "string"),
    synthetic.field_definition("Pdob", "Date Of Birth", "date"),
    synthetic.field_definition(
        "Pnti",
        "Nation",
        "database_record_unique_id",
        '<flags id="database_table_type" value="nation" />',
    ),
    synthetic.field_definition(
        "Pcti",
        "Club",
        "database_record_unique_id",
        '<flags id="database_table_type" value="team" />',
    ),
    synthetic.field_definition(
        "Pcbi",
        "City Of Birth",
        "database_record_unique_id",
        '<flags id="database_table_type" value="city" />',
    ),
    synthetic.field_definition("Page", "Age", "integer", synthetic.number_range(0, 99)),
    synthetic.field_definition("Phes", "Height", "integer", synthetic.number_range(0, 210)),
)
PLAYER = synthetic.definition_file(
    "play",
    synthetic.field_definition(
        "PCAB", "Current Ability", "integer", synthetic.number_range(0, 200)
    ),
    synthetic.field_definition(
        "PPAB", "Potential Ability", "integer", synthetic.number_range(-100, 200)
    ),
    synthetic.field_definition(
        "PPAR",
        "Potential Ability Range",
        "enum",
        '<list id="enum_values"><record enum="-8" /><record enum="-95" /></list>',
    ),
    synthetic.field_definition("PDfn", "Finishing", "attribute"),
)
NON_PLAYER = synthetic.definition_file(
    "nnpl",
    synthetic.field_definition(
        "Ncra", "Current Ability", "integer", synthetic.number_range(0, 200)
    ),
)


def write_editor(folder: Path, people=None) -> Path:
    write_definitions(folder)
    return write_database(folder, people)


def write_definitions(folder: Path, person: bytes = PERSON) -> Path:
    path = folder / "shared" / "data" / "editor.fmf"
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {"person": person, "player": PLAYER, "non player": NON_PLAYER}
    path.write_bytes(synthetic.definitions_container(files, synthetic.enum_file()))
    return folder


def write_database(folder: Path, people=None) -> Path:
    """People as (index, uid, name, birth year, ability, nation, club[, kind])."""
    database = folder / "shared/data/database/db/2700/2700_fm"
    database.mkdir(parents=True, exist_ok=True)
    people = [(*person, PLAYER_KIND)[:8] for person in people or PEOPLE]
    basic = [
        synthetic.basic_person(
            kind, index, uid, ca=ca, pa=ca + 20, nation=nation, club=club, birth_year=year
        )
        for index, uid, _, year, ca, nation, club, kind in people
    ]
    records = [
        synthetic.person_record(
            index,
            uid,
            full_name=name,
            year=year,
            nation=nation,
            attributes={52: 15, 84: 13},
            kind=kind,
        )
        for index, uid, name, year, ca, nation, club, kind in people
    ]
    (database / "basic_people_db.dat").write_bytes(
        synthetic.dat_file(synthetic.basic_people(basic))
    )
    (database / "people_db.dat").write_bytes(
        synthetic.dat_file(synthetic.people_stream(records, len(records)))
    )
    (database / "client_db.dat").write_bytes(
        synthetic.dat_container(
            "client_db",
            [
                ("name_table_extra_0", synthetic.string_table({1: "Testy"})),
                ("name_table_extra_1", synthetic.string_table({2: "McTestface"})),
                ("name_table_extra_2", synthetic.string_table({5: "Testo"})),
                (
                    "table_3",
                    synthetic.club_table(
                        [(9101, "Fictional City", "Fic City"), (9102, "Example United", "Example")]
                    ),
                ),
            ],
        )
    )
    (database / "lang_db.dat").write_bytes(
        synthetic.dat_container(
            "lang_db", [("8_9", synthetic.nation_names({9001: "Englandia", 9002: "Norwegia"}))]
        )
    )
    return folder
