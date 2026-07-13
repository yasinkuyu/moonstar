#! /usr/bin/python3
"""Deep probe: search for known English words in MTU.ING slot data."""
import os, struct

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

# Extract slot bodies (skip 2-byte header)
slot_bodies = {}
for i in range(1, num_slots):
    start = offsets[i]
    end = offsets[i+1] if i+1 < len(offsets) else len(data)
    if start >= end or start < data_start:
        continue
    slot_bodies[i] = data[start+2:end]

# Test: try to find known words by looking at byte patterns
# Hypothesis: each byte 0x00-0x19 = letter a-z
# So "a" = 00, "b" = 01, "the" = 13 07 04, "and" = 00 0d 03

def word_to_bytes(word, offset=0):
    """Convert word to bytes assuming a=0, b=1, ... z=25 with optional shift."""
    result = []
    for ch in word.lower():
        if 'a' <= ch <= 'z':
            result.append((ord(ch) - ord('a') + offset) % 26)
    return bytes(result)

# Test for "the" - should be 0x13 0x07 0x04 for a=0 mapping
test_words = ["the", "and", "for", "are", "not", "you", "all", "can", "had", "her",
              "was", "one", "our", "out", "has", "but", "two", "may", "its",
              "able", "tion", "ment", "ness", "less", "like", "ably", "ward"]

print("=== Searching for common English words in slot data ===")
print("Trying a=0, b=1, ..., z=25 alphabet:")
for word in test_words:
    pattern = word_to_bytes(word)
    count = 0
    for idx, body in slot_bodies.items():
        if pattern in body:
            count += 1
    print(f"  '{word}' → {pattern.hex()} → found in {count} slots")

# Try with offset/shift
print("\nTrying various Caesar shifts:")
for shift in range(26):
    total = 0
    for word in ["the", "and", "for", "are", "not", "but", "was", "all"]:
        pattern = word_to_bytes(word, shift)
        for body in slot_bodies.values():
            if pattern in body:
                total += 1
                break
    if total >= 3:
        print(f"  shift {shift}: {total}/8 words found")

# Try full word lookup: for each MTU.TRK word, try to find bytes in slot data
# Only check short words (3-5 letters) for first pass
print("\n=== Full word lookup: MTU.TRK short words in raw slot bytes ===")
short_words = [w for w in trk_words if 3 <= len(w) <= 5][:500]
found_words = []
for word in short_words:
    pattern = word_to_bytes(word)
    for body in slot_bodies.values():
        if pattern in body:
            found_words.append(word)
            break

print(f"Found {len(found_words)}/{len(short_words)} short words as raw bytes (a=0 mapping)")

# If that didn't work well, try each slot for known words
# Maybe the slot index encodes the first letter
print("\n=== Checking if slot maps to first letter ===")
# Slot 2 should contain 'a'-starting words (slot header [0x00, 0x03])
# Let's decode slot body trying different split schemes

def try_parse_entries(body):
    """Try to split body into entries assuming byte sequence structure."""
    results = []
    
    # Scheme: instruction byte, then letter bytes, then terminator 0xFC
    pos = 0
    while pos < len(body):
        # Read instruction byte
        if pos >= len(body):
            break
        instr = body[pos]
        pos += 1
        
        suffix_idx = None
        if instr >= 0x80:
            if pos < len(body):
                suffix_idx = body[pos]
                pos += 1
        
        # Collect letter bytes (0x00-0x19 = a-z range)
        letters = []
        while pos < len(body) and body[pos] != 0xFC and body[pos] != 0x00:
            if body[pos] < 26:
                letters.append(body[pos])
            pos += 1
        
        # Skip terminator if present
        if pos < len(body) and body[pos] in (0xFC, 0x00):
            pos += 1
        
        word = ''.join(chr(ord('a') + b) for b in letters)
        results.append((instr, suffix_idx, word))
    
    return results

for slot_idx in [2, 99, 100, 101]:
    body = slot_bodies.get(slot_idx, b'')
    if not body:
        continue
    entries = try_parse_entries(body)
    print(f"\nSlot {slot_idx}: {entries}")
