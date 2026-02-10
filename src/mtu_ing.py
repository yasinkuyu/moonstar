#! /usr/bin/python3

# mtu_ing.py
#
# Extracts data from MTU.ING for İngilizce Leb Demeden feature.
#
# MTU.ING consists of:
#     1- Base offset (3 bytes) - data starts at this position
#     2- Offset map for 2-letter prefixes (2028 bytes = 676 * 3)
#     3- English word entries using morpheme expansion with CP 857 encoding
#
# Note: Offset table contains ABSOLUTE positions, not relative offsets.
# Each prefix's data runs from the previous offset (or base_offset) to the current offset.
#
# @yasinkuyu

import os
import struct

# Suffixes from MTU.EXE
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

def ExpandMorpheme(prefix, morpheme, previous_morpheme, instruction, suffix_index):
    """
    Expands a morpheme using bytecode instructions.
    prefix: 2-letter prefix (aa-zz)
    morpheme: current morpheme string
    previous_morpheme: previous morpheme for combining
    instruction: bytecode instruction
    suffix_index: suffix index if instruction >= 0x80
    """
    if instruction == 0x00 or instruction == 0x12:
        pass  # No operation
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

    # First 3 bytes are the base offset
    base_offset_bytes = data[0:3] + b'\x00'
    base_offset = struct.unpack("<L", base_offset_bytes)[0]

    # Offset table starts at byte 3
    offset_table_start = 3
    offsets = [0] * (26 * 26)

    for i in range(len(offsets)):
        offset_bytes = data[offset_table_start + i*3:offset_table_start + (i+1)*3] + b'\x00'
        offsets[i] = struct.unpack("<L", offset_bytes)[0]

    # Process each prefix
    previous_morpheme = ''
    for prefix_idx in range(len(offsets)):
        # Start from previous offset (or base_offset for first prefix)
        start_pos = base_offset if prefix_idx == 0 else offsets[prefix_idx - 1]
        # End at current offset
        end_pos = offsets[prefix_idx]

        if start_pos >= end_pos or start_pos >= len(data):
            continue

        # Get 2-letter prefix
        prefix = chr(ord('a') + prefix_idx // 26) + chr(ord('a') + prefix_idx % 26)

        pos = start_pos

        # Read entries until we reach end_pos
        while pos < end_pos:
            # Read instruction byte
            instruction = data[pos]
            pos += 1

            if pos >= len(data) or pos >= end_pos:
                break

            # Check for suffix index (if instruction >= 0x80)
            suffix_index = 0
            if instruction >= 0x80:
                if pos >= len(data) or pos >= end_pos:
                    break
                suffix_index = data[pos]
                pos += 1

            if pos >= len(data) or pos >= end_pos:
                break

            # Read morpheme until 0xFF
            morpheme_start = pos
            while pos < end_pos and data[pos] != 0xFF:
                pos += 1

            if pos > morpheme_start and pos < end_pos:
                try:
                    # Decode morpheme using CP 857
                    morpheme_bytes = data[morpheme_start:pos]
                    morpheme = morpheme_bytes.decode("cp857")

                    # Expand using morpheme system
                    word = ExpandMorpheme(prefix, morpheme, previous_morpheme, instruction, suffix_index)

                    # Store for next iteration (without prefix)
                    if len(word) >= 2:
                        previous_morpheme = word[2:]

                    if word:
                        words.append(word)

                    pos += 1  # Skip 0xFF
                except (UnicodeDecodeError, ValueError, IndexError):
                    # Skip invalid entry
                    pos += 1
            else:
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
