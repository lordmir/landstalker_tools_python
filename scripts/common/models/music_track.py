"""Music track model — header + 10 channel byte streams.

A music ``.asm`` file under ``landstalker_disasm/code/audio/music/`` is
laid out as:

* an optional leading comment line(s),
* a 4-byte preamble (``db p0, p1, p2, tempo``),
* 10 channel pointers (``dw <label>`` lines, in canonical slot order),
* one labelled ``db`` block per unique target label.

The driver reads bytes 0-3 of the file at
``landstalker_disasm/code/audio/sounddrv.asm:371-411`` (``Load_Music``):
byte 0 must be 0 to count as music; bytes 1-2 are loaded into
``MUSIC_DOESNT_USE_SAMPLES`` (always 0 in the disasm); byte 3 + 3 is
written to YM2612 register ``$26`` (Timer B), making it the tempo
divisor.

Multiple channel slots can target the same data label (the
``music_null.asm`` track aliases all 10 to one ``FFh, 0, 0`` end
marker; ``music00.asm`` aliases ``PSG_noise`` to ``PSG3``). The model
preserves these aliases on round-trip for byte-perfect output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.common.models._asm import (
    HexInt,
    format_byte_literal,
    parse_byte_literal,
    parse_labelled_db_blocks,
)
from scripts.common.models.track_event import (
    Event,
    emit_channel_stream,
    parse_channel_stream,
    stream_from_yaml,
    stream_to_yaml,
)


CHANNEL_SLOTS: tuple[str, ...] = (
    "YM1", "YM2", "YM3", "YM4", "YM5", "YM6",
    "PSG1", "PSG2", "PSG3", "PSG_noise",
)
"""Canonical 10-channel slot order matching the ``dw`` lines in the
asm files; also the order the driver loads channel data into the
``YM_CHANNEL_DATA_*`` blocks (``Load_Music_Channels`` at
``sounddrv.asm:414-445``)."""


def channel_kind(slot: str) -> str:
    """Return ``"tone"``, ``"dac"`` or ``"noise"`` for a slot name.

    Only YM6 (DAC) and PSG_noise are non-tone; all other slots use
    pitched-note semantics. Used to drive note-name vs raw-integer
    rendering in the YAML output.
    """
    if slot == "YM6":
        return "dac"
    if slot == "PSG_noise":
        return "noise"
    return "tone"


@dataclass
class MusicChannel:
    """One non-aliased channel.

    Attributes:
        label: Asm label that the channel's ``dw`` pointer references.
        events: Decoded event stream (always ends with an end /
            chain / jump terminator on well-formed data).
        trailing_bytes: Any bytes that follow the first terminator in
            the source. The Z80 never reaches them but the disasm has
            a single occurrence (``MUSIC_2E_PSG3``); preserved
            verbatim for byte-perfect round-trip.
    """

    label: str
    events: list[Event] = field(default_factory=list)
    trailing_bytes: bytes = b""


@dataclass
class MusicTrack:
    """A music track header + 10 channel slots.

    Attributes:
        name: Logical track name used as the label prefix when
            auto-generating labels (e.g. ``MUSIC_00``). Set from the
            common label prefix on parse, or supplied by the YAML.
        comment: Leading source-file comment block (e.g.
            ``; Music Track 0x00 - Bustling Street``); preserved
            verbatim.
        preamble: First 3 header bytes — always ``[0, 0, 0]`` in the
            disasm.
        tempo: 4th header byte; the driver writes ``tempo + 3`` into
            YM2612 Timer B (``$26``).
        channels: Mapping from each :data:`CHANNEL_SLOTS` slot name to
            either a :class:`MusicChannel` (own data) or a string
            naming another slot it aliases to.
    """

    name: str
    comment: str
    preamble: tuple[int, int, int]
    tempo: int
    channels: dict[str, MusicChannel | str]

    # ------------------------------------------------------------------
    # asm parser
    # ------------------------------------------------------------------

    @classmethod
    def parse_asm(cls, text: str) -> "MusicTrack":
        """Parse a single music ``.asm`` file into a :class:`MusicTrack`."""
        comment_lines, preamble, dw_targets, body_text = _split_music_file(text)
        if len(dw_targets) != len(CHANNEL_SLOTS):
            raise ValueError(
                f"expected {len(CHANNEL_SLOTS)} dw lines in music header, "
                f"got {len(dw_targets)}"
            )

        blocks = parse_labelled_db_blocks(body_text)

        # Determine the track name as the common prefix of the targets,
        # falling back to the first target if there is no shared prefix.
        name = _common_label_prefix(dw_targets)

        # First slot to use each target is the "primary"; subsequent slots
        # become aliases to it. Targets that aren't defined in this file
        # are recorded as external-label string references for the encoder
        # to pass through verbatim (e.g. SFX 06-0C share SFX_05_NOOP).
        primary_for_target: dict[str, str] = {}
        channels: dict[str, MusicChannel | str] = {}
        for slot, target in zip(CHANNEL_SLOTS, dw_targets):
            if target in primary_for_target:
                channels[slot] = primary_for_target[target]
                continue
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
            preamble=(preamble[0], preamble[1], preamble[2]),
            tempo=preamble[3],
            channels=channels,
        )

    # ------------------------------------------------------------------
    # asm emitter
    # ------------------------------------------------------------------

    def to_asm(self) -> str:
        """Emit the track as ``.asm`` text suitable for the disasm build.

        Whitespace style is consistent rather than byte-identical to
        the source; the resulting bytes (after assembly) are the unit
        of round-trip, not the source whitespace.
        """
        lines: list[str] = []
        if self.comment:
            lines.append(self.comment.rstrip("\n"))
            lines.append("")

        preamble_tokens = ", ".join(
            format_byte_literal(b) for b in (*self.preamble, self.tempo)
        )
        lines.append(f"\tdb\t{preamble_tokens}")

        # 10 dw lines. Each slot resolves to its primary channel's
        # label (following aliases).
        for slot in CHANNEL_SLOTS:
            target_label = self._target_label(slot)
            lines.append(f"\tdw\t{target_label}")
        lines.append("")

        # One db block per primary channel, in slot order.
        emitted_labels: set[str] = set()
        for slot in CHANNEL_SLOTS:
            entry = self.channels[slot]
            if not isinstance(entry, MusicChannel):
                continue
            if entry.label in emitted_labels:
                continue
            emitted_labels.add(entry.label)
            data = emit_channel_stream(entry.events) + entry.trailing_bytes
            lines.extend(_format_channel_db(entry.label, data))

        return "\n".join(lines) + "\n"

    def _target_label(self, slot: str) -> str:
        """Resolve a slot's ``dw`` target.

        A slot's value can be:

        * a :class:`MusicChannel` — return its ``label`` directly;
        * a string naming another slot — chase the alias;
        * a string that does not name a slot — treat as an external
          label reference (defined in a different ``.asm`` file) and
          return the string verbatim.
        """
        seen: set[str] = set()
        current = slot
        while True:
            if current in seen:
                raise ValueError(
                    f"alias cycle through slot {current!r} in track "
                    f"{self.name!r}"
                )
            seen.add(current)
            entry = self.channels[current]
            if isinstance(entry, MusicChannel):
                return entry.label
            if entry in self.channels:
                current = entry
                continue
            return entry  # external label reference

    # ------------------------------------------------------------------
    # YAML helpers
    # ------------------------------------------------------------------

    def to_yaml_dict(self) -> dict:
        """Return a YAML-friendly dict representation."""
        chans: dict[str, object] = {}
        for slot in CHANNEL_SLOTS:
            entry = self.channels[slot]
            if isinstance(entry, str):
                chans[slot] = entry
            else:
                d: dict = {
                    "label": entry.label,
                    "events": stream_to_yaml(entry.events,
                                             channel_kind(slot)),
                }
                if entry.trailing_bytes:
                    d["trailing_bytes"] = [HexInt(b)
                                           for b in entry.trailing_bytes]
                chans[slot] = d
        out: dict = {
            "name": self.name,
            "preamble": [HexInt(b) for b in self.preamble],
            "tempo": HexInt(self.tempo),
            "channels": chans,
        }
        if self.comment:
            out["comment"] = self.comment
        return out

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "MusicTrack":
        """Inverse of :meth:`to_yaml_dict`."""
        preamble = d.get("preamble", [0, 0, 0])
        if len(preamble) != 3:
            raise ValueError(
                f"preamble must have 3 entries, got {len(preamble)}"
            )
        chans: dict[str, MusicChannel | str] = {}
        raw_chans = d.get("channels", {})
        name = str(d.get("name", "MUSIC"))
        for slot in CHANNEL_SLOTS:
            value = raw_chans.get(slot)
            if value is None:
                # Default: empty channel that immediately ends. Auto-
                # generated label.
                chans[slot] = MusicChannel(
                    label=f"{name}_{slot}",
                    events=stream_from_yaml([{"cmd": "end"}]),
                )
            elif isinstance(value, str):
                # String-valued slot is either an alias (matches a
                # canonical slot name) or an external label reference
                # (used for cross-file shared end-markers).
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
            preamble=(int(preamble[0]), int(preamble[1]), int(preamble[2])),
            tempo=int(d.get("tempo", 0)),
            channels=chans,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DW_RE = re.compile(r"^\s*dw\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_DB_RE = re.compile(r"^\s*db\s+(.+)$", re.IGNORECASE)


def _split_music_file(text: str) -> tuple[str, list[int], list[str], str]:
    """Split a music file into (comment, preamble bytes, dw targets, body).

    ``comment`` is the verbatim leading comment block (everything
    above the first ``db`` line); ``preamble`` is exactly 4 byte
    values; ``dw_targets`` are the 10 channel target label names; and
    ``body`` is the remaining text containing labelled ``db`` blocks.
    """
    lines = text.splitlines()
    comment_lines: list[str] = []
    preamble: list[int] | None = None
    dw_targets: list[str] = []
    body_start: int = 0

    in_header = True
    for idx, raw in enumerate(lines):
        stripped = raw.split(";", 1)[0].strip()
        if not stripped:
            if preamble is None:
                comment_lines.append(raw)
            continue

        if preamble is None:
            db_match = _DB_RE.match(stripped)
            if db_match:
                tokens = [t.strip() for t in db_match.group(1).split(",")]
                preamble = [parse_byte_literal(t) for t in tokens]
                if len(preamble) != 4:
                    raise ValueError(
                        f"music preamble must be 4 bytes, got {len(preamble)}"
                    )
                continue
            # Anything before the preamble that isn't a db is comment.
            comment_lines.append(raw)
            continue

        if in_header:
            dw_match = _DW_RE.match(stripped)
            if dw_match:
                dw_targets.append(dw_match.group(1))
                if len(dw_targets) == len(CHANNEL_SLOTS):
                    body_start = idx + 1
                    in_header = False
                continue
            # Non-dw line after preamble but before all dw collected
            # must be a comment or label — fall through to body.
            in_header = False
            body_start = idx
            break

    if preamble is None:
        raise ValueError("music file has no `db` preamble line")

    body_text = "\n".join(lines[body_start:])
    comment_text = "\n".join(comment_lines).rstrip()
    return comment_text, preamble, dw_targets, body_text


def _common_label_prefix(labels: list[str]) -> str:
    """Heuristically extract the music-track name from its labels.

    Strips the trailing ``_<slot>`` segment from a representative
    label (e.g. ``MUSIC_00_YM1`` → ``MUSIC_00``). Falls back to the
    longest common prefix if no recognisable suffix is found.
    """
    if not labels:
        return "MUSIC"
    sample = labels[0]
    for slot in CHANNEL_SLOTS:
        suffix = "_" + slot
        if sample.endswith(suffix):
            return sample[: -len(suffix)]
    # Try common prefix across all labels
    prefix = sample
    for other in labels[1:]:
        while not other.startswith(prefix) and prefix:
            prefix = prefix[:-1]
        if not prefix:
            break
    return prefix.rstrip("_") or sample


def _format_channel_db(label: str, data: bytes,
                       bytes_per_line: int = 16) -> list[str]:
    """Emit a labelled ``db`` block, splitting at ``bytes_per_line``."""
    if not data:
        return [f"{label}:"]
    lines: list[str] = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        tokens = ", ".join(format_byte_literal(b) for b in chunk)
        if i == 0:
            lines.append(f"{label}:\tdb\t{tokens}")
        else:
            lines.append(f"\t\tdb\t{tokens}")
    return lines
