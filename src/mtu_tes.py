#! /usr/bin/python3

# mtu_tes.py
#
# Extracts data from MTU.TES, which has the same structure as MTU.ING.
# Contains quiz/test word data for İngilizce Leb Demeden feature.
#
# Format:
#     1- Offset map for 2-letter prefixes (2028 bytes = 676 * 3)
#     2- Per-prefix word data using morpheme expansion with CP 857 encoding
#
# @yasinkuyu

import os
import struct

# Suffixes from MTU.EXE (shared with MTU.TRK/MTU.ING)
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

    # Offset table starts at byte 0 (676 offsets, 3 bytes each)
    offsets = [0] * (26 * 26)
    for i in range(len(offsets)):
        offsets[i] = struct.unpack("<L", data[i*3:(i+1)*3] + b'\x00')[0]

    previous_morpheme = ''
    for prefix_idx in range(len(offsets) - 1):
        start_pos = offsets[prefix_idx]
        end_pos = offsets[prefix_idx + 1]

        if start_pos >= end_pos or start_pos >= len(data):
            continue

        prefix = chr(ord('a') + prefix_idx // 26) + chr(ord('a') + prefix_idx % 26)

        pos = start_pos
        while pos < end_pos and pos < len(data):
            instruction = data[pos]
            pos += 1
            if pos >= end_pos or pos >= len(data):
                break

            suffix_index = 0
            if instruction >= 0x80:
                suffix_index = data[pos]
                pos += 1
                if pos >= end_pos or pos >= len(data):
                    break

            if instruction == 0xFF:
                continue

            morpheme_start = pos
            while pos < end_pos and pos < len(data) and data[pos] != 0xFF:
                pos += 1

            if pos > morpheme_start and pos < len(data):
                try:
                    morpheme_bytes = data[morpheme_start:pos]
                    morpheme = morpheme_bytes.decode("cp857")
                    word = ExpandMorpheme(prefix, morpheme, previous_morpheme, instruction, suffix_index)
                    if len(word) >= 2:
                        previous_morpheme = word[2:]
                    if word:
                        words.append(word)
                    pos += 1
                except (UnicodeDecodeError, ValueError, IndexError):
                    pos += 1
            else:
                break

def Export(words, path):
    with open(path, "w", encoding="utf-8") as file:
        for word in words:
            file.write(word)
            file.write('\n')

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "..", "data", "MTU.TES")
    output_path = os.path.join(script_dir, "..", "output", "MTU.TES.TXT")

    words = []
    Import(words, data_path)
    Export(words, output_path)
    print("Exported", len(words), "test/quiz entries from MTU.TES.")

if __name__ == "__main__":
    main()
