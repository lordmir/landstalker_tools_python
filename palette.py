from pathlib import Path
from argparse import ArgumentParser, Namespace
from json import dump, load

from tools.models.palette import Palettes

def start_encode(args: Namespace) -> None:
    if args.output_file is None:
        args.output_file = str(Path(args.input_files[0]).stem)
    
    with Path(args.input_files[0]).open("r") as f:
        inlist = load(f).get("palettes")
    
    palettes = Palettes(palettes=inlist)
    if not args.no_print:
        palettes.print_palette_preview()

    if not args.split:
        Path(args.output_file + ".pal").write_bytes(palettes.encode(bool(args.variable_width)))
    else:
        for i, p in enumerate(inlist):
            palettes = Palettes(palettes=[p])
            Path(f"{args.output_file}{i+1:03}.pal").write_bytes(palettes.encode(bool(args.variable_width)))
    
    print(f"Encoded {len(inlist)} palette(s) of {len(inlist[0])} entries.")


def start_decode(args: Namespace) -> None:
    if args.output_file is None:
        args.output_file = str(Path(args.input_files[0]).stem + ".json")
    
    data = bytearray()

    for file in args.input_files:
        fdata = Path(file).read_bytes()
        if args.start is not None:
            fdata = fdata[args.start:]
            if args.length is not None:
                fdata = fdata[:args.length]
        data.extend(fdata)
    
    palettes = Palettes(data=data, entries=args.count)
    result = palettes.palettes

    with Path(args.output_file).open("w") as f:
        dump({"palettes": result}, f, indent=2)
    
    if not args.no_print:
        palettes.print_palette_preview()
    
    print(f"Decoded {len(result)} palette(s) of {len(result[0])} entries.")

def build_argparser() -> ArgumentParser:
    # Create the main parser
    parser = ArgumentParser(description='Decode or Encode Palettes')

    # Create subparsers for each mode
    subparsers = parser.add_subparsers(title='Modes', help='Select a mode')

    # Create the subparser for decode mode
    decode_parser = subparsers.add_parser('decode', help='Decode Palette')
    decode_parser.add_argument("-n", "--no-print", help="Suppress printing", action='store_true')
    decode_parser.add_argument('-s', '--start', type=lambda x: int(x, base=0), default=None, help='File offset in hex')
    decode_parser.add_argument('-l', '--length', type=lambda x: int(x, base=0), default=None, help='File length in hex')
    length_group = decode_parser.add_mutually_exclusive_group(required=True)
    length_group.add_argument('-c', '--count', type=int, help='Number of colours per palette')
    length_group.add_argument('-w', '--variable-width', help='Variable-width palette', action='store_true')
    decode_parser.add_argument('-o', '--output-file', type=str, help='Output file (*.json)')
    decode_parser.add_argument('input_files', nargs='+', type=str, help='Input file (*.pal)')
    decode_parser.set_defaults(func=start_decode)

    # Create the subparser for encode mode
    encode_parser = subparsers.add_parser('encode', help='Encode Palette')
    encode_parser.add_argument("-n", "--no-print", help="Suppress Printing", action='store_true')
    encode_parser.add_argument('-o', '--output-file', type=str, help='Output pal file (*.pal)')
    encode_parser.add_argument('-s', '--split', action='store_true', help='Split output into multiple files')
    encode_parser.add_argument('-w', '--variable-width', help='Store as variable-width palette', action='store_true')
    encode_parser.add_argument('input_files', nargs=1, type=str, help='Input file (*.json)')
    encode_parser.set_defaults(func=start_encode)

    return parser


def main():
    # Make the parser
    parser = build_argparser()
    # Parse the arguments
    args = parser.parse_args()
    # Run the command
    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()


# data = bytearray()
# for p in Path(r"C:\projects\landstalker_disasm\disassembly\assets_packed\graphics\roompalettes").glob("pal*.pal"):
#     data.extend(p.read_bytes())

# pal = Palettes(data=data, entries=13)
# pal.print_palette_preview()
# print(pal.encode() == data)
