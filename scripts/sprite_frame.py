from argparse import ArgumentParser, Namespace
from pathlib import Path
from json import dump, load
import sys

from scripts.common.models.sprite_frame import SpriteFrame, SubSprite

def start_decode(args: Namespace):
    if not args.output_file:
        args.output_file = Path(args.input_file).stem + ".bin"
    if not args.output_json:
        args.output_json = Path(args.input_file).stem + ".json"
    pass

    encoded = Path(args.input_file).read_bytes()
    frame = SpriteFrame(data=encoded)
    subsprites = [{"x": s.x, "y": s.y, "width": s.width, "height": s.height} for s in frame.subsprites]

    Path(args.output_file).write_bytes(frame.tile_data)
    with Path(args.output_json).open("w") as f:
        dump({"subsprites": subsprites, "compressed": frame.is_compressed}, f, indent=2)

def start_encode(args: Namespace):
    paths = [Path(x) for x in args.input_files]
    if not any(p.suffix == ".json" for p in paths):
        raise ValueError("JSON file missing")
    if not any(p.suffix == ".bin" for p in paths):
        raise ValueError("BIN file missing")
    json_path = [p for p in paths if p.suffix == ".json"][0]
    bin_path = [p for p in paths if p.suffix == ".bin"][0]

    if not args.output_file:
        args.output_file = json_path.stem + ".frm"

    tile_data = bin_path.read_bytes()
    with json_path.open("r") as f:
        obj = load(f)
    
    subsprites = [SubSprite(**x) for x in obj["subsprites"]]
    
    frame = SpriteFrame(subsprites=subsprites, tiles=tile_data, compressed=obj["compressed"])

    Path(args.output_file).write_bytes(frame.encode())


def build_argparser() -> ArgumentParser:
    # Create the main parser
    parser = ArgumentParser(description='Decode or Encode a Sprite Frame')

    # Create subparsers for each mode
    subparsers = parser.add_subparsers(title='Modes', help='Select a mode')

    # Create the subparser for decode mode
    decode_parser = subparsers.add_parser('decode', help='Decode Sprite Frame')
    decode_parser.add_argument('-s', '--start', type=lambda x: int(x, base=0), default=None, help='File offset in hex')
    decode_parser.add_argument('-l', '--length', type=lambda x: int(x, base=0), default=None, help='File length in hex')
    decode_parser.add_argument('-o', '--output-file', type=str, help='Output file (*.bin)')
    decode_parser.add_argument('-j', '--output-json', type=str, help='Output file (*.json)')
    decode_parser.add_argument('input_file', type=str, help='Input file (*.frm)')
    decode_parser.set_defaults(func=start_decode)

    # Create the subparser for encode mode
    encode_parser = subparsers.add_parser('encode', help='Encode Sprite')
    encode_parser.add_argument('-o', '--output-file', type=str, help='Output pal file (*.frm)')
    encode_parser.add_argument('input_files', nargs=2, type=str, help='Input files (*.json and *.bin)')
    encode_parser.set_defaults(func=start_encode)

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
