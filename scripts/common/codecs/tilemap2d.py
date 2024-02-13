import struct
from enum import IntEnum
from types import SimpleNamespace

from scripts.common.models.tile import Tile


class Mode(IntEnum):
    """Modes for tile encoding."""

    COPY_TILE = (0x00,)
    RLE_TILE_RUN = (0x40,)
    RLE_LAST_RUN = (0x80,)
    RLE_INCREMENT_RUN = (0xC0,)
    MASK = 0xC0


class Tilemap2D:

    def __init__(self, tiles: list[list[Tile]] | None = None) -> None:
        """Class constructor."""
        self._reset()
        if tiles:
            self.height = len(tiles)
            self.width = len(tiles[0]) if self.height > 0 else 0
            self.tiles = [x for row in tiles for x in row]
    
    def get_tiles(self) -> list[list[Tile]]:
        tiles = []
        for y in range(self.height):
            tiles.append([self.tiles[x + y * self.width] for x in range(self.width)])
        return tiles

    def decompress(self, data: bytes) -> int:
        """Decompresses tilemap data.

        Args:
            data (bytes): The packed tilemap data.
        
        Returns:
            int: The index after decompression.
        """
        self._reset()
        idx = self._read_header(data)
        idx = self._decode_tile_attributes(data, idx)
        idx = self._decode_tile_indices(data, idx)
        return idx

    def compress(self) -> bytes:
        """Compresses the tilemap data.
        
        Returns:
            bytes: The compressed tilemap data.
        """
        data = bytearray()

        data = self._write_header(data)
        data = self._encode_tile_attributes(data)
        data = self._encode_tile_indices(data)

        return bytes(data)

    def _reset(self) -> None:
        """Resets tilemap properties for a new decode/encode.
        
        Returns:
            None
        """
        self.width = 0
        self.height = 0
        self.tiles = []

    def _read_header(self, data: bytes) -> int:
        """Reads the header from the data.

        Args:
            data (bytes): The packed tilemap data.
        
        Returns:
            int: The index after reading the header.
        """
        self.width, self.height = struct.unpack(">BB", data[0:2])
        self.tiles = [Tile() for _ in range(self.width * self.height)]
        return 2

    def _decode_tile_attributes(self, data: bytes, idx: int) -> int:
        """Decodes the tile attributes section.

        Args:
            data (bytes): The packed tilemap data.
            idx (int): The start index.
        
        Returns:
            int: The updated index after decoding.
        """
        i = 0
        while True:
            attrs = (data[idx] & 0xF8) << 8
            length = data[idx] & 0x03
            idx += 1
            if data[idx - 1] & 0x04 == 0:
                length <<= 8
                length |= data[idx]
                idx += 1
                if length == 0:
                    return idx
            for _ in range(length + 1):
                self.tiles[i].set_val(attrs)
                i += 1

    def _handle_decode_copy_tile(self, ds: SimpleNamespace) -> SimpleNamespace:
        """Handles decoding a copy tile run.

        Args:
            ds (SimpleNamespace): The decode state object containing the following attributes:
                data (bytes): The packed tilemap data.
                data_idx (int): The start index.
                tile_idx (int): The current tile index.
                done (bool): Flag indicating if decoding is complete.

        Returns:
            SimpleNamespace: The updated decode state object.
        """
        val = struct.unpack(">H", ds.data[ds.data_idx : ds.data_idx + 2])[0] & 0x7FF
        ds.data_idx += 2
        if val == 0x7FF:
            ds.done = True
        else:
            self.tiles[ds.tile_idx].idx = val
            ds.tile_idx += 1
        return ds

    def _handle_decode_rle_tile_run(self, ds: SimpleNamespace) -> SimpleNamespace:
        """Handles decoding a RLE tile run.

        Args:
            ds (SimpleNamespace): The decode state object containing the following attributes:
                data (bytes): The packed tilemap data.
                data_idx (int): The start index.
                tile_idx (int): The current tile index.
                last (int): The last tile index.
                incr (int): The current increment value.

        Returns:
            SimpleNamespace: The updated decode state object.
        """
        count = (ds.data[ds.data_idx] >> 3) & 7
        val = struct.unpack(">H", ds.data[ds.data_idx : ds.data_idx + 2])[0] & 0x7FF
        ds.data_idx += 2
        for _ in range(count + 1):
            self.tiles[ds.tile_idx].idx = val
            ds.tile_idx += 1
        ds.last = val
        if ds.incr is None:
            ds.incr = val
        return ds

    def _handle_decode_rle_last_run(self, ds: SimpleNamespace) -> SimpleNamespace:
        """Handles decoding a RLE last run.

        Args:
            ds (SimpleNamespace): The decode state object containing the following attributes:
                data (bytes): The packed tilemap data.
                data_idx (int): The start index.
                tile_idx (int): The current tile index.
                last (int): The last tile index.

        Returns:
            SimpleNamespace: The updated decode state object.
        """
        count = ds.data[ds.data_idx] & 0x3F
        ds.data_idx += 1
        for _ in range(count + 1):
            self.tiles[ds.tile_idx].idx = ds.last
            ds.tile_idx += 1
        return ds

    def _handle_decode_incr_run(self, ds: SimpleNamespace) -> SimpleNamespace:
        """Handles decoding an increment run.

        Args:
            ds (SimpleNamespace): The decode state object containing the following attributes:
                data (bytes): The packed tilemap data.
                data_idx (int): The start index.
                tile_idx (int): The current tile index.
                incr (int): The current increment value.

        Returns:
            SimpleNamespace: The updated decode state object.
        """
        count = ds.data[ds.data_idx] & 0x3F
        ds.data_idx += 1
        for _ in range(count + 1):
            ds.incr += 1
            self.tiles[ds.tile_idx].idx = ds.incr
            ds.tile_idx += 1
        return ds

    def _decode_tile_indices(self, data: bytes, data_idx: int) -> int:
        """Decodes the tile indices section.

        Args:
            data (bytes): The packed tilemap data.
            data_idx (int): The start index.
        
        Returns:
            int: The updated index after decoding.
        """

        DECODE_HANDLERS = {
            Mode.COPY_TILE: self._handle_decode_copy_tile,
            Mode.RLE_TILE_RUN: self._handle_decode_rle_tile_run,
            Mode.RLE_LAST_RUN: self._handle_decode_rle_last_run,
            Mode.RLE_INCREMENT_RUN: self._handle_decode_incr_run,
        }

        decode_state = SimpleNamespace(
            data=data, data_idx=data_idx, tile_idx=0, last=None, incr=None, done=False
        )

        while not decode_state.done:
            mode = Mode(data[decode_state.data_idx] & Mode.MASK)
            decode_state = DECODE_HANDLERS[mode](decode_state)
        return data_idx

    def _write_header(self, data: bytearray) -> bytearray:
        """Writes the tilemap header.

        Args:
            data (bytearray): The output data buffer.
        
        Returns:
            bytearray: The updated output data buffer.
        """
        data.extend(struct.pack(">BB", self.width, self.height))
        return data

    def _encode_tile_attributes(self, data: bytearray) -> bytearray:
        """Encodes the tile attributes.

        Args:
            data (bytearray): The output data buffer.
        
        Returns:
            bytearray: The updated output data buffer.
        """
        idx = 0
        while idx < len(self.tiles):
            count = 0
            prev_attrs = (self.tiles[idx].get_val() & 0xF800) >> 8

            while idx + count + 1 < len(self.tiles) and (count < 0x400):
                cur_attrs = (self.tiles[idx + count + 1].get_val() & 0xF800) >> 8
                if prev_attrs != cur_attrs:
                    break
                count += 1
            idx += count + 1

            if count > 4:
                data.extend(struct.pack(">BB", prev_attrs | (count >> 8), count & 0xFF))
            else:
                data.extend(struct.pack(">B", prev_attrs | 4 | (count & 0x03)))
        data.extend(b"\x00\x00")
        return data

    def _handle_encode_rle_last_run(self, es: SimpleNamespace) -> SimpleNamespace:
        """Handles encoding a RLE last run.

        Args:
            es (SimpleNamespace): The encode state object containing the following attributes:
                data (list): The output data buffer.
                mode (int): The current mode.
                tile_idx (int): The current tile index.
                last (int): The last tile index.

        Returns:
            SimpleNamespace: The updated encode state object.
        """
        count = 0
        j = es.tile_idx + 1
        while (
            (count <= 0x3F) and (j < len(self.tiles)) and (self.tiles[j].idx == es.last)
        ):
            count += 1
            j += 1
        es.data.append(es.mode | count)
        es.tile_idx += count + 1
        return es

    def _handle_encode_incr_run(self, es: SimpleNamespace) -> SimpleNamespace:
        """Handles encoding an increment run.

        Args:
            es (SimpleNamespace): The encode state object containing the following attributes:
                data (list): The output data buffer.
                mode (int): The current mode.
                tile_idx (int): The current tile index.
                incr (int): The current increment value.

        Returns:
            SimpleNamespace: The updated encode state object.
        """
        j = es.tile_idx + 1
        es.incr += 1
        count = 0
        while (count <= 0x3F) and (j < len(self.tiles)):
            cur_tile = self.tiles[j].idx
            if cur_tile != es.incr + 1:
                break
            es.incr += 1
            count += 1
            j += 1
        es.data.append(es.mode | count)
        es.tile_idx += count + 1
        return es

    def _handle_encode_rle_tile_run(self, es: SimpleNamespace) -> SimpleNamespace:
        """Handles encoding a RLE tile run.

        Args:
            es (SimpleNamespace): The encode state object containing the following attributes:
                data (list): The output data buffer.
                mode (int): The current mode.
                tile_idx (int): The current tile index.
                last (int): The last tile index.

        Returns:
            SimpleNamespace: The updated encode state object.
        """
        start_tile = self.tiles[es.tile_idx].idx
        count = 0
        j = es.tile_idx + 1
        while (
            (count < 7) and (j < len(self.tiles)) and (start_tile == self.tiles[j].idx)
        ):
            count += 1
            j += 1
        es.data.append(es.mode | ((count & 0x07) << 3) | ((start_tile >> 8) & 7))
        es.data.append(start_tile & 0xFF)
        es.last = start_tile
        es.tile_idx += count + 1
        return es

    def _handle_encode_copy_tile(self, es: SimpleNamespace) -> SimpleNamespace:
        """Handles encoding a copy tile run.

        Args:
            es (SimpleNamespace): The encode state object containing the following attributes:
                data (list): The output data buffer.
                mode (int): The current mode.
                tile_idx (int): The current tile index.

        Returns:
            SimpleNamespace: The updated encode state object.
        """
        start_tile = self.tiles[es.tile_idx].idx
        es.data.extend(struct.pack(">H", (es.mode << 8) | start_tile))
        es.tile_idx += 1
        return es

    def _encode_tile_indices(self, data: bytearray) -> bytearray:
        """Encodes the tile indices.

        Args:
            data (bytearray): The output data buffer.
        
        Returns:
            bytearray: The updated output data buffer.
        """
        ENCODE_HANDLERS = {
            Mode.COPY_TILE: self._handle_encode_copy_tile,
            Mode.RLE_TILE_RUN: self._handle_encode_rle_tile_run,
            Mode.RLE_LAST_RUN: self._handle_encode_rle_last_run,
            Mode.RLE_INCREMENT_RUN: self._handle_encode_incr_run,
        }

        # Encode tile indices

        encode_state = SimpleNamespace(
            data=data,
            mode=Mode.RLE_TILE_RUN,
            tile_idx=0,
            last=self.tiles[0].idx,
            incr=self.tiles[0].idx,
        )

        # Write out a single RLE run, so that we can set up the registers

        encode_state = ENCODE_HANDLERS[encode_state.mode](encode_state)
        while encode_state.tile_idx < len(self.tiles):

            start_tile = self.tiles[encode_state.tile_idx].idx

            if start_tile == encode_state.last:
                encode_state.mode = Mode.RLE_LAST_RUN
            elif start_tile == encode_state.incr + 1:
                encode_state.mode = Mode.RLE_INCREMENT_RUN
            elif (
                encode_state.tile_idx + 1 < len(self.tiles)
                and start_tile == self.tiles[encode_state.tile_idx + 1].idx
            ):
                encode_state.mode = Mode.RLE_TILE_RUN
            else:
                encode_state.mode = Mode.COPY_TILE
            encode_state = ENCODE_HANDLERS[encode_state.mode](encode_state)
        
        encode_state.data.extend(b"\x07\xff")  # Add end marker
        return bytes(encode_state.data)
