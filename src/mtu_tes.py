#! /usr/bin/python3

# mtu_tes.py
#
# Extracts data from MTU.TES, which appears to be a prefix index map for MTU.TUR Section 3.
# This file contains offset values that point to locations in MTU.TUR Section 3.
#
# MTU.TES has the same structure as MTU.ING:
#     1- Base offset (3 bytes, first offset value)
#     2- Offset map for 2-letter prefixes (2028 bytes = 676 * 3)
#
# Important: Offset values >= 0xFF00 are sentinel values indicating "no entries for this prefix".
# @yasinkuyu

import os
import struct

def Import(prefix_map, path):
    """
    Reads MTU.TES and creates a prefix map for MTU.TUR Section 3.
    Returns a dictionary mapping prefix strings to offset values (or None for sentinel values).
    """
    data = open(path, "rb").read()

    # First 3 bytes are the base offset
    base_offset_bytes = data[0:3] + b'\x00'
    base_offset = struct.unpack("<L", base_offset_bytes)[0]

    # Offset table starts at byte 3
    offset_table_start = 3
    
    # Read offset map for 26*26 = 676 prefixes (aa-zz)
    for prefix_idx in range(0, 26 * 26):
        offset_bytes = data[offset_table_start + prefix_idx*3:offset_table_start + (prefix_idx+1)*3] + b'\x00'
        offset = struct.unpack("<L", offset_bytes)[0]
        
        # Calculate prefix string
        prefix = chr(ord('a') + prefix_idx // 26) + chr(ord('a') + prefix_idx % 26)
        
        # Check if this is a sentinel value (0xFF00+ means "no entries")
        if offset >= 0xFF00:
            prefix_map[prefix] = None  # Sentinel - no entries for this prefix
        else:
            prefix_map[prefix] = offset  # Valid offset to MTU.TUR Section 3

def Export(prefix_map, path):
    """Exports the prefix map to a text file for analysis."""
    with open(path, "w", encoding="utf-8") as file:
        file.write("# MTU.TES Prefix Map\n")
        file.write("# Format: prefix | offset (None = sentinel, no entries)\n")
        file.write("# " + "=" * 70 + "\n\n")
        
        for prefix in sorted(prefix_map.keys()):
            offset = prefix_map[prefix]
            if offset is None:
                file.write(f"{prefix:4s} | SENTINEL (no entries)\n")
            else:
                file.write(f"{prefix:4s} | 0x{offset:04x} ({offset})\n")

def main():
    prefix_map = {}
    Import(prefix_map, os.path.join("..", "data", "MTU.TES"))
    Export(prefix_map, os.path.join("..", "output", "MTU.TES.TXT"))
    
    valid_count = sum(1 for v in prefix_map.values() if v is not None)
    sentinel_count = sum(1 for v in prefix_map.values() if v is None)
    
    print(f"Exported prefix map: {valid_count} valid offsets, {sentinel_count} sentinel values.")
    print(f"Use this prefix map with MTU.TUR Section 3 to extract Turkish-English dictionary.")

if __name__ == "__main__":
    main()
