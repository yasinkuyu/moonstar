#! /usr/bin/python3

# mtu_tes_words.py
#
# Extracts words from MTU.TES (test/quiz data for İngilizce Leb Demeden).
# Format appears similar to MTU.ING.
# @yasinkuyu

import os
import struct

# MTU.TES uses custom alphabet (same as MTU.TUR/MTU.ING)
alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

def DecodeWord(data, start, end):
    """
    Decodes a word from MTU.TES entry data.
    """
    word = ''
    pos = start
    
    if pos >= end:
        return word
    
    # Skip instruction byte (first byte)
    instruction = data[pos]
    pos += 1
    
    # Decode letters using custom alphabet
    while pos < end:
        byte = data[pos]
        if byte < len(alphabet):
            word += alphabet[byte]
        elif byte == 0:
            break
        else:
            break
        pos += 1
    
    return word

def Import(words, path):
    data = open(path, "rb").read()
    
    # First 3 bytes are base offset
    base_offset_bytes = data[0:3] + b'\x00'
    base_offset = struct.unpack("<L", base_offset_bytes)[0]
    
    # Offset table starts at byte 3
    offset_table_start = 3
    offsets = [0] * (26 * 26)
    
    for i in range(0, len(offsets)):
        offset_bytes = data[offset_table_start + i*3:offset_table_start + (i+1)*3] + b'\x00'
        offsets[i] = struct.unpack("<L", offset_bytes)[0]
    
    # Read entries for each prefix
    for prefix_idx in range(0, len(offsets) - 1):
        start = offsets[prefix_idx]
        end = offsets[prefix_idx + 1]
        
        if start >= len(data) or end > len(data) or start >= end:
            continue
        
        # Calculate prefix (aa-zz)
        prefix = chr(ord('a') + prefix_idx // 26) + chr(ord('a') + prefix_idx % 26)
        
        # Try to decode entries
        entry_data = data[start:end]
        
        pos = 0
        while pos < len(entry_data):
            word = DecodeWord(entry_data, pos, len(entry_data))
            
            if word:
                full_word = prefix + word
                words.append(full_word)
                pos += 1 + len(word)
            else:
                pos += 1
            
            if pos >= len(entry_data):
                break

def Export(words, path):
    with open(path, "w", encoding="utf-8") as file:
        for word in words:
            file.write(word)
            file.write('\n')

def main():
    words = []
    Import(words, os.path.join("..", "data", "MTU.TES"))
    Export(words, os.path.join("..", "output", "MTU.TES.TXT"))
    print("Exported", len(words), "words.")
    print("\nNote: This is experimental. Format may need adjustment.")

if __name__ == "__main__":
    main()

