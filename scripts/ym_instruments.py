"""CLI utility to convert YM2612 instrument banks between asm and YAML.

Subcommands:

* ``decode``: read a labelled-``db`` asm file (e.g.
  ``landstalker_disasm/code/audio/ym_instruments.asm``) and write a
  human-readable YAML file describing each instrument's algorithm,
  feedback and four operator envelopes.
* ``encode``: read such a YAML file and re-emit asm with the same
  ``LABEL: db ...`` shape used by the disasm.

The byte format is fixed by the Z80 driver
(``landstalker_disasm/code/audio/sounddrv.asm:1687-1806``); see the
header of :mod:`scripts.common.models.ym_instrument` for the per-byte
field layout and the README for editing guidance.
"""

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

import yaml

from scripts.common.models.ym_instrument import YmInstrumentBank


def start_decode(args: Namespace) -> None:
    """Read an asm instruments file and write a YAML representation.

    Uses ``args.input_file`` as the source and ``args.output_file``
    (defaulting to the input stem with ``.yaml``) as the destination.
    """
    if args.output_file is None:
        args.output_file = str(Path(args.input_file).stem) + ".yaml"

    text = Path(args.input_file).read_text(encoding="utf-8")
    bank = YmInstrumentBank.parse_asm(text)

    with Path(args.output_file).open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            bank.to_yaml_dict(), f,
            sort_keys=False, default_flow_style=None, width=120,
        )

    print(f"Decoded {len(bank)} instrument(s) to {args.output_file}.")


def start_encode(args: Namespace) -> None:
    """Read a YAML instruments file and write an asm representation.

    Uses ``args.input_file`` as the source and ``args.output_file``
    (defaulting to the input stem with ``.asm``) as the destination.
    """
    if args.output_file is None:
        args.output_file = str(Path(args.input_file).stem) + ".asm"

    with Path(args.input_file).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    bank = YmInstrumentBank.from_yaml_dict(data)
    Path(args.output_file).write_text(bank.to_asm(), encoding="utf-8")

    print(f"Encoded {len(bank)} instrument(s) to {args.output_file}.")


def build_argparser() -> ArgumentParser:
    """Build the argparse parser with ``decode`` and ``encode`` subcommands."""
    parser = ArgumentParser(
        description="Decode or encode YM2612 instrument banks "
                    "(ym_instruments.asm <-> YAML)."
    )
    subparsers = parser.add_subparsers(title="Modes", help="Select a mode")

    decode_parser = subparsers.add_parser(
        "decode", help="Decode an instruments asm file into YAML"
    )
    decode_parser.add_argument(
        "-o", "--output-file", type=str,
        help="Output YAML path (default: input stem + .yaml)"
    )
    decode_parser.add_argument(
        "input_file", type=str,
        help="Input asm file (e.g. ym_instruments.asm)"
    )
    decode_parser.set_defaults(func=start_decode)

    encode_parser = subparsers.add_parser(
        "encode", help="Encode a YAML instruments file back to asm"
    )
    encode_parser.add_argument(
        "-o", "--output-file", type=str,
        help="Output asm path (default: input stem + .asm)"
    )
    encode_parser.add_argument(
        "input_file", type=str,
        help="Input YAML file"
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
