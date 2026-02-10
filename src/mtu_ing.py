#! /usr/bin/python3

# mtu_ing.py
#
# Extracts data from MTU.ING, which is required for İngilizce Leb Demeden feature.
#
# MTU.ING consists of:
#     1- Base offset (3 bytes, first offset value)
#     2- Offset map for 2-letter prefixes (2028 bytes = 676 * 3)
#     3- List of English words (variable length)
#
# Format is similar to MTU.TRK: English words use morpheme expansion with 0xFF terminators.
# Each entry: [instruction] [suffix_index?] [morpheme] [0xFF] [offset_to_english_length_prefix]
# The offset points to a location where first 2 bytes are length, followed by English text.
# @yasinkuyu

import os
import struct

# Suffixes from MTU.EXE (same as MTU.TRK)
suffixes = [
    "ability", "ibility", "iveness", "ization", "fulness", "ousness",
    "ectomy", "edness", "liness", "ically", "lessly",
    "ality", "alism", "antly", "arian", "ating", "ation", "ative", "atory", "berry", "board",
    "bound", "ering", "esque", "fully", "house", "ially", "iness", "ingly", "ional", "istic",
    "ition", "ively", "ivity", "light", "ology", "orium", "ously", "stone", "ually",
    "able", "ance", "ancy", "ally", "ated", "back", "ball", "band", "bing", "bird",
    "boat", "bone", "book", "cide", "cule", "ding", "down", "ence", "ency", "ener",
    "ette", "fold", "ging", "head", "hood", "ible", "ical", "icle", "ings", "ious",
    "itis", "izer", "land", "less", "like", "line", "ling", "logy", "make", "ment",
    "ming", "ness", "ning", "ntly", "osis", "over", "ping", "ring", "room", "ship",
    "side", "sing", "sman", "some", "ster", "tail", "time", "ting", "wise", "wood",
    "work", "wort",
    "acy", "ade", "age", "and", "ant", "ary", "ate", "ble", "boy", "dom",
    "end", "ent", "ery", "ese", "ess", "est", "eur", "ful", "ger", "ial",
    "ian", "ide", "ied", "ier", "ile", "ily", "ine", "ing", "ion", "ise",
    "ish", "ism", "ist", "ite", "ity", "ium", "ive", "ize", "kin", "ler",
    "let", "man", "med", "nce", "ned", "oid", "ome", "oon", "ory", "ous",
    "out", "per", "red", "rer", "sed", "ted", "ter", "tic", "ual", "ule",
    "ure", "way", "yer",
    "ae", "al", "an", "ar", "by", "ch", "cy", "ed", "el", "en",
    "er", "et", "ey", "fy", "ia", "ic", "ie", "in", "is", "ly",
    "nt", "on", "or", "ow", "ry", "st", "th", "to", "ty", "us",
]

