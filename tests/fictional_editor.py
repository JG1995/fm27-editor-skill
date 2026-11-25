"""A fictional Editor install: a small base database and field definitions, built for tests."""

from pathlib import Path

import synthetic

PEOPLE = [
    (0, 100, "Alfa Striker", 2004, 120, (51, 9002), (1, 9101)),
    (1, 101, "Bravo Keeper", 2008, 60, (41, 9001), (0, 9102)),
]
PLAYER_KIND, STAFF_KIND = 2, 1

NATIONS = {9001: "Englandia", 9002: "Norwegia"}
CITIES = {9301: ("Testby", 0), 9302: ("Testham", 1)}
STADIUMS = {9401: ("Test Park", 0)}
COMPETITIONS = {
    9201: ("Example League", "League", {"nation": 0, "level": 1}, False),
    9202: ("Example Women's League", "Women", {"nation": 0, "level": 1}, True),
    9203: ("Example League North", "North", {"nation": 0, "parent": 0, "level": 2}, False),
    9204: ("Example Cup", "Cup", {"nation": 0}, False),
}
CLUBS = {
    9101: (
        "Fictional City",
        "Fic City",
        {"nation": 0, "based_nation": 1, "city": 0},
        {"reputation": 5_000, "division": 0, "last_division": 2, "last_position": 1, "stadium": 0},
    ),
    9102: ("Example United", "Example", {"nation": 0}, {"division": 2}),
    9103: ("Fictional City", "Fic Women", {"nation": 0, "female": True}, {"division": 1}),
    9104: ("Gone Town", "Gone", {"extinct_nation": 1}, {}),
}

PERSON = synthetic.definition_file(
    "pers",
    synthetic.field_definition("Ptyp", "Person Type", "enum"),
    synthetic.field_definition("Pfna", "First Name", "string"),
    synthetic.field_definition("Psna", "Second Name", "string"),
    synthetic.field_definition("Pdob", "Date Of Birth", "date"),
    synthetic.field_definition("Pnti", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("Pcti", "Club", *synthetic.reference("team")),
    synthetic.field_definition("Pcbi", "City Of Birth", *synthetic.reference("city")),
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
        '<list id="enum_values"><record enum="-8"><string id="name" value="130-160" /></record>'
        '<record enum="-95"><string id="name" value="160-190" /></record></list>',
    ),
    synthetic.field_definition("PDfn", "Finishing", "attribute"),
    synthetic.field_definition("Zmod", "Mood", "enum", '<flags id="enum_values" value="mood" />'),
)
NON_PLAYER = synthetic.definition_file(
    "nnpl",
    synthetic.field_definition(
        "Ncra", "Current Ability", "integer", synthetic.number_range(0, 200)
    ),
)

CLUB = synthetic.definition_file(
    "club",
    synthetic.field_definition("dbnm", "Name", "string"),
    synthetic.field_definition("Cnam", "Name", "string", synthetic.flag("is_client_field")),
    synthetic.field_definition("Csnm", "Short Name", "string"),
    synthetic.field_definition("Cnti", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("Cdvi", "Division", *synthetic.reference("competition")),
    synthetic.field_definition("Csti", "Stadium", *synthetic.reference("stadium")),
    synthetic.field_definition("Crep", "Reputation", "integer", synthetic.number_range(0, 10_000)),
    synthetic.field_definition("ttcl", "Foreground Colour", "colour"),
    synthetic.field_definition("Snam", "Stadium Name", "string"),
    synthetic.field_definition("CHAa", "Highest", "integer", synthetic.number_range(0, 100)),
)
COMPETITION = synthetic.definition_file(
    "comp",
    synthetic.field_definition("cnam", "Name", "string"),
    synthetic.field_definition("csnm", "Short Name", "string"),
    synthetic.field_definition("cnti", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("cpcm", "Parent Competition", *synthetic.reference("competition")),
    synthetic.field_definition("dbty", "Type", "enum", '<flags id="enum_values" value="cdbt" />'),
    synthetic.field_definition("levl", "Level", "integer", synthetic.number_range(1, 20)),
)

STADIUM = synthetic.definition_file(
    "stad", synthetic.field_definition("Secy", "Seating Capacity", "integer")
)
SHARED_CHOICES = synthetic.enum_file(
    dbts={1: "Person", 3: "Club", 21: "Stadium", 25: "Competition", 99: "Moon"},
    mood={0: "Calm", 2: "Cross"},
    cdbt={0: "Top Division", 2: "Main Cup"},
)


def write_editor(folder: Path, people=None) -> Path:
    write_definitions(folder)
    return write_database(folder, people)


def write_definitions(folder: Path, person: bytes = PERSON) -> Path:
    path = folder / "shared" / "data" / "editor.fmf"
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {
        "person": person,
        "player": PLAYER,
        "non player": NON_PLAYER,
        "club": CLUB,
        "comp": COMPETITION,
        "stadium": STADIUM,
    }
    path.write_bytes(synthetic.definitions_container(files, SHARED_CHOICES))
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
                *client_tables(),
            ],
        )
    )
    (database / "server_db.dat").write_bytes(synthetic.dat_container("server_db", server_tables()))
    (database / "lang_db.dat").write_bytes(synthetic.dat_container("lang_db", language_tables()))
    return folder


def client_tables() -> list[tuple[str, bytes]]:
    records = {
        "table_10": [(uid, b"nation") for uid in NATIONS],
        "table_2": [(uid, synthetic.city_record(nation)) for uid, (_, nation) in CITIES.items()],
        "table_21": [(uid, synthetic.stadium_record(city)) for uid, (_, city) in STADIUMS.items()],
        "table_25": [
            (uid, synthetic.competition_record(**facts))
            for uid, (_, _, facts, _) in COMPETITIONS.items()
        ],
        "table_3": [
            (uid, synthetic.club_record(name, short_name, **facts))
            for uid, (name, short_name, facts, _) in CLUBS.items()
        ],
    }
    return [(name, synthetic.record_table(rows)) for name, rows in records.items()]


def server_tables() -> list[tuple[str, bytes]]:
    teams = [(uid, synthetic.team_record(**facts)) for uid, (_, _, _, facts) in CLUBS.items()]
    competitions = [
        (uid, synthetic.competition_server_record(female=female))
        for uid, (_, _, _, female) in COMPETITIONS.items()
    ]
    return [
        ("table_24", synthetic.record_table(teams)),
        ("table_25", synthetic.record_table(competitions)),
    ]


def language_tables() -> list[tuple[str, bytes]]:
    return [
        ("8_9", synthetic.nation_names(NATIONS)),
        ("8_3", synthetic.club_names({uid: club[:2] for uid, club in CLUBS.items()})),
        ("8_25", synthetic.competition_names({uid: c[:2] for uid, c in COMPETITIONS.items()})),
        ("8_2", synthetic.city_names({uid: name for uid, (name, _) in CITIES.items()})),
        ("8_21", synthetic.stadium_names({uid: name for uid, (name, _) in STADIUMS.items()})),
    ]
