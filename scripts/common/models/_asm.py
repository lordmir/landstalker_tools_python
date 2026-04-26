"""Shared helpers for parsing/emitting Z80-style asm data files.

The audio data tables in ``landstalker_disasm/code/audio/`` use the
asm68k/sjasm convention: bare decimal for small values, hex with an
``h`` suffix (with a leading ``0`` if the first hex digit is A-F) for
larger values. Values are emitted via ``db`` (byte) directives, often
spread across multiple continuation lines under a single label.

These helpers are used by the YM instrument, pitch effect, PSG envelope
and sample-table models; they also tolerate ``0x``-prefixed literals
when reading user-edited inputs. The :class:`HexInt` wrapper plus
:func:`register_hex_int_representer` lets a model opt into hex YAML
output for fields whose natural representation is an address or a raw
byte/word value.
"""

import re

import yaml


_LABEL_LINE_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$"
)
_DB_LINE_RE = re.compile(r"^db\s+(.+)$", re.IGNORECASE)


def parse_byte_literal(token: str) -> int:
    """Parse one byte literal from an asm ``db`` directive.

    Accepts decimal (``3``), hex with ``h`` suffix (``20h``, ``0DFh``)
    and ``0x``-prefixed hex (``0x20``). Raises :class:`ValueError` if
    the token is empty, unparseable or out of the 0..255 range.
    """
    t = token.strip()
    if not t:
        raise ValueError("empty byte literal")
    lower = t.lower()
    if lower.endswith("h"):
        value = int(lower[:-1], 16)
    elif lower.startswith("0x"):
        value = int(lower, 16)
    else:
        value = int(lower, 10)
    if not 0 <= value <= 0xFF:
        raise ValueError(f"byte literal out of range: {token}")
    return value


def format_byte_literal(value: int) -> str:
    """Format a byte using the disasm's literal convention.

    Values < 16 are emitted as bare decimal (e.g. ``3``); values >= 16
    are emitted as two-digit hex with an ``h`` suffix and a leading
    zero where the first hex digit would otherwise be A-F (e.g. ``20h``,
    ``0DFh``). Matches the original disasm style so diffs stay minimal
    on round-trip.
    """
    if not 0 <= value <= 0xFF:
        raise ValueError(f"byte out of range: {value}")
    if value < 16:
        return str(value)
    text = f"{value:X}h"
    if text[0].isalpha():
        text = "0" + text
    return text


_BARE_LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*$")


def parse_labelled_db_blocks(text: str) -> dict[str, bytes]:
    """Parse ``LABEL: db ...`` blocks into ``{label: bytes}``.

    A label opens a new bytestring; any subsequent ``db`` lines append
    to it (allowing multi-line values); the next label closes the
    previous bytestring. ``dw`` directives and any other content
    (comments, blank lines, unrelated directives) are ignored, so the
    helper tolerates files that mix data tables with pointer tables and
    free text. Labels are returned in source order via dict iteration.

    Two label forms are recognised, matching asm68k convention:

    * ``LABEL:`` — colon-terminated, may be followed on the same line
      by a directive.
    * ``LABEL`` — bare identifier alone on a line, only if it starts
      at column 0 (i.e. no leading whitespace), to avoid mistaking a
      column-0 directive (``db ...``) for a label.
    """
    blocks: dict[str, bytes] = {}
    current_name: str | None = None
    current_bytes: bytearray = bytearray()

    def flush() -> None:
        """Commit the in-progress label, if one is open."""
        nonlocal current_name, current_bytes
        if current_name is not None:
            blocks[current_name] = bytes(current_bytes)
        current_name = None
        current_bytes = bytearray()

    for raw_line in text.splitlines():
        line_no_comment = raw_line.split(";", 1)[0]
        stripped = line_no_comment.strip()
        if not stripped:
            continue

        # Form 1: LABEL: ...
        label_match = _LABEL_LINE_RE.match(stripped)
        if label_match:
            flush()
            current_name = label_match.group(1)
            remainder = label_match.group(2).strip()
            if not remainder:
                continue
            stripped = remainder
        elif (line_no_comment[:1] not in " \t"
              and _BARE_LABEL_RE.match(stripped)):
            # Form 2: bare LABEL at column 0, alone on the line.
            flush()
            current_name = _BARE_LABEL_RE.match(stripped).group(1)
            continue

        db_match = _DB_LINE_RE.match(stripped)
        if db_match and current_name is not None:
            for token in db_match.group(1).split(","):
                current_bytes.append(parse_byte_literal(token))

    flush()
    return blocks


class HexInt(int):
    """``int`` subclass that YAML serialises as a hex literal.

    Use for fields whose natural representation is a memory address,
    bank number or raw byte/word value. PyYAML's loader already
    recognises ``0xNN`` syntax as :class:`int`, so loading does not
    need any special handling — only emit-time formatting differs. Call
    :func:`register_hex_int_representer` once on the dumper class
    you're using before dumping objects that contain :class:`HexInt`
    values.
    """


def _hex_int_representer(dumper: yaml.Dumper,
                         data: HexInt) -> yaml.ScalarNode:
    """YAML scalar representer that emits ``HexInt`` as ``0xN``.

    Negative values are emitted as ``-0xN`` (matching the standard YAML
    int form). The output is tagged as a regular int, so on reload the
    value comes back as a plain :class:`int` — the round trip is
    lossless for value but not for the :class:`HexInt` wrapper, which
    must be re-applied in the model's ``to_yaml_dict`` path.
    """
    value = int(data)
    if value < 0:
        text = f"-0x{-value:X}"
    else:
        text = f"0x{value:X}"
    return dumper.represent_scalar("tag:yaml.org,2002:int", text)


def register_hex_int_representer(dumper_cls: type = yaml.SafeDumper) -> None:
    """Register the :class:`HexInt` representer on a YAML dumper class.

    Idempotent — re-registering does not stack handlers. Defaults to
    :class:`yaml.SafeDumper` since the project's CLI scripts use
    ``yaml.safe_dump``.
    """
    dumper_cls.add_representer(HexInt, _hex_int_representer)


# Register on the standard SafeDumper at import time so any callsite
# can dump a model that contains HexInt values via yaml.safe_dump
# without first remembering to register. CLI scripts that use a custom
# dumper class can re-register on it via :func:`register_hex_int_representer`.
register_hex_int_representer(yaml.SafeDumper)


def format_db_lines(name: str, data: bytes,
                    bytes_per_line: int = 16,
                    label_pad: int = 19) -> list[str]:
    """Format a labelled byte array as one or more ``db`` lines.

    The first line is ``LABEL:\\tdb\\t...``; subsequent lines are pad-
    aligned with leading whitespace and ``db\\t...``. ``label_pad`` sets
    the column where the ``db`` keyword begins, matching the visual
    layout used in the disasm files.
    """
    if bytes_per_line <= 0:
        raise ValueError("bytes_per_line must be positive")
    if not data:
        return [f"{name}:"]
    lines: list[str] = []
    pad = " " * label_pad
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        tokens = ", ".join(format_byte_literal(b) for b in chunk)
        if i == 0:
            lines.append(f"{name}:\tdb\t{tokens}")
        else:
            lines.append(f"{pad}db\t{tokens}")
    return lines
