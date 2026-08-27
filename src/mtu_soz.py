#! /usr/bin/python3

# mtu_soz.py
#
# Extracts data from MTU.SOZ, which uses the MG2 format similar to MTU.TUR
# but with a DIFFERENT section layout.
#
# SOZ header [2193, 14227, 6415, 6166] does NOT map to the same sections as TUR.
# - Section 1 (66B) + Section 2 (2050B) are present but sec2 is NOT monotonic
# - Section 3 does NOT fit (header[1]=14227 × 14 = 199KB > 23KB file)
# - Section 4 (header[0]=2193 entries × 4 bytes) starts at offset 2128
# - Section 5 (header[2]=6415 bytes) follows Section 4
# - Section 6 (remaining bytes) follows Section 5
#
# The prefix for each entry is derived from Section 4 bytes 0-1 as alphabet32
# indices. Suffix is at Section 5 offset (bytes 2-3). Section 6 provides
# modification flags (capitalization etc).
#
# Output is PARTIALLY GARBLED (22% valid) because the exact decode pipeline
# for SOZ's unique structure is not yet fully reverse-engineered.
#
# @yasinkuyu

import os
import struct

alphabet32 = 'abcçdefgğhıijklmnoöpqrsştuüvwxyz'

def GetSuffixLength(value):
    if 0x00 <= value < 0xb8:
        return value // 8
    elif 0xb8 <= value < 0x100:
        return 3 + ((value - 0xb8) // 0x18)
    else:
        return None

def GetSuffixReordered(suffix, value):
    if value >= 0xb8 and suffix:
        rv = (value - 0xb8) % 0x18
        if 0x00 <= rv < 0x08:
            suffix = suffix[-1] + suffix[:-1]
        elif 0x08 <= rv < 0x10:
            suffix = suffix[1:] + suffix[0]
        elif 0x10 <= rv < 0x18:
            suffix = suffix[::-1]
    return suffix

def Import(dictionary, path):
    data = open(path, "rb").read()
    pos = 0

    if data[pos:pos+4] != b'MG2\x1a':
        raise ValueError("Invalid magic number")
    pos += 4

    header = []
    for i in range(4):
        length = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        header.append(length)

    # Skip Section 1 (66 bytes) and Section 2 (2050 bytes)
    sec1_size = 33 * 2  # 66 bytes
    sec2_size = (32 * 32 + 1) * 2  # 2050 bytes
    pos += sec1_size + sec2_size  # = 2128

    # Section 4: header[0] entries × 4 bytes
    sec4_count = header[0]  # 2193
    sec4_start = pos
    sec4_end = sec4_start + sec4_count * 4

    # Section 5: header[2] bytes
    sec5_start = sec4_end
    sec5_size = header[2]  # 6415
    sec5_end = sec5_start + sec5_size

    # Section 6: remaining bytes
    sec6_start = sec5_end
    sec6_size = len(data) - sec6_start
    sec6_count = sec6_size // 4 if sec6_size >= 4 else 0

    # Read Section 6
    section6 = []
    for i in range(sec6_count):
        section6.append(data[sec6_start + i*4:sec6_start + i*4 + 4])

    # Decode Section 4 entries
    for idx in range(sec4_count):
        entry = data[sec4_start + idx*4:sec4_start + idx*4 + 4]
        if len(entry) < 4:
            break

        p1, p2 = entry[0], entry[1]
        prefix = (alphabet32[p1] if p1 < len(alphabet32) else '') + \
                 (alphabet32[p2] if p2 < len(alphabet32) else '')

        # Suffix from Section 5
        suffix_len = GetSuffixLength(entry[1])
        suffix = ''

        if suffix_len and 1 <= suffix_len <= 2:
            for k in range(suffix_len):
                idx_b = entry[2 + k]
                if idx_b < len(alphabet32):
                    suffix += alphabet32[idx_b]
        elif suffix_len and suffix_len >= 3:
            off = entry[2] + entry[3] * 256
            spos = sec5_start + off
            for k in range(suffix_len):
                if spos + k < len(data):
                    bi = data[spos + k]
                    if bi < len(alphabet32):
                        suffix += alphabet32[bi]

        suffix = GetSuffixReordered(suffix, entry[1])

        # Apply Section 6 modifications
        mod_idx = entry[0]
        if mod_idx < len(section6):
            mod = section6[mod_idx]
            should_cap = (mod[0] == 0x0f or mod[1] in [0x41, 0x49, 0x51, 0x59] or
                         (mod[0] == 0x2f and mod[1] == 0x59))
            if should_cap and prefix:
                tc = {'ı': 'I', 'i': 'İ', 'ğ': 'Ğ', 'ü': 'Ü',
                      'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
                fc = prefix[0]
                prefix = tc.get(fc, fc.upper()) + prefix[1:]
            if mod[0] == 0x80:
                if suffix and suffix.endswith('ğ'):
                    suffix = suffix[:-1] + 'k'
                elif prefix and prefix.endswith('ğ'):
                    prefix = prefix[:-1] + 'k'

        word = prefix + suffix
        if word:
            dictionary.append(word)

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
