from scripts.common.strings.charset import Charset, INTRO_CHARSET, REVERSE_INTRO_CHARSET, CREDITS_CHARSET, REVERSE_CREDITS_CHARSET


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

def decode_credit_string(encoded_string: bytes) -> tuple[tuple[int, int, str], int]:
    """Decodes an encoded string using the Huffman trees and custom encoding."""
    charset = CREDITS_CHARSET
    decoded = ''
    height = int.from_bytes(encoded_string[0:1], "big", signed=False)
    column = int.from_bytes(encoded_string[1:2], "big", signed=True)
    i = 0
    for i, char in enumerate(encoded_string[2:]):
        if char == 0:
            break
        if char in charset:
            decoded += charset[char]
            if charset[char] in ("{SEGA_LOGO}", "{CLIMAX_LOGO}", "{DDS520_LOGO}", "{MIRAGE_LOGO}"):
                break
        else:
            decoded += f'{{{char}}}'
    
    return (height, column, decoded), i + 3

def encode_credit_string(input: tuple[int, int, str]) -> bytes:
    encoded = bytearray()
    encoded.append(input[0])
    encoded.extend(input[1].to_bytes(1, "big", signed=True))
    reverse_charset = REVERSE_CREDITS_CHARSET

    i = 0
    while i < len(input[2]):
        char = input[2][i]
        found = False
        for k, code in reverse_charset.items():
            if input[2][i:].startswith(k):
                encoded.append(code)
                i += len(k)
                found = True
                break
        if found:
            continue
        if char == "{":
            end = input[2].find("}", i)
            if end == -1:
                raise ValueError("Unterminated {} sequence")
            else:
                try:
                    num = int(input[2][i+1:end])
                except ValueError:
                    raise ValueError(f"Invalid integer between {{...}}: {input[2][i+1:end]}")
                encoded.append(num)
                i = end + 1
        else:
            raise ValueError(f"Bad character: \"{char}\"")
    if encoded[-1] not in (reverse_charset["{SEGA_LOGO}"], reverse_charset["{CLIMAX_LOGO}"],
                           reverse_charset["{DDS520_LOGO}"], reverse_charset["{MIRAGE_LOGO}"]):
        encoded.append(0)

    return encoded

def decode_intro_string(encoded_string: bytes) -> tuple[int, int, int, int, int, str, str]:
    """Decodes an encoded string using the Huffman trees and custom encoding."""
    charset = INTRO_CHARSET
    decoded = ''
    line1_x = int.from_bytes(encoded_string[0:2], "big")
    line1_y = int.from_bytes(encoded_string[2:4], "big")
    line2_x = int.from_bytes(encoded_string[4:6], "big")
    line2_y = int.from_bytes(encoded_string[6:8], "big")
    time = int.from_bytes(encoded_string[8:10], "big")
    for char in encoded_string[10:]:
        if char == 0xFF:
            break
        elif char in charset:
            decoded += charset[char]
        else:
            decoded += f'{{{char}}}'
    line1 = decoded[:16].rstrip()
    line2 = decoded[16:32].rstrip()

    return line1_x, line1_y, line2_x, line2_y, time, line1, line2

def encode_intro_string(input: tuple[int, int, int, int, int, str, str]) -> bytes:
    encoded = bytearray()
    encoded.extend(input[0].to_bytes(2, "big"))
    encoded.extend(input[1].to_bytes(2, "big"))
    encoded.extend(input[2].to_bytes(2, "big"))
    encoded.extend(input[3].to_bytes(2, "big"))
    encoded.extend(input[4].to_bytes(2, "big"))
    reverse_charset = REVERSE_INTRO_CHARSET

    string = f"{input[5]:16}{input[6]}"

    i = 0
    while i < len(string):
        char = string[i]
        if char in reverse_charset:
            encoded.append(reverse_charset[char])
            i += 1
        elif char == "{":
            end = string.find("}", i)
            if end == -1:
                raise ValueError("Unterminated {} sequence")
            else:
                try:
                    num = int(string[i+1:end])
                except ValueError:
                    raise ValueError(f"Invalid integer between {{...}}: {string[i+1:end]}")
                encoded.append(num)
                i = end + 1
        else:
            raise ValueError(f"Bad character: \"{char}\"")
    
    if len(encoded) < 42:
        encoded.append(0xFF)

    return encoded
