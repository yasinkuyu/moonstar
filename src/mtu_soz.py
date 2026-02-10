#! /usr/bin/python3

# mtu_soz.py
#
# Extracts data from MTU.SOZ, which uses the MG2 format similar to MTU.TUR.
#
# MTU.SOZ consists of eight parts:
#     1- Magic number (4 bytes): "MG2\x1a"
#     2- Header (8 bytes): 4 × 16-bit values
#     3- Section 1 (66 bytes): lookup table for letters (32 letters + 1)
#     4- Section 2 (2050 bytes): lookup table for two-letter prefixes (byte0=start, byte1=count)
#     5- Section 4 (8,772 bytes): instructions for Turkish word formation
#     6- Section 5 (6,415 bytes): suffix data
#     7- Section 6 (24,664 bytes): modification instructions
#
# Note: MTU.SOZ Section 2 uses byte pairs (start, count) unlike MTU.TUR which uses uint16 offsets.
#
# @yasinkuyu

import os
import struct

alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

def GetSuffixLength(value):
    if 0x00 <= value < 0xb8:
        return value // 8
    elif 0xb8 <= value < 0x100:
        return 3 + ((value - 0xb8) // 0x18)
    else:
        return None

def GetSuffixReordered(suffix, value):
    if value >= 0xb8:
        value = (value - 0xb8) % 0x18
        if 0x00 <= value < 0x08:
            suffix = suffix[-1] + suffix[:-1]
        elif 0x08 <= value < 0x10:
            suffix = suffix[1:] + suffix[0]
        elif 0x10 <= value < 0x18:
            suffix = suffix[::-1]
    return suffix

def GetSuffix(data, instructions, base_offset):
    suffix = ''
    suffix_length = GetSuffixLength(instructions[1])

    if suffix_length == 0:
        pass
    elif 1 <= suffix_length <= 2:
        for i in range(0, suffix_length):
            if instructions[2 + i] < len(alphabet):
                suffix += alphabet[instructions[2 + i]]
    else:
        offset = struct.unpack("<H", instructions[2:4])[0]
        pos = base_offset + offset
        for i in range(0, suffix_length):
            if pos + i < len(data):
                index = data[pos + i]
                if index < len(alphabet):
                    suffix += alphabet[index]

    suffix = GetSuffixReordered(suffix, instructions[1])
    return suffix

def ApplyModifications(data, prefix, suffix):
    """
    Applies modifications to prefix and suffix based on Section 6 data.
    """
    should_capitalize = False

    # Check capitalization flags
    if data[0] == 0x0f:
        should_capitalize = True
    elif data[1] in [0x41, 0x49, 0x51, 0x59]:
        should_capitalize = True
    elif data[0] == 0x2f and data[1] == 0x59:
        should_capitalize = True

    # Apply capitalization to prefix
    if should_capitalize and prefix:
        if len(prefix) > 0:
            first_char = prefix[0]
            turkish_lower = {'ı': 'I', 'i': 'İ', 'ğ': 'Ğ', 'ü': 'Ü',
                           'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
            if first_char in turkish_lower:
                prefix = turkish_lower[first_char] + prefix[1:]
            else:
                prefix = prefix[0].upper() + prefix[1:]

    # Apply ğ -> k conversion
    if data[0] == 0x80:
        if suffix and suffix.endswith('ğ'):
            suffix = suffix[:-1] + 'k'
        elif prefix and prefix.endswith('ğ'):
            prefix = prefix[:-1] + 'k'

    return prefix, suffix

def Import(dictionary, path):
    data = open(path, "rb").read()
    pos = 0

    # Skip magic number
    if data[pos:pos+4] != b'MG2\x1a':
        raise ValueError("Invalid magic number")
    pos += 4

    # Read header
    header = []
    for i in range(0, 4):
        length = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        header.append(length)

    letter_count = 32

    # Section 1 - skip
    pos += (letter_count + 1) * 2

    # Section 2 - read as byte0=start, byte1=count
    section2 = []
    for i in range(letter_count**2):
        start = data[pos]
        count = data[pos + 1]
        pos += 2
        section2.append((start, count))

    # Skip last Section 2 entry
    pos += 2

    # Section 4 starts here (MTU.SOZ does not have Section 3)
    section4_start = pos
    section4_count = header[0]  # 2193 entries

    # Section 5 starts after Section 4
    section5_start = section4_start + section4_count * 4

    # Section 6 starts after Section 5
    section6_start = section5_start + header[2]
    section6 = []
    for i in range(header[3]):
        section6.append(data[section6_start + i * 4:section6_start + i * 4 + 4])

    # Process each prefix
    for prefix_idx in range(letter_count**2):
        start, count = section2[prefix_idx]

        if count == 0:
            continue

        prefix = alphabet[prefix_idx // letter_count] + alphabet[prefix_idx % letter_count]

        # Read entries for this prefix
        for i in range(start, min(start + count, section4_count)):
            entry_pos = section4_start + i * 4
            entry = data[entry_pos:entry_pos + 4]

            # Decode suffix
            suffix = GetSuffix(data, entry, section5_start)

            # Apply modifications from Section 6
            section6_idx = entry[0]
            if section6_idx < len(section6):
                prefix_mod, suffix_mod = ApplyModifications(section6[section6_idx], prefix, suffix)
                word = prefix_mod + suffix_mod
            else:
                word = prefix + suffix

            dictionary.append(word)

def Export(dictionary, path):
    with open(path, "w", encoding="utf-8") as file:
        for entry in dictionary:
            file.write(entry)
            file.write('\n')

def main():
    dictionary = []
    Import(dictionary, os.path.join("..", "data", "MTU.SOZ"))
    Export(dictionary, os.path.join("..", "output", "MTU.SOZ.TXT"))
    print("Exported", len(dictionary), "entries from MTU.SOZ.")

if __name__ == "__main__":
    main()
