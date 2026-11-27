"""A fictional Editor install: a small base database and field definitions, built for tests."""

from pathlib import Path

import synthetic
from fictional_rules import write_rules

PEOPLE = [
    (0, 100, "Alfa Striker", 2004, 120, (51, 9002), (1, 9101)),
    (1, 101, "Bravo Keeper", 2008, 60, (41, 9001), (0, 9102)),
]
PLAYER_KIND, STAFF_KIND = 2, 1

NATIONS = {9001: "Englandia", 9002: "Norwegia"}
LANGUAGES = {8: "Englandish", 22: "Norwegish"}
CITIES = {9301: ("Testby", 0), 9302: ("Testham", 1)}
CONTINENTS = {1: "Testica", 3: "Europia"}
INJURIES = {1: "cold", 6: "twisted ankle"}
WEATHER = {1: "Testish Coastal", 115052: "Testish Inland"}
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

AWARDS = {
    9501: (
        "Example Player of the Year",
        "Player",
        {"nation": 0, "competition": 0, "previous_winner": 3},
    ),
    9502: ("Example Women's Player", "Women", {"female": True}),
}
NOBODY = synthetic.NO_INDEX
# By award and year, as in synthetic.award_year_record. A national team has the uid of the nation.
AWARD_YEARS = [
    (
        9601,
        synthetic.award_year_record(
            0,
            2024,
            (0, "Alfa Striker", 9101, 47, 0, 20, 1, 64),
            (NOBODY, "Old Master", 9102, 22, 3000, 0, 0, 0),
            (NOBODY, "Cup Hero", 9001, 9, 0, 33, 0, 0),
        ),
    ),
    (9602, synthetic.award_year_record(0, 2020, not_held=True)),
    (
        9603,
        synthetic.award_year_record(1, 2024, (NOBODY, "Bravo Keeper", 9103, 0, 0, 0, NOBODY, 0)),
    ),
    (9604, synthetic.award_year_record(0, 2023, (NOBODY, "Old Master", 9102, 30, 0, 0, 0, 0))),
]

