from bitstring import BitStream, Bits
import argparse
from pathlib import Path
from dataclasses import dataclass
from queue import PriorityQueue

DEFAULT_ENGLISH_CHARSET = {
    i: c for i, c in enumerate([
        " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K",
        "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V",
        "W", "X", "Y", "Z", "a", "b", "c", "d", "e", "f", "g",
        "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r",
        "s", "t", "u", "v", "w", "x", "y", "z", "*", ".", ",",
        "?", "!", "/", "<", ">", ":", "-", "'", "\"", "%", "#",
        "&", "(", ")", "=", "↖", "↗", "↘", "↙"
    ])
}

DEFAULT_FRENCH_CHARSET = {
    i: c for i, c in enumerate([
        " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K",
        "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V",
        "W", "X", "Y", "Z", "a", "b", "c", "d", "e", "f", "g",
        "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r",
        "s", "t", "u", "v", "w", "x", "y", "z", "*", ".", ",",
        "?", "!", "/", "<", ">", ":", "-", "'", "\"", "%", "#",
        "&", "(", ")", "=", "è", "á", "à", "ù", "â", "ê", "î",
        "ô", "û", "ç", "ü", ";", "`"
    ])
}

DEFAULT_GERMAN_CHARSET = {
    i: c for i, c in enumerate([
        " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K",
        "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V",
        "W", "X", "Y", "Z", "*", ".", ",", "?", "!", "/", "<",
        ">", ":", "-", "\'", "\"", "%", "#", "&", "(", ")", "=",
        "↖", "↗", "↘", "↙", "Ä", "Ö", "Ü", "ß"
    ])
}

DEFAULT_JAPANESE_CHARSET = {
    i: c for i, c in enumerate([
        "　", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "あ",
        "い", "う", "え", "お", "か", "き", "く", "け", "こ", "さ", "し",
        "す", "せ", "そ", "た", "ち", "つ", "て", "と", "な", "に",
        "ぬ", "ね", "の", "は", "ひ", "ふ", "へ", "ほ", "ま", "み", "む",
        "め", "も", "や", "ゆ", "よ", "ら", "り", "る", "れ", "ろ", "わ",
        "を", "ん", "ぁ", "ぃ", "ぅ", "ぇ", "ぉ", "ゃ", "ゅ", "ょ", "ゎ",
        "ア", "イ", "ウ", "エ", "オ", "カ", "キ", "ク", "ケ", "コ", "サ",
        "シ", "ス", "セ", "ソ", "タ", "チ", "ツ", "テ", "ト", "ナ", "ニ",
        "ヌ", "ネ", "ノ", "ハ", "ヒ", "フ", "ヘ", "ホ", "マ", "ミ", "ム",
        "メ", "モ", "ヤ", "ユ", "ヨ", "ラ", "リ", "ル", "レ", "ロ", "ワ",
        "ヲ", "ン", "ァ", "ィ", "ゥ", "ェ", "ォ", "ャ", "ュ", "ョ", "ッ",
        "、", "。", "゛", "゜", "ー", "！", "？", "※", "東", "西", "南",
        "北", "上", "中", "下", "道", "具", "屋", "教", "会", "宿", "神",
        "父", "冒", "険", "記", "録", "毒", "呪", "治", "療", "金", "貨",
        "枚", "買", "階", "本", "売", "泊", "客", "品", "男", "女", "子",
        "供", "人", "族", "殿", "公", "爵", "領", "主", "兵", "悪", "霊",
        "年", "月", "日", "財", "宝", "地", "図", "実", "灯", "台", "家",
        "店", "町", "村", "滝", "岬", "島", "海", "沼", "湖", "港", "城",
        "塔", "森", "橋", "団", "気", "船", "箱", "魔", "命", "危", "美",
        "長", "古", "老", "作", "名", "商", "大", "・", "「", "」", "↘",
        "↖", "↙", "↗", "王", "剣", "士", "国", "本", "法", "Ａ", "Ｂ",
        "Ｃ", "．", "╳"
    ])
}

