"""DAC sample table (``t_SAMPLE_LOAD_DATA``).

The Z80 driver stores 24 PCM sample descriptors in
``landstalker_disasm/code/audio/samples.asm`` under the single label
``t_SAMPLE_LOAD_DATA``. Each entry is 8 bytes and is decoded by
:func:`LoadDacSound`
(``landstalker_disasm/code/audio/sounddrv.asm:288-325``):

==========  ====  ==================================================
Offset      Size  Field
==========  ====  ==================================================
0x00        1     Rate divisor — written into ``Dac_Loop+1``;
                  controls the sample-rate of DAC playback.
0x01        1     Reserved (unused by the loader; preserved verbatim).
0x02        1     ROM bank — written into ``BANK_TO_LOAD`` so the
                  Z80 can address sample bytes via its 32 KB window.
0x03        1     Reserved (unused by the loader).
0x04..0x05  2     Length, little-endian (loaded into ``DE``).
0x06..0x07  2     Start address inside the bank window
                  (``$8000``..``$FFFF``), little-endian (loaded
                  into ``HL``).
==========  ====  ==================================================

The model exposes the four meaningful fields plus the two reserved
bytes (so unusual values round-trip exactly).
"""

from dataclasses import dataclass

from scripts.common.models._asm import (
    HexInt,
    format_db_lines,
    parse_labelled_db_blocks,
)


SAMPLE_ENTRY_SIZE: int = 8

# The Z80 maps ROM into its 32 KB window at $8000-$FFFF, so every
# sample's 16-bit start address has bit 15 set on disk. The YAML stores
# the more useful "offset within bank" form, with this constant applied
# on encode/decode.
BANK_WINDOW_BASE: int = 0x8000


@dataclass
class SampleEntry:
    """One 8-byte sample descriptor.

    Attributes:
        rate: Rate divisor written into ``Dac_Loop+1``.
        bank: ROM bank holding the sample bytes
            (written to ``BANK_TO_LOAD``).
        length: Sample length in bytes.
        start: Offset of the sample within the Z80's 32 KB bank window
            (i.e. the absolute Z80 address minus ``$8000``). Valid
            range is ``0x0000``..``0x7FFF``.
        reserved1: Byte at offset 0x01 — unused by the loader, stored
            for byte-perfect round-trip.
        reserved3: Byte at offset 0x03 — unused by the loader, stored
            for byte-perfect round-trip.
    """

    rate: int
    bank: int
    length: int
    start: int
    reserved1: int = 0
    reserved3: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "SampleEntry":
        """Decode an 8-byte descriptor.

        The 16-bit start address on disk lives in the Z80's bank
        window (``$8000``-``$FFFF``); this method strips
        :data:`BANK_WINDOW_BASE` so the stored ``start`` is the natural
        offset-within-bank form (``0x0000``-``0x7FFF``). Raises
        :class:`ValueError` if the on-disk address is below
        ``$8000``.
        """
        if len(data) != SAMPLE_ENTRY_SIZE:
            raise ValueError(
                f"sample entry: expected {SAMPLE_ENTRY_SIZE} bytes, "
                f"got {len(data)}"
            )
        raw_start = int.from_bytes(data[6:8], "little")
        if raw_start < BANK_WINDOW_BASE:
            raise ValueError(
                f"sample start 0x{raw_start:04X} is below the Z80 bank "
                f"window (expected >= 0x{BANK_WINDOW_BASE:04X})"
            )
        return cls(
            rate=data[0],
            reserved1=data[1],
            bank=data[2],
            reserved3=data[3],
            length=int.from_bytes(data[4:6], "little"),
            start=raw_start - BANK_WINDOW_BASE,
        )

    def to_bytes(self) -> bytes:
        """Encode back to the 8-byte descriptor.

        :data:`BANK_WINDOW_BASE` is added back to ``start`` so the
        on-disk address falls in the Z80 bank window. Raises
        :class:`ValueError` for out-of-range values.
        """
        if not 0 <= self.length <= 0xFFFF:
            raise ValueError(
                f"length out of range 0..0xFFFF: 0x{self.length:X}"
            )
        if not 0 <= self.start <= 0x7FFF:
            raise ValueError(
                f"start out of range 0..0x7FFF (offset within bank): "
                f"0x{self.start:X}"
            )
        abs_start = self.start + BANK_WINDOW_BASE
        return bytes([
            self.rate & 0xFF,
            self.reserved1 & 0xFF,
            self.bank & 0xFF,
            self.reserved3 & 0xFF,
            self.length & 0xFF, (self.length >> 8) & 0xFF,
            abs_start & 0xFF, (abs_start >> 8) & 0xFF,
        ])

    def to_yaml_dict(self) -> dict:
        """Return a YAML-friendly mapping with hex-formatted integers.

        All numeric fields are wrapped in :class:`HexInt` so a dumper
        with the hex representer registered emits them as ``0xN``
        literals. The ``reserved`` keys are omitted when zero so the
        common case stays compact.
        """
        d: dict = {
            "rate": HexInt(self.rate),
            "bank": HexInt(self.bank),
            "length": HexInt(self.length),
            "start": HexInt(self.start),
        }
        if self.reserved1:
            d["reserved1"] = HexInt(self.reserved1)
        if self.reserved3:
            d["reserved3"] = HexInt(self.reserved3)
        return d

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "SampleEntry":
        """Build from a YAML-loaded mapping."""
        return cls(
            rate=int(d.get("rate", 0)),
            bank=int(d.get("bank", 0)),
            length=int(d.get("length", 0)),
            start=int(d.get("start", 0)),
            reserved1=int(d.get("reserved1", 0)),
            reserved3=int(d.get("reserved3", 0)),
        )


