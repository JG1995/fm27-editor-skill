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
    magic: bytes = b"\x02\x01afe.",
    version: int = 8,
) -> bytes:
    region = b""

    def record(name: str, extension: str, data: bytes) -> bytes:
        nonlocal region
        stored = stored_member(data, compressed=storage == 3, size_prefix=size_prefix)
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
    header = magic + struct.pack("<HB", version, 0)
    header += struct.pack("<QQ", index_at - 9, 17) + bytes([storage])
    return header + region + b"\x02\x01fmf.\x08\x00\x00" + frame