JAPANESE_DIACRITIC_MAP = {
    "゛": {
        "か": "が", "き": "ぎ", "く": "ぐ", "け": "げ", "こ": "ご", "さ": "ざ", "し": "じ",
        "す": "ず", "せ": "ぜ", "そ": "ぞ", "た": "だ", "ち": "ぢ", "つ": "づ", "て": "で",
        "と": "ど", "は": "ば", "ひ": "び", "ふ": "ぶ", "へ": "べ", "ほ": "ぼ", "カ": "ガ",
        "キ": "ギ", "ク": "グ", "ケ": "ゲ", "コ": "ゴ", "サ": "ザ", "シ": "ジ", "ス": "ズ",
        "セ": "ゼ", "ソ": "ゾ", "タ": "ダ", "チ": "ヂ", "ツ": "ヅ", "テ": "デ", "ト": "ド",
        "ハ": "バ", "ヒ": "ビ", "フ": "ブ", "ヘ": "ベ", "ホ": "ボ", "ウ": "ヴ"
    },
    "゜": {
        "は": "ぱ", "ひ": "ぴ", "ふ": "ぷ", "へ": "ぺ", "ほ": "ぽ", "ハ": "パ", "ヒ": "ピ",
        "フ": "プ", "ヘ": "ペ", "ホ": "ポ"
    }
}

@dataclass
class Charset:
    charset: dict[int, str]
    diacritic_map: dict[dict[str, str]]
    eof_char: int

    def __post_init__(self):
        self.reverse_charset = {char: code for code, char in self.charset.items()}
        self.reverse_diacritic_map = {char: symbol+orgchar for symbol, accdict in self.diacritic_map.items() for orgchar, char in accdict.items()}

CHARSETS = {
    "ENGLISH": Charset(DEFAULT_ENGLISH_CHARSET, {}, 0x55),
    "FRENCH": Charset(DEFAULT_FRENCH_CHARSET, {}, 0x64),
    "GERMAN": Charset(DEFAULT_GERMAN_CHARSET, {}, 0x41),
    "JAPANESE": Charset(DEFAULT_JAPANESE_CHARSET, JAPANESE_DIACRITIC_MAP, 0xE9),
}

class HuffmanTrees:
    def __init__(self):
        self.trees = {}  # Map characters (bytes) to Huffman trees
        self.num_chars = 0

    def recalculate_trees(self, strings: list[bytes], eos_marker: int):
        """Recalculates Huffman trees based on character frequencies in the strings."""
        self.trees = {}
        frequencies = self._calculate_frequencies(strings, eos_marker)

        for char, freq in frequencies.items():
            self.trees[char] = HuffmanTree(freq, char)

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


class Node:
    def __init__(self, char=None, freq=None, parent=None):
        self.char = char
        self.weight = freq
        self.left = None
        self.right = None
        self.parent = parent
    
    def __lt__(self, rhs: "Node") -> bool:
        return self.weight < rhs.weight

