import argparse
from pathlib import Path
from csv import reader, writer

from tools.strings.charset import CHARSETS, Charset
from tools.strings.huffman_trees import HuffmanTrees
from tools.strings.encode_decode import encode_string, decode_string, encode_credit_string, decode_credit_string, encode_intro_string, decode_intro_string

def begin_decompress(tree_offsets: bytes, tree_data: bytes, strings: bytes, charset: Charset) -> list[str]:
    """Decompress strings using Huffman trees and custom encoding."""
    hts = HuffmanTrees()
    hts.decode_trees(tree_offsets, tree_data)
    n = 0
    strs = []
    while n < len(strings) - 1 and strings[n] not in (0x00, 0xFF):
        data = strings[n+1:n+strings[n]]
        decompressed = hts.decompress_string(data, charset.eof_char)
        strs.append(decode_string(decompressed, charset))
        n += strings[n]
    return strs


def set_default_paths(args: argparse.Namespace, ext: str) -> argparse.Namespace:
    """Set default output file paths if not provided."""
    base_file = Path(args.input_file[0]).stem.rsplit('_',1)[0]

    if hasattr(args, "offset_file") and not args.offset_file:
        args.offset_file = f"{base_file}_offsets.bin"
    if hasattr(args, "tree_file") and not args.tree_file:
        args.tree_file = f"{base_file}_trees.bin"
    if hasattr(args, "string_file") and not args.string_file and ext:
        args.string_file = base_file + "." + ext
    
    return args


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def compress_func(args: argparse.Namespace) -> None:
    """Compress input strings and write compressed data to output files."""
    args = set_default_paths(args, "")

    # Read input strings
    input_path = Path(args.input_file[0])
    if not input_path.exists():
        raise FileNotFoundError(f"Input file {input_path} not found.")
    strings = input_path.read_text(encoding="utf-8").splitlines()

    # Encode and compress strings
    charset = CHARSETS[args.language]
    encoded_strings = [encode_string(s.strip('\n\r'), charset) for s in strings]
    hts = HuffmanTrees()
    hts.recalculate_trees(encoded_strings, charset.eof_char)
    compressed_data = [hts.compress_string(e, charset.eof_char) for e in encoded_strings]

    # Write compressed data to output files
    for i, chunk in enumerate(chunks(compressed_data, 256)):
        output_path = Path(f"{args.string_file}_{i:02}.huf")
        with output_path.open("wb") as f:
            for data in chunk:
                f.write(bytes([len(data) + 1]))
                f.write(data)

    # Write Huffman trees to output files
    offsets, trees = hts.encode_trees()
    Path(args.offset_file).write_bytes(offsets)
    Path(args.tree_file).write_bytes(trees)

    print(f"Compressed {len(compressed_data)} strings.")


def decompress_func(args: argparse.Namespace) -> None:
    """Decompress input strings and write uncompressed data to output file."""
    args = set_default_paths(args, "txt")

    # Read input data
    tree_offsets = Path(args.offset_file).read_bytes()
    tree_data = Path(args.tree_file).read_bytes()
    compressed_data = bytearray()
    for input_path in [Path(p) for p in args.input_file]:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file {input_path} not found.")
        compressed_data.extend(input_path.read_bytes())

    # Decompress strings
    charset = CHARSETS[args.language]
    result = begin_decompress(tree_offsets, tree_data, compressed_data, charset)

    # Write uncompressed strings to output file
    output_path = Path(args.string_file)
    output_path.write_text("\n".join(result), encoding="utf-8")
    print(f"Wrote {len(result)} strings to {output_path}.")


def rom_decompress_func(args: argparse.Namespace) -> None:
    """Decompress strings from a ROM file."""
    args = set_default_paths(args, "txt")

    # Read input data
    rom_data = Path(args.input_file[0]).read_bytes()

    tree_offsets = rom_data[args.offset_loc:args.tree_loc]
    tree_data = rom_data[args.tree_loc:args.string_loc]
    strings = rom_data[args.string_loc:]

    # Decompress strings
    charset = CHARSETS[args.language]
    result = begin_decompress(tree_offsets, tree_data, strings, charset)

    # Write uncompressed strings to output file
    output_path = Path(args.string_file)
    output_path.write_text("\n".join(result), encoding="utf-8")
    print(f"Wrote {len(result)} strings to {output_path}.")


