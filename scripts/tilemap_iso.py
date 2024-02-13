from argparse import ArgumentParser, Namespace
from pathlib import Path
from csv import reader, writer
import sys

from scripts.common.codecs.tilemap3d import Tilemap3D

def make_2d(data: list[int], width: int) -> list[list[int]]:
    result = []
    for i in range(0, len(data), width):
        result.append(data[i:i+width])
    return result

def flatten(data: list[list[int]]) -> tuple[list[list[int]], int, int]:
    result = []
    for row in data:
        result.extend(row)
    return result, len(data[0]), len(data)

def start_decompress(args: Namespace):

    if args.output_dir is None and any(x is None for x in (args.foreground_file, args.background_file, args.heightmap_file)):
        args.output_dir = f'{Path(args.input_file[0]).stem}'
    if args.foreground_file is None:
        args.foreground_file = str(Path(args.output_dir).joinpath("foreground.csv"))
    if args.background_file is None:
        args.background_file = str(Path(args.output_dir).joinpath("background.csv"))
    if args.heightmap_file is None:
        args.heightmap_file = str(Path(args.output_dir).joinpath("heightmap.csv"))
    
    data = Path(args.input_file[0]).read_bytes()

    if args.start is not None:
        data = data[args.start:]
        if args.length is not None:
            data = data[:args.length]

    tm = Tilemap3D(data, verbose=bool(args.verbose))

    if args.output_dir is not None:
        outdir = Path(args.output_dir)
        if not outdir.is_dir():
            outdir.mkdir()

    with Path(args.foreground_file).open("w", newline="", encoding="utf-8") as f:
        w = writer(f)
        for row in make_2d(tm.foreground, tm.width):
            w.writerow([f"{x:5}" for x in row])
    with Path(args.background_file).open("w", newline="", encoding="utf-8") as f:
        w = writer(f)
        for row in make_2d(tm.background, tm.width):
            w.writerow([f"{x:5}" for x in row])
    with Path(args.heightmap_file).open("w", newline="", encoding="utf-8") as f:
        w = writer(f)
        w.writerow([tm.left, tm.top])
        for row in make_2d(tm.heightmap, tm.hm_width):
            w.writerow([f"0x{x:04X}" for x in row])
    print(f"Decompressed {tm.width}x{tm.height} isometric tilemap from {len(data)} bytes.")

def start_compress(args: Namespace):
    if args.input_dir is None and any(x is None for x in (args.foreground_file, args.background_file, args.heightmap_file)):
        args.input_dir = f'{Path(args.output_file[0]).stem}'
    if args.foreground_file is None:
        args.foreground_file = str(Path(args.input_dir).joinpath("foreground.csv"))
    if args.background_file is None:
        args.background_file = str(Path(args.input_dir).joinpath("background.csv"))
    if args.heightmap_file is None:
        args.heightmap_file = str(Path(args.input_dir).joinpath("heightmap.csv"))
    if args.output_file is None:
        args.output_file = [str(Path(args.input_dir).stem + ".cmp")]

    foreground = []
    background = []
    heightmap = []
    with Path(args.foreground_file).open('r', encoding="utf-8") as f:
        csv = reader(f)
        for row in csv:
            foreground.append([int(x) for x in row])
    with Path(args.background_file).open('r', encoding="utf-8") as f:
        csv = reader(f)
        for row in csv:
            background.append([int(x) for x in row])
    with Path(args.heightmap_file).open('r', encoding="utf-8") as f:
        csv = reader(f)
        first = True
        for row in csv:
            if first:
                left, top = row
                first = False
            else:
                heightmap.append([int(x,0) for x in row])
    
    tm = Tilemap3D(verbose=bool(args.verbose))
    tm.foreground, tm.width, tm.height = flatten(foreground)
    tm.background, *_ = flatten(background)
    tm.heightmap, tm.hm_width, tm.hm_height = flatten(heightmap)
    tm.left = left
    tm.top = top
    compressed = tm.encode()
    Path(args.output_file[0]).write_bytes(compressed)

    print(f"Compressed {tm.width}x{tm.height} tilemap to {len(compressed)} bytes.")


def build_argparser() -> ArgumentParser:
    # Create the main parser
    parser = ArgumentParser(description='Compress or decompress Isometric Maps')
    parser.add_argument("-v", "--verbose", help="Enable Verbose Mode", action='store_true')

    # Create subparsers for each mode
    subparsers = parser.add_subparsers(title='Modes', help='Select a mode')

    # Create the subparser for compress mode
    decompress_parser = subparsers.add_parser('extract', help='Extract Tilemap')
    output_group = decompress_parser.add_mutually_exclusive_group()
    output_group.add_argument('-o', '--output-dir', type=str, help='Output directory')
    outfile_group = output_group.add_argument_group("Output Files", "Output Files")
    outfile_group.add_argument('-F', '--foreground-file', type=str, help='Foreground CSV to compress')
    outfile_group.add_argument('-B', '--background-file', type=str, help='Background CSV to compress')
    outfile_group.add_argument('-H', '--heightmap-file', type=str, help='Heightmap CSV to compress')
    decompress_parser.add_argument('-s', '--start', type=lambda x: int(x, base=0), default=None, help='File offset in hex')
    decompress_parser.add_argument('-l', '--length', type=lambda x: int(x, base=0), default=None, help='File length in hex')
    decompress_parser.add_argument('input_file', nargs=1, type=str, help='Input file (*.cmp)')
    decompress_parser.set_defaults(func=start_decompress)

    # Create the subparser for normal decompress mode
    compress_parser = subparsers.add_parser('compress', help='Compress Tilemap')
    input_group = compress_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('-i', '--input-dir', type=str, help='Input directory')
    infile_group = input_group.add_argument_group("Input Files", "Input Files")
    infile_group.add_argument('-F', '--foreground-file', type=str, help='Foreground CSV to compress')
    infile_group.add_argument('-B', '--background-file', type=str, help='Background CSV to compress')
    infile_group.add_argument('-H', '--heightmap-file', type=str, help='Heightmap CSV to compress')
    compress_parser.add_argument('output_file', nargs='?', type=str, help='Output cmp file')
    compress_parser.set_defaults(func=start_compress)

    return parser


def main(argv: list[str]):
    # Make the parser
    parser = build_argparser()
    # Parse the arguments
    args = parser.parse_args(argv)
    # Run the command
    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main(sys.argv)
