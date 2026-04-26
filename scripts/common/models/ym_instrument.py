"""YM2612 instrument bank model.

Parses, decodes, encodes and re-emits the 80-entry instrument bank stored
in ``landstalker_disasm/code/audio/ym_instruments.asm``. The byte layout
is dictated by the Z80 driver's ``YM1_LoadInstrument`` routine
(``landstalker_disasm/code/audio/sounddrv.asm:1687-1806``); each patch
is exactly 29 bytes and is keyed by a label of the form ``YM_INSTMT_xx``.

Bit-fields per operator follow the YM2612 datasheet register map:

==========  ============  ===============================================
Offset      YM register   Bit-fields
==========  ============  ===============================================
0x00..0x03  $30 + slot    bits 6-4 = DT, bits 3-0 = MUL
0x04..0x07  $40 + slot    bits 6-0 = TL
0x08..0x0B  $50 + slot    bits 7-6 = KS (RS), bits 4-0 = AR
0x0C..0x0F  $60 + slot    bit 7 = AM, bits 4-0 = D1R
0x10..0x13  $70 + slot    bits 4-0 = D2R
0x14..0x17  $80 + slot    bits 7-4 = D1L (SL), bits 3-0 = RR
0x18..0x1B  $90 + slot    bits 3-0 = SSG-EG (bit 3 enable, 2-0 mode)
0x1C        $B0           bits 5-3 = Feedback, bits 2-0 = Algorithm
==========  ============  ===============================================

The YM2612 stores operators in register-slot order 0,1,2,3, which
corresponds to the algorithm-numbered operators OP1, OP3, OP2, OP4. The
on-disk patch follows the slot order; the YAML schema names operators by
their algorithm-number (op1..op4) for readability and the model handles
the remap on serialise/deserialise.
"""

from dataclasses import dataclass

from scripts.common.models._asm import (
    format_byte_literal as _format_byte_literal,
    parse_labelled_db_blocks,
)


# Maps slot index (the order operator bytes are stored on disk) to
# algorithm-numbered operator name. See the YM2612 datasheet "Channel
# operator slot assignment" — slots 0,1,2,3 are OP1, OP3, OP2, OP4.
_SLOT_TO_OP: tuple[str, str, str, str] = ("op1", "op3", "op2", "op4")
_OP_TO_SLOT: dict[str, int] = {name: i for i, name in enumerate(_SLOT_TO_OP)}

INSTRUMENT_SIZE: int = 29


@dataclass
class YmOperator:
    """One YM2612 FM operator's envelope and multiplier settings.

    Attributes:
        dt: Detune, 0-7 (YM2612 reg $30 bits 6-4).
        mul: Frequency multiplier, 0-15 (reg $30 bits 3-0).
        tl: Total level / output attenuation, 0-127 (reg $40 bits 6-0).
        ks: Key scale / rate scaling, 0-3 (reg $50 bits 7-6).
        ar: Attack rate, 0-31 (reg $50 bits 4-0).
        am: Amplitude-modulation enable, 0 or 1 (reg $60 bit 7).
        d1r: First decay rate, 0-31 (reg $60 bits 4-0).
        d2r: Second decay rate, 0-31 (reg $70 bits 4-0).
        d1l: First decay level (sustain level), 0-15 (reg $80 bits 7-4).
        rr: Release rate, 0-15 (reg $80 bits 3-0).
        ssg_eg: SSG-EG mode, 0-15 (reg $90 bits 3-0; bit 3 = enable).
    """

    dt: int
    mul: int
    tl: int
    ks: int
    ar: int
    am: int
    d1r: int
    d2r: int
    d1l: int
    rr: int
    ssg_eg: int

    @classmethod
    def from_register_bytes(cls, r30: int, r40: int, r50: int, r60: int,
                            r70: int, r80: int, r90: int) -> "YmOperator":
        """Build an operator from its seven YM2612 register bytes.

        Inputs are the patch bytes destined for registers $30, $40, $50,
        $60, $70, $80 and $90 (each offset by the operator's slot
        index). Returns a populated :class:`YmOperator`.
        """
        return cls(
            dt=(r30 >> 4) & 0x07,
            mul=r30 & 0x0F,
            tl=r40 & 0x7F,
            ks=(r50 >> 6) & 0x03,
            ar=r50 & 0x1F,
            am=(r60 >> 7) & 0x01,
            d1r=r60 & 0x1F,
            d2r=r70 & 0x1F,
            d1l=(r80 >> 4) & 0x0F,
            rr=r80 & 0x0F,
            ssg_eg=r90 & 0x0F,
        )

    def to_register_bytes(self) -> tuple[int, int, int, int, int, int, int]:
        """Pack the operator back into its seven YM2612 register bytes.

        Returns a 7-tuple (r30, r40, r50, r60, r70, r80, r90) matching
        the input order of :meth:`from_register_bytes`. Each field is
        masked to its valid bit-width so out-of-range values silently
        wrap; validation belongs to the caller.
        """
        r30 = ((self.dt & 0x07) << 4) | (self.mul & 0x0F)
        r40 = self.tl & 0x7F
        r50 = ((self.ks & 0x03) << 6) | (self.ar & 0x1F)
        r60 = ((self.am & 0x01) << 7) | (self.d1r & 0x1F)
        r70 = self.d2r & 0x1F
        r80 = ((self.d1l & 0x0F) << 4) | (self.rr & 0x0F)
        r90 = self.ssg_eg & 0x0F
        return r30, r40, r50, r60, r70, r80, r90

    def to_yaml_dict(self) -> dict[str, int]:
        """Return a flat dict with field-name keys, suitable for YAML."""
        return {
            "dt": self.dt, "mul": self.mul, "tl": self.tl,
            "ks": self.ks, "ar": self.ar, "am": self.am,
            "d1r": self.d1r, "d2r": self.d2r,
            "d1l": self.d1l, "rr": self.rr,
            "ssg_eg": self.ssg_eg,
        }

    @classmethod
    def from_yaml_dict(cls, d: dict[str, int]) -> "YmOperator":
        """Build from a YAML-loaded mapping. Missing keys default to 0."""
        return cls(
            dt=int(d.get("dt", 0)),
            mul=int(d.get("mul", 0)),
            tl=int(d.get("tl", 0)),
            ks=int(d.get("ks", 0)),
            ar=int(d.get("ar", 0)),
            am=int(d.get("am", 0)),
            d1r=int(d.get("d1r", 0)),
            d2r=int(d.get("d2r", 0)),
            d1l=int(d.get("d1l", 0)),
            rr=int(d.get("rr", 0)),
            ssg_eg=int(d.get("ssg_eg", 0)),
        )