def decode(encoded_data: bytes, charset: Charset) -> list[str]:
    """Decode array of bytes into a list of strings"""
    n = 0
    decoded_text = []
    while n < len(encoded_data) and encoded_data[n] not in (0x00, 0xFF):
        encoded_string = encoded_data[n+1:n+encoded_data[n]+1]
        decoded_text.append(decode_string(encoded_string, charset))
        n += encoded_data[n] + 1
    
    return decoded_text


def decode_func(args: argparse.Namespace) -> None:
    """Decode input data using a specific charset and write to output file."""
    args = set_default_paths(args, "txt" if args.type == "NORMAL" else "csv")

    input_path = Path(args.input_file[0])
    output_path = Path(args.string_file)
    charset = CHARSETS[args.language]

    input_data = input_path.read_bytes()

    if args.type == "CREDITS":
        decode_credits(input_data, output_path)
    elif args.type == "INTRO":
        decode_intro(input_data, output_path)
    else:
        decode_normal(input_data, CHARSETS[args.language], output_path)

def rom_decode_func(args: argparse.Namespace) -> None:
    """Decode data from a ROM file using a specific charset and write to output file."""
    args = set_default_paths(args, "txt" if args.type == "NORMAL" else "csv")

    rom_path = Path(args.input_file[0])
    output_path = Path(args.string_file)
    charset = CHARSETS[args.language]

    rom_data = rom_path.read_bytes()
    if not args.end_offset:
        args.end_offset = len(rom_data)
    encoded_data = rom_data[args.start_offset:args.end_offset]

    if args.type == "CREDIT":
        decode_credits(encoded_data, output_path)
    elif args.type == "INTRO":
        decode_intro(encoded_data, output_path)
    else:
        decode_normal(encoded_data, CHARSETS[args.language], output_path)

def decode_normal(input_data: bytes, charset: Charset, outfile: Path) -> None:
    """Decode input data using a specific charset and write to output file."""

    outfile.write_text("\n".join(decode(input_data, charset)), encoding="utf-8")

    print(f"Decoded data and wrote to {outfile}.")

def decode_intro(input_data: bytes, outfile: Path):

    data = [decode_intro_string(input_data)]

    with outfile.open("w", encoding="utf-8", newline="") as f:
        w = writer(f)
        w.writerows(data)

    print(f"Decoded data and wrote to {outfile}.")

def decode_credits(input_data: bytes, outfile: Path):

    data = []
    i = 0
    while i < len(input_data):
        line, n = decode_credit_string(input_data[i:])
        if line[0] == 0xFF:
            break
        data.append(line)
        i += n

    with outfile.open("w", encoding="utf-8", newline="") as f:
        w = writer(f)
        w.writerows(data)

    print(f"Decoded data and wrote to {outfile}.")

def encode_func(args: argparse.Namespace) -> None:
    """Encode input text using a specific charset and write to output file."""
    if args.type == "NORMAL":
        encode_normal(args)
    elif args.type == "INTRO":
        encode_intro(args)
    elif args.type == "CREDITS":
        encode_credits(args)

def encode_normal(args: argparse.Namespace) -> None:
    """Encode input text using a specific charset and write to output file."""
    args = set_default_paths(args, "bin")

    input_path = Path(args.input_file[0])
    output_path = Path(args.string_file)
    charset = CHARSETS[args.language]
    strings = input_path.read_text(encoding="utf-8").splitlines()

    encoded_strings = [encode_string(s.strip('\n\r'), charset) for s in strings]

    encoded_data = bytearray()
    for e in encoded_strings:
        encoded_data.append(len(e))
        encoded_data.extend(e)

    output_path.write_bytes(encoded_data)

    print(f"Encoded text and wrote to {output_path}.")


