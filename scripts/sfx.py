"""CLI utility for round-tripping an SFX header/data pair through YAML.

Wraps :class:`scripts.common.models.sfx_track.SfxTrack`. SFX have two
formats (Type 1 with 10 channel slots and Type 2 with 3); both use the
same channel byte-stream opcodes as music, documented in the README.
"""

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

import yaml

from scripts.common.models._asm import register_hex_int_representer
from scripts.common.models.sfx_track import SfxTrack

register_hex_int_representer(yaml.SafeDumper)


def start_decode(args: Namespace) -> None:
    """Read an SFX header + data pair and write their YAML representation."""
    if args.output_file is None:
        args.output_file = str(
            Path(args.header).stem.replace("_header", "")
        ) + ".yaml"

    sfx = SfxTrack.parse_asm(
        Path(args.header).read_text(encoding="utf-8"),
        Path(args.data).read_text(encoding="utf-8"),
    )
    with Path(args.output_file).open("w", encoding="utf-8") as f:
        yaml.safe_dump(sfx.to_yaml_dict(), f,
                       sort_keys=False, default_flow_style=None, width=120)
    print(f"Decoded SFX {sfx.name!r} (type {sfx.type_byte}) "
          f"-> {args.output_file}.")


def start_encode(args: Namespace) -> None:
    """Read an SFX YAML and write its header / data ``.asm`` files."""
    with Path(args.input_file).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sfx = SfxTrack.from_yaml_dict(data)
    header_text, data_text = sfx.to_asm()
    Path(args.header).write_text(header_text, encoding="utf-8")
    Path(args.data).write_text(data_text, encoding="utf-8")
    print(f"Encoded SFX {sfx.name!r} -> {args.header} + {args.data}.")


def build_argparser() -> ArgumentParser:
    """Build the argparse parser with ``decode``/``encode`` subcommands."""
    parser = ArgumentParser(
        description="Round-trip a Landstalker SFX between asm and YAML."
    )
    sub = parser.add_subparsers(title="Modes", help="Select a mode")

    dec = sub.add_parser(
        "decode", help="Decode an SFX header + data pair into YAML"
    )
    dec.add_argument("--header", type=str, required=True,
                     help="Input SFX header asm (e.g. sfx01_header.asm)")
    dec.add_argument("--data", type=str, required=True,
                     help="Input SFX data asm (e.g. sfx01_data.asm)")
    dec.add_argument("-o", "--output-file", type=str,
                     help="Output YAML path (default: stem of header)")
    dec.set_defaults(func=start_decode)

    enc = sub.add_parser(
        "encode", help="Encode an SFX YAML back to header + data asm files"
    )
    enc.add_argument("--header", type=str, required=True,
                     help="Output header asm path")
    enc.add_argument("--data", type=str, required=True,
                     help="Output data asm path")
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
