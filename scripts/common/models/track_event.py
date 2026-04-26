"""Music / SFX channel event stream model.

The Z80 driver consumes per-channel byte streams via a single dispatcher
at ``landstalker_disasm/code/audio/sounddrv.asm:946-1043``
(``YM1_Parsing_Start``). A byte is a command iff
``byte & 0xF8 == 0xF8``; otherwise it is a note (or rest) where bit 7
indicates "duration follows immediately" and a clear bit 7 means
"reuse the previously-stored duration".

This module decodes the byte stream into a sequence of typed events
(``Note``, ``Rest``, and one ``Cmd*`` per opcode) and re-emits them.
The emitter tracks the previously-stored duration so notes/rests with
unchanged duration emit their bit-7-clear short form, matching the
disasm's encoding for byte-perfect round-trip.

For tone channels (FM 1-5, PSG 1-3) note pitches are surfaced as
musical names (``C0``..``B6``); for DAC (YM6) and PSG noise channels
the same byte values are sample/noise indices and are exposed as raw
integers instead. The ``channel_kind`` argument on the YAML helpers
selects between the two.
"""

from dataclasses import dataclass

from scripts.common.models._asm import HexInt


# 7 octaves of chromatic indices (0..83). Index 0x70 (=112) is the
# rest sentinel; values >=0x84 (132) are not valid pitches but the byte
# encoding still allows up to 0x7F so the model just leaves them as raw
# integers.
PITCH_REST: int = 0x70
_NOTE_NAMES: tuple[str, ...] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
)


def pitch_to_name(idx: int) -> str:
    """Map a pitch index 0..83 to its ``C0``..``B6`` name.

    Raises :class:`ValueError` for indices outside that range so the
    caller (channel kind dispatch) can fall back to the raw-integer
    representation used by DAC / noise channels.
    """
    if not 0 <= idx <= 83:
        raise ValueError(f"pitch index out of named range 0..83: {idx}")
    octave, semitone = divmod(idx, 12)
    return f"{_NOTE_NAMES[semitone]}{octave}"


def name_to_pitch(name: str) -> int:
    """Map a ``C0``..``B6`` (or sharp) name back to its pitch index."""
    text = name.strip()
    if not text:
        raise ValueError("empty pitch name")
    # Split letter+optional sharp from octave digit(s).
    octave_pos = 0
    while octave_pos < len(text) and text[octave_pos] not in "0123456789":
        octave_pos += 1
    if octave_pos == 0 or octave_pos == len(text):
        raise ValueError(f"unparseable pitch name: {name!r}")
    note = text[:octave_pos]
    octave = int(text[octave_pos:])
    if note not in _NOTE_NAMES:
        raise ValueError(f"unknown note letter in {name!r}: {note!r}")
    semitone = _NOTE_NAMES.index(note)
    idx = octave * 12 + semitone
    if not 0 <= idx <= 83:
        raise ValueError(f"pitch {name!r} out of range C0..B6")
    return idx


def _pitch_yaml(idx: int, channel_kind: str) -> dict:
    """Return ``{note: NAME}`` or ``{value: INT}`` for a pitch index.

    Tone channels emit a note name; DAC/noise channels emit a hex int.
    Out-of-range values (>83) silently fall back to the integer form
    even on tone channels.
    """
    if channel_kind in {"dac", "noise"} or not 0 <= idx <= 83:
        return {"value": HexInt(idx)}
    return {"note": pitch_to_name(idx)}


def _pitch_from_yaml(d: dict) -> int:
    """Read a pitch index from a YAML dict that has either ``note`` or
    ``value`` set. Accepts either form regardless of channel kind so
    user edits aren't punished for picking the "wrong" key."""
    if "note" in d:
        return name_to_pitch(str(d["note"]))
    if "value" in d:
        return int(d["value"])
    raise ValueError(f"pitch event missing both 'note' and 'value': {d}")


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Note:
    """A pitched note with duration.

    Attributes:
        pitch: Pitch index 0..127 (only 0..83 map to named notes; the
            remainder are valid bytes for non-tone channels).
        duration: Number of frames the note holds.
        explicit: Force the encoder to emit the bit-7-set "explicit
            duration" form even when ``duration`` matches the
            previously-stored value. The disasm sometimes emits this
            redundantly (typically after loop / command boundaries),
            so the decoder sets this flag for any note whose source
            byte had bit 7 set despite a matching prior duration. The
            encoder also uses bit-7-set automatically when
            ``duration`` differs from the previous, regardless of
            this flag.
    """

    pitch: int
    duration: int
    explicit: bool = False


