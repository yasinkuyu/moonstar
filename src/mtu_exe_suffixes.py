#! /usr/bin/python3

# mtu_exe_suffixes.py
#
# Extracts suffix list from MTU.EXE (offset 1B8B8h-1BC45h).
# These suffixes are used by MTU.TRK for word formation.

import os

def ExtractSuffixes(suffixes, path):
    data = open(path, "rb").read()
    
    # Suffix list offset: 1B8B8h - 1BC45h
    suffix_start = 0x1B8B8  # 112824
    suffix_end = 0x1BC45    # 113733
    
    if suffix_end > len(data):
        print(f"Warning: Suffix offset exceeds file size!")
        print(f"Required: {suffix_end}, Available: {len(data)}")
        return
    
    suffix_data = data[suffix_start:suffix_end]
    
    # Suffixes are null-terminated strings in CP 857
    current_suffix = b''
    for byte in suffix_data:
        if byte == 0:
            if current_suffix:
                try:
                    suffix = current_suffix.decode('cp857')
                    suffixes.append(suffix)
                except:
                    pass
                current_suffix = b''
        else:
            current_suffix += bytes([byte])
    
    # Add last suffix if not null-terminated
    if current_suffix:
        try:
            suffix = current_suffix.decode('cp857')
            suffixes.append(suffix)
        except:
            pass

def Export(suffixes, path):
    with open(path, "w", encoding="utf-8") as file:
        file.write("# MTU.EXE Suffix List\n")
        file.write("# Extracted from offset 1B8B8h-1BC45h\n")
        file.write("# " + "=" * 70 + "\n\n")
        
        # Group by length
        by_length = {}
        for suffix in suffixes:
            length = len(suffix)
            if length not in by_length:
                by_length[length] = []
            by_length[length].append(suffix)
        
        for length in sorted(by_length.keys(), reverse=True):
            file.write(f"\n# {length}-letter suffixes ({len(by_length[length])} items):\n")
            file.write("# " + ", ".join(f'"{s}"' for s in sorted(by_length[length])) + "\n")

def main():
    suffixes = []
    ExtractSuffixes(suffixes, os.path.join("..", "data", "MTU.EXE"))
    Export(suffixes, os.path.join("..", "output", "MTU.EXE.SUFFIXES.TXT"))
    print(f"Extracted {len(suffixes)} suffixes from MTU.EXE")
    print(f"Saved to output/MTU.EXE.SUFFIXES.TXT")

if __name__ == "__main__":
    main()