@dataclass
class YmInstrument:
    """One YM2612 FM patch (29 bytes on disk).

    Attributes:
        name: Asm label (e.g. ``YM_INSTMT_00``); preserved on round-trip.
        algorithm: Algorithm 0-7 (reg $B0 bits 2-0).
        feedback: Feedback 0-7 (reg $B0 bits 5-3).
        op1, op2, op3, op4: The four FM operators in algorithm-number
            order. On disk they are stored in YM2612 slot order
            (op1, op3, op2, op4); the model handles the remap.
    """

    name: str
    algorithm: int
    feedback: int
    op1: YmOperator
    op2: YmOperator
    op3: YmOperator
    op4: YmOperator

    @classmethod
    def from_bytes(cls, name: str, data: bytes) -> "YmInstrument":
        """Decode a 29-byte patch.

        Args:
            name: Label to preserve (used when re-emitting asm).
            data: Exactly :data:`INSTRUMENT_SIZE` bytes.

        Returns a populated :class:`YmInstrument`. Raises ``ValueError``
        if ``data`` is not 29 bytes.
        """
        if len(data) != INSTRUMENT_SIZE:
            raise ValueError(
                f"instrument {name!r}: expected {INSTRUMENT_SIZE} bytes, "
                f"got {len(data)}"
            )
        slots: list[YmOperator] = []
        for slot in range(4):
            slots.append(YmOperator.from_register_bytes(
                r30=data[0x00 + slot],
                r40=data[0x04 + slot],
                r50=data[0x08 + slot],
                r60=data[0x0C + slot],
                r70=data[0x10 + slot],
                r80=data[0x14 + slot],
                r90=data[0x18 + slot],
            ))
        fb_alg = data[0x1C]
        return cls(
            name=name,
            algorithm=fb_alg & 0x07,
            feedback=(fb_alg >> 3) & 0x07,
            op1=slots[_OP_TO_SLOT["op1"]],
            op2=slots[_OP_TO_SLOT["op2"]],
            op3=slots[_OP_TO_SLOT["op3"]],
            op4=slots[_OP_TO_SLOT["op4"]],
        )

    def to_bytes(self) -> bytes:
        """Encode back to the 29-byte on-disk representation."""
        ops_by_name = {
            "op1": self.op1, "op2": self.op2,
            "op3": self.op3, "op4": self.op4,
        }
        slots: list[YmOperator] = [ops_by_name[name] for name in _SLOT_TO_OP]
        out = bytearray(INSTRUMENT_SIZE)
        for slot, op in enumerate(slots):
            r30, r40, r50, r60, r70, r80, r90 = op.to_register_bytes()
            out[0x00 + slot] = r30
            out[0x04 + slot] = r40
            out[0x08 + slot] = r50
            out[0x0C + slot] = r60
            out[0x10 + slot] = r70
            out[0x14 + slot] = r80
            out[0x18 + slot] = r90
        out[0x1C] = ((self.feedback & 0x07) << 3) | (self.algorithm & 0x07)
        return bytes(out)

    def to_yaml_dict(self) -> dict:
        """Return a YAML-friendly dict with named operator keys."""
        return {
            "name": self.name,
            "algorithm": self.algorithm,
            "feedback": self.feedback,
            "operators": {
                "op1": self.op1.to_yaml_dict(),
                "op2": self.op2.to_yaml_dict(),
                "op3": self.op3.to_yaml_dict(),
                "op4": self.op4.to_yaml_dict(),
            },
        }

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "YmInstrument":
        """Build from a YAML-loaded mapping. Required keys: ``name``,
        ``algorithm``, ``feedback``, ``operators`` (with ``op1``..``op4``
        sub-mappings). Missing operator fields default to 0.
        """
        ops = d.get("operators", {})
        return cls(
            name=str(d["name"]),
            algorithm=int(d.get("algorithm", 0)),
            feedback=int(d.get("feedback", 0)),
            op1=YmOperator.from_yaml_dict(ops.get("op1", {})),
            op2=YmOperator.from_yaml_dict(ops.get("op2", {})),
            op3=YmOperator.from_yaml_dict(ops.get("op3", {})),
            op4=YmOperator.from_yaml_dict(ops.get("op4", {})),
        )


