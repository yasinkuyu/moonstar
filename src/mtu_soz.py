#! /usr/bin/python3

# mtu_soz.py
#
# Extracts data from MTU.SOZ, which uses the MG2 format similar to MTU.TUR.
#
# MTU.SOZ consists of seven parts (no Section 3 like MTU.TUR):
#     1- Magic number (4 bytes): "MG2\x1a"
#     2- Header (8 bytes): 4 × 16-bit values
#     3- Section 1 (66 bytes): lookup table for letters (32 letters + 1)
#     4- Section 2 (2050 bytes): lookup table for two-letter prefixes (byte0=start, byte1=count)
#     5- Section 4 (8,772 bytes): instructions for Turkish word formation
#     6- Section 5 (6,415 bytes): suffix data
#     7- Section 6 (≈5,692 bytes): modification instructions
#
# The existing 22.5 KB MTU.SOZ file has NO Section 3 (header[1] = 14227 is
# not an entry count here — it likely has a different meaning for this file).
#
# Section 2 uses byte pairs (start, count) unlike MTU.TUR which uses uint16 offsets.
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

    # In MTU.SOZ, Section 4 starts directly after the header (offset 12)
    # Section 1 (66 bytes) and Section 2 (2050 bytes) are present in the file size layout
    # but contain dummy/unused index data.
    # The actual word rules start at offset 2128 (12 + 66 + 2050).
    sec4_start = 12 + 66 + 2050
    sec4_count = header[0]  # 2193 entries

    sec5_start = sec4_start + sec4_count * 4
    sec5_size = header[2]  # 6415 bytes

    alphabet32 = 'abcçdefgğhıijklmnoöpqrsştuüvwxyz'

    # Read all rules
    rules = []
    for i in range(sec4_count):
        entry_pos = sec4_start + i * 4
        entry = data[entry_pos:entry_pos + 4]
        
        p1, p2 = entry[0], entry[1]
        prefix = (alphabet32[p1] if p1 < 32 else '') + (alphabet32[p2] if p2 < 32 else '')
        
        offset = entry[2] + entry[3] * 256
        rules.append({
            'index': i,
            'prefix': prefix,
            'offset': offset
        })

    # Sort rules by offset to determine suffix boundaries (suffix compaction)
    sorted_rules = sorted(rules, key=lambda x: x['offset'])
    for i in range(len(sorted_rules)):
        curr = sorted_rules[i]
        next_offset = sec5_size
        for j in range(i + 1, len(sorted_rules)):
            if sorted_rules[j]['offset'] > curr['offset']:
                next_offset = sorted_rules[j]['offset']
                break
        curr['suffix_len'] = next_offset - curr['offset']

    # Reconstruct words
    for r in rules:
        pos = sec5_start + r['offset']
        slen = min(r['suffix_len'], 30)  # limit sanity check
        suffix = ''
        for k in range(slen):
            if pos + k < len(data):
                idx = data[pos + k]
                suffix += alphabet32[idx] if idx < 32 else ''
        
        word = r['prefix'] + suffix
        if word:
            # Capitalize properly if it looks like a name
            word = word[0].upper() + word[1:]
            dictionary.append(word)

