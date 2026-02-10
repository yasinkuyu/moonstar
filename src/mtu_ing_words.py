#! /usr/bin/python3

# mtu_ing_words.py
#
# Extracts English words from MTU.ING for İngilizce Leb Demeden feature.
# Format appears to use custom alphabet similar to MTU.TUR.
# @yasinkuyu

import os
import struct

# MTU.ING uses custom alphabet (same as MTU.TUR)
alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

def DecodeWord(data, start, end):
    """
    Decodes a word from MTU.ING entry data.
    Format appears to be: instruction_byte + alphabet_encoded_letters
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
            # Unknown byte - might be a terminator or special marker
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
        
        # Try to decode entries in this prefix range
        entry_data = data[start:end]
        
        # Try to find word boundaries
        # Words might be separated by specific patterns or fixed lengths
        pos = 0
        while pos < len(entry_data):
            # Try to decode a word starting from current position
            word = DecodeWord(entry_data, pos, len(entry_data))
            
            if word:
                # Combine prefix with decoded word
                full_word = prefix + word
                words.append(full_word)
                
                # Move past the decoded word
                # Estimate: instruction byte (1) + word length
                pos += 1 + len(word)
            else:
                # No word found, skip one byte and try again
                pos += 1
            
            # Safety: don't loop forever
            if pos >= len(entry_data):
                break

def Export(words, path):
    with open(path, "w", encoding="utf-8") as file:
        for word in words:
            file.write(word)
            file.write('\n')

def main():
    words = []
    Import(words, os.path.join("..", "data", "MTU.ING"))
    Export(words, os.path.join("..", "output", "MTU.ING.TXT"))
    print("Exported", len(words), "words.")
    print("\nNote: This is experimental. Format may need adjustment.")

if __name__ == "__main__":
    main()

