"""Records of the base database that hold their own name in English, such as languages.

Such a record is a zero byte, the name, and a fixed number of bytes that the lookup does not use.
A currency differs: its names, its symbol, and its exchange rates follow the zero byte.
"""

import struct
from dataclasses import dataclass

from fm27_editor.binary import FormatError, Reader
from fm27_editor.dat_tables import read_records

HEAD = b"\x00"
# Each past year's exchange rate is this byte, the year, and the rate.
PAST_YEAR, PAST_YEAR_SIZE = b"\x01", 7


class NamedRecordError(FormatError):
    """A record that holds its own name does not follow the layout this library knows."""


@dataclass(frozen=True, slots=True)
class Currency:
    name: str
    short_name: str
    symbol: str
    per_pound: float
    """How many of it make a pound: the Editor's exchange rate."""


def parse_named_records(table: bytes, one: str, tail_size: int) -> dict[int, str]:
    """The name of each record, by its ID; `one` is what a record is, for errors."""
    names = {}
    for record in read_records(table):
        reader = Reader(record.data, NamedRecordError)
        head = reader.take(len(HEAD))
        names[record.uid] = reader.text()
        tail = len(record.data) - reader.position
        if head != HEAD or tail != tail_size:
            raise NamedRecordError(
                f"{one} {record.uid} starts with {head.hex()} and has {tail} bytes after its"
                f" name; expected {HEAD.hex()} and {tail_size}"
            )
    return names


def parse_currencies(table: bytes) -> dict[int, Currency]:
    """Each currency by its ID. A text that is empty in every currency stands before the symbol,
    and the rates of past years follow the rate."""
    currencies = {}
    for record in read_records(table):
        reader = Reader(record.data, NamedRecordError)
        head = reader.take(len(HEAD))
        name, short_name, _, symbol = [reader.text() for _ in range(4)]
        (per_pound,) = struct.unpack("<f", reader.take(4))
        years = [reader.take(PAST_YEAR_SIZE) for _ in range(reader.u32())]
        if head != HEAD or not reader.at_end or any(year[:1] != PAST_YEAR for year in years):
            raise NamedRecordError(f"currency {record.uid} does not follow the known layout")
        currencies[record.uid] = Currency(name, short_name, symbol, per_pound)
    return currencies
