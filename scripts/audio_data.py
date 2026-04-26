"""CLI utility to round-trip the audio-driver data tables through YAML.

Handles three sections of the Landstalker audio data:

* **Pitch effects** (vibratos / glissandos) — the
  ``t_PITCH_EFFECT_0..15`` tables in
  ``landstalker_disasm/code/audio/instrument_params.asm``.
* **PSG instrument envelopes** — the ``t_PSG_INSTRUMENT_0..15`` tables
  in the same file.
* **DAC sample table** — the single ``t_SAMPLE_LOAD_DATA`` block in
  ``landstalker_disasm/code/audio/samples.asm``.

The frequency, level and slot-per-algorithm tables that share
``instrument_params.asm`` are *not* exposed in the YAML — they are
hardware calibration constants and rarely benefit from editing. To keep
``encode`` round-trippable anyway, the encoder uses the existing asm
file as a template: it preserves everything up to (but not including)
``pt_PITCH_EFFECTS:`` and rewrites the pitch-effect and PSG-envelope
sections from the YAML. ``samples.asm`` contains only the sample table,
so it is rewritten in full.
"""

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

import yaml

from scripts.common.models._asm import register_hex_int_representer
from scripts.common.models.pitch_effect import PitchEffectBank
from scripts.common.models.psg_instrument import PsgInstrumentBank
from scripts.common.models.sample_table import SampleTable

# Activate hex-literal output for sample-table fields. Idempotent —
# safe to register at import time.
register_hex_int_representer(yaml.SafeDumper)


_PITCH_HEAD_LABEL: str = "pt_PITCH_EFFECTS"


def _load_text(path: str) -> str:
    """Read a UTF-8 text file by path. Thin wrapper for readability."""
    return Path(path).read_text(encoding="utf-8")


def _write_text(path: str, content: str) -> None:
    """Write a UTF-8 text file by path. Thin wrapper for readability."""
    Path(path).write_text(content, encoding="utf-8")


def _split_params_template(text: str) -> str:
    """Return the prelude of ``instrument_params.asm`` up to (but not
    including) the ``pt_PITCH_EFFECTS:`` line.

    Used as the template prefix when re-emitting the file: the audio
    constants (frequency tables, level tables, slot-per-algo masks) are
    preserved verbatim while the pitch-effect and PSG-envelope sections
    are regenerated from the YAML.

    Raises :class:`ValueError` if the marker label is not found.
    """
    out_lines: list[str] = []
    for raw_line in text.splitlines():
        # Comments start with ';'; strip before checking the label.
        line_no_comment = raw_line.split(";", 1)[0].strip()
        if line_no_comment.startswith(f"{_PITCH_HEAD_LABEL}:") \
                or line_no_comment == f"{_PITCH_HEAD_LABEL}":
            return "\n".join(out_lines).rstrip("\n") + "\n"
        out_lines.append(raw_line)
    raise ValueError(
        f"could not find '{_PITCH_HEAD_LABEL}:' label in params asm"
    )


def start_decode(args: Namespace) -> None:
    """Read ``--params`` and ``--samples`` asm files; emit a single YAML.

    Output keys are ``pitch_effects``, ``psg_instruments`` and
    ``samples``. The output file path defaults to ``audio_data.yaml`` in
    the current directory.
    """
    if args.output_file is None:
        args.output_file = "audio_data.yaml"

    params_text = _load_text(args.params)
    samples_text = _load_text(args.samples)

    pitch = PitchEffectBank.parse_asm(params_text)
    psg = PsgInstrumentBank.parse_asm(params_text)
    samples = SampleTable.parse_asm(samples_text)

    yaml_dict = {
        "pitch_effects": pitch.to_yaml_dict(),
        "psg_instruments": psg.to_yaml_dict(),
        "samples": samples.to_yaml_dict(),
    }

    with Path(args.output_file).open("w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_dict, f, sort_keys=False,
                       default_flow_style=None, width=120)

    print(
        f"Decoded {len(pitch)} pitch effect(s), "
        f"{len(psg)} PSG envelope(s), "
        f"{len(samples)} sample entr(ies) to {args.output_file}."
    )


def start_encode(args: Namespace) -> None:
    """Read a YAML file; write back the two asm files.

    The pitch-effect and PSG-envelope sections of ``--params`` are
    rewritten using its existing prelude as a template (preserving the
    frequency/level tables that the YAML doesn't carry). ``--samples``
    is rewritten in full from the YAML's ``samples`` list.
    """
    with Path(args.input_file).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    pitch = PitchEffectBank.from_yaml_dict(data.get("pitch_effects", []))
    psg = PsgInstrumentBank.from_yaml_dict(data.get("psg_instruments", []))
    samples = SampleTable.from_yaml_dict(data.get("samples", []))

    template_text = _load_text(args.params)
    prelude = _split_params_template(template_text)
    new_params = prelude + pitch.to_asm() + psg.to_asm()
    _write_text(args.params, new_params)
    _write_text(args.samples, samples.to_asm())

    print(
        f"Encoded {len(pitch)} pitch effect(s), "
        f"{len(psg)} PSG envelope(s) into {args.params}; "
        f"{len(samples)} sample entr(ies) into {args.samples}."
    )


def build_argparser() -> ArgumentParser:
    """Build the argparse parser with ``decode`` and ``encode`` subcommands."""
    parser = ArgumentParser(
        description="Round-trip the audio data tables (pitch effects, "
                    "PSG envelopes, sample table) between asm and YAML."
    )
    subparsers = parser.add_subparsers(title="Modes", help="Select a mode")

    decode_parser = subparsers.add_parser(
        "decode", help="Decode params + samples asm into a single YAML"
    )
    decode_parser.add_argument(
        "--params", type=str, required=True,
        help="Input instrument_params.asm path"
    )
    decode_parser.add_argument(
        "--samples", type=str, required=True,
        help="Input samples.asm path"
    )
    decode_parser.add_argument(
        "-o", "--output-file", type=str,
        help="Output YAML path (default: audio_data.yaml)"
    )
    decode_parser.set_defaults(func=start_decode)

    encode_parser = subparsers.add_parser(
        "encode",
        help="Encode a YAML back to the params + samples asm files. "
             "The params asm is template-spliced: everything before "
             f"'{_PITCH_HEAD_LABEL}:' is preserved verbatim."
    )
    encode_parser.add_argument(
        "--params", type=str, required=True,
        help="instrument_params.asm path (read as template, then "
             "rewritten in place)"
    )
    encode_parser.add_argument(
        "--samples", type=str, required=True,
        help="samples.asm path (rewritten in full)"
    )
    encode_parser.add_argument(
        "input_file", type=str, help="Input YAML file"
    )
    encode_parser.set_defaults(func=start_encode)

    return parser


def main(argv: list[str]) -> None:
    """Entry point matching the convention of other scripts in the project."""
    parser = build_argparser()
    args = parser.parse_args(argv)
    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main(sys.argv[1:])
