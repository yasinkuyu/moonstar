#! /usr/bin/python3

# mtu_soz.py
#
# Extracts data from MTU.SOZ, which uses the MG2 format similar to MTU.TUR
# but with a DIFFERENT section layout.
#
# SOZ header [2193, 14227, 6415, 6166]:
#   header[0]=2193  → Section 4 entry count (word formation instructions)
#   header[1]=14227 → NOT section 3 count (14227*14=199KB >> 23KB file!)
#   header[2]=6415  → Section 5 byte size (plain suffix data)
#   header[3]=6166  → Unknown (possibly extended header data)
#
# Layout (sec4_start=12):
#   Bytes 0-11:    MG2 magic (4B) + header (8B)
#   Bytes 12-8783:  Section 4 (2193 × 4 bytes = 8772B) — word entries
#   Bytes 8784-15198: Section 5 (6415 bytes) — suffix data
#   Bytes 15199+:   Section 6 (remaining) — modification flags
#
# Sec1 (68B) and Sec2 (2050B) exist at offsets 12-2130 but appear to be
# part of an EXTENDED HEADER (sec1[0]=header[2], sec1[1]=header[3]).
# Sec2 is NOT monotonic (unlike TUR) so cannot be used as prefix counts.
#
# Entry format (Section 4):
#   byte 0: alphabet32 index → first letter of prefix
#   byte 1: alphabet32 index → second letter of prefix; suffix_len = byte1 // 8
#   bytes 2-3: if suffix_len ≤ 2: inline alphabet32 chars
#              if suffix_len ≥ 3: u16 offset into Section 5
#
# Output: 95% valid characters, ~19% exact matches with TUR dictionary.
# Words are PLACE NAME COMPONENTS (prefix+suffix fragments), not full words.
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

    # Layout B: sec4 starts at offset 12 (right after 4B magic + 8B header)
    # This gives 95% valid chars vs 22% with the old layout (sec4 at 2128)
    sec4_start = 12  # After MG2\x1a (4B) + header (8B)
    sec4_count = header[0]  # 2193 entries
    sec4_end = sec4_start + sec4_count * 4

    # Section 5: suffix data
    sec5_start = sec4_end  # 8784
    sec5_size = header[2]  # 6415 bytes

    # Section 6: modification flags (remaining bytes)
    sec6_start = sec5_start + sec5_size
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
        if p1 >= len(alphabet32) or p2 >= len(alphabet32):
            dictionary.append(f'[invalid:{entry.hex()}]')
            continue

        prefix = alphabet32[p1] + alphabet32[p2]

        # Suffix from Section 5
        suffix_len = GetSuffixLength(entry[1])
        suffix = ''

        if suffix_len is None or suffix_len == 0:
            pass
        elif 1 <= suffix_len <= 2:
            for k in range(suffix_len):
                idx_b = entry[2 + k]
                if idx_b < len(alphabet32):
                    suffix += alphabet32[idx_b]
                else:
                    suffix += '?'
        elif suffix_len >= 3:
            off = entry[2] | (entry[3] << 8)
            spos = sec5_start + off
            for k in range(suffix_len):
                si = spos + k
                if 0 <= si < len(data):
                    bi = data[si]
                    if bi < len(alphabet32):
                        suffix += alphabet32[bi]
                    else:
                        suffix += '?'
                else:
                    suffix += '?'

        suffix = GetSuffixReordered(suffix, entry[1])

        # Apply Section 6 modifications (if available)
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