class SampleTable:
    """Ordered list of :class:`SampleEntry` descriptors.

    The on-disk form is a single labelled ``db`` block
    (``t_SAMPLE_LOAD_DATA``) of N × 8 bytes; each row of 8 bytes is one
    sample. The model preserves entry order, which is also the index
    used by the music data (sample numbers in DAC channel streams).

    Attributes:
        entries: List of :class:`SampleEntry` in source order.
    """

    LABEL: str = "t_SAMPLE_LOAD_DATA"

    def __init__(self, entries: list[SampleEntry] | None = None):
        """Create a table, optionally seeded with a list of entries."""
        self.entries: list[SampleEntry] = list(entries or [])

    @classmethod
    def parse_asm(cls, text: str) -> "SampleTable":
        """Parse the ``t_SAMPLE_LOAD_DATA`` block out of an asm file.

        Other labelled blocks are ignored. Raises :class:`ValueError`
        if the table's byte length is not a multiple of 8.
        """
        blocks = parse_labelled_db_blocks(text)
        data = blocks.get(cls.LABEL, b"")
        if len(data) % SAMPLE_ENTRY_SIZE:
            raise ValueError(
                f"{cls.LABEL}: byte length {len(data)} is not a multiple "
                f"of {SAMPLE_ENTRY_SIZE}"
            )
        entries = [
            SampleEntry.from_bytes(data[i:i + SAMPLE_ENTRY_SIZE])
            for i in range(0, len(data), SAMPLE_ENTRY_SIZE)
        ]
        return cls(entries)

    def to_asm(self) -> str:
        """Emit the table as a ``t_SAMPLE_LOAD_DATA`` block, 8 bytes/line.

        Each line carries one full sample descriptor so a diff highlights
        the entry that changed.
        """
        if not self.entries:
            return f"{self.LABEL}:\n"
        data = b"".join(e.to_bytes() for e in self.entries)
        lines = format_db_lines(self.LABEL, data,
                                bytes_per_line=SAMPLE_ENTRY_SIZE)
        return "\n".join(lines) + "\n"

    def to_yaml_dict(self) -> list[dict]:
        """Return a list of entry dicts for embedding under a YAML key."""
        return [e.to_yaml_dict() for e in self.entries]

    @classmethod
    def from_yaml_dict(cls, items: list[dict]) -> "SampleTable":
        """Build a table from a YAML-loaded list of entry dicts."""
        return cls([SampleEntry.from_yaml_dict(i) for i in items])

    def __len__(self) -> int:
        """Number of sample entries in the table."""
        return len(self.entries)
