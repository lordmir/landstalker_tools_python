from argparse import ArgumentParser, Namespace
from pathlib import Path
import sys

from scripts.common.codecs.lz77 import LZ77_encode, LZ77_decode

def start_decompress(args: Namespace) -> None:
    """Starts decompression with command line args.

    Args:
        args: Command line arguments namespace.
    """
    if args.output is None:
        args.output = f'{Path(args.infile[0]).stem}.bin'
    
    with open(args.infile[0], 'rb') as f:
        compressed = f.read()
    
    if args.start is not None:
        compressed = compressed[args.start:]
        if args.length is not None:
            compressed = compressed[:args.length]

    
    uncompressed, clen = LZ77_decode(compressed)
    with open(args.output, "wb") as f:
        f.write(uncompressed)

    print(f"Decompressed {len(uncompressed)} bytes from {clen} bytes, {args.infile[0]} to {args.output}.")

def start_compress(args: Namespace) -> None:
    """Starts compression with command line args.

    Args:  
        args: Command line arguments namespace.
    """
    if args.output is None:
        args.output = f'{Path(args.infile[0]).stem}.lz77'
    
    with open(args.infile[0], 'rb') as f:
        uncompressed = f.read()

    compressed = bytes(LZ77_encode(uncompressed))
    with open(args.output, "wb") as f:
        f.write(compressed)

    print(f"Compressed {len(uncompressed)} bytes to {len(compressed)} bytes, {args.infile[0]} to {args.output}.")


def main(argv: list[str]) -> None:
    """Main entry point for the program."""
    parser = ArgumentParser(description='LZ77 Graphics Compressor / Decompressor')

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
                        help='Output filename (optional, should default to .bin in decompression mode, or .lz77 in compression mode)')
    parser.add_argument('infile', type=str, nargs=1,
                        help='Input filename')

    # Parse the arguments
    args = parser.parse_args(argv)

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
    main(sys.argv)
