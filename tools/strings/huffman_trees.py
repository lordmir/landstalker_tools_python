from bitstring import BitStream

from tools.strings.huffman_tree import HuffmanTree

class HuffmanTrees:
    def __init__(self):
        self.trees = {}  # Map characters (bytes) to Huffman trees
        self.num_chars = 0

    def recalculate_trees(self, strings: list[bytes], eos_marker: int):
        """Recalculates Huffman trees based on character frequencies in the strings."""
        self.trees = {}
        frequencies = self._calculate_frequencies(strings, eos_marker)

        for char, freq in frequencies.items():
            self.trees[char] = HuffmanTree(freq)

        self.num_chars = len(frequencies)

    def _calculate_frequencies(self, strings: list[bytes], eos_marker: int) -> dict[bytes, int]:
        """Calculates character frequencies across all provided strings."""
        frequencies = {}
        for s in strings:
            prev = eos_marker
            
            for char in s:
                if prev not in frequencies:
                    frequencies[prev] = {}
                frequencies[prev][char] = frequencies[prev].get(char, 0) + 1
                prev = char
        return frequencies

    def encode_trees(self) -> tuple[bytes, bytes]:
        """Encodes all Huffman trees into serialized byte arrays."""
        char_offsets = bytearray()
        encoded_trees = bytearray()

        for i in range(max(self.trees) + 1):
            if i in self.trees:
                chrs, bits = self.trees[i].encode_tree()
                encoded_trees.extend(chrs)
                offset = len(encoded_trees)
                char_offsets.extend((offset).to_bytes(2, 'big'))
                encoded_trees.extend(bits)
            else:
                char_offsets.extend((0xFFFF).to_bytes(2, 'big'))

        return char_offsets, encoded_trees

    def decode_trees(self, char_offsets: bytes, encoded_trees: bytes):
        """Decodes Huffman trees from serialized byte arrays."""
        self.trees: dict[int, HuffmanTree] = {}
        self.num_chars = len(char_offsets) // 2

        for i in range(self.num_chars):
            offset = (char_offsets[i * 2] << 8) + char_offsets[i * 2 + 1]
            if offset != 0xFFFF:
                tree = HuffmanTree()
                tree.decode_tree(encoded_trees, offset)
                self.trees[i] = tree  # Store trees indexed by bytes

    def compress_string(self, text: bytes, eos_marker: bytes) -> bytes:
        """Compresses a string using the set of Huffman trees."""
        compressed = BitStream()
        last_char = eos_marker

        for char in text:
            if last_char not in self.trees:
                raise ValueError(f'Huffman tree not found for character: {last_char}')
            self.trees[last_char].encode_char(char, compressed)
            last_char = char

        if last_char != eos_marker:
            raise ValueError('String terminator not the last character')

        return bytes(compressed)

    def decompress_string(self, compressed: bytes, eos_marker: int) -> bytes:
        """Decompresses a string using the set of Huffman trees."""
        decompressed = bytearray()
        bits = BitStream(compressed)
        last_char = eos_marker

        while True:
            if last_char not in self.trees:
                raise ValueError(f'Huffman tree not found for character: {last_char}')
            next_char = self.trees[last_char].decode_char(bits)
            decompressed.append(next_char)
            if next_char == eos_marker:
                break
            last_char = next_char

        return bytes(decompressed)
