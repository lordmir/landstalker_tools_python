import argparse
from pathlib import Path

from tools.strings.charset import CHARSETS
from tools.strings.huffman_trees import HuffmanTrees
from tools.strings.encode_decode import encode_string, decode_string

def begin_decompress(tree_offsets: bytes, tree_data: bytes, strings: bytes, language: str) -> list[str]:
    hts = HuffmanTrees()
    hts.decode_trees(tree_offsets, tree_data)
    n = 0
    strs = []
    while n < len(strings) - 1 and strings[n] not in (0x00, 0xFF):
        data = strings[n+1:n+strings[n]]
        strs.append(decode_string(hts.decompress_string(data, CHARSETS[language].eof_char), CHARSETS[language]))
        n += strings[n]
    
    return strs


def compress_func(args):
    BASE_FILE = Path(args.input_file[0]).stem.rsplit('_',1)[0]
    if not args.offset_file:
        args.offset_file = BASE_FILE + "_offsets.bin"
    if not args.tree_file:
        args.tree_file = BASE_FILE + "_trees.bin"
    if not args.string_file:
        args.string_file = BASE_FILE
    
    with open(args.input_file[0], "r", encoding="utf-8") as f:
        strings = f.readlines()
    encoded_strings = [encode_string(s.strip('\n\r'), CHARSETS[args.language]) for s in strings]

    hts = HuffmanTrees()
    hts.recalculate_trees(encoded_strings, CHARSETS[args.language].eof_char)
    
    cmp = [hts.compress_string(e, CHARSETS[args.language].eof_char) for e in encoded_strings]

    for i in range((len(cmp) + 255) // 256):
        with open(f"{args.string_file}_{i:02}.huf","wb") as f:
            for j in range(min(256, len(cmp) - i * 256)):
                f.write(bytes([len(cmp[i * 256 + j]) + 1]))
                f.write(cmp[i * 256 + j])
    
    offsets, trees = hts.encode_trees()

    with open(args.offset_file, "wb") as f:
        f.write(offsets)
    with open(args.tree_file, "wb") as f:
        f.write(trees)
    
    print(f"Compressed {len(cmp)} strings.")


def decompress_func(args):
    BASE_FILE = Path(args.input_file[0]).stem.rsplit('_',1)[0]
    if not args.offset_file:
        args.offset_file = BASE_FILE + "_offsets.bin"
    if not args.tree_file:
        args.tree_file = BASE_FILE + "_trees.bin"
    if not args.string_file:
        args.string_file = BASE_FILE + ".txt"

    with open(args.offset_file, "rb") as f:
        tree_offsets = f.read()
    with open(args.tree_file, "rb") as f:
        tree_data = f.read()
    strings = bytearray()
    for filename in args.input_file:
        with open(filename, "rb") as f:
            strings.extend(f.read())
    result = begin_decompress(tree_offsets, tree_data, strings, args.language)
    with open(args.string_file, "w", encoding="utf-8") as f:
        f.write("\n".join(result))
    print(f"Wrote {len(result)} strings to {args.string_file}.")


def rom_decompress_func(args):
    BASE_FILE = Path(args.input_file[0]).stem.rsplit('_',1)[0]
    if not args.string_file:
        args.string_file = BASE_FILE + ".txt"
    with open(args.input_file[0], "rb") as f:
        rom = f.read()
    tree_offsets = rom[args.offset_loc:args.tree_loc]
    tree_data = rom[args.tree_loc:args.string_loc]
    strings = rom[args.string_loc:]
    result = begin_decompress(tree_offsets, tree_data, strings, args.language)
    with open(args.string_file, "w", encoding="utf-8") as f:
        f.write("\n".join(result))
    print(f"Wrote {len(result)} strings to {args.string_file}.")


def build_argparser() -> argparse.ArgumentParser:

    # Create the main parser
    parser = argparse.ArgumentParser(description='Compress or decompress strings')

    # Create subparsers for each mode
    subparsers = parser.add_subparsers(title='Modes', help='Select a mode')

    # Create the subparser for compress mode
    compress_parser = subparsers.add_parser('compress', help='Compress strings')
    compress_parser.add_argument('-f', '--offset-file', type=str, help='Output file for Huffman offset table')
    compress_parser.add_argument('-t', '--tree-file', type=str, help='Output file for Huffman tree')
    compress_parser.add_argument('-s', '--string-file', type=str, help='Template output file for compressed strings')
    compress_parser.add_argument('-l', '--language', choices=['ENGLISH', 'JAPANESE', 'FRENCH', 'GERMAN'], default='ENGLISH', help='Language to use')
    compress_parser.add_argument('input_file', nargs=1, type=str, help='Input files (string file)')
    compress_parser.set_defaults(func=compress_func)

    # Create the subparser for normal decompress mode
    decompress_parser = subparsers.add_parser('decompress', help='Decompress strings')
    decompress_parser.add_argument('-f', '--offset-file', type=str, help='Input file for Huffman offset table')
    decompress_parser.add_argument('-t', '--tree-file', type=str, help='Input file for Huffman tree')
    decompress_parser.add_argument('-s', '--string-file', type=str, help='Output file for uncompressed strings')
    decompress_parser.add_argument('-l', '--language', choices=['ENGLISH', 'JAPANESE', 'FRENCH', 'GERMAN'], default='ENGLISH', help='Language to use')
    decompress_parser.add_argument('input_file', nargs='+', type=str, help='Input file (compressed string file)')
    decompress_parser.set_defaults(func=decompress_func)

    # Create the subparser for ROM decompress mode
    rom_decompress_parser = subparsers.add_parser('rom-decompress', help='Decompress from ROM')
    rom_decompress_parser.add_argument('-F', '--offset-loc', type=lambda x: int(x,0), help='Offset location in ROM for Huffman table', required=True)
    rom_decompress_parser.add_argument('-T', '--tree-loc', type=lambda x: int(x,0), help='Offset location in ROM for Huffman tree data', required=True)
    rom_decompress_parser.add_argument('-S', '--string-loc', type=lambda x: int(x,0), help='Offset location in ROM for compressed strings, required=True')
    rom_decompress_parser.add_argument('-s', '--string-file', type=str, help='Output file for uncompressed strings')
    rom_decompress_parser.add_argument('-l', '--language', choices=['ENGLISH', 'JAPANESE', 'FRENCH', 'GERMAN'], default='ENGLISH', help='Language to use')
    rom_decompress_parser.add_argument('input_file', nargs=1, type=str, help='Input file (ROM file)')
    rom_decompress_parser.set_defaults(func=rom_decompress_func)

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


if __name__ == "__main__":
    main()
