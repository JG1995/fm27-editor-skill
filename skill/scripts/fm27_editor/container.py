"""The .fmf wrapper: named members in a small folder tree.

A version 8 file is a 26-byte header, the stored members, and a compressed index that describes
them. Each member carries its own AES-128 key and IV in front of its data.
"""

import os
import struct
from compression import zstd
from dataclasses import dataclass, field
from enum import IntEnum

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from fm27_editor.binary import FormatError, Reader, text_bytes, unpack_frame

MAGIC = b"\x02\x01afe."
INDEX_TAG = b"\x02\x01fmf.\x08\x00\x00"
FORMAT_VERSION = 8
HEADER_SIZE = 26
INDEX_POINTER_AT = 9
MEMBER_REGION_MARK = 17  # HEADER_SIZE counted from INDEX_POINTER_AT
CIPHER_PART_SIZE = 16
MEMBER_HEADER_SIZE = 8 + 2 * CIPHER_PART_SIZE
MAX_INDEX_SIZE = 16 * 1024 * 1024


class ContainerError(FormatError):
    """The bytes are not a container this library can read."""


class Storage(IntEnum):
    """How every member of a container is stored, from header byte 25.

    The Editor refuses a file whose flag does not match its members.
    """

    RAW = 0
    ZSTD = 3


@dataclass
class Member:
    name: str
    extension: str
    data: bytes
    created: int = 0
    modified: int = 0


@dataclass
class Folder:
    name: str
    members: list[Member] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)


@dataclass
class Container:
    storage: Storage
    root: Folder


def read_container(content: bytes) -> Container:
    index = _read_index(content)
    return Container(index.storage, _load_folder(index.root, index))


def write_container(container: Container) -> bytes:
    region = bytearray()
    index = _write_folder(container.root, container.storage, region)
    index_at = HEADER_SIZE + len(region)
    header = MAGIC + struct.pack("<HB", FORMAT_VERSION, 0)
    header += struct.pack("<QQ", index_at - INDEX_POINTER_AT, MEMBER_REGION_MARK)
    header += bytes([container.storage])
    return header + bytes(region) + INDEX_TAG + _compress(index)


def _read_header(content: bytes) -> tuple[Storage, int]:
    if len(content) < HEADER_SIZE or content[:6] != MAGIC:
        raise ContainerError("not an FM editor file")
    version = struct.unpack_from("<H", content, 6)[0]
    if version != FORMAT_VERSION:
        raise ContainerError(f"format version {version} is not supported")
    try:
        storage = Storage(content[25])
    except ValueError as error:
        raise ContainerError(f"unknown storage flag {content[25]:#x}") from error
    index_at = struct.unpack_from("<Q", content, INDEX_POINTER_AT)[0] + INDEX_POINTER_AT
    if content[index_at : index_at + len(INDEX_TAG)] != INDEX_TAG:
        raise ContainerError("the index is not where the header says")
    return storage, index_at


@dataclass
class _Record:
    """A member as the index describes it, before its data is read."""

    name: str
    extension: str
    offset: int
    stored_size: int
    unpacked_size: int
    created: int
    modified: int


@dataclass
class _FolderRecord:
    name: str
    records: list[_Record] = field(default_factory=list)
    folders: list[_FolderRecord] = field(default_factory=list)


@dataclass
class _Index:
    storage: Storage
    region: bytes
    root: _FolderRecord


def _read_index(content: bytes) -> _Index:
    storage, index_at = _read_header(content)
    index = unpack_frame(
        content[index_at + len(INDEX_TAG) :], "index", ContainerError, MAX_INDEX_SIZE
    )
    reader = Reader(index, ContainerError)
    root = _read_folder_record(reader)
    if not reader.at_end:
        raise ContainerError(f"{len(index) - reader.position} unexpected bytes end the index")
    return _Index(storage, content[HEADER_SIZE:index_at], root)


def _read_folder_record(reader: Reader) -> _FolderRecord:
    folder = _FolderRecord(reader.text())
    for _ in range(reader.u32()):
        folder.records.append(
            _Record(reader.text(), reader.text(), *(reader.u64() for _ in range(5)))
        )
    for _ in range(reader.u32()):
        folder.folders.append(_read_folder_record(reader))
    return folder


def _load_folder(folder: _FolderRecord, index: _Index) -> Folder:
    return Folder(
        folder.name,
        [_load_member(record, index) for record in folder.records],
        [_load_folder(sub, index) for sub in folder.folders],
    )


def _load_member(record: _Record, index: _Index) -> Member:
    what = f"member {record.name}{record.extension}"
    stored = index.region[record.offset : record.offset + record.stored_size]
    if len(stored) != record.stored_size:
        raise ContainerError(f"{what} does not lie inside the file")
    stored = _decrypt(stored, what)
    data = _unstore(stored, record.unpacked_size, index.storage, what)
    return Member(record.name, record.extension, data, record.created, record.modified)


def _decrypt(stored: bytes, what: str) -> bytes:
    if stored[:8] != struct.pack("<II", CIPHER_PART_SIZE, CIPHER_PART_SIZE):
        raise ContainerError(f"{what} has an unknown cipher header")
    return _aes_ctr(stored[MEMBER_HEADER_SIZE:], stored[8:24], stored[24:40])


def _unstore(stored: bytes, size: int, storage: Storage, what: str) -> bytes:
    data = unpack_frame(stored, what, ContainerError, size) if storage is Storage.ZSTD else stored
    if len(data) != size:
        raise ContainerError(f"{what} has {len(data)} bytes, expected {size}")
    return data


def _write_folder(folder: Folder, storage: Storage, region: bytearray) -> bytes:
    index = text_bytes(folder.name) + struct.pack("<I", len(folder.members))
    for member in folder.members:
        index += _write_member(member, storage, region)
    index += struct.pack("<I", len(folder.folders))
    return index + b"".join(_write_folder(sub, storage, region) for sub in folder.folders)


def _write_member(member: Member, storage: Storage, region: bytearray) -> bytes:
    body = _compress(member.data) if storage is Storage.ZSTD else member.data
    key, iv = os.urandom(CIPHER_PART_SIZE), os.urandom(CIPHER_PART_SIZE)
    stored = struct.pack("<II", CIPHER_PART_SIZE, CIPHER_PART_SIZE) + key + iv
    stored += _aes_ctr(body, key, iv)
    offset = len(region)
    region += stored
    record = text_bytes(member.name) + text_bytes(member.extension)
    record += struct.pack("<QQQ", offset, len(stored), len(member.data))
    return record + struct.pack("<QQ", member.created, member.modified)


def _aes_ctr(data: bytes, key: bytes, iv: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return cipher.update(data) + cipher.finalize()


def _compress(data: bytes) -> bytes:
    """Compress the way the Editor does: a checksum, no content size, and a 1 MiB window."""
    options = {
        zstd.CompressionParameter.checksum_flag: 1,
        zstd.CompressionParameter.window_log: 20,
    }
    compressor = zstd.ZstdCompressor(options=options)
    return compressor.compress(data) + compressor.flush()
