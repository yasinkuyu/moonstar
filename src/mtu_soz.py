#! /usr/bin/python3

# mtu_soz.py
#
# Extracts data from MTU.SOZ, which uses the same format as MTU.TUR.
# This file appears to be for Turkish synonyms (Eş Anlamlılar) dictionary.
#
# MTU.SOZ has the same structure as MTU.TUR:
#     1- Magic number ("MG2\x1A")
#     2- Header (12 bytes)
#     3- Section 1 (66 bytes)
#     4- Section 2 (2050 bytes)
#     5- Section 3 (variable)
#     6- Section 4 (variable)
#     7- Section 5 (variable)
#     8- Section 6 (variable)
# @yasinkuyu

import os
import struct

# MTU.SOZ uses the same custom alphabet as MTU.TUR
alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

def GetSuffixLength(value):
    # Same as MTU.TUR
    if 0x00 <= value < 0xb8:
        return value // 8
    elif 0xb8 <= value < 0x100:
        return 3 + ((value - 0xb8) // 0x18)
    else:
        return None

def GetSuffixReodered(suffix, value):
    if value >= 0xb8:
        value = (value - 0xb8) % 0x18
        if 0x00 <= value < 0x08:
            suffix = suffix[-1] + suffix[:-1]
        elif 0x08 <= value < 0x10:
            suffix = suffix[1:] + suffix[0]
        elif 0x10 <= value < 0x18:
            suffix = suffix[::-1]
    return suffix

def GetSuffix(data, instructions, base_offset):
    suffix = ''
    suffix_length = GetSuffixLength(instructions[1])

    if suffix_length == 0:
        pass
    elif 1 <= suffix_length <= 2:
        for i in range(0, suffix_length):
            suffix += alphabet[instructions[2 + i]]
    else:
        offset = struct.unpack("<H", instructions[2:4])[0]
        pos = base_offset + offset
        for i in range(0, suffix_length):
            index = data[pos + i]
            suffix += alphabet[index]

    suffix = GetSuffixReodered(suffix, instructions[1])
    return suffix

def ApplyModifications(data, prefix, suffix):
    '''
    Applies modifications similar to MTU.TUR
    '''
    should_capitalize = False
    
    if data[0] == 0x0f:
        should_capitalize = True
    elif data[1] in [0x41, 0x49, 0x51, 0x59]:
        should_capitalize = True
    elif data[0] == 0x2f and data[1] == 0x59:
        should_capitalize = True
    
    if should_capitalize and prefix:
        if len(prefix) > 0:
            first_char = prefix[0]
            turkish_lower = {'ı': 'I', 'i': 'İ', 'ğ': 'Ğ', 'ü': 'Ü', 
                           'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
            if first_char in turkish_lower:
                prefix = turkish_lower[first_char] + prefix[1:]
            else:
                prefix = prefix[0].upper() + prefix[1:]
    
    if data[0] == 0x80:
        if suffix and suffix.endswith('ğ'):
            suffix = suffix[:-1] + 'k'
        elif prefix and prefix.endswith('ğ'):
            prefix = prefix[:-1] + 'k'
    
    return prefix, suffix

def ReadDictionaryEntries(dictionary, data, base_offset, prefixes, section4, section6):
    item_index = 0
    for prefix, count in prefixes:
        if count == 0:
            continue
        end_index = min(item_index + count, len(section4))
        for i in range(item_index, end_index):
            if i >= len(section4):
                break
            try:
                suffix = GetSuffix(data, section4[i], base_offset)
                section6_index = section4[i][0]
                if section6_index < len(section6):
                    prefix_mod, suffix_mod = ApplyModifications(section6[section6_index], prefix, suffix)
                    word = prefix_mod + suffix_mod
                    dictionary.append(word)
                else:
                    # Fallback if section6 index is out of range
                    word = prefix + suffix
                    dictionary.append(word)
            except (IndexError, ValueError) as e:
                # Skip invalid entries
                continue
        item_index = end_index

def Import(dictionary, path):
    data = open(path, "rb").read()
    pos = 0

    # Skip magic number ("0x4D 0x47 0x32 0x1A")
    if data[pos:pos+4] != b'MG2\x1a':
        raise ValueError("Invalid magic number")
    pos += 4

    # Read header
    header = []
    for i in range(0, 4):
        length = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        header.append(length)

    letter_count = 32

    # Section 1
    section1 = []
    for i in range(0, letter_count + 1):
        if pos + 2 > len(data):
            break
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section1.append(value)

    # Section 2
    section2 = []
    for i in range(0, letter_count**2 + 1):
        if pos + 2 > len(data):
            break
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section2.append(value)
    prefixes = []
    for prefix_index in range(0, len(section2) - 1):
        prefix = alphabet[prefix_index // letter_count]
        prefix += alphabet[prefix_index % letter_count]
        count = section2[prefix_index + 1] - section2[prefix_index]
        prefixes.append((prefix, count))

    # Section 3
    # Format: [byte0] [bytes1-2: Section4 ref] [bytes3-13: MTU.ING offset (11 bytes)]
    section3 = []
    for i in range(0, header[1]):
        if pos + 14 > len(data):
            break
        byte0 = data[pos]
        pos += 1
        section4_ref = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        bytes3_13 = data[pos:pos + 11]  # Save the 11-byte block that may contain MTU.ING offset
        pos += 11
        section3.append((byte0, section4_ref, bytes3_13))

    # Section 4
    section4 = []
    for i in range(0, header[0]):
        if pos + 4 > len(data):
            break
        section4.append(data[pos:pos + 4])
        pos += 4

    # Section 5
    base_offset = pos
    if pos + header[2] > len(data):
        print(f"Warning: Section 5 exceeds file size")
    pos = min(pos + header[2], len(data))

    # Section 6
    section6 = []
    for i in range(0, header[3]):
        if pos + 4 > len(data):
            break
        section6.append(data[pos:pos + 4])
        pos += 4

    # Read entries
    ReadDictionaryEntries(dictionary, data, base_offset, prefixes, section4, section6)

def Export(dictionary, path):
    with open(path, "w", encoding="utf-8") as file:
        for entry in dictionary:
            file.write(entry)
            file.write('\n')

def ExtractTurkishEnglishPairs(section3, section4, section6, data, base_offset, prefixes, ing_data):
    """
    Extract Turkish-English pairs by connecting:
    1. Section 4 (Turkish words) via Section 3's section4_ref
    2. MTU.ING (English translations) via Section 3's 11-byte block
    
    Returns list of (turkish_word, english_text) tuples.
    """
    # First, build all Turkish words from Section 4
    turkish_words = []
    item_index = 0
    for prefix, count in prefixes:
        if count == 0:
            item_index += count
            continue
        end_index = min(item_index + count, len(section4))
        for i in range(item_index, end_index):
            if i >= len(section4):
                break
            try:
                suffix = GetSuffix(data, section4[i], base_offset)
                section6_index = section4[i][0]
                if section6_index < len(section6):
                    prefix_mod, suffix_mod = ApplyModifications(section6[section6_index], prefix, suffix)
                    word = prefix_mod + suffix_mod
                else:
                    word = prefix + suffix
                turkish_words.append((i, word))  # Store (section4_index, word)
            except (IndexError, ValueError):
                turkish_words.append((i, None))  # Invalid entry
        item_index = end_index
    
    # Now build Turkish-English pairs from Section 3
    results = []
    
    for byte0, section4_ref, bytes3_13 in section3:
        # Extract MTU.ING offset from first 3 bytes (middle-endian, like MTU.TRK)
        ing_offset = bytes3_13[1] | (bytes3_13[2] << 8) | (bytes3_13[0] << 16)
        
        # Find Turkish word using section4_ref
        turkish_word = None
        if section4_ref < len(turkish_words):
            _, word = turkish_words[section4_ref]
            if word:
                turkish_word = word
        
        # Extract English translation from MTU.ING using length-prefix format (like MTU.TRK Turkish definitions)
        english_text = None
        if ing_offset > 0 and ing_offset < len(ing_data):
            if ing_offset < len(ing_data) - 2:
                try:
                    ing_len = struct.unpack('<H', ing_data[ing_offset:ing_offset+2])[0]
                    if 0 < ing_len < 500:  # Reasonable length limit
                        ing_pos = ing_offset + 2
                        if ing_pos + ing_len <= len(ing_data):
                            english_text = ing_data[ing_pos:ing_pos+ing_len].decode('cp857', errors='ignore')
                except:
                    pass
        
        # Only add if we have both Turkish and English
        if turkish_word and english_text:
            results.append((turkish_word, english_text))
    
    return results

def main():
    try:
        # Read MTU.SOZ and MTU.ING files
        with open(os.path.join("..", "data", "MTU.SOZ"), "rb") as f:
            soz_data = f.read()
        with open(os.path.join("..", "data", "MTU.ING"), "rb") as f:
            ing_data = f.read()
        
        if soz_data[:4] != b'MG2\x1a':
            raise ValueError("Invalid MTU.SOZ magic number")
        
        pos = 4
        
        # Read header
        header = []
        for i in range(4):
            val = struct.unpack('<H', soz_data[pos:pos+2])[0]
            header.append(val)
            pos += 2
        
        letter_count = 32
        
        # Section 1
        section1 = []
        for i in range(letter_count + 1):
            if pos + 2 > len(soz_data):
                break
            val = struct.unpack('<H', soz_data[pos:pos+2])[0]
            pos += 2
            section1.append(val)
        
        # Section 2
        section2 = []
        for i in range(letter_count**2 + 1):
            if pos + 2 > len(soz_data):
                break
            val = struct.unpack('<H', soz_data[pos:pos+2])[0]
            pos += 2
            section2.append(val)
        
        prefixes = []
        for prefix_index in range(len(section2) - 1):
            prefix_char1 = alphabet[prefix_index // letter_count]
            prefix_char2 = alphabet[prefix_index % letter_count]
            prefix = prefix_char1 + prefix_char2
            count = section2[prefix_index + 1] - section2[prefix_index]
            prefixes.append((prefix, count))
        
        # Section 3 - Read entries until end of file or section
        # Note: Header says 14227 entries, but file size is only 23007 bytes
        # So we read as many entries as fit in the file
        section3 = []
        section3_end = len(soz_data)  # Limit to file size
        while pos + 14 <= section3_end:
            byte0 = soz_data[pos]
            pos += 1
            section4_ref = struct.unpack('<H', soz_data[pos:pos+2])[0]
            pos += 2
            bytes3_13 = soz_data[pos:pos+11]
            pos += 11
            section3.append((byte0, section4_ref, bytes3_13))
        
        # Section 4 - Read as many as fit
        section4 = []
        while pos + 4 <= len(soz_data):
            section4.append(soz_data[pos:pos+4])
            pos += 4
            # Stop if we've read header[0] entries or reached end
            if len(section4) >= header[0]:
                break
        
        # Section 5 - Read up to header[2] bytes or end of file
        base_offset = pos
        section5_size = min(header[2], len(soz_data) - pos)
        pos += section5_size
        
        # Section 6 - Read as many as fit
        section6 = []
        while pos + 4 <= len(soz_data):
            section6.append(soz_data[pos:pos+4])
            pos += 4
            # Stop if we've read header[3] entries or reached end
            if len(section6) >= header[3]:
                break
        
        print(f"Parsed MTU.SOZ:")
        print(f"  Section 3 entries: {len(section3)}")
        print(f"  Section 4 entries: {len(section4)}")
        print(f"  Section 6 entries: {len(section6)}")
        print(f"  Prefixes: {len(prefixes)}")
        
        # Extract Turkish-English pairs
        pairs = ExtractTurkishEnglishPairs(section3, section4, section6, soz_data, base_offset, prefixes, ing_data)
        
        print(f"\nExtracted {len(pairs)} Turkish-English pairs")
        
        # Export Turkish-English dictionary
        with open(os.path.join("..", "output", "MTU.SOZ.TXT"), "w", encoding="utf-8") as f:
            for turkish_word, english_text in pairs:
                f.write(f"{turkish_word:<30} {english_text}\n")
        
        print(f"Exported to MTU.SOZ.TXT")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

