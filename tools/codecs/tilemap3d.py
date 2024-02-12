"""Compresses and Decompresses Isometric Tilemap Data."""

from bitstring import BitStream, Bits
from types import SimpleNamespace
from enum import IntEnum
from collections import defaultdict

class TileCommand(IntEnum):
    """
    Enum representing the different tile commands.

    Attributes:
        DECODE_LONG_TILE: Command to decode a long tile.
        DECODE_SHORT_TILE: Command to decode a short tile.
        INCREMENT_LONG_TILE: Command to increment the long tile counter.
        INCREMENT_SHORT_TILE: Command to increment the short tile counter.
    """
    DECODE_LONG_TILE = 0,
    DECODE_SHORT_TILE = 1,
    INCREMENT_LONG_TILE = 2
    INCREMENT_SHORT_TILE = 3,

class Tilemap3D:
    """
    Tilemap3D class for decoding and manipulating a 3D tilemap.

    Attributes:
        foreground: List of foreground tile values.
        background: List of background tile values.
        heightmap: List of heightmap values.
        width: Width of the tilemap.
        height: Height of the tilemap.
        left: Left offset of the tilemap.
        hm_width: Width of the heightmap.
        hm_height: Height of the heightmap.
    """
    def __init__(self, data: bytes | None = None) -> None:
        """Class Constructor"""
        if data:
            self.decode(data)
        else:
            self._reset()

    def decode(self, src: bytes) -> int:
        """
        Decodes the tilemap from the given source bytes.

        Args:
            src (bytes): Source bytes to decode.

        Returns:
            int: The byte position in the input stream after decoding.
        """
        bitstream = BitStream(src)
        self._reset()
        self._decode_header(bitstream)
        self._decode_maps(bitstream)
        self._decode_heightmap(bitstream)

        return bitstream.bytepos

    def encode(self) -> bytes:
        """Encodes the tilemap to a compressed binary format.

        Returns:
            bytes: The compressed binary tilemap data.
        """
        tiles = self._make_tile_list()
        offsets = self._make_offset_dictionary(tiles)
        lz77_entries, compressed = self._lz77_compress(tiles, offsets)
        lz77_entries = self._identify_vertical_runs(tiles, lz77_entries)
        tile_dictionary = self._make_tile_dictionary(tiles, compressed)
        tile_entries = self._encode_tiles(tiles, compressed, tile_dictionary)
        heightmap = self._encode_heightmap()

        return self._serialise(lz77_entries, tile_entries, tile_dictionary, offsets, heightmap)

    def _make_tile_list(self) -> list[int]:
        """Creates a single list of all foreground and background tiles.

        Returns:
            List[int]: The list of all tiles.
        """
        return [t for t in self.foreground] + [t for t in self.background]

    def _make_offset_dictionary(self, tiles: list[int]) -> list[int]:
        """Analyzes tile patterns and generates an LZ77 offset dictionary.

        Args:
            tiles (List[int]): The list of tiles.

        Returns:
            List[int]: The generated offset dictionary.
        """
        offsets = [0, 1, 2, self.width, self.width * 2, self.width + 1]

        # First stage of map compression involves LZ77 with a fixed-size dictionary
        # Step 1: Make a list of LZ77 offset frequencies.
        offset_freq_count = {}
        idx = 1
        while idx < len(tiles):
            run = self._find_match_frequency(tiles, idx, offset_freq_count)
            if not run:
                idx += 1
            else:
                idx += run

        # STEP 2: Identify top 8 back offsets and add to back offset dictionary
        freqency_counts = sorted(offset_freq_count.items(), key=lambda x: (-x[1], x[0]))
        for offset, _ in freqency_counts:
            if offset not in offsets:
                offsets.append(offset)
                if len(offsets) >= 14:
                    break
        
        if len(offsets) < 14:
            offsets.extend([0] * (14 - len(offsets)))
        
        return offsets
    
    def _lz77_compress(self, tiles: list[int], offsets: list[int]) -> tuple[list[dict[str, int]], list[bool]]:
        """Applies LZ77 compression to the tiles.

        Args:
            tiles (List[int]): The tile values.
            offsets (List[int]): The offset dictionary.

        Returns:
            Tuple[List[Dict[str, int]], List[bool]]: 
                The LZ77 entries and a list indicating which tiles are compressed.
        """
        lz77_entries = [{"run_length": 1, "back_offset_idx": 0, "index": 0}]
        compressed = [False] * len(tiles)
        idx = 1

        while idx < len(tiles):
            back_offset_idx, run_length = self._find_match(tiles, idx, offsets)
            if back_offset_idx != 0 or lz77_entries[-1]["back_offset_idx"] != 0:
                lz77_entries.append({"run_length": run_length, "back_offset_idx": back_offset_idx, "index": idx})
            else:
                lz77_entries[-1]["run_length"] += 1

            if lz77_entries[-1]["back_offset_idx"] == 0:
                compressed[idx] = False
                idx += 1
            else:
                compressed[idx:idx+lz77_entries[-1]['run_length']] = [True] * lz77_entries[-1]["run_length"]
                idx += lz77_entries[-1]["run_length"]
        
        return lz77_entries, compressed

    def _identify_vertical_runs(self, tiles: list[int], lz77_entries: list[dict[str, int]]) -> list[dict[str, int]]:
        """Identifies vertical runs in the LZ77 compressed tiles.

        Args: 
            tiles (List[int]): The tile values.
            lz77_entries (List[Dict[str, int]]): The LZ77 entries.

        Returns:
            List[Dict[str, int]]: The LZ77 entries with vertical runs marked.
        """
        for i, entry in enumerate(lz77_entries):
            if entry["back_offset_idx"] != -1:
                self._encode_vertical_run(i, tiles, lz77_entries)

        # Remove entries with back_offset_idx == -1
        lz77_entries = [entry for entry in lz77_entries if entry["back_offset_idx"] != -1]
        
        return lz77_entries
    
    def _encode_vertical_run(self, index: int, tiles: list[int], lz77_entries: list[dict]) -> None:
        """Encodes a vertical run for an LZ77 entry.

        Args:
            index (int): Index of LZ77 entry.
            tiles (List[int]): Tile values.
            lz77_entries (List[dict]): LZ77 entries.
        """
        count = 0
        right_offset = 0
        begin = True
        entry = lz77_entries[index]
        next_idx = entry["index"]
        prev_idx = next_idx

        while next_idx < len(tiles):
            next_idx += self.width + right_offset
            next_entry = next((e for e in lz77_entries[index:]
                                if e["index"] == next_idx and 
                                    e["back_offset_idx"] == entry["back_offset_idx"]),
                                None)
            if next_entry:
                count += 1
                next_entry["back_offset_idx"] = -1  # Mark for deletion
                prev_idx = next_idx
            else:
                if count > 0:
                    if "vertical_info" not in entry:
                        entry["vertical_info"] = []
                    entry["vertical_info"].append((right_offset, count))
                    count = 0
                elif not begin:
                    break
                begin = False
                right_offset ^= 1
                next_idx = prev_idx
    
    def _make_tile_dictionary(self, tiles: list[int], compressed: list[bool]):
        """Analyzes uncompressed tiles and generates a tile dictionary.

        Args:
            tiles (List[int]): The tile values.
            compressed (List[bool]): Flags indicating compressed tiles.

        Returns:
            Dict[str, int]: The generated tile dictionary.
        """
        # Identify sequential runs of tiles, the longest run including decrements will be
        # stored as "long" in the tile dict.
        # The longest run where ilog2(base) == ilog2(highest tile #) will be stored as
        # "short" in the tile dict.
        incrementing_tile_counts, ranged_tile_counts = self._get_tile_counts(tiles, compressed)

        short_tile_key = self._calculate_short_tile_key(incrementing_tile_counts)
        long_tile_key = self._calculate_long_tile_key(incrementing_tile_counts, ranged_tile_counts)

        # print("TILE DICT 0:", hex(long_tile_key))
        # print("TILE DICT 1:", hex(short_tile_key))

        return {"long": long_tile_key, "short": short_tile_key}

    def _calculate_short_tile_key(self, incrementing_tile_counts: defaultdict[int]) -> int:
        """Determines optimal short tile dict key from counts.

        Args:
            incrementing_tile_counts (DefaultDict[int, int]): Tile increment counts.

        Returns:
            int: Short tile key.
        """
        def frequency_comparator(item):
            frequency = item[1]  # second element is frequency
            return -frequency  # descending order

        incrementing_tile_freqs = sorted(incrementing_tile_counts.items(), key=frequency_comparator)

        return incrementing_tile_freqs[0][0]
    
    def _calculate_long_tile_key(self, incrementing_tile_counts: defaultdict[int],
                                 ranged_tile_counts: defaultdict[int]) -> int:
        """Determines optimal long tile dict key from counts.

        Args:
            incrementing_tile_counts (DefaultDict[int, int]): Tile increment counts.
            ranged_tile_counts (DefaultDict[int, int]): Tile range counts.

        Returns:
            int: Long tile key.
        """
        max_tile = max(incrementing_tile_counts.keys())
        min_dict_entry = 1 << (max_tile.bit_length() - 1)

        long_tile_key = 0

        for base, count in incrementing_tile_counts.items():
            if long_tile_key == 0 and base >= min_dict_entry:
                long_tile_key = base
                incrementing_tile_counts[base] = 0
            else:
                incrementing_tile_counts[base] = count * 4 + ranged_tile_counts.get(base, 0)

        if long_tile_key == 0:
            long_tile_key = min_dict_entry
        
        return long_tile_key

    def _get_tile_counts(self, tiles: list[str], compressed: list[bool]) -> tuple[defaultdict[int], defaultdict[int]]:
        """Gets tile pattern counts from uncompressed tiles.

        Args:
            tiles (List[int]): The tile values.
            compressed (List[bool]): Flags for compressed tiles.

        Returns:
            Tuple[DefaultDict[int, int], DefaultDict[int, int]]: 
                Incrementing and range tile counts.
        """
        incrementing_tile_counts = defaultdict(int)
        ranged_tile_counts = defaultdict(int)

        for i, tile in enumerate(tiles):
            if not compressed[i]:
                for base, count in incrementing_tile_counts.items():
                    if tile == base + count:
                        incrementing_tile_counts[base] += 1
                    if base <= tile < base + count:
                        ranged_tile_counts[tile] += 1
                incrementing_tile_counts.setdefault(tile, 1)
        
        return incrementing_tile_counts, ranged_tile_counts
    
    @staticmethod
    def _handle_encode_increment_short_tile(tile: int, tile_dict: dict[str, int],
                                            tile_increment: dict[str, int]) -> dict[str, int]:
        # print("INCREMENT TILE 0 [", hex(tile), " @", i, "]")
        tile_increment["short"] += 1
        return {"mode": TileCommand.INCREMENT_SHORT_TILE, "val": 0, "len": 0}

    @staticmethod
    def _handle_encode_increment_long_tile(tile: int, tile_dict: dict[str, int],
                                           tile_increment: dict[str, int]) -> dict[str, int]:
        # print("INCREMENT TILE 1 [", hex(tile), " @", i, "]")
        tile_increment["long"] += 1
        return {"mode": TileCommand.INCREMENT_LONG_TILE, "val": 0, "len": 0}

    @staticmethod
    def _handle_encode_short_tile(tile: int, tile_dict: dict[str, int],
                                  tile_increment: dict[str, int]) -> dict[str, int]:
        # print("PLACE REL TILE [", hex(tile), " @", i, "]")
        return {"mode": TileCommand.DECODE_SHORT_TILE,
                "val": tile - tile_dict["short"],
                "len": tile_increment["short"].bit_length()}

    @staticmethod
    def _handle_encode_long_tile(tile: int, tile_dict: dict[str, int],
                                 tile_increment: dict[str, int]) -> dict[str, int]:
        # print("PLACE TILE", hex(tile), "@", i)
        return {"mode": TileCommand.DECODE_LONG_TILE,
                "val": tile,
                "len": tile_dict["long"].bit_length()}

    def _encode_tiles(self, tiles: list[str], compressed: list[bool], tile_dict: dict[str, int]) -> list[dict]:
        """Encodes tile entries using tile dictionary patterns.

        Args:
            tiles (List[int]): The tile values.
            compressed (List[bool]): Flags for compressed tiles. 
            tile_dict (Dict[str, int]): The tile dictionary.

        Returns:
            List[Dict[str, int]]: The encoded tile entries.
        """
        # Start to compress tile data. Identify if tile is:
        #   (1) equal to any in tile dictionary + increment,
        #   (2) between tileDict[0] and tileDict[0] + tileDictIncr[0]
        #   (3) none of the above.

        tile_entries = []
        tile_increment = {"short": 0, "long": 0}
        ENCODE_HANDLERS = {
            TileCommand.INCREMENT_SHORT_TILE: self._handle_encode_increment_short_tile,
            TileCommand.INCREMENT_LONG_TILE: self._handle_encode_increment_long_tile,
            TileCommand.DECODE_SHORT_TILE: self._handle_encode_short_tile,
            TileCommand.DECODE_LONG_TILE: self._handle_encode_long_tile
        }

        for i, tile in enumerate(tiles):
            if not compressed[i]:
                if tile == tile_dict["short"] + tile_increment["short"]:
                    mode = TileCommand.INCREMENT_SHORT_TILE
                elif tile == tile_dict["long"] + tile_increment["long"]:
                    mode = TileCommand.INCREMENT_LONG_TILE
                elif tile_dict["short"] <= tile < tile_dict["short"] + tile_increment["short"]:
                    mode = TileCommand.DECODE_SHORT_TILE
                else:
                    mode = TileCommand.DECODE_LONG_TILE
                tile_entries.append(ENCODE_HANDLERS[mode](tile, tile_dict, tile_increment))
        return tile_entries

    def _encode_heightmap(self) -> list[tuple[int, int]]:
        """Encodes heightmap using run-length encoding.

        Returns:
            List[Tuple[int, int]]: Run-length encoded heightmap patterns. 
        """
        hm_buffer = []
        for i, height in enumerate(self.heightmap):
            if not hm_buffer or hm_buffer[-1][1] != height:
                hm_buffer.append((0, height))
            else:
                hm_buffer[-1] = (hm_buffer[-1][0] + 1, height)
        
        return hm_buffer
    
    def _serialise(self, lz77_entries: list[dict], tile_entries: list[dict], tile_dictionary: dict[str, int],
                   offsets: list[int], heightmap: list[tuple[int, int]]) -> bytes:
        """Serializes the compressed data to a bitstream.

        Args:
            lz77_entries (List[Dict[str, int]]): LZ77 compressed tile entries.
            tile_entries (List[Dict[str, int]]): Encoded tile entries.
            tile_dictionary (Dict[str, int]): Tile dictionary.
            offsets (List[int]): LZ77 offset dictionary.
            heightmap (List[Tuple[int, int]]): RLE encoded heightmap.

        Returns:
            bytes: The serialized compressed binary data.
        """
        bits = BitStream()
        self._serialise_headers(bits, tile_dictionary, offsets)
        self._serialise_maps(bits, lz77_entries, tile_entries)
        self._serialise_heightmap(bits, heightmap)
        return bytes(bits)

    def _serialise_headers(self, bits: BitStream, tile_dict: dict[str, int], offsets: list[int]) -> None:
        """Serializes the header data including dictionaries.

        Args:
            bits (BitStream): The output bitstream.
            tile_dict (Dict[str, int]): The tile dictionary.
            offsets (List[int]): The LZ77 offset dictionary.
        """
        # Top, Left, Width, Height
        bits.append(Bits(uint=self.left, length=8))
        bits.append(Bits(uint=self.top, length=8))
        bits.append(Bits(uint=self.width - 1, length=8))
        bits.append(Bits(uint=self.height * 2 - 1, length=8))

        # Tile Dictionary
        bits.append(Bits(uint=tile_dict["short"], length=10))
        bits.append(Bits(uint=tile_dict["long"], length=10))

        # Offset Dictionary
        for i in range(6, 14):
            bits.append(Bits(uint=offsets[i], length=12))
    
    def _serialise_maps(self, bits: BitStream, lz77_entries: list[dict], tile_entries: list[dict]) -> None:
        """Serializes the tilemap encoding data to the bitstream.

        Args:
            bits (BitStream): The output bitstream.
            lz77_entries (List[dict]): The LZ77 entries.
            tile_entries (List[dict]): The encoded tile entries.
        """
        self._serialise_lz77_data(bits, lz77_entries)
        
        # Tile data: 2-bit operand + variable length data
        for entry in tile_entries:
            bits.append(Bits(uint=entry["mode"], length=2))
            if entry["mode"] in (0, 1):
                bits.append(Bits(uint=entry["val"], length=entry["len"]))
        
        # Byte align
        if bits.bitpos % 8 > 0:
            bits.append(Bits(uint=0, length=8-(bits.bitpos % 8)))
    
    def _serialise_lz77_data(self, bits: BitStream, lz77_entries: list[int]) -> None:
        """Serializes the LZ77 entries to the bitstream.

        Args:
            bits (BitStream): The output bitstream.
            lz77_entries (List[dict]): The LZ77 entries to serialize.
        """
        # LZ77 Data: run length, back offset index, vertical run data
        last_idx = -1
        for entry in lz77_entries:
            # Run length
            bits.append(Bits(ue=(entry["index"] - last_idx - 1)))
            last_idx = entry["index"]

            # Back index
            if entry["back_offset_idx"] < 6:
                bits.append(Bits(uint=entry["back_offset_idx"], length=3))
            else:
                bits.append(Bits(uint=3, length=2))
                bits.append(Bits(uint=entry["back_offset_idx"]-6, length=3))

            bits.append(Bits(bool=bool("vertical_info" in entry)))
            # Vertical run
            if "vertical_info" in entry:
                self._serialize_vertial_rle(bits, entry)

        buffer_size = self.width * self.height * 2
        if last_idx < buffer_size:
            bits.append(Bits(ue=(buffer_size - last_idx)))
        else:
            bits.append(Bits(ue=1))
    
    def _serialize_vertial_rle(self, bits: BitStream, entry: dict) -> None:
        """Serializes the vertical RLE data for an LZ77 entry.

        Args:
            bits (BitStream): The output bitstream.
            entry (dict): The LZ77 entry dictionary.
        """
        begin = True
        for right, count in entry["vertical_info"]:
            if begin:
                bits.append(Bits(bool=right))
                begin = False
            else:
                bits.append(Bits(bool=True))
            for _ in range(1, count):
                bits.append(Bits(bool=True))
            bits.append(Bits(bool=False))
        bits.append(Bits(bool=False))

    def _serialise_heightmap(self, bits: BitStream, hm_entries: list[tuple[int, int]]) -> None:
        """Serializes the RLE encoded heightmap to the bitstream.

        Args:
            bits (BitStream): The output bitstream.
            hm_entries (List[Tuple[int, int]]): RLE heightmap entries.
        """
        # Heightmap Dimensions
        bits.append(Bits(uint=self.hm_width, length=8))
        bits.append(Bits(uint=self.hm_height, length=8))
        
        # Heightmap data: pattern + run length. If run length >= 0xFF, output 0xFF then run length - 0xFF
        for count, pattern in hm_entries:
            bits.append(Bits(uint=pattern, length=16))
            remaining = count
            while remaining >= 0xFF:
                bits.append(Bits(uint=0xFF, length=8))
                remaining -= 0xFF
            bits.append(Bits(uint=remaining, length=8))

    @staticmethod
    def _find_match(input: list[int], offset: int, back_offsets: list[int]) -> tuple[int, int]:
        """Finds the longest match at given offset in LZ77 compression.

        Args:
            input (List[int]): The input tile values.
            offset (int): The current offset to check.
            back_offsets (List[int]): List of back offsets to check.

        Returns:
            Tuple[int, int]: Index of best match and its length.
        """
        lookback_size = min(offset, 4095)
        lookahead_size = len(input) - offset
        ret = (0, 0)  # (back_offset_idx, run_length)
        
        for i, b in enumerate(back_offsets):
            if b == 0 or b > lookback_size:
                continue
            
            match_run = 0
            for m in range(lookahead_size):
                if input[offset - b + m] != input[offset + m]:
                    break
                match_run += 1
                
            if match_run > ret[1]:
                ret = (i, match_run)
                
        if ret[1] == 0:
            ret = (0, 1)  # Minimum run length is 1
            
        return ret

    @staticmethod
    def _find_match_frequency(input: list[int], offset: int, fc: dict[int, int]) -> int:
        """
        Finds longest matching run at given offset and fills frequency count.

        Args:
            input: List of tile values
            offset: Offset to check
            fc: Dictionary to hold frequency counts

        Returns:
            Run length of longest match
        """

        lookback_size = min(offset, 4095)
        lookahead_size = len(input) - offset

        best = 0
        for b in range(1, lookback_size+1):
            match_run = 0
            for m in range(lookahead_size):
                if input[offset-b+m] != input[offset+m]:
                    break
                match_run += 1

            if match_run > best:
                best = match_run

        if best < 2:
            return 0

        for b in range(1, lookback_size+1):
            match_run = 0
            for m in range(lookahead_size):
                if input[offset-b+m] != input[offset+m]:
                    break
                match_run += 1

            if match_run == best:
                fc[b] = fc.get(b, 0) + 1
                
        return best

    def _decode_header(self, bitstream: BitStream) -> None:
        """
        Decodes the header of the tilemap.

        Args:
            bitstream (BitStream): The input bitstream.
        """
        self.left = bitstream.read("uint:8")
        self.top = bitstream.read("uint:8")
        self.width = bitstream.read("uint:8") + 1
        self.height = (bitstream.read("uint:8") + 1) // 2

    def _decode_maps(self, bitstream: BitStream) -> int:
        """
        Decodes the foreground and background maps.

        Args:
            bitstream (BitStream): The input bitstream.

        Returns:
            int: The byte position in the input stream after decoding.
        """
        offset_dictionary, tile_dictionary = self._decode_dictionaries(bitstream)
        buffer = self._decode_map_buffer_pass_one(bitstream, offset_dictionary)
        self._decode_maps_pass_two(bitstream, buffer, tile_dictionary)
        return bitstream.bytepos

    def _decode_heightmap(self, bitstream: BitStream) -> int:
        """
        Decodes the heightmap.

        Args:
            bitstream (BitStream): The input bitstream.

        Returns:
            int: The byte position in the input stream after decoding.
        """
        self.hm_width = bitstream.read("uint:8")
        self.hm_height = bitstream.read("uint:8")

        hm_pattern = 0
        hm_rle_count = 0
        hm_size = self.hm_width * self.hm_height

        self.heightmap = [0] * hm_size
        dst_addr = 0
        for _ in range(hm_size):
            if not hm_rle_count:
                read_count = 0
                hm_rle_count = 1
                hm_pattern = bitstream.read("uint:16")
                while True:
                    read_count = bitstream.read("uint:8")
                    hm_rle_count += read_count
                    if read_count != 0xFF:
                        break
            hm_rle_count -= 1
            self.heightmap[dst_addr] = hm_pattern
            dst_addr += 1
        bitstream.bytealign()
        return bitstream.pos // 8

    def _decode_dictionaries(self, bitstream: BitStream) -> tuple[list[int], list[int]]:
        """
        Decodes the offset and tile dictionaries.

        Args:
            bitstream (BitStream): The input bitstream.

        Returns:
            Tuple[List[int], List[int]]: A tuple containing the offset dictionary and the tile dictionary.
        """
        tile_dictionary = [0, 0]
        offset_dictionary = [0xFFFF, 1, 2, self.width, self.width * 2, self.width + 1,
                             0, 0, 0, 0, 0, 0, 0, 0]

        tile_dictionary[1] = bitstream.read("uint:10")
        tile_dictionary[0] = bitstream.read("uint:10")

        for i in range(6, 14):
            offset_dictionary[i] = bitstream.read("uint:12")
        return offset_dictionary, tile_dictionary

    def _decode_map_buffer_pass_one(self, bitstream: BitStream,
                                    offset_dictionary: list[int]) -> list[int]:
        """
        Performs the first pass of decoding the map buffer.

        Args:
            bitstream (BitStream): The input bitstream.
            offset_dictionary (List[int]): The offset dictionary.

        Returns:
            List[int]: The decoded map buffer.
        """
        size = self.width * self.height
        buffer_size = size * 2
        buffer = [0] * buffer_size

        dst_addr = -1
        while True:
            start = bitstream.read("ue") + 1
            dst_addr += start
            if dst_addr >= buffer_size:
                break
            next_offset_idx = bitstream.read("uint:3")
            if next_offset_idx > 5:
                next_offset_idx = 6 + (
                    ((next_offset_idx & 1) << 2) | bitstream.read("uint:2")
                )
            next_offset = offset_dictionary[next_offset_idx]
            buffer[dst_addr] = next_offset
            if bitstream.read("bool"):
                self._decode_vertical_rle(bitstream, buffer, dst_addr)
        return buffer

    def _decode_vertical_rle(self, bitstream: BitStream, buffer: list[int],
                             dst_addr: int) -> None:
        """
        Decodes the vertical run-length encoding.

        Args:
            bitstream (BitStream): The input bitstream.
            buffer (List[int]): The map buffer.
            dst_addr (int): The destination address.
        """
        row_addr = dst_addr
        width_offset = bitstream.read("uint:1")

        while True:
            while True:
                row_addr += self.width + width_offset
                buffer[row_addr] = buffer[dst_addr]
                if not bitstream.read("bool"):
                    break
            width_offset = width_offset ^ 1
            if not bitstream.read("bool"):
                break

    def _handle_decode_lz77_across(self, ds: SimpleNamespace) -> None:
        """
        Handles the LZ77 decoding across the map.

        Args:
            ds (SimpleNamespace): Contains:
                - ds.buffer (List[int]): The map buffer
                - ds.buffer_idx (int): The current buffer index  
        """
        offset = ds.buffer_idx - ds.buffer[ds.buffer_idx]

        while True:
            ds.buffer[ds.buffer_idx] = ds.buffer[offset]
            ds.buffer_idx += 1
            offset += 1
            if ds.buffer_idx >= len(ds.buffer) or ds.buffer[ds.buffer_idx] != 0:
                break

    @staticmethod 
    def _handle_decode_long_tile(ds: SimpleNamespace) -> int:
        """
        Handles the decoding of a long tile.

        Args: 
            ds (SimpleNamespace): Contains:
                - ds.bitstream (BitStream): The input bitstream
                - ds.tile_counters (List[int]): The tile counters
        """
        if ds.tile_counters[0]:
            bit_width = ds.tile_counters[0].bit_length()
            value = ds.bitstream.read(f"uint:{bit_width}")
        else:
            value = 0
        return value

    @staticmethod
    def _handle_decode_short_tile(ds: SimpleNamespace) -> int:
        """
        Handles the decoding of a short tile.

        Args:
            ds (SimpleNamespace): Contains:
                - ds.bitstream (BitStream): The input bitstream 
                - ds.tile_dictionary (List[int]): The tile dictionary
                - ds.tile_counters (List[int]): The tile counters
        """
        value = 0

        if ds.tile_counters[1] != ds.tile_dictionary[1]:
            tile_diff = ds.tile_counters[1] - ds.tile_dictionary[1]
            bit_width = tile_diff.bit_length()
            value = ds.bitstream.read(f"uint:{bit_width}")

        return value + ds.tile_dictionary[1]

    @staticmethod
    def _handle_increment_long_tile(ds: SimpleNamespace) -> int:
        """
        Handles the incrementing of the long tile counter.

        Args:
            ds (SimpleNamespace): Contains:
                - ds.tile_counters (List[int]): The tile counters

        Returns:
            int: The incremented long tile counter value.
        """
        value = ds.tile_counters[0]
        ds.tile_counters[0] += 1
        return value

    @staticmethod
    def _handle_increment_short_tile(ds: SimpleNamespace) -> int:
        """
        Handles the incrementing of the short tile counter.

        Args:
            ds (SimpleNamespace): Contains:
                - ds.tile_counters (List[int]): The tile counters

        Returns:
            int: The incremented short tile counter value.
        """
        value = ds.tile_counters[1]
        ds.tile_counters[1] += 1
        return value

    def _decode_maps_pass_two(self, bitstream: BitStream, buffer: list[int],
                              tile_dictionary: list[int]) -> None:
        """
        Performs the second pass of decoding the maps.

        Args:
            bitstream (BitStream): The input bitstream.
            buffer (List[int]): The map buffer.
            tile_dictionary (List[int]): The tile dictionary.
        """
        decode_state = SimpleNamespace(bitstream=bitstream, buffer=buffer, buffer_idx=0,
                                       tile_dictionary=tile_dictionary, tile_counters=[*tile_dictionary])

        DECODE_HANDLERS = {
            TileCommand.DECODE_LONG_TILE: self._handle_decode_long_tile,
            TileCommand.DECODE_SHORT_TILE: self._handle_decode_short_tile,
            TileCommand.INCREMENT_LONG_TILE: self._handle_increment_long_tile,
            TileCommand.INCREMENT_SHORT_TILE: self._handle_increment_short_tile
        }

        while decode_state.buffer_idx < len(buffer):
            if decode_state.buffer[decode_state.buffer_idx] != 0xFFFF:
                self._handle_decode_lz77_across(decode_state)
            else:
                while (decode_state.buffer_idx < len(decode_state.buffer)
                       and decode_state.buffer[decode_state.buffer_idx] in (0, 0xFFFF)):
                    command = TileCommand(bitstream.read("uint:2"))
                    value = DECODE_HANDLERS[command](decode_state)
                    buffer[decode_state.buffer_idx] = value
                    decode_state.buffer_idx += 1
        bitstream.bytealign()
        size = self.width * self.height
        self.background.extend([x for x in decode_state.buffer[size:]])
        self.foreground.extend([x for x in decode_state.buffer[:size]])

    def _reset(self) -> None:
        """
        Resets the state of the Tilemap3D object.
        """
        self.foreground = []
        self.background = []
        self.heightmap = []
        self.width = 0
        self.height = 0
        self.left = 0
        self.height = 0
        self.hm_width = 0
        self.hm_height = 0