def encode_credits(args: argparse.Namespace) -> None:
    """Encode credit text and write to output file."""
    args = set_default_paths(args, "bin")

    input_path = Path(args.input_file[0])
    output_path = Path(args.string_file)
    data = []
    with input_path.open("r",encoding="utf-8") as f:
        csv = reader(f)
        for row in csv:
            data.append((int(row[0]), int(row[1]), row[2]))

    encoded_data = bytearray()
    for row in data:
        encoded_data.extend(encode_credit_string(row))
    encoded_data.append(0xFF)

    output_path.write_bytes(encoded_data)

    print(f"Encoded text and wrote to {output_path}.")


def encode_intro(args: argparse.Namespace) -> None:
    """Encode intro text and write to output file."""
    args = set_default_paths(args, "")

    input_path = Path(args.input_file[0])
    data = []
    with input_path.open("r",encoding="utf-8") as f:
        csv = reader(f)
        for row in csv:
            data.append((int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), row[5], row[6]))

    encoded_strings = [encode_intro_string(line) for line in data]

    if len(encoded_strings) == 1:
        outfile = Path(args.string_file + ".bin")
        outfile.write_bytes(encoded_strings[0])
        print(f"Encoded text and wrote to {outfile}.")
    else:
        for i in len(encoded_strings):
            outfile = Path(args.string_file + f"{i:02}.bin")
            outfile.write_bytes(encoded_strings[i])
            outfile.write_bytes(encoded_strings[0])
            print(f"Encoded text and wrote to {outfile}.")


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

    # Create the subparser for decode mode
    decode_parser = subparsers.add_parser('decode', help='Decode data using a specific charset')
    decode_parser.add_argument('-s', '--string-file', type=str, help='Output file for decoded text')
    decode_parser.add_argument('-l', '--language', choices=['ENGLISH', 'JAPANESE', 'FRENCH', 'GERMAN'], default='ENGLISH', help='Language to use')
    decode_parser.add_argument('-t', '--type', choices=['INTRO', 'CREDITS', 'NORMAL'], default='NORMAL', help='Charset type to use')
    decode_parser.add_argument('input_file', nargs=1, type=str, help='Input file (encoded data)')
    decode_parser.set_defaults(func=decode_func)

    # Create the subparser for rom-decode mode
    rom_decode_parser = subparsers.add_parser('rom-decode', help='Decode data from a ROM file using a specific charset')
    rom_decode_parser.add_argument('-S', '--start-offset', type=lambda x: int(x,0), help='Offset location in ROM for encoded data', required=True)
    rom_decode_parser.add_argument('-E', '--end-offset', type=lambda x: int(x,0), help='End of encoded data in ROM', required=False)
    rom_decode_parser.add_argument('-s', '--string-file', type=str, help='Output file for decoded text')
    rom_decode_parser.add_argument('-l', '--language', choices=['ENGLISH', 'JAPANESE', 'FRENCH', 'GERMAN'], default='ENGLISH', help='Language to use')
    rom_decode_parser.add_argument('-t', '--type', choices=['INTRO', 'CREDITS', 'NORMAL'], default='NORMAL', help='Charset type to use')
    rom_decode_parser.add_argument('input_file', nargs=1, type=str, help='Input file (ROM file)')
    rom_decode_parser.set_defaults(func=rom_decode_func)

    # Create the subparser for encode mode
    encode_parser = subparsers.add_parser('encode', help='Encode text using a specific charset')
    encode_parser.add_argument('-s', '--string-file', type=str, help='Output file for encoded data')
    encode_parser.add_argument('-l', '--language', choices=['ENGLISH', 'JAPANESE', 'FRENCH', 'GERMAN'], default='ENGLISH', help='Language to use')
    encode_parser.add_argument('-t', '--type', choices=['INTRO', 'CREDITS', 'NORMAL'], default='NORMAL', help='Charset type to use')
    encode_parser.add_argument('input_file', nargs=1, type=str, help='Input file (text file)')
    encode_parser.set_defaults(func=encode_func)

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
