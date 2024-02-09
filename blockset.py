from argparse import ArgumentParser, Namespace
from pathlib import Path
from csv import reader, writer

from tools.codecs.blockset import compress, decompress
from tools.models.tile import Tile

def start_decompress(args: Namespace):

    if args.output is None:
        args.output = f'{Path(args.infile[0]).stem}.csv'
    
    with open(args.infile[0], 'rb') as f:
        data = f.read()
    
    if args.start is not None:
        data = data[args.start:]
        if args.length is not None:
            data = data[:args.length]

    
    blocks = decompress(data)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = writer(f)
        for block in blocks:
            w.writerow([str(t.encode()) for t in block])
    print(f"Decompressed {len(blocks)} blocks from {len(data)} bytes, {args.infile[0]} to {args.output}.")

def start_compress(args: Namespace):

    if args.output is None:
            args.output = f'{Path(args.infile[0]).stem}.cbs'
    
    blocks = []
    with open(args.infile[0], 'r', encoding="utf-8") as f:
        csv = reader(f)
        for row in csv:
            blocks.extend([Tile(int(x, 16)) for x in row])

    data = bytes(compress(blocks))
    with open(args.output, "wb") as f:
        f.write(data)
    print(f"Compressed {len(blocks)//4} blocks to {len(data)} bytes, {args.infile[0]} to {args.output}.")


def main():
    parser = ArgumentParser(description='My program')

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('-d', '--decompress', action='store_true',
                            help='Decompression mode')
    mode_group.add_argument('-c', '--compress', action='store_true',
                            help='Compression mode')
    parser.add_argument('-s', '--start', type=lambda x: int(x, base=0), default=None,
                        help='Start address in hex (requires decompression mode)')
    parser.add_argument('-l', '--length', type=lambda x: int(x, base=0), default=None,
                        help='Length in hex (requires decompression mode and start address)')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='Output filename (optional, should default to .csv in decompression mode, or .cbs in compression mode)')
    parser.add_argument('infile', type=str, nargs=1,
                        help='Input filename')

    # Parse the arguments
    args = parser.parse_args()

    # Check if start address and length are specified without decompression mode
    if (args.start or args.length) and not args.decompress:
        parser.error('--start and --length require --decompress')
    
    if not args.start:
        args.start = 0
    
    inpath = Path(args.infile[0])
    if inpath.is_file():
        if not args.length and args.start < inpath.stat().st_size:
            args.length = inpath.stat().st_size - args.start
        if args.start + args.length > inpath.stat().st_size:
            raise parser.error(f'{args.start:X} + {args.length:X} is greater than the size of the file.')
    else:
        raise parser.error(f'{args.infile} does not exist.')

    if args.decompress:
        start_decompress(args)
    elif args.compress:
        start_compress(args)


if __name__ == '__main__':
    main()
