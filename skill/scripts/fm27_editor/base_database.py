"""A local SQLite copy of the base database for lookups, rebuilt when the Editor's files change."""

import hashlib
import os
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from fm27_editor import award_lookup, place_lookup
from fm27_editor.award_lookup import insert_awards
from fm27_editor.binary import FormatError
from fm27_editor.dat_tables import read_stream, read_string_table, read_tables
from fm27_editor.people import Names, Person, iter_people, parse_basic_people
from fm27_editor.person_fields import FIELD_NAMES
from fm27_editor.place_lookup import insert_places

DATABASE_PATTERN = "shared/data/database/db/*/*_fm"
SOURCE_FILES = [
    "basic_people_db.dat",
    "people_db.dat",
    "client_db.dat",
    "server_db.dat",
    "lang_db.dat",
]
BATCH = 5_000
CLIENT_TABLES = place_lookup.CLIENT_TABLES | award_lookup.CLIENT_TABLES
SERVER_TABLES = place_lookup.SERVER_TABLES | award_lookup.SERVER_TABLES
LANGUAGE_TABLES = place_lookup.LANGUAGE_TABLES | award_lookup.LANGUAGE_TABLES


class DatabaseError(FormatError):
    """The Editor's base database is missing or cannot be turned into a lookup."""


def open_database(editor_dir: Path, cache_path: Path) -> sqlite3.Connection:
    """A read-only connection to the cached lookup, built first when it is missing or out of date.

    The `people` view has one row per person with the names of the nation and the club. Attributes
    that the database leaves to the game are NULL.
    """
    source = _database_folder(editor_dir)
    fingerprint = f"{_code_fingerprint()}|{_fingerprint(source)}"
    if not _is_current(cache_path, fingerprint):
        _build(source, cache_path, fingerprint)
    lookup = sqlite3.connect(f"{cache_path.resolve().as_uri()}?mode=ro", uri=True)
    # Read-only covers this file alone; a query could attach another one and write there.
    lookup.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    return lookup


def record_name(lookup: sqlite3.Connection, table: str, uid: int) -> str | None:
    """The name of a person, club, or nation."""
    row = lookup.execute(f"SELECT name FROM {table} WHERE uid = ?", (uid,)).fetchone()
    return None if row is None else row[0]


def _database_folder(editor_dir: Path) -> Path:
    """The newest database: its folder is named by number, such as 2700/2700_fm."""
    folders = [folder for folder in editor_dir.glob(DATABASE_PATTERN) if folder.is_dir()]
    if not folders:
        raise DatabaseError(f"no base database folder under {editor_dir}")
    return max(folders, key=lambda folder: folder.parent.name)


def _code_fingerprint() -> str:
    """The library itself, so a change to the parsing or columns rebuilds the cache."""
    sources = sorted(Path(__file__).parent.glob("*.py"))
    return hashlib.sha256(b"".join(path.read_bytes() for path in sources)).hexdigest()


def _fingerprint(source: Path) -> str:
    try:
        stats = [(source / name).stat() for name in SOURCE_FILES]
    except FileNotFoundError as error:
        raise DatabaseError(f"a base database file is missing: {error.filename}") from error
    return "|".join(f"{stat.st_size}:{stat.st_mtime_ns}" for stat in stats)


def _is_current(cache_path: Path, fingerprint: str) -> bool:
    """Whether the cache matches. A file that is not a cache is an error and stays untouched."""
    if not cache_path.exists():
        return False
    with closing(sqlite3.connect(f"{cache_path.resolve().as_uri()}?mode=ro", uri=True)) as cache:
        try:
            row = cache.execute("SELECT fingerprint FROM meta").fetchone()
        except sqlite3.DatabaseError as error:
            raise DatabaseError(f"{cache_path.name} is not a lookup cache") from error
    return row == (fingerprint,)


def _build(source: Path, cache_path: Path, fingerprint: str) -> None:
    """Build beside the cache and swap it in whole, so a failed build leaves no half-filled one."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    partial = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.partial")
    partial.unlink(missing_ok=True)
    try:
        _fill(partial, source, fingerprint)
        os.replace(partial, cache_path)
    finally:
        partial.unlink(missing_ok=True)


def _fill(path: Path, source: Path, fingerprint: str) -> None:
    basic = parse_basic_people(read_stream(source / "basic_people_db.dat"))
    name_tables = [f"name_table_extra_{i}" for i in range(3)]
    client = read_tables(source / "client_db.dat", {*name_tables, *CLIENT_TABLES})
    server = read_tables(source / "server_db.dat", SERVER_TABLES)
    language = read_tables(source / "lang_db.dat", LANGUAGE_TABLES)
    names = Names(*(read_string_table(client[name]) for name in name_tables))
    content = read_stream(source / "people_db.dat")
    with closing(sqlite3.connect(path)) as cache, cache:
        _create_tables(cache)
        cache.execute("INSERT INTO meta VALUES (?)", (fingerprint,))
        insert_places(cache, client, server, language)
        insert_awards(cache, client, server, language, [person.uid for person in basic])
        _insert_people(cache, iter_people(basic, content, names))
        cache.executescript(
            "CREATE INDEX person_nation ON person(nation_uid);"
            "CREATE INDEX person_club ON person(club_uid);"
            "CREATE INDEX person_birth ON person(birth_date);"
            "CREATE INDEX person_name ON person(name);"
        )


def _create_tables(cache: sqlite3.Connection) -> None:
    columns = ", ".join(f"{name} INTEGER" for name in FIELD_NAMES)
    cache.executescript(
        f"CREATE TABLE meta(fingerprint TEXT);{place_lookup.SCHEMA}{award_lookup.SCHEMA}"
        "CREATE TABLE person(uid INTEGER PRIMARY KEY, kind TEXT, name TEXT, full_name TEXT,"
        " birth_date TEXT, nation_uid INTEGER, club_uid INTEGER, ca INTEGER, pa INTEGER,"
        f" {columns});"
        "CREATE VIEW people AS SELECT person.*, nation.name AS nation, club.name AS club,"
        " club.gender AS club_gender, club.division_uid, competition.name AS division"
        " FROM person LEFT JOIN nation ON nation.uid = person.nation_uid"
        " LEFT JOIN club ON club.uid = person.club_uid"
        " LEFT JOIN competition ON competition.uid = club.division_uid;"
    )


def _insert_people(cache: sqlite3.Connection, people: Iterable[Person]) -> None:
    placeholders = ", ".join("?" * (9 + len(FIELD_NAMES)))
    statement = f"INSERT INTO person VALUES ({placeholders})"
    batch = []
    for person in people:
        batch.append(
            (
                person.uid,
                person.kind.name.lower(),
                person.name,
                person.full_name,
                person.birth_date.isoformat(),
                person.nation_uid,
                person.club_uid,
                person.ca,
                person.pa,
                *(person.fields.get(name) for name in FIELD_NAMES),
            )
        )
        if len(batch) == BATCH:
            cache.executemany(statement, batch)
            batch.clear()
    cache.executemany(statement, batch)
