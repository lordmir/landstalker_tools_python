from tools.strings.charset import Charset


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
