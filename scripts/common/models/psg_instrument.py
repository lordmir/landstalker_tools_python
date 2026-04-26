"""PSG (SN76489) instrument envelopes.

The Z80 driver stores up to 16 PSG envelope tables, indexed via
``pt_PSG_INSTRUMENTS`` and named ``t_PSG_INSTRUMENT_0`` through
``t_PSG_INSTRUMENT_15`` in
``landstalker_disasm/code/audio/instrument_params.asm``. Each envelope
is consumed by :func:`PSG_ParseToneData` /
:func:`PSG_ParseNoiseData` once per frame
(``landstalker_disasm/code/audio/sounddrv.asm:2326-2391``):

* The low 4 bits of each byte are a "loudness" value (0 = silent,
  15 = loudest); the driver inverts this to the SN76489 attenuation
  register's 0=loudest convention at write time.
* Bit 7 marks a **sustain point**. While bit 7 is clear, the position
  counter advances each frame; once a bit-7 byte is hit, the position
  freezes there and the volume is held until the next note triggers.
* On key release, a separate scan
  (``sounddrv.asm:2381-2391``) skips past the current sustain byte to
  the next byte and continues from there — so envelopes typically have
  a second bit-7 byte downstream that becomes the release-time
  sustain.

Bytes ``$00``..``$7F`` and ``$80``..``$8F`` are therefore the only
meaningful values. The model decodes each step into ``vol`` (4 bits)
and ``hold`` (whether bit 7 is set); raw bytes outside those nibble
ranges round-trip via the same 8-bit field, so unusual padding (such as
the trailing zeros in ``t_PSG_INSTRUMENT_15``) is preserved.
"""

from dataclasses import dataclass

from scripts.common.models._asm import (
    format_db_lines,
    parse_labelled_db_blocks,
)


@dataclass
class PsgEnvelopeStep:
    """One step in a PSG envelope.

    Attributes:
        vol: Loudness 0-15, taken from bits 3-0 of the source byte.
        hold: ``True`` if bit 7 was set in the source byte (meaning the
            envelope counter freezes at this step until a key event).
        extra_bits: Bits 6-4 of the source byte (always zero in the
            disasm's data, but preserved verbatim for round-trip
            safety).
    """

    vol: int
    hold: bool
    extra_bits: int = 0

    @classmethod
    def from_byte(cls, b: int) -> "PsgEnvelopeStep":
        """Decode a single envelope byte."""
        return cls(
            vol=b & 0x0F,
            hold=bool(b & 0x80),
            extra_bits=(b >> 4) & 0x07,
        )

    def to_byte(self) -> int:
        """Encode the step back to a single byte."""
        if not 0 <= self.vol <= 15:
            raise ValueError(f"vol out of range 0..15: {self.vol}")
        if not 0 <= self.extra_bits <= 7:
            raise ValueError(f"extra_bits out of range 0..7: {self.extra_bits}")
        return ((0x80 if self.hold else 0)
                | ((self.extra_bits & 0x07) << 4)
                | (self.vol & 0x0F))

    def to_yaml_dict(self) -> dict:
        """Return a flat mapping suitable for YAML.

        ``hold`` and ``extra_bits`` are omitted when at their default
        values to keep the common case compact.
        """
        d: dict = {"vol": self.vol}
        if self.hold:
            d["hold"] = True
        if self.extra_bits:
            d["extra_bits"] = self.extra_bits
        return d

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "PsgEnvelopeStep":
        """Build from a YAML-loaded mapping. Missing fields default to 0/False."""
        return cls(
            vol=int(d.get("vol", 0)),
            hold=bool(d.get("hold", False)),
            extra_bits=int(d.get("extra_bits", 0)),
        )


@dataclass
class PsgInstrument:
    """One PSG envelope table.

    Attributes:
        name: Asm label (e.g. ``t_PSG_INSTRUMENT_0``); preserved on
            round-trip.
        steps: Sequential envelope steps, one per source byte.
    """

    name: str
    steps: list[PsgEnvelopeStep]

    @classmethod
    def from_bytes(cls, name: str, data: bytes) -> "PsgInstrument":
        """Decode an envelope from its raw byte form."""
        return cls(name=name, steps=[PsgEnvelopeStep.from_byte(b) for b in data])

    def to_bytes(self) -> bytes:
        """Encode back to the raw byte form."""
        return bytes(s.to_byte() for s in self.steps)

    def to_yaml_dict(self) -> dict:
        """Return a YAML-friendly representation."""
        return {
            "name": self.name,
            "envelope": [s.to_yaml_dict() for s in self.steps],
        }

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "PsgInstrument":
        """Build from a YAML-loaded mapping."""
        return cls(
            name=str(d["name"]),
            steps=[PsgEnvelopeStep.from_yaml_dict(s)
                   for s in d.get("envelope", [])],
        )


class PsgInstrumentBank:
    """Ordered collection of :class:`PsgInstrument` envelopes.

    Attributes:
        instruments: List of :class:`PsgInstrument` in source order.
    """

    LABEL_PREFIX: str = "t_PSG_INSTRUMENT_"
    POINTER_TABLE_LABEL: str = "pt_PSG_INSTRUMENTS"

    def __init__(self, instruments: list[PsgInstrument] | None = None):
        """Create a bank, optionally seeded with a list of envelopes."""
        self.instruments: list[PsgInstrument] = list(instruments or [])

    @classmethod
    def parse_asm(cls, text: str) -> "PsgInstrumentBank":
        """Pick out every ``t_PSG_INSTRUMENT_*`` label and decode it."""
        blocks = parse_labelled_db_blocks(text)
        instruments = [
            PsgInstrument.from_bytes(name, data)
            for name, data in blocks.items()
            if name.startswith(cls.LABEL_PREFIX)
        ]
        return cls(instruments)

    def to_asm(self) -> str:
        """Emit the pointer table and each envelope's ``db`` block."""
        lines: list[str] = []
        if self.instruments:
            lines.append(
                f"{self.POINTER_TABLE_LABEL}:\tdw\t{self.instruments[0].name}"
            )
            for inst in self.instruments[1:]:
                lines.append(f"\t\t\tdw\t{inst.name}")
        for inst in self.instruments:
            lines.extend(format_db_lines(inst.name, inst.to_bytes()))
        return "\n".join(lines) + "\n"

    def to_yaml_dict(self) -> list[dict]:
        """Return a list of instrument dicts for embedding under a YAML key."""
        return [i.to_yaml_dict() for i in self.instruments]

    @classmethod
    def from_yaml_dict(cls, items: list[dict]) -> "PsgInstrumentBank":
        """Build a bank from a YAML-loaded list of instrument dicts."""
        return cls([PsgInstrument.from_yaml_dict(i) for i in items])

    def __len__(self) -> int:
        """Number of PSG envelopes in the bank."""
        return len(self.instruments)