@dataclass
class Rest:
    """A rest (key-off) with duration.

    Attributes:
        duration: Number of frames the rest holds.
        explicit: See :attr:`Note.explicit`.
    """

    duration: int
    explicit: bool = False


@dataclass
class CmdInstrument:
    """``FE ii`` — set instrument index for the channel."""

    index: int


@dataclass
class CmdVolume:
    """``FD vv`` — set channel volume.

    Attributes:
        level: Volume level 0..15 (low nibble of the source byte; the
            driver masks ``vv & 0x0F``).
        raw: Full source byte. Stored only when the source byte's high
            nibble is non-zero, so byte-perfect round-trip is preserved
            even though the driver discards those bits.
    """

    level: int
    raw: int | None = None


@dataclass
class CmdSlideRelease:
    """``FC vv`` — slide / key-release. Semantics depend on ``vv``;
    the model preserves the raw byte for round-trip."""

    value: int


@dataclass
class CmdVibrato:
    """``FB vv`` — vibrato setup.

    Attributes:
        effect: Pitch-effect index 0..15 (high nibble of source byte).
        delay: Frames of delay before vibrato kicks in (low nibble).
    """

    effect: int
    delay: int


@dataclass
class CmdPan:
    """``FA vv`` — channel stereo pan.

    Attributes:
        mode: ``"both"``, ``"left"``, ``"right"``, or ``"escape"``.
            ``escape`` covers the bit-0-set form which the driver
            treats as a no-op; ``raw`` is preserved in that case.
        raw: Full source byte (always preserved for completeness; on
            non-escape modes it is reconstructable from ``mode``).
    """

    mode: str
    raw: int


@dataclass
class CmdPitchShift:
    """``F9 vv`` — channel transpose / fine-tune.

    Attributes:
        semitones: Sign-extended transpose from low 4 bits + bit 7.
        fine: Fine-tune offset (bits 4-6 of vv, doubled).
    """

    semitones: int
    fine: int


@dataclass
class CmdLoop:
    """``F8 bb [..]`` — loop control.

    Attributes:
        op: Sub-opcode name (see plan / README).
        count: Repeat count (only set for ``repeat_set``).
        raw_low5: Low 5 bits of ``bb``. Always 0 for most subtypes; for
            ``jump_start`` / ``jump_end`` carries bit 0 of ``bb``;
            preserved for round-trip.
    """

    op: str
    count: int | None = None
    raw_low5: int = 0


@dataclass
class CmdEnd:
    """``FF 00 00`` — end-of-track."""


@dataclass
class CmdChain:
    """``FF lo 00`` (lo != 0) — end-of-track plus signal next operation."""

    next_op: int


@dataclass
class CmdJump:
    """``FF lo hi`` (hi != 0) — absolute jump.

    The address is preserved verbatim; this opcode is not currently
    used in the disasm and is provided for completeness.
    """

    address: int


Event = (Note | Rest | CmdInstrument | CmdVolume | CmdSlideRelease
         | CmdVibrato | CmdPan | CmdPitchShift | CmdLoop | CmdEnd
         | CmdChain | CmdJump)


# ---------------------------------------------------------------------------
# Byte stream parser
# ---------------------------------------------------------------------------


_PAN_MODE_BY_BITS: dict[int, str] = {0xC0: "both", 0x80: "left", 0x40: "right",
                                     0x00: "off"}
_PAN_BITS_BY_MODE: dict[str, int] = {v: k for k, v in _PAN_MODE_BY_BITS.items()}

_LOOP_OP_BY_SUBTYPE: dict[int, str] = {
    0: "section_start", 1: "section_end",
    2: "first_pass_only", 3: "second_pass_only",
    4: "anchor", 5: "jump",        # 5 splits into jump_start/jump_end on bb&1
    6: "repeat_set", 7: "repeat_dec",
}


