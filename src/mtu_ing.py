#! /usr/bin/python3

# mtu_ing.py
#
# Extracts data from MTU.ING for İngilizce Leb Demeden feature.
#
# REVERSE-ENGINEERING STATUS (2026-07-13):
#   ✅ Offset structure: 96000 B offset table, 32000 × 3-byte abs positions
#   ✅ Slot header: [0x00, (slot_idx + 1) % 256]
#   ✅ Alphabet: frequency-ordered (0x00=e, 0x03=t, 0x0b=a, ...)
#       - Verified: "the" (0x03 0x04 0x00) in 56+ slots
#       - Verified: 185 words match TRK dictionary
#   ✅ Instruction bytes (0x80-0xFF) = suffix table indices from MTU.EXE
#   ✅ Every slot body ends with an instruction byte
#   ❌ Instruction semantics: how suffixes combine with letter morphemes unknown
#
# @yasinkuyu

import os
import struct
from collections import Counter

# Alphabet: bytes 0x00-0x19, ordered by frequency in slot data
BYTE_TO_LETTER = {
    0x00: 'e', 0x01: 'y', 0x02: 'o', 0x03: 't', 0x04: 'h',
    0x05: 'n', 0x06: 'p', 0x07: 'w', 0x08: 'q', 0x09: 'f',
    0x0a: 'z', 0x0b: 'a', 0x0c: 'j', 0x0d: 'b', 0x0e: 'm',
    0x0f: 'g', 0x10: 'l', 0x11: 'i', 0x12: 'x', 0x13: 'c',
    0x14: 'k', 0x15: 'r', 0x16: 's', 0x17: 'v', 0x18: 'u',
    0x19: 'd',
}

def load_suffixes(exe_path):
    with open(exe_path, 'rb') as f:
        d = f.read()
    suffix_data = d[0x1B8B8:0x1BC45+1]
    suffixes = []
    i = 0
    while i < len(suffix_data):
        end = suffix_data.find(b'\x00', i)
        if end == -1:
            break
        s = suffix_data[i:end].decode('latin-1', errors='replace')
        if s:
            suffixes.append(s)
        i = end + 1
    return suffixes

def decode_letter(b):
    if b < 26:
        return BYTE_TO_LETTER.get(b, '?')
    return None

def read_offsets(data):
    table_size = struct.unpack("<L", data[0:3] + b'\x00')[0]
    num_slots = table_size // 3
    offsets = []
    for i in range(num_slots):
        off = struct.unpack("<L", data[3 + i*3: 3 + (i+1)*3] + b'\x00')[0]
        offsets.append(off)
    return offsets, 3 + table_size

def decode_slot_detailed(body, suffix_table):
    parts = []
    cur_letters = []
    for b in body:
        if b >= 0x80:
            if cur_letters:
                parts.append(('letters', ''.join(cur_letters)))
                cur_letters = []
            suffix_idx = b - 0x80
            suffix = suffix_table[suffix_idx] if suffix_idx < len(suffix_table) else '???'
            parts.append(('instr', f'0x{b:02x}({suffix_idx}:{suffix})'))
        elif b < 26:
            cur_letters.append(BYTE_TO_LETTER.get(b, '?'))
        elif 32 <= b < 127:
            cur_letters.append(chr(b))
        else:
            if cur_letters:
                cur_letters.append(f'[{b:02x}]')
            else:
                cur_letters.append(f'[{b:02x}]')
    if cur_letters:
        parts.append(('letters', ''.join(cur_letters)))
    return parts

def Import(words, path, exe_path):
    data = open(path, "rb").read()
    suffixes = load_suffixes(exe_path)
    offsets, data_start = read_offsets(data)

    for si in range(1, len(offsets)):
        start = offsets[si]
        end = offsets[si+1] if si+1 < len(offsets) else len(data)
        if start >= end or start < data_start:
            continue
        if start + 2 > len(data) or data[start] != 0x00:
            continue
        body = data[start+2:end]
        parts = decode_slot_detailed(body, suffixes)
        # Extract just the letter groups
        letter_groups = [txt for typ, txt in parts if typ == 'letters']
        if letter_groups:
            words.append(' | '.join(letter_groups))

def Export(words, path):
    with open(path, "w", encoding="utf-8") as f:
        for word in words:
            f.write(word + '\n')

def diagnose(path, exe_path):
    data = open(path, "rb").read()
    suffixes = load_suffixes(exe_path)
    offsets, data_start = read_offsets(data)
    num_slots = len(offsets)

    print(f"File: {len(data)} B, offset table: {3+num_slots*3} B ({num_slots} slots)")
    print(f"Data region: byte {data_start}+ ({len(data)-data_start} B)")
    print(f"Suffixes: {len(suffixes)} from EXE")

    # Count non-empty slots
    non_empty = 0
    ctrl_last = 0
    for si in range(1, num_slots):
        start = offsets[si]
        end = offsets[si+1] if si+1 < num_slots else len(data)
        if start >= end or start < data_start:
            continue
        if start + 2 <= len(data) and data[start] == 0x00:
            non_empty += 1
            if len(data) > start+2:
                last_b = data[end-1] if end > start else 0
                if last_b >= 0x80:
                    ctrl_last += 1

    print(f"Non-empty slots: {non_empty}")
    print(f"Slots ending with instruction byte: {ctrl_last} / {non_empty}")

    # Verify: 'the' in slot data
    the_bytes = bytes([0x03, 0x04, 0x00])
    count_the = 0
    for si in range(1, num_slots):
        start = offsets[si]
        end = offsets[si+1] if si+1 < num_slots else len(data)
        if start >= end or start < data_start:
            continue
        body = data[start+2:end]
        if the_bytes in body:
            count_the += 1
    print(f"'the' (03 04 00) found in {count_the} slots")

    print("\n=== Sample slots ===")
    for si in [2, 100, 1431, 8007]:
        start = offsets[si]
        end = offsets[si+1] if si+1 < num_slots else len(data)
        if start >= end or start < data_start:
            continue
        body = data[start+2:end]
        parts = decode_slot_detailed(body, suffixes)
        print(f"\nSlot {si} ({len(body)} B):")
        for typ, txt in parts:
            print(f"  [{typ}] {txt}")

    # Show most common instruction bytes
    print("\n=== Top 20 instruction bytes ===")
    ctrl_count = Counter()
    for si in range(1, num_slots):
        start = offsets[si]
        end = offsets[si+1] if si+1 < num_slots else len(data)
        if start >= end or start < data_start:
            continue
        for b in data[start+2:end]:
            if b >= 0x80:
                ctrl_count[b] += 1
    for byte_val, cnt in ctrl_count.most_common(20):
        idx = byte_val - 0x80
        s = suffixes[idx] if idx < len(suffixes) else '?'
        print(f"  0x{byte_val:02x} (idx {idx:3d}): cnt={cnt:6d}  suffix='{s}'")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "..", "data", "MTU.ING")
    exe_path = os.path.join(script_dir, "..", "data", "MTU.EXE")
    output_dir = os.path.join(script_dir, "..", "output")

    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        diagnose(data_path, exe_path)
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    words = []
    Import(words, data_path, exe_path)
    Export(words, os.path.join(output_dir, "MTU.ING.TXT"))
    print(f"Exported {len(words)} entries to {output_dir}/MTU.ING.TXT")
    print("WARNING: Letter groups extracted, instruction semantics not applied.")

if __name__ == "__main__":
    main()
