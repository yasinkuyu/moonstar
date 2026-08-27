#! /usr/bin/python3

# mtu_soz.py
#
# Extracts data from MTU.SOZ, which uses the MG2 format similar to MTU.TUR.
#
# MTU.SOZ is a supplementary spell check dictionary containing Turkish place
# names and other specialized terms. It uses the same MG2 morphological
# pipeline as MTU.TUR but with a different header structure.
#
# MG2 format:
#     1- Magic number (4 bytes): "MG2\x1a"
#     2- Header (8 bytes): 4 x 16-bit values
#        [0] = Section 4 entry count (word formation instructions)
#        [1] = Section 3 entry count (suffix stripping table)
#        [2] = Section 5 size (suffix data bytes)
#        [3] = Section 6 entry count (modification flags)
#     3- Section 1 (66 bytes): letter lookup table (32 letters + 1)
#     4- Section 2 (2050 bytes): two-letter prefix offset table
#     5- Section 3: suffix stripping table (if header[1] > 0)
#     6- Section 4: word formation instructions
#     7- Section 5: suffix data
#     8- Section 6: modification flags
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
    '''
    Applies modifications to prefix and suffix based on Section 6 data.
    '''
    should_capitalize = False

    if data[0] == 0x0f:
        should_capitalize = True
    elif data[1] in [0x41, 0x49, 0x51, 0x59]:
        should_capitalize = True
    elif data[0] == 0x2f and data[1] == 0x59:
        should_capitalize = True

    if should_capitalize and prefix:
        if len(prefix) > 0:
            first_char = prefix[0]
            turkish_lower = {'ı': 'I', 'i': 'İ', 'ğ': 'Ğ', 'ü': 'Ü',
                           'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
            if first_char in turkish_lower:
                prefix = turkish_lower[first_char] + prefix[1:]
            else:
                prefix = prefix[0].upper() + prefix[1:]

    if data[0] == 0x80:
        if suffix and suffix.endswith('ğ'):
            suffix = suffix[:-1] + 'k'
        elif prefix and prefix.endswith('ğ'):
            prefix = prefix[:-1] + 'k'

    return prefix, suffix

def ReadDictionaryEntries(dictionary, data, base_offset, prefixes, section4, section6):
    item_index = 0
    for prefix, count in prefixes:
        if count == 0:
            continue
        for i in range(item_index, item_index + count):
            suffix = GetSuffix(data, section4[i], base_offset)
            section6_index = section4[i][0]
            prefix_mod, suffix_mod = ApplyModifications(section6[section6_index], prefix, suffix)
            word = prefix_mod + suffix_mod
            dictionary.append(word)
        item_index += count

def Import(dictionary, path):
    data = open(path, "rb").read()
    pos = 0

    if data[pos:pos+4] != b'MG2\x1a':
        raise ValueError("Invalid magic number")
    pos += 4

    header = []
    for i in range(0, 4):
        length = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        header.append(length)

    letter_count = 32

    section1 = []
    for i in range(0, letter_count + 1):
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section1.append(value)

    section2 = []
    for i in range(0, letter_count**2 + 1):
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section2.append(value)
    prefixes = []
    for prefix_index in range(0, len(section2) - 1):
        prefix = alphabet[prefix_index // letter_count]
        prefix += alphabet[prefix_index % letter_count]
        count = section2[prefix_index + 1] - section2[prefix_index]
        prefixes.append((prefix, count))

    section3 = []
    for i in range(0, header[1]):
        pos += 1
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section3.append(value)
        pos += 11

    section4 = []
    for i in range(0, header[0]):
        section4.append(data[pos:pos + 4])
        pos += 4

    base_offset = pos
    pos += header[2]

    section6 = []
    for i in range(0, header[3]):
        section6.append(data[pos:pos + 4])
        pos += 4

    ReadDictionaryEntries(dictionary, data, base_offset, prefixes, section4, section6)

def Export(dictionary, path):
    with open(path, "w", encoding="utf-8") as file:
        for entry in dictionary:
            file.write(entry)
            file.write('\n')

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "..", "data", "MTU.SOZ")
    output_dir = os.path.join(script_dir, "..", "output")

    dictionary = []
    Import(dictionary, data_path)
    Export(dictionary, os.path.join(output_dir, "MTU.SOZ.TXT"))
    print(f"Exported {len(dictionary)} entries from MTU.SOZ.")

if __name__ == "__main__":
    main()
