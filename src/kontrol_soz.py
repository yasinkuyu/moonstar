#! /usr/bin/python3

# kontrol_soz.py
#
# Extracts data from KONTROL.SOZ, which appears to be a small control/configuration file.
#
# KONTROL.SOZ has the same magic number as MTU.TUR/MTU.SOZ but is very small (12 bytes).
# @yasinkuyu

import os
import struct

def Import(data_dict, path):
    data = open(path, "rb").read()
    
    data_dict['size'] = len(data)
    data_dict['magic'] = data[0:4].hex()
    
    if data[0:4] == b'MG2\x1a':
        data_dict['magic_text'] = 'MG2\\x1a'
        pos = 4
        
        # Read header (similar to MTU.TUR but smaller)
        if len(data) >= 12:
            header = []
            for i in range(0, 4):
                if pos + 2 <= len(data):
                    value = struct.unpack("<H", data[pos:pos + 2])[0]
                    header.append(value)
                    pos += 2
            data_dict['header'] = header
            data_dict['remaining'] = data[pos:].hex()
    else:
        data_dict['magic_text'] = 'Unknown'
        data_dict['raw'] = data.hex()

def Export(data_dict, path):
    with open(path, "w", encoding="utf-8") as file:
        file.write("# KONTROL.SOZ Analysis\n")
        file.write("# " + "=" * 70 + "\n\n")
        file.write(f"File size: {data_dict['size']} bytes\n")
        file.write(f"Magic number: {data_dict['magic']} ({data_dict.get('magic_text', 'Unknown')})\n\n")
        
        if 'header' in data_dict:
            file.write("Header (4 x 16-bit values):\n")
            for i, val in enumerate(data_dict['header']):
                file.write(f"  [{i}]: {val} (0x{val:04x})\n")
            file.write("\n")
        
        if 'remaining' in data_dict:
            file.write(f"Remaining data: {data_dict['remaining']}\n")

def main():
    data_dict = {}
    Import(data_dict, os.path.join("..", "data", "KONTROL.SOZ"))
    Export(data_dict, os.path.join("..", "output", "KONTROL.SOZ.TXT"))
    print("Exported KONTROL.SOZ analysis.")
    print(f"File size: {data_dict['size']} bytes")
    print(f"Magic: {data_dict.get('magic_text', 'Unknown')}")

if __name__ == "__main__":
    main()

