from bitstring import BitStream, Bits
from queue import PriorityQueue


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
    def __init__(self, frequencies=None):
        """Initializes the root node of the tree."""
        self.root = Node()
        if frequencies:
            self.recalculate_tree(frequencies)
            
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
                
    def recalculate_tree(self, frequencies: dict[int, int]) -> None:
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