def parse_channel_stream(data: bytes) -> tuple[list[Event], bytes]:
    """Decode a channel byte stream into a list of :class:`Event`.

    Walks the bytes using the same dispatch the Z80 driver uses
    (``sounddrv.asm:946-1043``); the walk stops as soon as an
    :class:`CmdEnd`, :class:`CmdChain` or :class:`CmdJump` is consumed.
    Returns ``(events, trailing_bytes)``: ``trailing_bytes`` are the
    raw bytes that follow the first terminator (rare in the disasm,
    but ``MUSIC_2E_PSG3`` has 12 such dead bytes). The caller
    preserves them verbatim for byte-perfect round-trip. Raises
    :class:`ValueError` on unexpected truncation.
    """
    events: list[Event] = []
    i = 0
    n = len(data)

    def need(extra: int) -> None:
        """Bail out if fewer than ``extra`` bytes remain after ``i``."""
        if i + extra > n:
            raise ValueError(
                f"channel stream truncated at offset {i}: needed "
                f"{extra} more byte(s)"
            )

    last_duration: int | None = None

    while i < n:
        b = data[i]

        # Commands occupy 0xF8..0xFF.
        if b & 0xF8 == 0xF8:
            if b == 0xFF:
                need(2)
                lo, hi = data[i + 1], data[i + 2]
                i += 3
                if hi == 0 and lo == 0:
                    events.append(CmdEnd())
                elif hi == 0:
                    events.append(CmdChain(next_op=lo))
                else:
                    events.append(CmdJump(address=(hi << 8) | lo))
                return events, data[i:]  # FF terminates the stream
            elif b == 0xFE:
                need(1)
                events.append(CmdInstrument(index=data[i + 1]))
                i += 2
            elif b == 0xFD:
                need(1)
                vv = data[i + 1]
                level = vv & 0x0F
                raw = vv if vv != level else None
                events.append(CmdVolume(level=level, raw=raw))
                i += 2
            elif b == 0xFC:
                need(1)
                events.append(CmdSlideRelease(value=data[i + 1]))
                i += 2
            elif b == 0xFB:
                need(1)
                vv = data[i + 1]
                events.append(CmdVibrato(
                    effect=(vv >> 4) & 0x0F,
                    delay=vv & 0x0F,
                ))
                i += 2
            elif b == 0xFA:
                need(1)
                vv = data[i + 1]
                if vv & 1:
                    mode = "escape"
                else:
                    mode = _PAN_MODE_BY_BITS.get(vv & 0xC0, "off")
                events.append(CmdPan(mode=mode, raw=vv))
                i += 2
            elif b == 0xF9:
                need(1)
                vv = data[i + 1]
                # Transpose: low 4 bits + bit 7 (sign-extended).
                trans = vv & 0x0F
                if vv & 0x80:
                    trans |= -16  # sign-extend the negative half
                fine = (vv >> 3) & 0x0E
                events.append(CmdPitchShift(semitones=trans, fine=fine))
                i += 2
            elif b == 0xF8:
                need(1)
                bb = data[i + 1]
                sub = (bb >> 5) & 0x07
                low5 = bb & 0x1F
                op = _LOOP_OP_BY_SUBTYPE[sub]
                count: int | None = None
                if sub == 5:
                    op = "jump_start" if (bb & 1) else "jump_end"
                elif sub == 6:
                    count = low5 + 1
                events.append(CmdLoop(op=op, count=count, raw_low5=low5))
                i += 2
            else:  # pragma: no cover — defensive; mask above covers F8-FF
                raise ValueError(f"unknown command byte 0x{b:02X} at {i}")
            continue

        # Note or rest. Bit 7 set ⇒ duration byte follows.
        pitch = b & 0x7F
        if b & 0x80:
            need(1)
            duration = data[i + 1]
            # "Explicit" iff the source emitted a duration byte even
            # though it matches the previously-stored duration. We
            # preserve this for byte-perfect round-trip.
            explicit = (last_duration is not None
                        and duration == last_duration)
            i += 2
        else:
            if last_duration is None:
                raise ValueError(
                    f"channel stream byte 0x{b:02X} at offset {i} reuses "
                    "the previous duration but no duration has been "
                    "established yet"
                )
            duration = last_duration
            explicit = False
            i += 1
        last_duration = duration

        if pitch == PITCH_REST:
            events.append(Rest(duration=duration, explicit=explicit))
        else:
            events.append(Note(pitch=pitch, duration=duration,
                               explicit=explicit))

    return events, b""


# ---------------------------------------------------------------------------
# Byte stream emitter
# ---------------------------------------------------------------------------