def ImportBridgeTable(bridge, path):
    """
    Reads Section 3 (if it exists in the file) and pairs each entry with its
    resolved Turkish word from Section 4.

    In the current 22.5 KB MTU.SOZ file, Section 3 does NOT exist — header[1]
    is not an entry count. This function detects the mismatch and returns
    early. A larger/different MTU.SOZ binary may contain a proper bridge table
    with 14-byte entries.

    The 11-byte block inside each bridge entry is kept as raw hex since its
    internal layout hasn't been confirmed. It likely encodes an MTU.ING offset
    (possibly middle-endian, like MTU.TRK's Turkish offsets) but with 11 bytes
    available it probably stores more than a single offset.
    """
    data = open(path, "rb").read()
    pos = 0

    if data[pos:pos + 4] != b'MG2\x1a':
        raise ValueError("Invalid magic number")
    pos += 4

    header = []
    for i in range(0, 4):
        length = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        header.append(length)

    letter_count = 32

    pos += (letter_count + 1) * 2

    section2 = []
    for i in range(letter_count**2):
        start = data[pos]
        count = data[pos + 1]
        pos += 2
        section2.append((start, count))
    pos += 2

    # Check if a potential Section 3 would fit
    sec3_bytes_needed = header[1] * 14
    sec4_bytes_needed = header[0] * 4
    sec5_bytes_needed = header[2]
    after_s2 = len(data) - pos
    after_s3 = after_s2 - sec3_bytes_needed
    sec6_estimate = after_s3 - sec4_bytes_needed - sec5_bytes_needed

    if sec3_bytes_needed > after_s2 or sec6_estimate < 0:
        print(f"Note: Section 3 does not fit in this {len(data)} B file "
              f"(needs {sec3_bytes_needed} B). Skipping bridge table.")
        return

    # Section 3 exists — read it
    section3 = []
    for i in range(header[1]):
        byte0 = data[pos]
        pos += 1
        section4_ref = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        ing_block = data[pos:pos + 11]
        pos += 11
        section3.append((byte0, section4_ref, ing_block))

    section4_start = pos
    section4_count = header[0]

    section5_start = section4_start + section4_count * 4

    section6_start = section5_start + header[2]
    section6_available = (len(data) - section6_start) // 4
    section6_count = min(header[3], section6_available)
    section6 = []
    for i in range(section6_count):
        section6.append(data[section6_start + i * 4:section6_start + i * 4 + 4])

    turkish_words = {}
    for prefix_idx in range(letter_count**2):
        start, count = section2[prefix_idx]
        if count == 0:
            continue
        prefix = alphabet[prefix_idx // letter_count] + alphabet[prefix_idx % letter_count]
        for i in range(start, min(start + count, section4_count)):
            entry_pos = section4_start + i * 4
            entry = data[entry_pos:entry_pos + 4]
            suffix = GetSuffix(data, entry, section5_start)
            section6_idx = entry[0]
            if section6_idx < len(section6):
                prefix_mod, suffix_mod = ApplyModifications(section6[section6_idx], prefix, suffix)
                turkish_words[i] = prefix_mod + suffix_mod
            else:
                turkish_words[i] = prefix + suffix

    for byte0, section4_ref, ing_block in section3:
        turkish_word = turkish_words.get(section4_ref, '')
        bridge.append((turkish_word, byte0, ing_block.hex()))

def Export(dictionary, path):
    with open(path, "w", encoding="utf-8") as file:
        for entry in dictionary:
            file.write(entry)
            file.write('\n')

def ExportBridgeTable(bridge, path):
    with open(path, "w", encoding="utf-8") as file:
        for turkish_word, byte0, ing_hex in bridge:
            file.write(f"{turkish_word:<30} flag=0x{byte0:02x}  ing_block={ing_hex}\n")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "..", "data", "MTU.SOZ")
    output_dir = os.path.join(script_dir, "..", "output")

    dictionary = []
    Import(dictionary, data_path)
    Export(dictionary, os.path.join(output_dir, "MTU.SOZ.TXT"))
    print("Exported", len(dictionary), "entries from MTU.SOZ.")

    bridge = []
    ImportBridgeTable(bridge, data_path)
    if bridge:
        ExportBridgeTable(bridge, os.path.join(output_dir, "MTU.SOZ_BRIDGE.TXT"))
        print("Exported", len(bridge), "Section 3 bridge entries (raw, for analysis).")
    else:
        with open(os.path.join(output_dir, "MTU.SOZ_BRIDGE.TXT"), "w") as f:
            f.write("# No Section 3 bridge data in this MTU.SOZ file.\n")
            import struct
            with open(data_path, "rb") as df:
                d = df.read()
            h = [struct.unpack("<H", d[6:8])[0]]
            f.write(f"# File size: {os.path.getsize(data_path)} B — "
                    f"too small to hold header[1]={h[0]} × 14 B entries.\n")
            f.write("# A larger/correct MTU.SOZ binary is needed for the bridge table.\n")

if __name__ == "__main__":
    main()
