"""CLI utility for round-tripping a music ``.asm`` track through YAML.

Wraps :class:`scripts.common.models.music_track.MusicTrack`. See the
README for the YAML schema and the channel byte-stream opcode table.
"""

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

import yaml

from scripts.common.models._asm import register_hex_int_representer
from scripts.common.models.music_track import MusicTrack

# Hex representer is shared with audio_data; registering on SafeDumper
# is idempotent.
register_hex_int_representer(yaml.SafeDumper)


def start_decode(args: Namespace) -> None:
    """Read a music ``.asm`` file and write its YAML representation."""
    if args.output_file is None:
        args.output_file = str(Path(args.input_file).stem) + ".yaml"

    track = MusicTrack.parse_asm(
        Path(args.input_file).read_text(encoding="utf-8")
    )
    with Path(args.output_file).open("w", encoding="utf-8") as f:
        yaml.safe_dump(track.to_yaml_dict(), f,
                       sort_keys=False, default_flow_style=None, width=120)
    print(f"Decoded music track {track.name!r} -> {args.output_file}.")


def start_encode(args: Namespace) -> None:
    """Read a music YAML file and write its ``.asm`` representation."""
    if args.output_file is None:
        args.output_file = str(Path(args.input_file).stem) + ".asm"

    with Path(args.input_file).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    track = MusicTrack.from_yaml_dict(data)
    Path(args.output_file).write_text(track.to_asm(), encoding="utf-8")
    print(f"Encoded music track {track.name!r} -> {args.output_file}.")


def build_argparser() -> ArgumentParser:
    """Build the argparse parser with ``decode``/``encode`` subcommands."""
    parser = ArgumentParser(
        description="Round-trip a Landstalker music track between asm and YAML."
    )
    sub = parser.add_subparsers(title="Modes", help="Select a mode")

    dec = sub.add_parser("decode", help="Decode a music asm file into YAML")
    dec.add_argument("-o", "--output-file", type=str,
                     help="Output YAML path (default: input stem + .yaml)")
    dec.add_argument("input_file", type=str,
                     help="Input music asm file (e.g. music00.asm)")
    dec.set_defaults(func=start_decode)

    enc = sub.add_parser("encode", help="Encode a music YAML back to asm")
    enc.add_argument("-o", "--output-file", type=str,
                     help="Output asm path (default: input stem + .asm)")
    enc.add_argument("input_file", type=str, help="Input YAML file")
    enc.set_defaults(func=start_encode)
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