def _emit_pitch_byte(pitch: int, duration: int,
                     last_duration: int | None,
                     explicit: bool) -> bytes:
    """Encode one note/rest, choosing between the bit-7-set "explicit
    duration" form and the bit-7-clear "reuse previous duration" form.

    The explicit form is emitted when ``duration`` differs from
    ``last_duration``, when no previous duration has been established,
    or when the caller forces it via ``explicit=True`` (the disasm
    sometimes does this redundantly after loop/command boundaries).
    """
    if not 0 <= pitch <= 0x7F:
        raise ValueError(f"pitch out of range 0..0x7F: {pitch}")
    if not 0 <= duration <= 0xFF:
        raise ValueError(f"duration out of range 0..255: {duration}")
    if (not explicit
            and last_duration is not None
            and duration == last_duration):
        return bytes([pitch & 0x7F])
    return bytes([pitch | 0x80, duration])


def emit_channel_stream(events: list[Event]) -> bytes:
    """Encode a list of events back into the byte stream.

    Mirrors the parser's dispatch: commands map back to their opcode
    forms; notes/rests use the short bit-7-clear form when the
    duration matches the previously-emitted duration.
    """
    out = bytearray()
    last_duration: int | None = None

    for ev in events:
        if isinstance(ev, Note):
            out.extend(_emit_pitch_byte(ev.pitch, ev.duration,
                                        last_duration, ev.explicit))
            last_duration = ev.duration
        elif isinstance(ev, Rest):
            out.extend(_emit_pitch_byte(PITCH_REST, ev.duration,
                                        last_duration, ev.explicit))
            last_duration = ev.duration
        elif isinstance(ev, CmdInstrument):
            out.extend([0xFE, ev.index & 0xFF])
        elif isinstance(ev, CmdVolume):
            byte = ev.raw if ev.raw is not None else (ev.level & 0x0F)
            out.extend([0xFD, byte & 0xFF])
        elif isinstance(ev, CmdSlideRelease):
            out.extend([0xFC, ev.value & 0xFF])
        elif isinstance(ev, CmdVibrato):
            byte = ((ev.effect & 0x0F) << 4) | (ev.delay & 0x0F)
            out.extend([0xFB, byte])
        elif isinstance(ev, CmdPan):
            out.extend([0xFA, ev.raw & 0xFF])
        elif isinstance(ev, CmdPitchShift):
            byte = (ev.semitones & 0x8F) | ((ev.fine & 0x0E) << 3)
            out.extend([0xF9, byte & 0xFF])
        elif isinstance(ev, CmdLoop):
            sub_for_op = {
                "section_start": 0, "section_end": 1,
                "first_pass_only": 2, "second_pass_only": 3,
                "anchor": 4, "jump_end": 5, "jump_start": 5,
                "repeat_set": 6, "repeat_dec": 7,
            }
            sub = sub_for_op[ev.op]
            low5 = ev.raw_low5 & 0x1F
            if ev.op == "jump_start":
                low5 |= 1
            elif ev.op == "jump_end":
                low5 &= 0x1E
            elif ev.op == "repeat_set":
                if ev.count is None:
                    raise ValueError("repeat_set CmdLoop requires count")
                low5 = (ev.count - 1) & 0x1F
            bb = (sub << 5) | low5
            out.extend([0xF8, bb])
        elif isinstance(ev, CmdEnd):
            out.extend([0xFF, 0x00, 0x00])
        elif isinstance(ev, CmdChain):
            out.extend([0xFF, ev.next_op & 0xFF, 0x00])
        elif isinstance(ev, CmdJump):
            addr = ev.address & 0xFFFF
            out.extend([0xFF, addr & 0xFF, (addr >> 8) & 0xFF])
        else:
            raise TypeError(f"unknown event type: {type(ev).__name__}")

    return bytes(out)


# ---------------------------------------------------------------------------
# YAML serialization
# ---------------------------------------------------------------------------