class HuffmanTree:
    """Class for building and encoding/decoding a Huffman tree.
    
    Attributes:
        root: Node
        The root node of the Huffman tree.
    """
    def __init__(self, frequencies=None, c=None):
        """Initializes the root node of the tree."""
        self.root = Node()
        if frequencies:
            self.recalculate_tree(frequencies, c)
            
    def encode_tree(self) -> bytes:
        """Encodes the Huffman tree to a bitstream.

        Returns:
            BitStream: The encoded tree bits.
        """
        self.tree = []
        self.bits = BitStream()
        self.encode_tree_preorder(self.root)
        self.tree.reverse()
        return bytes(self.tree), bytes(self.bits)
        
    def decode_tree(self, encoded_trees: bytes, offset: int) -> None:
        """Decodes a Huffman tree from a bitstream.

        Args:
            bits: BitStream - The encoded tree bits.
        """ 
        bits = BitStream(encoded_trees)
        bits.bitpos = offset * 8
        next_chr = offset - 1
        node = self.root
        while True:
            if not bits.read(1).bool: # Node
                if not node.left:
                    node.left = Node(parent=node)
                    node = node.left
                else:
                    raise ValueError("Huffman Tree Corrupt")
            else: # Leaf
                node.char = encoded_trees[next_chr]
                next_chr -= 1
                if node == self.root:
                    break  # Reached root, exit loop
                node = node.parent
                while node != self.root and node.right:
                    node = node.parent
                if node == self.root and node.right:
                    break  # Root node has right child, tree complete
                node.right = Node(parent=node)
                node = node.right
        self.update_encoding_table()  # Add this call
        return bits  
                
    def recalculate_tree(self, frequencies: dict[int, int], c) -> None:
        """Recalculates the Huffman tree from character frequencies.
        
        Args:
        frequencies: Dict[int, int] - Mapping of chars to frequencies.
        """
        nodes = PriorityQueue()
        for char, freq in frequencies.items():
            nodes.put((freq, Node(char, freq)))
        while nodes.qsize() > 1:
            left = nodes.get()[1]
            right = nodes.get()[1]
            node = Node()
            node.left = left
            node.right = right
            left.parent = node
            right.parent = node
            node.weight = left.weight + right.weight
            nodes.put((node.weight, node))
        self.root = nodes.get()[1]
        self.update_encoding_table()

    def encode_char(self, char: int, bits: BitStream) -> None:
        """Encodes a character to the bitstream."""
        encoding = self.encoding[char]  
        for bit in encoding:
            bits.append(Bits(bool=int(bit)))

    def decode_char(self, bits: BitStream) -> int:
        """Decodes a character from the bitstream."""
        node = self.root
        while node.char is None:
            if not bits.read(1).bool:
                node = node.left
            else:  
                node = node.right
        return node.char

    def encode_tree_preorder(self, node: 'Node') -> None:
        """Helper method for preorder tree encoding."""

        if node.char is not None:
            self.tree.append(node.char)
            self.bits.append(Bits(bool=True))
        else:
            if node.left:  
                self.bits.append(Bits(bool=False))
                self.encode_tree_preorder(node.left)
            if node.right:
                self.encode_tree_preorder(node.right)


    def update_encoding_table(self) -> None:
        """Populates the character encodings table."""
        self.encoding = {}  
        self.update_table(self.root, "")

    def update_table(self, node: 'Node', encoding: str) -> None:
        if node.char is not None:  
            self.encoding[node.char] = encoding
        else:
            if node.left:  
                self.update_table(node.left, encoding+"0")
            if node.right:
                self.update_table(node.right, encoding+"1")
    
    def print_tree(self, node: Node | None = None, indent: int = 0) -> None:
        """Pretty prints the Huffman tree."""
        if not node:
            node = self.root
        if node.char is not None:
            print(f'{" "*indent}{node.char}')
        else:
            print(f'{" "*indent}Node')
            if node.left:
                self.print_tree(node.left, indent + 2)
            if node.right:
                self.print_tree(node.right, indent + 2)

def decode_string(encoded_string: bytes, charset: Charset) -> str:
    """Decodes an encoded string using the Huffman trees and custom encoding."""
    decoded = ''
    for char in encoded_string:
        if char in charset.charset:
            decoded += charset.charset[char]
        else:
            decoded += f'{{{char}}}'

    for symbol, mapping in charset.diacritic_map.items():
        for character, accented_character in mapping.items():
            decoded = decoded.replace(symbol + character, accented_character)
    
    
    return decoded


def encode_string(input: str, charset: Charset) -> bytes:
    encoded = bytearray()
    conv = input
    for char in input:
        # Convert accented characters back to symbol/char pairs
        if char in charset.reverse_diacritic_map:
            conv = conv.replace(char, charset.reverse_diacritic_map[char])
    
    i = 0
    while i < len(conv):
        char = conv[i]
        if char == "{":
            end = conv.find("}", i)
            if end == -1:
                raise ValueError("Unterminated {} sequence")
            else:
                try:
                    num = int(conv[i+1:end])
                except ValueError:
                    raise ValueError(f"Invalid integer between {{...}}: {conv[i+1:end]}")
                encoded.append(num)
                i = end + 1
        elif char in charset.reverse_charset:
            encoded.append(charset.reverse_charset[char])
            i += 1
        else:
            raise ValueError(f"Bad character: \"{char}\"")

    return encoded


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


def main():

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

    # Parse the arguments
    args = parser.parse_args()
    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
