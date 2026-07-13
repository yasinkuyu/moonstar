#! /usr/bin/python3
"""
Deep dive: frequency-order alphabet, cross-reference with MTU.TRK.

Find the correct letter -> byte mapping by cross-referencing known words
with slot data.
"""
import os, struct
from collections import Counter

script_dir = os.path.dirname(os.path.abspath(__file__))
data = open(os.path.join(script_dir, "..", "data", "MTU.ING"), "rb").read()
trk_words = open(os.path.join(script_dir, "..", "output", "MTU.TRK.TXT")).read().splitlines()

table_size = struct.unpack("<L", data[0:3] + b'\x00')[0]
num_slots = table_size // 3

offsets = []
for i in range(num_slots):
    off = struct.unpack("<L", data[3 + i*3: 3 + (i+1)*3] + b'\x00')[0]
    offsets.append(off)
data_start = 3 + table_size

# Collect slot bodies (skip 2-byte header)
slot_bodies = {}
for i in range(1, num_slots):
    start = offsets[i]
    end = offsets[i+1] if i+1 < len(offsets) else len(data)
    if start >= end or start < data_start:
        continue
    slot_bodies[i] = data[start+2:end]

# Build byte frequency in slot bodies
freq = Counter()
for body in slot_bodies.values():
    freq.update(body)

# English letter frequency
eng_freq = "etaoinshrdlcumwfgypbvkjxqz"
eng_order = {ch: i for i, ch in enumerate(eng_freq)}

# Sort custom alphabet bytes by frequency (descending)
# Only consider bytes 0x00-0x19 (traditional a-z range)
custom_bytes = sorted([b for b in range(26)], key=lambda b: freq.get(b, 0), reverse=True)
print("Custom alphabet bytes sorted by frequency:")
print(f"  Bytes: {' '.join(f'{b:02x}' for b in custom_bytes)}")
print(f"  Freqs: {' '.join(f'{freq.get(b,0):5d}' for b in custom_bytes)}")
print(f"  Mapped: {''.join(eng_freq[i] if i < 26 else '?' for i in range(26))}")

# Build byte-to-letter mapping based on frequency
byte_to_letter = {}
for i, b in enumerate(custom_bytes):
    if i < 26:
        byte_to_letter[b] = eng_freq[i]
# Remaining custom range bytes (0x1a-0x1f) - use standard mapping
for b in range(26, 32):
    if b not in byte_to_letter:
        byte_to_letter[b] = chr(ord('a') + b) if b < 26 else '?'

# Verify mapping: check known 3-letter words
print("\n=== Verify: find known words with frequency-based mapping ===")
for word in ["the", "and", "for", "are", "not", "can", "her", "was", "but", "all"]:
    pattern_bytes = []
    for ch in word:
        for b in range(26):
            if byte_to_letter.get(b, '') == ch:
                pattern_bytes.append(b)
                break
    if len(pattern_bytes) >= 3:
        pattern = bytes(pattern_bytes[:3])
        count = sum(1 for body in slot_bodies.values() if pattern in body)
        print(f"  '{word}' → {pattern.hex()} → {count} slots")

# Most importantly: check what bytes appear MOST OFTEN at position 0 of each entry
# This tells us what "first letter" byte is used

# Try extracting words by filtering: custom alphabet bytes are letters, >=0x80 are control
print("\n=== Entry extraction: filter control bytes, then decode ===")
# For each slot, try: entries separated by 0xFC terminator
# Each entry: skip leading >=0x80 control bytes, then letters are 0x00-0x19

for slot_idx in [2, 3, 4, 99, 100, 101]:
    body = slot_bodies.get(slot_idx, b'')
    if not body:
        continue
    # Split by 0xFC
    parts = body.split(b'\xfc')
    
    decoded_words = []
    for part in parts:
        if not part:
            continue
        # Skip control bytes (>= 0x80 or 0x00 at start as instruction)
        letters = []
        i = 0
        while i < len(part):
            b = part[i]
            if b < 26:
                # Custom alphabet letter
                letters.append(chr(ord('a') + b))
                i += 1
            elif b >= 0x80:
                # Control byte - skip it and possible suffix index
                i += 1
                if i < len(part) and b >= 0x80 and part[i] >= 0x80:
                    i += 1  # Skip potential second control byte
            elif 32 <= b < 127:
                # ASCII letter
                letters.append(chr(b))
                i += 1
            else:
                i += 1  # Skip unknown byte
        
        word = ''.join(letters)
        if word and len(word) >= 2:
            decoded_words.append(word)
    
    print(f"\nSlot {slot_idx} ({' '.join(f'{b:02x}' for b in body[:40])}...):")
    for w in decoded_words:
        print(f"  -> {w}")

# Cross-reference: print all unique decoded words and compare with MTU.TRK
print("\n=== Cross-reference with MTU.TRK ===")
trk_set = set(trk_words)
all_decoded = []
for slot_idx, body in slot_bodies.items():
    parts = body.split(b'\xfc')
    for part in parts:
        if not part:
            continue
        letters = []
        i = 0
        while i < len(part):
            b = part[i]
            if b < 26:
                letters.append(chr(ord('a') + b))
                i += 1
            elif 32 <= b < 127:
                letters.append(chr(b))
                i += 1
            else:
                i += 1
        word = ''.join(letters)
        if word and len(word) >= 2:
            all_decoded.append(word)

decoded_set = set(all_decoded)
matched = decoded_set & trk_set
print(f"Decoded unique words (a=0, filter ctrl): {len(decoded_set)}")
print(f"Match with MTU.TRK: {len(matched)}")
if matched:
    for w in sorted(matched)[:20]:
        print(f"  ✓ {w}")
