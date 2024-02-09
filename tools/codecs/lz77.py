import bitstring

# Constants for encoding (aligned as closely as possible with the C++ version)
MAX_OFFSET = 4095 
MIN_MATCH_LENGTH = 3
MAX_MATCH_LENGTH = 18

def LZ77_encode(inbuf: bytes) -> bytes:
    """Compresses data using LZ77 encoding.

    Args:
      inbuf: Input bytes to compress.

    Returns:
      bytes: Compressed byte string.
    """
    outbuf = bytearray()
    entries = []
    
    i = 0
    cmd = bitstring.BitStream() # Bit barrel
    
    while i < len(inbuf):
        match_len, match_offset = find_best_match(inbuf, i)
        
        if match_len >= 3:
            tmatch_len, tmatch_offset = find_best_match(inbuf, i+1)
            if tmatch_len > match_len:
                match_offset = tmatch_offset
                match_len = tmatch_len
                entries.append(("byte", inbuf[i], 0))
                i += 1
            assert match_len in range(3, 19)
            assert match_offset in range(0, 4096)
            entries.append(("run", match_len, match_offset)) 
            i += match_len
        else:
            entries.append(("byte", inbuf[i], 0))
            i += 1
            
    entries.append(("end", 0, 0))
    
    command_bits = bitstring.BitStream()
    for e in entries:
        if e[0] == "byte":
            command_bits += bitstring.Bits(bool=True)
        else:
            command_bits += bitstring.Bits(bool=False)
    
    cmdbytes = bytes(command_bits)
    cmd = 0

    for i, e in enumerate(entries):
        print(e)
        if i % 8 == 0: # Flush full byte
            outbuf.append(cmdbytes[i//8]) 

        if e[0] == "byte":
            outbuf.append(e[1])
        elif e[0] == "run":
            b1 = ((e[2] >> 4) & 0xF0) | ((18 - e[1]) & 0x0F)
            b2 = e[2] & 0xFF
            outbuf.append(b1)
            outbuf.append(b2)
        else: # End marker
            outbuf.append(0)
            outbuf.append(0)
            break
    print(len(outbuf))
    return bytes(outbuf)


def LZ77_decode(inbuf: bytes) -> tuple[bytes, int]:
    """Decompresses LZ77 encoded data.

    Args:
      inbuf: Input compressed bytes.  

    Returns:
      bytes: Decompressed bytes.
      int: Number of bytes read from input.
    """
    cmd = bitstring.BitStream()
    outbuf = bytearray()
    idx = 0

    while True:
        if not cmd or cmd.bitpos >= 8:
            cmd = bitstring.BitStream(uint=inbuf[idx], length=8)
            idx += 1
        if cmd.read(1).bool:  # Read 1 bit from cmd
            byte = inbuf[idx]
            idx += 1
            outbuf.append(byte)
            print(('byte',byte,0))
        else:
            offset = ((inbuf[idx] & 0xF0) << 4) | inbuf[idx + 1]
            length = 18 - (inbuf[idx] & 0x0F)
            idx += 2
            print(('run',length,offset))
            if offset == 0:
                break  # End marker

            for i in range(length):
                outbuf.append(outbuf[-offset])

    return outbuf, idx

def find_best_match(inbuf: bytes, start: int, max_len = 18) -> tuple[int, int]:
    """Finds longest match in sliding window.

    Args:
      inbuf: Input bytes.
      start: Search position.
      
    Returns: 
      int: Match length.
      int: Match offset.
    """
    MAX_OFFSET = 4095
    MAX_LEN_LIMIT = 18
    MIN_LEN_LIMIT = 3

    END_SEARCH = start - MAX_OFFSET if start > MAX_OFFSET else 0
    MAX_LEN = min(max_len, MAX_LEN_LIMIT, len(inbuf) - start)

    best_len = 0
    match_offset = 0
    
    if MAX_LEN < MIN_LEN_LIMIT:
        return 1

    for i in range(start, END_SEARCH, -1):
        length = 0
        while inbuf[length + i -1] == inbuf[start + length]:
            length += 1
            if length == MAX_LEN:
                break
        if length > best_len:
            best_len = length
            match_offset = start - i + 1
            if best_len == MAX_LEN:
                break

    return best_len, match_offset
   