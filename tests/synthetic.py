"""Fictional FM editor files, built from the documented layout.

Nothing here uses the library's constants or parsers, so a wrong offset in the library fails the
tests that use these files.
"""

import struct
from compression import zstd

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = b"0123456789abcdef"
IV = b"fedcba9876543210"


def text(value: str) -> bytes:
    raw = value.encode()
    return struct.pack("<I", len(raw)) + raw


def zstd_frame(data: bytes) -> bytes:
    compressor = zstd.ZstdCompressor()
    return compressor.compress(data) + compressor.flush()


def aes_ctr(data: bytes, key: bytes = KEY, iv: bytes = IV) -> bytes:
    """Encrypt or decrypt; AES-CTR is its own inverse."""
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return cipher.update(data) + cipher.finalize()


def stored_member(data: bytes, *, compressed: bool, size_prefix: bool = False) -> bytes:
    body = zstd_frame(data) if compressed else data
    if compressed and size_prefix:
        body = struct.pack("<I", len(body)) + body
    return struct.pack("<II", 16, 16) + KEY + IV + aes_ctr(body)


def member_record(name: str, extension: str, offset: int, stored: int, unpacked: int) -> bytes:
    times = struct.pack("<QQ", 1_700_000_000, 1_700_000_001)
    return text(name) + text(extension) + struct.pack("<QQQ", offset, stored, unpacked) + times


def container(
    root: str,
    files: list[tuple[str, str, bytes]],
    *,
    storage: int = 3,
    folder: tuple[str, list[tuple[str, str, bytes]]] | None = None,
    size_prefix: bool = False,
    declared_unpacked: int | None = None,
    encrypted: bool = True,
    magic: bytes | None = None,
    version: int = 8,
) -> bytes:
    region = b""

    def record(name: str, extension: str, data: bytes) -> bytes:
        nonlocal region
        if encrypted:
            stored = stored_member(data, compressed=storage == 3, size_prefix=size_prefix)
        else:
            stored = zstd_frame(data) if storage == 3 else data
        unpacked = len(data) if declared_unpacked is None else declared_unpacked
        entry = member_record(name, extension, len(region), len(stored), unpacked)
        region += stored
        return entry

    index = text(root) + struct.pack("<I", len(files))
    index += b"".join(record(*item) for item in files)
    if folder is None:
        index += struct.pack("<I", 0)
    else:
        folder_name, folder_files = folder
        index += struct.pack("<I", 1) + text(folder_name) + struct.pack("<I", len(folder_files))
        index += b"".join(record(*item) for item in folder_files) + struct.pack("<I", 0)
    frame = zstd_frame(index)
    if size_prefix:
        frame = struct.pack("<I", len(frame)) + frame
    index_at = 26 + len(region)
    if magic is None:
        magic = b"\x02\x01afe." if encrypted else b"\x02\x01fmf."
    header = magic + struct.pack("<HB", version, 0)
    header += struct.pack("<QQ", index_at - 9, 17) + bytes([storage])
    return header + region + b"\x02\x01fmf.\x08\x00\x00" + frame


def prop(tag: str, kind: int, payload: bytes = b"") -> bytes:
    return tag.encode()[::-1] + b"\x01" + bytes([kind]) + payload


def props(*items: bytes) -> bytes:
    return struct.pack("<I", len(items)) + b"".join(items)


def change(*items: bytes) -> bytes:
    return props(*items)


def change_list(*changes: bytes, count: int | None = None) -> bytes:
    declared = len(changes) if count is None else count
    general = props(
        prop("dchc", 0x18, struct.pack("<Q", declared)),
        prop("desc", 0x1A, text("")),
        prop("vers", 0x12, struct.pack("<H", 3756)),
    )
    editor = props(prop("EdBr", 0x1A, text("fictional-branch")))
    body = general + editor + struct.pack("<I", declared) + b"".join(changes)
    return b"\x03\x01cbd.\x06\x00\x00" + zstd_frame(body)


def capacity_change(new: int) -> bytes:
    return change(
        prop("dtty", 0x11, b"\x15"),
        prop("duni", 0x0F, b"\x01\x02\x03\x04" * 2),
        prop("prty", 0x02, b"yceS"),
        prop("nwvl", 0x01, struct.pack("<i", new)),
        prop("vers", 0x12, b"\xaa\x0e"),
        prop("odvl", 0x01, struct.pack("<i", 50_000)),
    )


