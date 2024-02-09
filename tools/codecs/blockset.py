from bitstring import BitStream, Bits

from tools.models.tile import Tile, Attr


def decompress(data: bytes) -> list[list[Tile]]:
    """Decompress tile data from .cbs stream into list of blocks
    
    Args:
        stream: Bitstream containing compressed tile data
        
    Returns: 
        List of block lists, each containing 4 Tiles 
    """
    stream = BitStream(data)

    total_blocks = stream.read('uint:16')

    tiles = []
    for _ in range(total_blocks * 4):
        tiles.append(Tile()) 

    _mask_tiles(tiles, Attr.PRIORITY, stream)
    _mask_tiles(tiles, Attr.VFLIP, stream) 
    _mask_tiles(tiles, Attr.HFLIP, stream)

    queue = [0] * 16
    for i in range(0, len(tiles), 2):
        t1 = _decode_tile(stream, queue)
        tiles[i].idx = t1

        if stream.read('bin:1') == '1':
            if tiles[i].hflip:
                tiles[i+1].idx = t1 - 1
            else: 
                tiles[i+1].idx = t1 + 1
        else:
            tiles[i+1].idx = _decode_tile(stream, queue)

    # reconstruct blocks
    blocks = []
    for i in range(0, len(tiles), 4):
        blocks.append(tiles[i:i+4])

    return blocks 


def compress(tiles: list[list[Tile]]) -> bytes:
    """Compress tile data using the provided encoding scheme.

    Args:
        tiles: List of block lists, each containing 4 Tiles.

    Returns:
        BitStream: Compressed tile data.
    """

    stream = BitStream()

    stream += Bits(uint=len(tiles)//4, length=16)  # Write the number of tiles

    _encode_mask(stream, tiles, Attr.PRIORITY)
    _encode_mask(stream, tiles, Attr.VFLIP)
    _encode_mask(stream, tiles, Attr.HFLIP)

    queue = [0] * 16
    for i in range(0, len(tiles), 2):
        # Encode first tile
        _encode_tile(stream, tiles[i].idx, queue)

        # Encode second tile relationship
        if (tiles[i + 1].idx == tiles[i].idx + (-1 if tiles[i].hflip else 1)):
            stream += Bits(bool=True)  # Flag bit to denote relationship
        else:
            stream += Bits(bool=False)
            _encode_tile(stream, tiles[i + 1].idx, queue)

    return stream


def _mask_tiles(tiles: list[Tile], attr: Attr, stream: BitStream) -> None:
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


def _decode_tile(stream: BitStream, queue: list[int]) -> int:
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


def _encode_mask(stream: BitStream, tiles: list[Tile], attr: Attr) -> None:
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


def _encode_tile(stream: BitStream, tile_index: int, queue: list[int]):
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
