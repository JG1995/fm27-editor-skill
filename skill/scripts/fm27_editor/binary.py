"""Bounds-checked reading of little-endian binary data."""

import struct
from compression import zstd

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class FormatError(Exception):
    """The bytes do not follow the layout this library knows."""


class Reader:
    """Reads values in order and raises `error` instead of running past the end."""

    def __init__(self, content: bytes, error: type[FormatError] = FormatError):
        self.content = content
        self.position = 0
        self._error = error

    def take(self, size: int) -> bytes:
        end = self.position + size
        if size < 0 or end > len(self.content):
            raise self._error(f"expected {size} bytes at {self.position}, but the data ends")
        taken = self.content[self.position : end]
        self.position = end
        return taken

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def text(self) -> str:
        start = self.position
        raw = self.take(self.u32())
        try:
            return raw.decode()
        except UnicodeDecodeError as error:
            raise self._error(f"text at {start} is not UTF-8") from error

    @property
    def at_end(self) -> bool:
        return self.position == len(self.content)


def text_bytes(value: str) -> bytes:
    raw = value.encode()
    return struct.pack("<I", len(raw)) + raw


def unpack_frame(content: bytes, what: str, error: type[FormatError], size_limit: int) -> bytes:
    """Unpack one whole zstd frame; some files put a u32 frame size in front of it.

    A frame that is cut short, or has bytes after it, is an error: its last bytes hold the
    checksum, so without them damage would go unnoticed.
    """
    start = 0 if content[:4] == ZSTD_MAGIC else 4
    if content[start : start + 4] != ZSTD_MAGIC:
        raise error(f"{what} is not compressed data")
    decompressor = zstd.ZstdDecompressor()
    try:
        data = decompressor.decompress(content[start:], size_limit + 1)
    except zstd.ZstdError as cause:
        raise error(f"{what} cannot be decompressed") from cause
    if len(data) > size_limit:
        raise error(f"{what} is larger than {size_limit} bytes")
    if not decompressor.eof or decompressor.unused_data:
        raise error(f"{what} does not end where its data ends")
    return data
