#! /usr/bin/python3
"""Analyze MTU.ING slot data to figure out the entry format."""
import os, struct
from collections import Counter

script_dir = os.path.dirname(os.path.abspath(__file__))
data = open(os.path.join(script_dir, "..", "data", "MTU.ING"), "rb").read()

table_size = struct.unpack("<L", data[0:3] + b'\x00')[0]
num_slots = table_size // 3  # 32000

offsets = []
for i in range(num_slots):
    off = struct.unpack("<L", data[3 + i*3: 3 + (i+1)*3] + b'\x00')[0]
    offsets.append(off)

data_start = 3 + table_size

# Analyze a few slots in detail
for slot_idx in [2, 3, 4, 99, 100, 101]:
    start = offsets[slot_idx]
    end = offsets[slot_idx + 1] if slot_idx + 1 < len(offsets) else len(data)
    if start >= end or start < data_start:
        continue
    
    chunk = data[start:min(end, start + 200)]
    hdr = chunk[0:2]
    body = chunk[2:]
    
    print(f"\n=== Slot {slot_idx} (offset={start}, size={end-start}) ===")
    print(f"Header: [{hdr[0]:02x}, {hdr[1]:02x}]")
    print(f"Body ({len(body)} B): {' '.join(f'{b:02x}' for b in body[:80])}")
    
    # Try: bytes 0x00-0x19 = a-z, mask lower 5 bits
    txt5 = ''
    for b in body[:80]:
        if b < 26:
            txt5 += chr(ord('a') + b)
        elif 0x80 <= b < 0xC0:
            txt5 += f'[{b-0x80:02x}]'
        elif 0xC0 <= b < 0x100:
            txt5 += f'<{b:02x}>'
        else:
            txt5 += chr(b) if 32 <= b < 127 else '.'
    print(f"a-z decode: {txt5}")
    
    # Try: bytes 0x00-0x1F = a-z + special chars
    txt6 = ''
    alpha32 = "abcdefghijklmnopqrstuvwxyz"
    for b in body[:80]:
        if b < 26:
            txt6 += alpha32[b]
        elif b == 0xFF:
            txt6 += '|'
        elif b == 0x00:
            txt6 += '_'
        elif b == 0xFC:
            txt6 += ';'
        else:
            txt6 += f'.'
    print(f"26-alpha:  {txt6}")

# Byte distribution WITHIN slot data only (skip headers)
slot_data_bytes = Counter()
for slot_idx in range(1, num_slots):
    start = offsets[slot_idx]
    end = offsets[slot_idx + 1] if slot_idx + 1 < len(offsets) else len(data)
    if start >= end or start < data_start:
        continue
    for b in data[start+2:end]:  # skip 2-byte header
        slot_data_bytes[b] += 1

print("\n=== Byte distribution in slot data (excl. headers) ===")
for b in range(256):
    c = slot_data_bytes.get(b, 0)
    if c > 500:
        pfx = 'LETTER' if b < 26 else f'CTL_{b:02x}' if b >= 0x80 else f'MID_{b:02x}'
        print(f"  {pfx}: 0x{b:02x} ({b:3d}) = {c:6d}")

# Look for common patterns: what follows 0x81, 0x84, 0x85, etc?
print("\n=== What follows common bytes? ===")
for probe in [0x00, 0x81, 0x84, 0x85, 0x87, 0x8a, 0xfc]:
    followers = Counter()
    for slot_idx in range(1, num_slots):
        start = offsets[slot_idx]
        end = offsets[slot_idx + 1] if slot_idx + 1 < len(offsets) else len(data)
        if start >= end or start < data_start:
            continue
        blob = data[start+2:end]
        for i, b in enumerate(blob):
            if b == probe and i + 1 < len(blob):
                followers[blob[i+1]] += 1
    top = followers.most_common(10)
    print(f"\nAfter 0x{probe:02x}: {top}")

# Check what bytes precede letter-like values (0x00-0x19)
print("\n=== What precedes letters (0x00-0x19)? ===")
preceding = Counter()
for slot_idx in range(1, num_slots):
    start = offsets[slot_idx]
    end = offsets[slot_idx + 1] if slot_idx + 1 < len(offsets) else len(data)
    if start >= end or start < data_start:
        continue
    blob = data[start+2:end]
    for i, b in enumerate(blob):
        if b < 26 and i > 0:
            preceding[blob[i-1]] += 1
for b, c in preceding.most_common(15):
    print(f"  0x{b:02x}: {c}")