def ExpandMorpheme(prefix_index, morpheme, previous_morpheme, instruction, suffix_index):
    prefix = chr(ord('a') + prefix_index // 26) + chr(ord('a') + prefix_index % 26)

    if instruction == 0x00 or instruction == 0x12:
        pass
    elif instruction == 0x20:
        prefix = prefix.title()
    elif 0x40 < instruction < 0x50:
        n = instruction - 0x40
        morpheme = previous_morpheme[:n] + morpheme
    elif 0x60 < instruction < 0x70:
        n = instruction - 0x60
        morpheme = previous_morpheme[:n] + morpheme
        prefix = prefix.title()
    elif instruction == 0x80:
        if suffix_index < len(suffixes):
            morpheme = morpheme + suffixes[suffix_index]
    elif instruction == 0xA0:
        if suffix_index < len(suffixes):
            morpheme = morpheme + suffixes[suffix_index]
        prefix = prefix.title()
    elif 0xC0 < instruction < 0xD0:
        n = instruction - 0xC0
        if suffix_index < len(suffixes):
            morpheme = previous_morpheme[:n] + morpheme + suffixes[suffix_index]
    elif 0xE0 < instruction < 0xF0:
        n = instruction - 0xE0
        if suffix_index < len(suffixes):
            morpheme = previous_morpheme[:n] + morpheme + suffixes[suffix_index]
        prefix = prefix.title()

    return prefix + morpheme

def Import(words, path):
    data = open(path, "rb").read()

    # First 3 bytes are the base offset (like MTU.TRK but stored explicitly)
    base_offset_bytes = data[0:3] + b'\x00'
    base_offset_value = struct.unpack("<L", base_offset_bytes)[0]

    # Offset table starts at byte 3
    offset_table_start = 3
    offsets = [0] * (26 * 26)

    for i in range(0, len(offsets)):
        offset_bytes = data[offset_table_start + i*3:offset_table_start + (i+1)*3] + b'\x00'
        offsets[i] = struct.unpack("<L", offset_bytes)[0]

    # MTU.ING uses ABSOLUTE offsets (not relative like MTU.TRK)
    # The first 3 bytes (base_offset_value = 96000) indicates where data actually starts
    # But offsets in the table are absolute file positions
    previous_word = ''
    for prefix_idx in range(0, len(offsets)):
        # Offsets are absolute file positions
        start_pos = offsets[prefix_idx]
        end_pos = offsets[prefix_idx + 1] if prefix_idx + 1 < len(offsets) else len(data)
        
        if start_pos >= len(data) or end_pos > len(data) or start_pos >= end_pos:
            continue
        
        # Skip empty prefixes (0xFF marker)
        pos = start_pos
        if pos < end_pos and data[pos] == 0xFF:
            # Format: 0xFF [count] - no entries here
            continue
        
        # Read entries using MTU.TRK logic: [instruction] [suffix?] [morpheme] [0xFF]
        # BUT: Some prefixes may have [instruction] [count] header - check and skip
        if pos + 1 < end_pos and data[pos] == 0x00:
            count_byte = data[pos + 1]
            # If count is small and next byte looks like an instruction, skip header
            if count_byte < 50 and pos + 2 < end_pos:
                next_byte = data[pos + 2]
                # Check if it's a valid instruction byte
                if (next_byte == 0x00 or next_byte == 0x12 or next_byte == 0x20 or
                    (0x40 <= next_byte < 0x50) or (0x60 <= next_byte < 0x70) or
                    next_byte == 0x80 or next_byte == 0xA0 or
                    (0xC0 <= next_byte < 0xD0) or (0xE0 <= next_byte < 0xF0)):
                    pos += 2  # Skip [0x00] [count] header
        
        while pos < end_pos:
            instruction = data[pos]
            pos += 1

            if pos >= end_pos:
                break

            suffix_index = 0
            if instruction >= 0x80:
                if pos >= end_pos:
                    break
                suffix_index = data[pos]
                pos += 1

            if pos >= end_pos:
                break

            # English entries are terminated by a 0xFF character (same as MTU.TRK)
            en_len = 0
            while pos + en_len < len(data) and pos + en_len < end_pos:
                if data[pos + en_len] == 0xFF:
                    break
                en_len += 1
            
            if en_len > 0 and pos + en_len < len(data) and pos + en_len < end_pos:
                # EXACT MTU.TRK logic: decode morpheme and expand
                try:
                    english = data[pos:pos + en_len].decode("cp857")
                    english = ExpandMorpheme(prefix_idx, english, previous_word, instruction, suffix_index)
                    previous_word = english[2:]  # No need to store the prefix (same as MTU.TRK)
                    
                    if english:
                        words.append(english)
                    
                    # CRITICAL: MTU.ING contains only English words, NO Turkish offset
                    # Skip only morpheme + 0xFF (unlike MTU.TRK which also reads 3-byte Turkish offset)
                    pos += en_len + 1
                except (UnicodeDecodeError, ValueError, IndexError):
                    # Skip invalid entries - try to find next 0xFF
                    pos += 1
                    while pos < end_pos and pos < len(data) and data[pos] != 0xFF:
                        pos += 1
                    if pos < end_pos and pos < len(data):
                        pos += 1  # Skip 0xFF
            else:
                # No 0xFF found or end of data
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
    print("Exported", len(words), "English words (İngilizce Leb Demeden).")

if __name__ == "__main__":
    main()