def event_to_yaml(ev: Event, channel_kind: str) -> dict:
    """Convert a single event to a YAML-friendly dict.

    ``channel_kind`` is one of ``"tone"``, ``"dac"`` or ``"noise"``;
    it controls whether note pitches are emitted as names or raw
    integers. All other fields are independent of channel kind.
    """
    if isinstance(ev, Note):
        d = _pitch_yaml(ev.pitch, channel_kind)
        d["duration"] = HexInt(ev.duration)
        if ev.explicit:
            d["explicit"] = True
        return d
    if isinstance(ev, Rest):
        d = {"rest": HexInt(ev.duration)}
        if ev.explicit:
            d["explicit"] = True
        return d
    if isinstance(ev, CmdInstrument):
        return {"cmd": "instrument", "index": HexInt(ev.index)}
    if isinstance(ev, CmdVolume):
        d = {"cmd": "volume", "level": ev.level}
        if ev.raw is not None:
            d["raw"] = HexInt(ev.raw)
        return d
    if isinstance(ev, CmdSlideRelease):
        return {"cmd": "slide_release", "value": HexInt(ev.value)}
    if isinstance(ev, CmdVibrato):
        return {"cmd": "vibrato", "effect": ev.effect, "delay": ev.delay}
    if isinstance(ev, CmdPan):
        d = {"cmd": "pan", "mode": ev.mode}
        # The driver masks vv to bits 7-6 (or treats bit 0 as a no-op
        # escape), so bits 5-1 are usually 0. When they aren't, the
        # source byte must be preserved verbatim for byte-perfect
        # round-trip — the runtime behaviour is unchanged either way.
        canonical = _PAN_BITS_BY_MODE.get(ev.mode)
        if ev.mode == "escape" or canonical is None or ev.raw != canonical:
            d["raw"] = HexInt(ev.raw)
        return d
    if isinstance(ev, CmdPitchShift):
        return {"cmd": "pitch_shift",
                "semitones": ev.semitones, "fine": ev.fine}
    if isinstance(ev, CmdLoop):
        d: dict = {"cmd": "loop", "op": ev.op}
        if ev.count is not None:
            d["count"] = ev.count
        if ev.raw_low5 and ev.op not in {"jump_start", "jump_end",
                                         "repeat_set"}:
            d["raw_low5"] = HexInt(ev.raw_low5)
        return d
    if isinstance(ev, CmdEnd):
        return {"cmd": "end"}
    if isinstance(ev, CmdChain):
        return {"cmd": "chain", "next_op": HexInt(ev.next_op)}
    if isinstance(ev, CmdJump):
        return {"cmd": "jump", "address": HexInt(ev.address)}
    raise TypeError(f"unknown event type: {type(ev).__name__}")


def event_from_yaml(d: dict) -> Event:
    """Inverse of :func:`event_to_yaml`. Tolerates both
    ``note: NAME`` and ``value: INT`` for pitches regardless of
    channel kind."""
    cmd = d.get("cmd")
    if cmd is None:
        if "rest" in d:
            return Rest(duration=int(d["rest"]),
                        explicit=bool(d.get("explicit", False)))
        if "note" in d or "value" in d:
            return Note(
                pitch=_pitch_from_yaml(d),
                duration=int(d["duration"]),
                explicit=bool(d.get("explicit", False)),
            )
    if cmd == "instrument":
        return CmdInstrument(index=int(d["index"]))
    if cmd == "volume":
        raw = d.get("raw")
        return CmdVolume(level=int(d["level"]),
                         raw=int(raw) if raw is not None else None)
    if cmd == "slide_release":
        return CmdSlideRelease(value=int(d["value"]))
    if cmd == "vibrato":
        return CmdVibrato(effect=int(d["effect"]), delay=int(d["delay"]))
    if cmd == "pan":
        mode = str(d.get("mode", "both"))
        if "raw" in d:
            return CmdPan(mode=mode, raw=int(d["raw"]))
        if mode == "escape":
            raise ValueError("pan mode 'escape' requires a 'raw' byte")
        if mode in _PAN_BITS_BY_MODE:
            return CmdPan(mode=mode, raw=_PAN_BITS_BY_MODE[mode])
        raise ValueError(f"unknown pan mode: {mode!r}")
    if cmd == "pitch_shift":
        return CmdPitchShift(semitones=int(d["semitones"]),
                             fine=int(d.get("fine", 0)))
    if cmd == "loop":
        op = str(d["op"])
        return CmdLoop(
            op=op,
            count=int(d["count"]) if "count" in d else None,
            raw_low5=int(d.get("raw_low5", 0)),
        )
    if cmd == "end":
        return CmdEnd()
    if cmd == "chain":
        return CmdChain(next_op=int(d["next_op"]))
    if cmd == "jump":
        return CmdJump(address=int(d["address"]))
    raise ValueError(f"unknown event dict: {d}")


def stream_to_yaml(events: list[Event], channel_kind: str) -> list[dict]:
    """Convert a list of events to a YAML-friendly list of dicts."""
    return [event_to_yaml(e, channel_kind) for e in events]


def stream_from_yaml(items: list[dict]) -> list[Event]:
    """Convert a list of YAML dicts back to events."""
    return [event_from_yaml(d) for d in items]
