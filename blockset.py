from bitstring import BitStream, Bits
from dataclasses import dataclass
from enum import Enum
from argparse import ArgumentParser, Namespace
from pathlib import Path
from csv import reader, writer

class Attr(Enum):
    """Tile attributes that can be masked on/off.

    Attributes:
        HFLIP: Mask for horizontal flip.
        VFLIP: Mask for vertical flip. 
        PRIORITY: Mask for priority attribute.
    """
    HFLIP = 0,
    VFLIP = 1,
    PRIORITY = 2

class Tile:
    """Single 16x16 tile with attributes.

    Attributes:
        idx: Tile index value.
        hflip: Boolean for horizontal flip attribute.
        vflip: Boolean for vertical flip attribute.
        priority: Boolean for priority attribute.
    """
    idx: int = 0
    hflip: bool = False
    vflip: bool = False
    priority: bool = False

    def __init__(self, val: int = 0) -> None:
        self.idx = val & 0x7FF
        self.hflip = (val & 0x800) > 0
        self.vflip = (val & 0x1000) > 0
        self.priority = (val & 0x8000) > 0

    def set_attr(self, attr: Attr) -> None:
        """Set boolean attribute on tile
        
        Args:
            attr: Attribute to set
        Returns:
            None
        """

        if attr == Attr.HFLIP:
            self.hflip = True
        elif attr == Attr.VFLIP:
            self.vflip = True
        elif attr == Attr.PRIORITY:
            self.priority = True
    
    def has_attr(self, attr: Attr) -> bool:
        """Read boolean attribute on tile
        
        Args:
            attr: Attribute to read
        Returns:
            bool: the attribute
        """

        if attr == Attr.HFLIP:
            return self.hflip
        elif attr == Attr.VFLIP:
            return self.vflip
        elif attr == Attr.PRIORITY:
            return self.priority

    def __repr__(self):
        """String representation showing index and attributes
        
        Returns:
            Nicely formatted attribute string
        """

        s = f"{self.idx:04X}"
        s += "H" if self.hflip else " "
        s += "V" if self.vflip else " "
        s += "P" if self.priority else " "
        return s

    def encode(self) -> str:
        code = self.idx & 0x7FF
        code |= 0x800 if self.hflip else 0
        code |= 0x1000 if self.vflip else 0
        code |= 0x8000 if self.priority else 0
        return f"{code:04X}"


def mask_tiles(tiles: list[Tile], attr: Attr, stream: BitStream) -> None:
    """Decode attribute mask from stream and set attrs on tiles
    
    Args:
        tiles: List of tiles to set attributes on
        attr: Attribute to decode and set
        stream: Bitstream to decode mask from
    Returns:
        None
    """
    set_attr = True
    i = 0
    num = 0

    while i < len(tiles):
        set_attr = not set_attr
        num += stream.read('ue')

        for j in range(num):
            if set_attr:
                tiles[i + j].set_attr(attr)
        i += num
        num = 1


def decode_tile(stream: BitStream, queue: list[int]) -> int:
    """Decode tile index from stream, using queue for caching
    
    Args:
        stream: Bitstream to decode tile index from
        queue: Tile queue for reusing indices
        
    Returns: 
        Decoded tile index
    """
    if stream.read('bin:1') == '1':
        idx = int(stream.read('bin:4'),2)
        queue.insert(0, queue.pop(idx))
    else:  
        val = int(stream.read('bin:11'),2)
        queue.insert(0, val)
        queue.pop()
    return queue[0]


def decompress(stream: BitStream) -> list[list[Tile]]:
    """Decompress tile data from .cbs stream into list of blocks
    
    Args:
        stream: Bitstream containing compressed tile data
        
    Returns: 
        List of block lists, each containing 4 Tiles 
    """
    total_blocks = stream.read('uint:16')

    tiles = []
    for _ in range(total_blocks * 4):
        tiles.append(Tile()) 

    mask_tiles(tiles, Attr.PRIORITY, stream)
    mask_tiles(tiles, Attr.VFLIP, stream) 
    mask_tiles(tiles, Attr.HFLIP, stream)

    queue = [0] * 16
    for i in range(0, len(tiles), 2):
        t1 = decode_tile(stream, queue)
        tiles[i].idx = t1

        if stream.read('bin:1') == '1':
            if tiles[i].hflip:
                tiles[i+1].idx = t1 - 1
            else: 
                tiles[i+1].idx = t1 + 1
        else:
            tiles[i+1].idx = decode_tile(stream, queue)

    # reconstruct blocks
    blocks = []
    for i in range(0, len(tiles), 4):
        blocks.append(tiles[i:i+4])

    return blocks 


def encode_mask(stream: BitStream, tiles: list[Tile], attr: Attr) -> None:
    """Encode run lengths of tile attributes into a bitstream.

    Args:
        stream: A BitStream to store the RLE-encoded mask.
        tiles: List of tiles to encode.
        attr: The attribute to check for encoding.

    Returns:
        None
    """

    current_run = 0
    tile_has_attribute = False

    for i in range(len(tiles)):
        new_tile_has_attribute = tiles[i].has_attr(attr)

        if new_tile_has_attribute != tile_has_attribute:
            tile_has_attribute = new_tile_has_attribute
            stream += Bits(ue=current_run)
            current_run = 0
        else:
            current_run += 1

    # Encode the final run
    if current_run > 0:
        stream += Bits(ue=(current_run))

    return stream


def compress(tiles: list[list[Tile]]) -> bytes:
    """Compress tile data using the provided encoding scheme.

    Args:
        tiles: List of block lists, each containing 4 Tiles.

    Returns:
        BitStream: Compressed tile data.
    """

    stream = BitStream()

    stream += Bits(uint=len(tiles)//4, length=16)  # Write the number of tiles

    encode_mask(stream, tiles, Attr.PRIORITY)
    encode_mask(stream, tiles, Attr.VFLIP)
    encode_mask(stream, tiles, Attr.HFLIP)

    queue = [0] * 16
    for i in range(0, len(tiles), 2):
        # Encode first tile
        encode_tile(stream, tiles[i].idx, queue)

        # Encode second tile relationship
        if (tiles[i + 1].idx == tiles[i].idx + (-1 if tiles[i].hflip else 1)):
            stream += Bits(bool=True)  # Flag bit to denote relationship
        else:
            stream += Bits(bool=False)
            encode_tile(stream, tiles[i + 1].idx, queue)

    return stream


def encode_tile(stream: BitStream, tile_index: int, queue: list[int]):
    """Encode a single tile index into the stream.

    Args:
        stream: BitStream to write into.
        tile_index: Tile index to encode.
        queue: Tile queue for caching.
    """
    if tile_index in queue:
        idx = queue.index(tile_index)
        stream.append(Bits(bool=True))  # Flag bit
        stream.append(Bits(uint=idx, length=4))
        queue.insert(0, queue.pop(idx))
        return

    # Not in queue, encode full index
    stream.append(Bits(bool=False))
    stream.append(Bits(uint=tile_index, length=11))
    queue.insert(0, tile_index)
    queue.pop()

def start_decompress(args: Namespace):

    if args.output is None:
        args.output = f'{Path(args.infile[0]).stem}.csv'
    
    with open(args.infile[0], 'rb') as f:
        data = f.read()
    
    if args.start is not None:
        data = data[args.start:]
        if args.length is not None:
            data = data[:args.length]

    
    stream = BitStream(data)
    blocks = decompress(stream)
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
