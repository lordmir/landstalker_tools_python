"""Pitch-effect (vibrato/glissando) tables.

The Z80 driver stores up to 16 pitch effects, indexed via
``pt_PITCH_EFFECTS`` and named ``t_PITCH_EFFECT_0`` through
``t_PITCH_EFFECT_15`` in
``landstalker_disasm/code/audio/instrument_params.asm``. Each effect is
a stream of bytes consumed once per frame by the parser at
``landstalker_disasm/code/audio/sounddrv.asm:1212-1236`` (and the PSG
mirror at :2279-2302):

* Bytes other than ``$80`` and ``$81`` are interpreted as **signed**
  pitch deltas added to the channel frequency that frame.
* ``$80`` rewinds the position counter to the start of the table.
* ``$81`` halts the position counter (no further deltas).

This makes ``$80`` and ``$81`` reserved values; valid signed deltas
range from -126 to +127. The model exposes the deltas as plain Python
ints and keeps the terminator as either ``"loop"`` or ``"end"``.
"""

from dataclasses import dataclass

from scripts.common.models._asm import (
    format_db_lines,
    parse_labelled_db_blocks,
)


_LOOP_BYTE: int = 0x80
_END_BYTE: int = 0x81


@dataclass
class PitchEffect:
    """One pitch-effect table.

    Attributes:
        name: Asm label (e.g. ``t_PITCH_EFFECT_0``); preserved on round-
            trip and used to regenerate the pointer table.
        deltas: Signed pitch deltas applied per frame. Each value must
            be in the range -126..+127 (the bytes ``$80`` and ``$81``
            are reserved for the terminator).
        terminator: ``"loop"`` for ``$80`` (rewind to start, the common
            case for vibratos) or ``"end"`` for ``$81`` (hold last
            position, used for one-shot effects).
    """

    name: str
    deltas: list[int]
    terminator: str  # "loop" or "end"

    @classmethod
    def from_bytes(cls, name: str, data: bytes) -> "PitchEffect":
        """Decode a pitch effect from its raw byte form.

        The last byte must be ``$80`` (loop) or ``$81`` (end). All
        preceding bytes are decoded as signed-byte deltas. Raises
        :class:`ValueError` if the trailing byte is missing or the
        stream contains an in-line ``$80``/``$81``.
        """
        if not data:
            raise ValueError(f"pitch effect {name!r}: empty data")
        terminator_byte = data[-1]
        if terminator_byte == _LOOP_BYTE:
            terminator = "loop"
        elif terminator_byte == _END_BYTE:
            terminator = "end"
        else:
            raise ValueError(
                f"pitch effect {name!r}: missing terminator "
                f"(last byte = 0x{terminator_byte:02X})"
            )
        delta_bytes = data[:-1]
        for b in delta_bytes:
            if b in (_LOOP_BYTE, _END_BYTE):
                raise ValueError(
                    f"pitch effect {name!r}: reserved byte "
                    f"0x{b:02X} in delta stream"
                )
        deltas = [b - 0x100 if b >= 0x80 else b for b in delta_bytes]
        return cls(name=name, deltas=deltas, terminator=terminator)

    def to_bytes(self) -> bytes:
        """Encode back to the raw byte form (deltas + terminator byte)."""
        out = bytearray()
        for d in self.deltas:
            if not -126 <= d <= 127:
                raise ValueError(
                    f"pitch effect {self.name!r}: delta {d} out of "
                    "range -126..127"
                )
            out.append(d & 0xFF)
        if self.terminator == "loop":
            out.append(_LOOP_BYTE)
        elif self.terminator == "end":
            out.append(_END_BYTE)
        else:
            raise ValueError(
                f"pitch effect {self.name!r}: unknown terminator "
                f"{self.terminator!r}"
            )
        return bytes(out)

    def to_yaml_dict(self) -> dict:
        """Return a YAML-friendly representation."""
        return {
            "name": self.name,
            "deltas": list(self.deltas),
            "terminator": self.terminator,
        }

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "PitchEffect":
        """Build from a YAML-loaded mapping. Default terminator is ``"loop"``."""
        return cls(
            name=str(d["name"]),
            deltas=[int(x) for x in d.get("deltas", [])],
            terminator=str(d.get("terminator", "loop")),
        )


class PitchEffectBank:
    """Ordered collection of :class:`PitchEffect` tables.

    Provides asm parse/emit helpers for the labelled-``db`` blocks in
    ``instrument_params.asm`` plus YAML dict round-tripping.

    Attributes:
        effects: List of :class:`PitchEffect`, ordered by appearance in
            the asm source (which matches the index used by the
            ``pt_PITCH_EFFECTS`` pointer table).
    """

    LABEL_PREFIX: str = "t_PITCH_EFFECT_"
    POINTER_TABLE_LABEL: str = "pt_PITCH_EFFECTS"

    def __init__(self, effects: list[PitchEffect] | None = None):
        """Create a bank, optionally seeded with a list of effects."""
        self.effects: list[PitchEffect] = list(effects or [])

    @classmethod
    def parse_asm(cls, text: str) -> "PitchEffectBank":
        """Pick out every ``t_PITCH_EFFECT_*`` label and decode it.

        Other labels (frequency tables, level tables, the pointer
        table) are ignored, so the parser is safe to point at the full
        ``instrument_params.asm`` file.
        """
        blocks = parse_labelled_db_blocks(text)
        effects = [
            PitchEffect.from_bytes(name, data)
            for name, data in blocks.items()
            if name.startswith(cls.LABEL_PREFIX)
        ]
        return cls(effects)

    def to_asm(self) -> str:
        """Emit the pointer table and each effect's ``db`` block.

        Output starts with ``pt_PITCH_EFFECTS:`` followed by 16 ``dw``
        entries (one per effect, in source order), then each
        ``t_PITCH_EFFECT_N: db ...`` block. Whitespace is set to roughly
        match the disasm style.
        """
        lines: list[str] = []
        if self.effects:
            lines.append(f"{self.POINTER_TABLE_LABEL}:\tdw\t{self.effects[0].name}")
            for eff in self.effects[1:]:
                lines.append(f"\t\t\tdw\t{eff.name}")
        for eff in self.effects:
            lines.extend(format_db_lines(eff.name, eff.to_bytes()))
        return "\n".join(lines) + "\n"

    def to_yaml_dict(self) -> list[dict]:
        """Return a list of effect dicts for embedding under a YAML key."""
        return [e.to_yaml_dict() for e in self.effects]

    @classmethod
    def from_yaml_dict(cls, items: list[dict]) -> "PitchEffectBank":
        """Build a bank from a YAML-loaded list of effect dicts."""
        return cls([PitchEffect.from_yaml_dict(i) for i in items])

    def __len__(self) -> int:
        """Number of pitch effects in the bank."""
        return len(self.effects)
