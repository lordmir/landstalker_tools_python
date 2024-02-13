from pathlib import Path
from dataclasses import dataclass
from enum import IntEnum
import sys

from scripts.common.codecs.lz77 import LZ77_encode, LZ77_decode

@dataclass
class SubSprite:
    x: int
    y: int
    width: int
    height: int


class TileCmds(IntEnum):
    BLANK_RUN_BIT = 8,
    STOP_BIT = 4,
    COMPRESSED_BIT = 2


class SpriteFrame:
    def __init__(self, **kwargs):
        self.subsprites = kwargs.get("subsprites", [])
        self.tile_data = kwargs.get("tiles", bytearray())
        self.tile_width = 8
        self.tile_height = 8
        self.is_compressed = kwargs.get("compressed", False)
        if "data" in kwargs:
            self.decode(kwargs["data"])
        pass

    def decode(self, data: bytes) -> int:
        """Decodes sprite frame data into subsprites and tile data.

        Args:
            data: Input byte data containing sprite frame information

        Returns:
            int: Number of bytes consumed from the input data

        Raises:
            ValueError: If the input data is invalid
        """
        # Validate input data
        if len(data) < 4:
            raise ValueError("Data too short")
        
        idx = self._decode_subsprites(data)
        idx = self._decode_tile_data(data, idx)

        # Return number of bytes parsed               
        return idx

    def encode(self) -> bytearray:
        encoded = self._encode_subsprites()
        encoded.extend(self._encode_tile_data())
        return bytes(encoded)
    
    def _encode_subsprites(self) -> bytearray:
        """Encodes subsprite definitions into byte data.

        Converts SubSprite objects in self.subsprites into their encoded
        byte representation.

        Returns: 
            bytearray: Encoded subsprite data
        """
        COORDINATE_MASK = 0x7C
        COORDINATE_SHIFT = 1
        DIMENSION_MASK = 0x03
        SUBSPRITE_END_BIT = 0x80

        encoded_data = bytearray()
        print(self.subsprites)
        for subsprite in self.subsprites:
            # Add 0x100 to coordinates if negative
            x = subsprite.x + 0x100 if subsprite.x < 0 else subsprite.x
            y = subsprite.y + 0x100 if subsprite.y < 0 else subsprite.y

            # Encode x and y coordinates
            encoded_data.append(((y >> COORDINATE_SHIFT) & COORDINATE_MASK) | ((subsprite.width - 1) & DIMENSION_MASK))
            encoded_data.append(((x >> COORDINATE_SHIFT) & COORDINATE_MASK) | ((subsprite.height - 1) & DIMENSION_MASK))

        # Mark the end of subsprites with a special byte
        encoded_data[-1] |= SUBSPRITE_END_BIT

        return encoded_data
    
    def _encode_tile_data(self) -> bytes:
        """Encodes tile data for the sprite frame.

        Compresses tile data if self.is_compressed is True, otherwise encodes
        it with blank run detection.

        Returns:
            bytes: Encoded tile data
        """
        tile_data = self.tile_data
        output = bytearray()
        BLANK_THRESHOLD = 5
        last_cmd = 0

        def encode_word(word: int):
            print(f"{word:04X}")
            output.extend(word.to_bytes(2, 'big'))

        def encode_compressed(data: bytes):
            compressed = LZ77_encode(data)
            ctrl = TileCmds.COMPRESSED_BIT
            size = len(data) // 2
            encode_word((ctrl << 12) | size)
            output.extend(compressed)
            return len(data)

        i = 0
        blank_count = 0
        while i < len(tile_data):
            if self.is_compressed:
                # Compress every byte
                last_cmd = len(output)
                encode_compressed(tile_data)
                i += encode_compressed(tile_data)
            else:
                # Check for runs:
                blank_count = 0
                run_length = 0
                for j in range(i, len(tile_data), 2):
                    word = int.from_bytes(tile_data[j:j+2], "big")
                    run_length += 1
                    if word == 0:
                        blank_count += 1
                        if run_length > blank_count and blank_count >= BLANK_THRESHOLD:
                            run_length -= blank_count
                            blank_count = 0
                            break
                    else:
                        if blank_count >= BLANK_THRESHOLD:
                            if run_length == blank_count + 1:
                                run_length = 0
                            break
                        blank_count = 0
                if blank_count >= BLANK_THRESHOLD:
                    # Encode blank run
                    control_word = TileCmds.BLANK_RUN_BIT
                    last_cmd = len(output)
                    encode_word((control_word << 12) | blank_count)

                    i += blank_count * 2
                else:
                    # Encode words directly
                    last_cmd = len(output)
                    encode_word(run_length)
                    for j in range(i, i + run_length*2, 2):
                        output.append(tile_data[j])
                        output.append(tile_data[j + 1])
                    i += run_length * 2

        # Set the stop bit
        output[last_cmd] |= TileCmds.STOP_BIT << 4

        return bytes(output)

    def _decode_subsprites(self, data: bytes) -> int:
        """Decodes subsprite definitions from sprite frame data.

        Extracts subsprite x, y, width and height values from input data.
        Adds SubSprite objects to self.subsprites and returns number of 
        bytes parsed.

        Args:
            data: Input data to parse

        Returns: 
            int: Number of bytes read for subsprites

        """
        COORDINATE_MASK = 0x7C
        COORDINATE_SHIFT = 1
        DIMENSION_MASK = 0x03
        SUBSPRITE_END_BIT = 0x80

        # Parse subsprite info
        idx = 0
        self.subsprites = []
        while True:
            y = (data[idx] & COORDINATE_MASK) << COORDINATE_SHIFT
            y = y - 0x100 if y > 0x80 else y

            x = (data[idx+1] & COORDINATE_MASK) << COORDINATE_SHIFT
            x = x - 0x100 if x > 0x80 else x

            w = (data[idx] & DIMENSION_MASK) + 1
            h = (data[idx+1] & DIMENSION_MASK) + 1

            self.subsprites.append(SubSprite(x, y, w, h))
            idx += 2
            if data[idx - 1] & SUBSPRITE_END_BIT > 0:
                break
        
        print(self.subsprites)
        return idx

    def _decode_tile_data(self, data: bytes, idx: int) -> int:
        """Decodes tile data for the sprite frame.

        Parses input data from given index onwards and extracts tileset 
        for the sprite frame, handling compressed/uncompressed formats.

        Args:
            data: Input byte array containing sprite data
            idx: Index in `data` to start decoding from

        Returns:
            int: Number of bytes parsed for tile data
        
        """
        self.tile_data = bytearray()
        self.is_compressed = False
        while True:
            word = (data[idx] << 8) | data[idx+1]
            ctrl = word >> 12
            count = word & 0xFFF
            idx += 2
            if ctrl & TileCmds.COMPRESSED_BIT:  # Compressed
                decompressed, dlen = LZ77_decode(data[idx:idx+count*2])
                self.is_compressed = True
                self.tile_data.extend(decompressed)
                idx += dlen
            elif ctrl & TileCmds.BLANK_RUN_BIT:  # Blank word
                self.tile_data.extend([0]*count*2)
            else:  # Copy word 
                self.tile_data.extend(data[idx:idx+count*2])
                idx += count*2
            if ctrl & TileCmds.STOP_BIT:
                break
            
        for i in range(0, len(self.tile_data), 4):
            print("".join([f"{x:02X}" for x in self.tile_data[i:i+4]]))
        print(len(self.tile_data) / 32)

        return idx