# --- base database -------------------------------------------------------------------------

DAT_PREFIX = b"\x03\x01tad." + b"\xa0\x0f\xa9\x0e\x09\x00"


def dat_file(content: bytes) -> bytes:
    """A database file whose body is one compressed stream."""
    return DAT_PREFIX + zstd_frame(content)


def dat_container(root: str, tables: list[tuple[str, bytes]]) -> bytes:
    """A database file whose body is a container of tables."""
    files = [(name, ".dat", data) for name, data in tables]
    return DAT_PREFIX + container(root, files, encrypted=False)


def string_table(entries: dict[int, str]) -> bytes:
    table = b"\x03\x01tad.\xa0\x0f" + struct.pack("<I", len(entries))
    for uid, value in entries.items():
        table += struct.pack("<I", uid) + text(value)
    return table


def club_table(clubs: list[tuple[int, str, str]]) -> bytes:
    """Clubs as (uid, name, short name); each ends in its index and its uid twice."""
    table = b"\x03\x01tad.\xa0\x0f" + struct.pack("<I", len(clubs))
    for index, (uid, name, short_name) in enumerate(clubs):
        table += b"\x07" * 17 + text(name) + text(short_name) + b"\x00\x00\x00"
        table += struct.pack("<III", index, uid, uid)
    return table


def nation_names(nations: dict[int, str]) -> bytes:
    table = b"\x03\x01tad.\xa9\x0e" + struct.pack("<I", len(nations)) + b"\x05\x00\x00\x00"
    for uid, name in nations.items():
        table += struct.pack("<I", uid) + text(name) + b"\xff" + text(name) + b"\xff" + b"\x09"
    return table


def basic_person(
    kind: int,
    index: int,
    uid: int,
    *,
    nation: tuple[int, int] = (3, 9001),
    club: tuple[int, int] = (9, 9101),
    reputations: tuple[int, int, int] = (10, 20, 30),
    ca: int = 120,
    pa: int = 140,
    birth_year: int = 2004,
) -> bytes:
    sizes = {1: 84, 2: 84, 3: 84, 4: 34, 5: 22}
    record = bytearray(b"\x00" * sizes[kind])
    record[0], record[1] = 0x11, kind
    if sizes[kind] == 84:
        struct.pack_into("<IIII", record, 2, *nation, *club)
        struct.pack_into("<HHHHHH", record, 42, *reputations, ca, pa & 0xFFFF, birth_year)
    struct.pack_into("<III", record, sizes[kind] - 12, index, uid, uid)
    return bytes(record)


def basic_people(records: list[bytes]) -> bytes:
    footer = struct.pack("<IBI", 0, 1, 2_000_000_000)
    return struct.pack("<I", len(records)) + b"\x00" + b"".join(records) + footer


def person_record(
    index: int,
    uid: int,
    *,
    full_name: str = "Testy McTestface",
    first: int = 1,
    second: int = 2,
    common: int = 0xFFFFFFFF,
    day: int = 60,
    year: int = 2004,
    nation: tuple[int, int] = (3, 9001),
    attributes: dict[int, int] | None = None,
    personality: bytes = b"\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11",
    decoy: bool = False,
) -> bytes:
    """A person: fixed fields from the start, then name, birth date, nation, personality, ids."""
    record = bytearray(b"\x00" * 110)
    struct.pack_into("<I", record, 0, index)
    record[4] = 2
    for offset, value in (attributes or {}).items():
        record[offset] = value
    record += b"\x03\x01" + struct.pack("<II", *nation) if decoy else b""
    name_block = struct.pack("<I", first) + b"\x00" + struct.pack("<I", second) + b"\x00"
    name_block += struct.pack("<I", common) + b"\x00" + text(full_name)
    record += b"\x06\x10\x00" + name_block + struct.pack("<HH", day, year)
    record += b"\xff\x00\x07\x01" + struct.pack("<I", 2) + b"\x03\x01"
    record += struct.pack("<II", *nation) + personality + b"\x01\x00"
    return bytes(record) + struct.pack("<III", index, uid, uid)


def people_stream(records: list[bytes], count: int) -> bytes:
    return b"\x00\x00" + struct.pack("<I", count) + b"".join(records)