class YmInstrumentBank:
    """Ordered collection of :class:`YmInstrument` patches.

    Provides parse/emit for the disasm asm format and YAML dict round-
    tripping. Construct empty (``YmInstrumentBank()``) and append
    instruments, or via :meth:`parse_asm` / :meth:`from_yaml_dict`.

    Attributes:
        instruments: List of :class:`YmInstrument` in source order.
    """

    def __init__(self, instruments: list[YmInstrument] | None = None):
        """Create a bank, optionally seeded with a list of instruments."""
        self.instruments: list[YmInstrument] = list(instruments or [])

    @classmethod
    def parse_asm(cls, text: str) -> "YmInstrumentBank":
        """Parse an asm file containing labelled ``db`` blocks.

        Uses :func:`scripts.common.models._asm.parse_labelled_db_blocks`
        to collect bytes per label, then promotes each block of exactly
        :data:`INSTRUMENT_SIZE` bytes into an instrument. Blocks of any
        other size are silently ignored, so the helper tolerates files
        that mix instrument data with unrelated tables.
        """
        blocks = parse_labelled_db_blocks(text)
        instruments = [
            YmInstrument.from_bytes(name, data)
            for name, data in blocks.items()
            if len(data) == INSTRUMENT_SIZE
        ]
        return cls(instruments)

    def to_asm(self, bytes_per_line: tuple[int, int] = (15, 14)) -> str:
        """Emit asm text matching the disasm style.

        Each instrument is rendered as ``LABEL: db ...`` followed by
        continuation ``db`` lines, splitting the 29 bytes per
        ``bytes_per_line`` (default ``(15, 14)`` to match
        ``ym_instruments.asm``). Byte literals follow the original
        formatting convention (see :func:`_format_byte_literal`).
        """
        if sum(bytes_per_line) != INSTRUMENT_SIZE:
            raise ValueError(
                f"bytes_per_line must sum to {INSTRUMENT_SIZE}, "
                f"got {bytes_per_line}"
            )
        lines: list[str] = []
        for instr in self.instruments:
            data = instr.to_bytes()
            offset = 0
            for line_idx, count in enumerate(bytes_per_line):
                chunk = data[offset:offset + count]
                offset += count
                tokens = ", ".join(_format_byte_literal(b) for b in chunk)
                if line_idx == 0:
                    lines.append(f"{instr.name}:\tdb\t{tokens}")
                else:
                    lines.append(f"\t\t\tdb\t{tokens}")
        return "\n".join(lines) + "\n"

    def to_yaml_dict(self) -> dict:
        """Return ``{"instruments": [...]}`` suitable for ``yaml.safe_dump``."""
        return {"instruments": [i.to_yaml_dict() for i in self.instruments]}

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "YmInstrumentBank":
        """Build a bank from a YAML-loaded ``{"instruments": [...]}`` dict."""
        items = d.get("instruments", [])
        return cls([YmInstrument.from_yaml_dict(i) for i in items])

    def __len__(self) -> int:
        """Number of instruments in the bank."""
        return len(self.instruments)
