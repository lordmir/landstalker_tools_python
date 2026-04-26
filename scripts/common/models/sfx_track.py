"""SFX track model — type byte + variable channel byte streams.

An SFX is split into two ``.asm`` files under
``landstalker_disasm/code/audio/sfx/``: a header file
(``sfxXX_header.asm``) and a data file (``sfxXX_data.asm``). The
header begins with a type byte (``db 1`` or ``db 2``) followed by N
``dw`` channel pointers; the data file holds one labelled ``db`` block
per unique target.

* **Type 1** (``db 1``) — 10 channel slots, identical layout to a
  music track. The driver routes them to the same physical channels.
* **Type 2** (``db 2``) — 3 channel slots, mapping to YM4 / YM5 / YM6
  by data-label naming convention (verified by a full grep of
  ``sfx/*_header.asm``). These run on dedicated SFX-Type-2 channel
  state and do not preempt music.

Loader: ``landstalker_disasm/code/audio/sounddrv.asm:474-546``
(``Load_SFX``). The channel byte-stream opcodes are identical to
music's; the same parser/emitter from
:mod:`scripts.common.models.track_event` handles both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.common.models._asm import (
    HexInt,
    format_byte_literal,
    parse_byte_literal,
    parse_labelled_db_blocks,
)
from scripts.common.models.music_track import (
    MusicChannel,
    _format_channel_db,
)
from scripts.common.models.track_event import (
    emit_channel_stream,
    parse_channel_stream,
    stream_from_yaml,
    stream_to_yaml,
)


SFX_TYPE_1_SLOTS: tuple[str, ...] = (
    "YM1", "YM2", "YM3", "YM4", "YM5", "YM6",
    "PSG1", "PSG2", "PSG3", "PSG_noise",
)
"""Channel slots used by Type 1 SFX — same as music tracks."""

SFX_TYPE_2_SLOTS: tuple[str, ...] = ("YM4", "YM5", "YM6")
"""Channel slots used by Type 2 SFX — the dedicated SFX-Type-2 trio."""


def _slots_for_type(type_byte: int) -> tuple[str, ...]:
    """Return the canonical slot names for an SFX type byte."""
    if type_byte == 1:
        return SFX_TYPE_1_SLOTS
    if type_byte == 2:
        return SFX_TYPE_2_SLOTS
    raise ValueError(f"unsupported SFX type byte: {type_byte}")


def _channel_kind(slot: str) -> str:
    """Match :func:`scripts.common.models.music_track.channel_kind`
    semantics for SFX slots."""
    if slot == "YM6":
        return "dac"
    if slot == "PSG_noise":
        return "noise"
    return "tone"


@dataclass
class SfxTrack:
    """An SFX header + data file pair.

    Attributes:
        name: Logical SFX name (e.g. ``SFX_01``); becomes the label
            prefix when writing the asm.
        comment: Optional leading comment from the header file.
        type_byte: 1 or 2 (other values are rejected by
            :meth:`parse_asm`).
        channels: Mapping from slot name to either
            :class:`scripts.common.models.music_track.MusicChannel`
            or a string aliasing another slot. The set of slot keys
            depends on :attr:`type_byte`.
    """

    name: str
    comment: str
    type_byte: int
    channels: dict[str, MusicChannel | str]

    # ------------------------------------------------------------------
    # asm parser
    # ------------------------------------------------------------------

    @classmethod
    def parse_asm(cls, header_text: str, data_text: str) -> "SfxTrack":
        """Parse an SFX header + data pair into an :class:`SfxTrack`."""
        comment_lines, type_byte, dw_targets = _split_sfx_header(header_text)
        slots = _slots_for_type(type_byte)
        if len(dw_targets) != len(slots):
            raise ValueError(
                f"SFX type {type_byte}: header has {len(dw_targets)} dw "
                f"lines, expected {len(slots)}"
            )

        blocks = parse_labelled_db_blocks(data_text)
        name = _common_sfx_name(dw_targets)

        primary_for_target: dict[str, str] = {}
        channels: dict[str, MusicChannel | str] = {}
        for slot, target in zip(slots, dw_targets):
            if target in primary_for_target:
                channels[slot] = primary_for_target[target]
                continue
            # Cross-SFX shared NOOP labels (e.g. SFX_05_NOOP referenced
            # by SFX 06-0C) live in another data file. We record them
            # as external-label strings; the encoder passes them
            # through to the dw line without writing a local block.
            if target not in blocks:
                channels[slot] = target
                primary_for_target[target] = slot
                continue
            events, trailing = parse_channel_stream(blocks[target])
            channels[slot] = MusicChannel(
                label=target, events=events, trailing_bytes=trailing,
            )
            primary_for_target[target] = slot

        return cls(
            name=name,
            comment=comment_lines,
            type_byte=type_byte,
            channels=channels,
        )

    # ------------------------------------------------------------------
    # asm emitter
    # ------------------------------------------------------------------

    def to_asm(self) -> tuple[str, str]:
        """Emit the header / data text pair.

        The header file gets the comment, the type byte, and the
        ``dw`` pointers. The data file gets one ``db`` block per
        unique target label (in slot order).
        """
        slots = _slots_for_type(self.type_byte)

        # Header
        header_lines: list[str] = []
        if self.comment:
            header_lines.append(self.comment.rstrip("\n"))
            header_lines.append("")
        header_lines.append(f"\tdb\t{format_byte_literal(self.type_byte)}")
        for slot in slots:
            header_lines.append(f"\tdw\t{self._target_label(slot)}")

        # Data
        data_lines: list[str] = []
        emitted: set[str] = set()
        for slot in slots:
            entry = self.channels[slot]
            if not isinstance(entry, MusicChannel):
                continue
            if entry.label in emitted:
                continue
            emitted.add(entry.label)
            data = emit_channel_stream(entry.events) + entry.trailing_bytes
            data_lines.extend(_format_channel_db(entry.label, data))

        return "\n".join(header_lines) + "\n", "\n".join(data_lines) + "\n"

    def _target_label(self, slot: str) -> str:
        """Resolve a slot's ``dw`` target.

        Behaves like :meth:`MusicTrack._target_label`: chases string
        aliases until either a :class:`MusicChannel` is reached
        (return its label) or the alias names a non-slot identifier
        (return it verbatim as an external label reference).
        """
        seen: set[str] = set()
        current = slot
        while True:
            if current in seen:
                raise ValueError(
                    f"alias cycle through slot {current!r} in SFX "
                    f"{self.name!r}"
                )
            seen.add(current)
            entry = self.channels[current]
            if isinstance(entry, MusicChannel):
                return entry.label
            if entry in self.channels:
                current = entry
                continue
            return entry

    # ------------------------------------------------------------------
    # YAML helpers
    # ------------------------------------------------------------------

    def to_yaml_dict(self) -> dict:
        """Return a YAML-friendly dict representation."""
        slots = _slots_for_type(self.type_byte)
        chans: dict[str, object] = {}
        for slot in slots:
            entry = self.channels[slot]
            if isinstance(entry, str):
                chans[slot] = entry
            else:
                d: dict = {
                    "label": entry.label,
                    "events": stream_to_yaml(entry.events,
                                             _channel_kind(slot)),
                }
                if entry.trailing_bytes:
                    d["trailing_bytes"] = [HexInt(b)
                                           for b in entry.trailing_bytes]
                chans[slot] = d
        out: dict = {
            "name": self.name,
            "type": HexInt(self.type_byte),
            "channels": chans,
        }
        if self.comment:
            out["comment"] = self.comment
        return out

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "SfxTrack":
        """Inverse of :meth:`to_yaml_dict`."""
        type_byte = int(d.get("type", 1))
        slots = _slots_for_type(type_byte)
        name = str(d.get("name", "SFX"))
        raw_chans = d.get("channels", {})
        chans: dict[str, MusicChannel | str] = {}
        for slot in slots:
            value = raw_chans.get(slot)
            if value is None:
                # Default empty slot: end-marker label aliased per type.
                # Use a per-SFX NOOP label so default-emitted SFX still
                # assemble. The user can override via explicit alias.
                chans[slot] = MusicChannel(
                    label=f"{name}_{slot}",
                    events=stream_from_yaml([{"cmd": "end"}]),
                )
            elif isinstance(value, str):
                # String-valued slot is either an alias to another slot
                # (when value matches a slot name) or an external label
                # reference (e.g. SFX_05_NOOP shared across SFX 06-0C).
                chans[slot] = value
            elif isinstance(value, dict):
                label = str(value.get("label", f"{name}_{slot}"))
                trailing = bytes(int(b) & 0xFF
                                 for b in value.get("trailing_bytes", []))
                chans[slot] = MusicChannel(
                    label=label,
                    events=stream_from_yaml(value.get("events", [])),
                    trailing_bytes=trailing,
                )
            else:
                raise ValueError(
                    f"channel {slot!r}: expected string or mapping, "
                    f"got {type(value).__name__}"
                )
        return cls(
            name=name,
            comment=str(d.get("comment", "")),
            type_byte=type_byte,
            channels=chans,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DW_RE = re.compile(r"^\s*dw\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_DB_RE = re.compile(r"^\s*db\s+(.+)$", re.IGNORECASE)


def _split_sfx_header(text: str) -> tuple[str, int, list[str]]:
    """Split an SFX header file into (comment, type byte, dw targets)."""
    lines = text.splitlines()
    comment_lines: list[str] = []
    type_byte: int | None = None
    dw_targets: list[str] = []

    for raw in lines:
        stripped = raw.split(";", 1)[0].strip()
        if not stripped:
            if type_byte is None:
                comment_lines.append(raw)
            continue

        if type_byte is None:
            db_match = _DB_RE.match(stripped)
            if db_match:
                tokens = [t.strip() for t in db_match.group(1).split(",")]
                if len(tokens) != 1:
                    raise ValueError(
                        f"SFX header `db` line should declare exactly 1 byte; "
                        f"got {len(tokens)}: {raw!r}"
                    )
                type_byte = parse_byte_literal(tokens[0])
                continue
            comment_lines.append(raw)
            continue

        dw_match = _DW_RE.match(stripped)
        if dw_match:
            dw_targets.append(dw_match.group(1))
            continue

    if type_byte is None:
        raise ValueError("SFX header has no `db` line for the type byte")

    return "\n".join(comment_lines).rstrip(), type_byte, dw_targets


def _common_sfx_name(targets: list[str]) -> str:
    """Heuristically extract the SFX prefix from its target labels.

    Strips a trailing ``_<slot>`` or ``_NOOP`` segment from a
    representative target. Falls back to the longest common prefix
    across all targets (with the trailing underscore removed) if no
    suffix matches.
    """
    if not targets:
        return "SFX"
    candidates = list(SFX_TYPE_1_SLOTS) + ["NOOP"]
    sample = targets[0]
    for tail in candidates:
        suffix = "_" + tail
        if sample.endswith(suffix):
            return sample[: -len(suffix)]
    prefix = sample
    for other in targets[1:]:
        while not other.startswith(prefix) and prefix:
            prefix = prefix[:-1]
        if not prefix:
            break
    return prefix.rstrip("_") or sample
