#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""
mtu_soz.py
===========
Decoder and Substring Search Engine for MTU.SOZ (Turkish Place Names Spell-Checker Database).

Structure verified from MTU.EXE and Win16 memory dump analysis:
- File Size: 23,007 bytes
- Magic: MG2\x1a (4 bytes)
- Header: [2193, 14227, 6415, 6166]
  * header[0] = 2193: Byte offset of Stream 2 start
  * header[1] = 14227: Approx. boundary of alphabetic stream zone (actual: 14065)
  * header[2] = 6415: Stream 1 character metrics (6,409 alpha32 chars)
  * header[3] = 6166: Morphology/flags data parameter
- Stream 1 [12:2193]: Alphabet32 character stream with group delimiters (0x20, 0x2B)
- Stream 2 [2193:14065]: Alphabet32 character stream with group delimiters (0x20, 0x2B)
- Section 3 [14065:23007]: High-byte morphology and flag tables (8,942 bytes)

EXE Spell-Check Mechanism:
- The database stores place name streams inside contiguous group blocks.
- Matching is performed via substring search (e.g. "ankara in group", "marmara in group").
"""

import os
import struct

ALPHABET32 = 'abcçdefgğhıijklmnoöpqrsştuüvwxyz'

def decode_soz(path):
    """
    Decodes MTU.SOZ into structured group blocks and character streams.
    Returns:
        dict: {
            'header': list of 4 uint16 values,
            'stream1_text': str,
            'stream2_text': str,
            'groups': list of str (clean text blocks for substring matching),
            'total_alpha_chars': int
        }
    """
    with open(path, 'rb') as f:
        data = f.read()

    if len(data) < 12 or data[:4] != b'MG2\x1a':
        raise ValueError(f"Invalid magic number in {path}")

    header = [struct.unpack('<H', data[4 + i*2 : 6 + i*2])[0] for i in range(4)]
    stream2_offset = header[0]   # 2193
    alpha_zone_end = 14065       # Actual alphabetic boundary (~14227)

    # Stream 1: [12:stream2_offset]
    s1_data = data[12:stream2_offset]
    # Stream 2: [stream2_offset:alpha_zone_end]
    s2_data = data[stream2_offset:alpha_zone_end]

    def bytes_to_text(byte_seq):
        chars = []
        for b in byte_seq:
            if b < 32:
                chars.append(ALPHABET32[b])
            else:
                chars.append(' ')  # Separator (0x20, 0x2B)
        return ''.join(chars)

    s1_text = bytes_to_text(s1_data)
    s2_text = bytes_to_text(s2_data)

    full_alpha_text = bytes_to_text(data[12:alpha_zone_end])
    groups = [g for g in full_alpha_text.split(' ') if len(g) >= 2]

    return {
        'header': header,
        'stream1_text': s1_text,
        'stream2_text': s2_text,
        'groups': groups,
        'total_alpha_chars': sum(len(g) for g in groups)
    }

class SozPlaceSpellChecker:
    """
    Simulates the Win16 MTU.EXE spell-checker lookup on MTU.SOZ.
    """
    def __init__(self, soz_path):
        self.data = decode_soz(soz_path)
        self.groups = self.data['groups']
        # Map Turkish characters to normalized alphabet32
        self.tr_map = str.maketrans('ABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ', 'abcçdefgğhıijklmnoöpqrsştuüvwxyz')

    def check(self, word):
        """
        Returns True if the place name or compound occurs in the SOZ database.
        """
        w = word.strip().translate(self.tr_map).lower()
        if len(w) < 2:
            return False
        return any(w in group for group in self.groups)

    def search_prefixes(self, prefix):
        """
        Finds all groups containing the given prefix.
        """
        p = prefix.strip().translate(self.tr_map).lower()
        matches = []
        for g in self.groups:
            if p in g:
                matches.append(g)
        return matches

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    soz_path = os.path.join(base_dir, 'data', 'MTU.SOZ')
    out_path = os.path.join(base_dir, 'output', 'MTU.SOZ.TXT')

    if not os.path.exists(soz_path):
        print(f"File not found: {soz_path}")
        return

    print(f"Decoding {soz_path}...")
    decoded = decode_soz(soz_path)

    print(f"Header: {decoded['header']}")
    print(f"Total alphabet32 characters: {decoded['total_alpha_chars']}")
    print(f"Total group blocks: {len(decoded['groups'])}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("# MTU.SOZ Decoded Place Name Blocks (Moonstar Spell-Checker DB)\n")
        f.write(f"# Header: {decoded['header']}\n")
        f.write(f"# Total Groups: {len(decoded['groups'])}\n\n")
        for i, g in enumerate(decoded['groups']):
            f.write(f"--- GROUP {i+1} ({len(g)} chars) ---\n")
            f.write(g + "\n\n")

    print(f"Saved decoded SOZ blocks to {out_path}")

    # Test verification
    checker = SozPlaceSpellChecker(soz_path)
    test_words = ['marmara', 'ankara', 'karaağaç', 'boğazköy', 'edirne', 'derinkuyu', 'devrek', 'sancaklıboğazköy', 'istanbul']
    print("\nVerification Test:")
    for tw in test_words:
        res = checker.check(tw)
        print(f"  '{tw}': {'FOUND' if res else 'NOT FOUND'}")

if __name__ == '__main__':
    main()
