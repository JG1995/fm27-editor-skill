"""Bounds-checked reading of little-endian binary data."""

import struct

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