SECOND_NATIONS = synthetic.list_items(
    synthetic.field_definition("nati", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition(
        "ntin",
        "Nationality Info",
        "enum",
        '<list id="enum_values">'
        '<record enum="80"><string id="name" value="Eligible For Nation" /></record>'
        '<record enum="85"><string id="name" value="Born In Nation" /></record></list>',
    ),
)
FAVOURITE_CLUBS = synthetic.list_items(
    synthetic.field_definition("club", "Club", *synthetic.reference("club")),
    synthetic.field_definition(
        "rrea",
        "Reason",
        "enum",
        '<list id="enum_values"><record enum="1"><string id="name" value="Supporter" /></record>'
        "</list>",
    ),
    synthetic.field_definition("leve", "Level", "integer", synthetic.number_range(0, 100)),
)
DAYS_AT_CLUB = synthetic.list_items(
    synthetic.field_definition("Ttea", "Club Or Nation", *synthetic.reference("team")),
    synthetic.field_definition("days", "Days", "integer", synthetic.number_range(0, 30000)),
    *(
        synthetic.field_definition(code, "Between Ages", "boolean")
        for code in ("0t21", "d152", "bfat", "etto", "0t19", "d021")
    ),
)
FAVOURITE_PEOPLE = synthetic.list_items(
    synthetic.field_definition("pers", "Person", *synthetic.reference("person")),
    synthetic.field_definition("leve", "Level", "integer", synthetic.number_range(0, 100)),
    synthetic.field_definition(
        "rrea",
        "Reason",
        "enum",
        '<list id="enum_values"><record enum="1"><string id="name" value="Parent" /></record>'
        "</list>",
    ),
    synthetic.field_definition("perm", "Permanent", "boolean"),
)
ADDITIONAL_LANGUAGES = synthetic.list_items(
    synthetic.field_definition("lang", "Language", *synthetic.reference("language")),
    synthetic.field_definition("prof", "Proficiency", "integer", synthetic.number_range(0, 10)),
    synthetic.field_definition(
        "proe",
        "Proficiency Description",
        "enum",
        '<list id="enum_values"><record enum="2"><string id="name" value="Fluent" /></record>'
        '<record enum="3"><string id="name" value="Good" /></record></list>',
    ),
    synthetic.field_definition("csln", "Cannot Speak Language", "boolean"),
)
PERSON = synthetic.definition_file(
    "pers",
    synthetic.field_definition("PElg", "Additional Languages", "list", ADDITIONAL_LANGUAGES),
    synthetic.field_definition("PNRs", "Second Nations", "list", SECOND_NATIONS),
    synthetic.field_definition("Pfvc", "Favourite Clubs", "list", FAVOURITE_CLUBS),
    synthetic.field_definition("Pdcn", "Days At Club/In Nation", "list", DAYS_AT_CLUB),
    synthetic.field_definition("Pfvp", "Favourite People", "list", FAVOURITE_PEOPLE),
    synthetic.field_definition("Ptyp", "Person Type", "enum"),
    synthetic.field_definition("Pfna", "First Name", "string"),
    synthetic.field_definition("Psna", "Second Name", "string"),
    synthetic.field_definition("Pdob", "Date Of Birth", "date"),
    synthetic.field_definition("Pnti", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("Pcti", "Club", *synthetic.reference("team")),
    synthetic.field_definition("Pcbi", "City Of Birth", *synthetic.reference("city")),
    synthetic.field_definition("dfln", "Default Language", *synthetic.reference("language")),
    synthetic.field_definition("Page", "Age", "integer", synthetic.number_range(0, 99)),
    synthetic.field_definition("Phes", "Height", "integer", synthetic.number_range(0, 210)),
    synthetic.field_definition("Pcwg", "Wage", "cash", synthetic.number_range(0, 3_500_000)),
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
    synthetic.field_definition("PbvE", "Transfer Value", "cash"),
    synthetic.field_definition(
        "Pbnl",
        "Bans",
        "list",
        synthetic.list_items(synthetic.field_definition("matc", "Matches", "integer")),
    ),
)
NON_PLAYER = synthetic.definition_file(
    "nnpl",
    synthetic.field_definition(
        "Ncra", "Current Ability", "integer", synthetic.number_range(0, 200)
    ),
)

GENDERS = (
    "enum",
    '<list id="enum_values">'
    '<record enum="male" enum_id="0"><string id="name" value="Male" /></record>'
    '<record enum="female" enum_id="1"><string id="name" value="Female" /></record></list>',
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
    synthetic.field_definition("PLgn", "Player Gender", *GENDERS),
    synthetic.field_definition("Snam", "Stadium Name", "string"),
    synthetic.field_definition("CHAa", "Highest", "integer", synthetic.number_range(0, 100)),
    synthetic.field_definition("Cffy", "Five Year Total", "real", synthetic.number_range(0, 200)),
    synthetic.field_definition("Cmni", "Manager", *synthetic.reference("person")),
    synthetic.field_definition("Tcap", "Captain", *synthetic.reference("person")),
)
COMPETITION = synthetic.definition_file(
    "comp",
    synthetic.field_definition("cnam", "Name", "string"),
    synthetic.field_definition("csnm", "Short Name", "string"),
    synthetic.field_definition("cnti", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("cpcm", "Parent Competition", *synthetic.reference("competition")),
    synthetic.field_definition("dbty", "Type", "enum", '<flags id="enum_values" value="cdbt" />'),
    synthetic.field_definition("levl", "Level", "integer", synthetic.number_range(1, 20)),
    synthetic.field_definition("PLgn", "Player Gender", *GENDERS),
)

PREVIOUS_WINNER = (
    "enum",
    '<list id="enum_values">'
    '<record enum="0"><string id="name" value="Not Set" /></record>'
    '<record enum="1"><string id="name" value="Never" /></record>'
    '<record enum="3"><string id="name" value="Yes" /></record></list>',
)
AWARD_HISTORY = synthetic.list_items(
    synthetic.field_definition("AHye", "Year", "integer", synthetic.number_range(1800, 2100)),
    *(
        definition
        for number in (1, 2, 3)
        for definition in (
            synthetic.field_definition(f"AH{number}p", "Placed", *synthetic.reference("person")),
            synthetic.field_definition(f"AH{number}n", "Placed Name", "string"),
            synthetic.field_definition(f"AH{number}t", "Team", *synthetic.reference("team")),
            synthetic.field_definition(
                f"AH{number}i", "Info", "integer", synthetic.number_range(1, 5000)
            ),
            synthetic.field_definition(
                f"A{number}i2", "Info 2", "integer", synthetic.number_range(1, 5000)
            ),
            synthetic.field_definition(
                f"A{number}ag", "Age", "integer", synthetic.number_range(14, 120)
            ),
            synthetic.field_definition(f"AH{number}c", "Nation", *synthetic.reference("nation")),
            synthetic.field_definition(
                f"AHp{number}", "Position", "enum", '<flags id="enum_values" value="posm" />'
            ),
        )
    ),
    synthetic.field_definition("AHnd", "No Data For Year", "boolean"),
    synthetic.field_definition("Ahnt", "Did Not Take Place", "boolean"),
)
AWARD = synthetic.definition_file(
    "awar",
    synthetic.field_definition("dbnm", "Name", "string"),
    synthetic.field_definition("AWna", "Name", "string", synthetic.flag("is_client_field")),
    synthetic.field_definition("AWsn", "Short Name", "string", synthetic.flag("is_client_field")),
    synthetic.field_definition("AWci", "Continent", *synthetic.reference("continent")),
    synthetic.field_definition("AWni", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("AWmi", "Competition", *synthetic.reference("competition")),
    synthetic.field_definition("AWxa", "Maximum Age", "integer", synthetic.number_range(10, 99)),
    synthetic.field_definition(
        "AWap", "Allow Previous Winner", *PREVIOUS_WINNER, synthetic.flag("is_client_field")
    ),
    synthetic.field_definition("AWsh", "History", "list", AWARD_HISTORY),
)

STADIUM = synthetic.definition_file(
    "stad",
    synthetic.field_definition("Snam", "Name", "string"),
    synthetic.field_definition("Scti", "City", *synthetic.reference("city")),
    synthetic.field_definition("Scpy", "Capacity", "integer", synthetic.number_range(0, 200000)),
    synthetic.field_definition("Secy", "Seating Capacity", "integer"),
    synthetic.field_definition("Slat", "Latitude", "real"),
)
NATION = synthetic.definition_file(
    "nati",
    synthetic.field_definition("Nnam", "Name", "string"),
    synthetic.field_definition("Necf", "Economic Factor", "integer", synthetic.number_range(1, 20)),
    synthetic.field_definition("Nnsi", "National Stadium", *synthetic.reference("stadium")),
)
CITY = synthetic.definition_file(
    "city",
    synthetic.field_definition("Cnam", "Name", "string"),
    synthetic.field_definition("Cnti", "Nation", *synthetic.reference("nation")),
    synthetic.field_definition("Clgi", "Language", *synthetic.reference("language")),
    synthetic.field_definition("Catt", "Attraction", "integer", synthetic.number_range(0, 20)),
    synthetic.field_definition("Clat", "Latitude", "real"),
    synthetic.field_definition("Cwea", "Weather", *synthetic.reference("weather")),
)
CONTINENT = synthetic.definition_file(
    "cont",
    synthetic.field_definition("Cnam", "Name", "string"),
    synthetic.field_definition("Crgs", "Regional Strength", "real"),
    synthetic.field_definition("DBvw", "", "enum", '<flags id="enum_values" value="mood" />'),
)
INJURY = synthetic.definition_file(
    "inju",
    synthetic.field_definition("Inam", "Name", "string"),
    synthetic.field_definition(
        "Iocr", "Occurrence Ratio", "real", '<integer id="min" value="0" />'
    ),
    synthetic.field_definition(
        "Imip", "Match Injury Percentage", "integer", synthetic.number_range(0, 100)
    ),
)
WEATHER_DEFINITIONS = synthetic.definition_file(
    "weat",
    synthetic.field_definition("wnam", "Name", "string"),
    synthetic.field_definition("w0p0", "Dry", "integer", synthetic.number_range(0, 100)),
)
SHARED_CHOICES = synthetic.enum_file(
    dbts={
        **{0: "Award", 1: "Person", 2: "City", 3: "Club", 9: "National Team", 10: "Nation"},
        **{5: "Continent", 6: "Injury", 21: "Stadium", 25: "Competition", 27: "Weather"},
        99: "Moon",
    },
    mood={0: "Calm", 2: "Cross"},
    cdbt={0: "Top Division", 2: "Main Cup"},
    posm={64: "Wing-Back Left"},
)


def write_editor(folder: Path, people=None) -> Path:
    write_definitions(folder)
    write_rules(folder)
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
        "award": AWARD,
        "stadium": STADIUM,
        "nation": NATION,
        "city": CITY,
        "continent": CONTINENT,
        "injury": INJURY,
        "weather": WEATHER_DEFINITIONS,
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
    (database / "lang_db.dat").write_bytes(synthetic.dat_container("lang_db", name_tables()))
    return folder


def client_tables() -> list[tuple[str, bytes]]:
    records = {
        "table_9": [(uid, b"nation") for uid in NATIONS],
        # The base database has a table beside the nations with almost the same uids, in an order
        # that differs at one place. Records refer to nations by their place in table 9.
        "table_10": [(uid, b"other") for uid in reversed(NATIONS)],
        "table_8": [(uid, synthetic.language_record(name)) for uid, name in LANGUAGES.items()],
        "table_27": [(uid, synthetic.weather_record(name)) for uid, name in WEATHER.items()],
        "table_5": [(uid, b"continent") for uid in CONTINENTS],
        "table_6": [(uid, b"\x00\x0c\x30\x00") for uid in INJURIES],
        "table_2": [(uid, synthetic.city_record(nation)) for uid, (_, nation) in CITIES.items()],
        "table_21": [(uid, synthetic.stadium_record(city)) for uid, (_, city) in STADIUMS.items()],
        "table_25": [
            (uid, synthetic.competition_record(**facts))
            for uid, (_, _, facts, _) in COMPETITIONS.items()
        ],
        "table_0": [
            (uid, synthetic.award_record(**facts)) for uid, (_, _, facts) in AWARDS.items()
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
        ("table_12", synthetic.record_table(AWARD_YEARS)),
    ]


def name_tables() -> list[tuple[str, bytes]]:
    return [
        ("8_9", synthetic.nation_names(NATIONS)),
        ("8_3", synthetic.club_names({uid: club[:2] for uid, club in CLUBS.items()})),
        ("8_25", synthetic.competition_names({uid: c[:2] for uid, c in COMPETITIONS.items()})),
        ("8_0", synthetic.award_names({uid: award[:2] for uid, award in AWARDS.items()})),
        ("8_2", synthetic.city_names({uid: name for uid, (name, _) in CITIES.items()})),
        ("8_21", synthetic.stadium_names({uid: name for uid, (name, _) in STADIUMS.items()})),
        ("8_5", synthetic.continent_names(CONTINENTS)),
        ("8_6", synthetic.injury_names(INJURIES)),
    ]
