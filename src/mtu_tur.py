#! /usr/bin/python3

# mtu_tur.py
#
# Extracts data from MTU.TUR, which is required for Turkish-English dictionary,
# Türkçe Eş Anlamlılar dictionary and Türkçe Leb Demeden feature.
#
# MTU.TUR consists of seven parts:
#     1- Header (12 bytes)
#     2- 1st section (66 bytes)
#     3- 2nd section (2050 bytes)
#     4- 3rd section (45052 bytes)
#     5- 4th section (107100 bytes)
#     6- 5th section (62800 bytes)
#     7- 6th section (3640 bytes)

import os
import struct

# MTU.TUR encodes all text in its own custom alphabet, where 0x00 is 'a', 0x01
# is 'b' and so on.
alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

def GetSuffixLength(value):
    # 0x00-0x08: 0, 0x08-0x10: 1, 0x10-0x18: 2, (...), 0xb0-0xb8: 22
    if 0x00 <= value < 0xb8:
        return value // 8
    # 0xb8-0xd0: 3, 0xd0-0xe8: 4, 0xe8-0x100: 5
    elif 0xb8 <= value < 0x100:
        return 3 + ((value - 0xb8) // 0x18)
    else:
        return None

def GetSuffixReodered(suffix, value):
    if value >= 0xb8:
        value = (value - 0xb8) % 0x18
        if 0x00 <= value < 0x08:
            # 'abcd' -> 'dabc'
            suffix = suffix[-1] + suffix[:-1]
        elif 0x08 <= value < 0x10:
            # 'abcd' -> 'bcda'
            suffix = suffix[1:] + suffix[0]
        elif 0x10 <= value < 0x18:
            # 'abcd' -> 'dcba'
            suffix = suffix[::-1]

    return suffix

def GetSuffix(data, instructions, base_offset):
    suffix = ''
    suffix_length = GetSuffixLength(instructions[1])

    if suffix_length == 0:
        # TODO: What's the purpose of [2] and [3] here?
        pass
    # One/Two-letter suffixes are formed directly from our custom alphabet.
    elif 1 <= suffix_length <= 2:
        for i in range(0, suffix_length):
            suffix += alphabet[instructions[2 + i]]
    # For anything else, we need to read the suffix from the 5th section.
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
    Applies modifications to prefix and suffix based on Section 6 data.

    data[0] - Modifications:
    - 0x00: Normal (most common: 76%)
    - 0x0f: Capitalize first letter
    - 0x20: Contains â, î, û (circumflex check?)
    - 0x80: ğ -> k conversion
    - Others: Under analysis

    data[1] - Additional flags:
    - 0x00: Normal
    - 0x41: Capitalize first letter
    - 0x49: Capitalize first letter (for some suffixes)
    - 0x51: Capitalize first letter (special case)
    - 0x59: Capitalize first letter
    - Others: Under analysis

    data[2-3]: Additional modification parameters (under analysis)
    '''

    should_capitalize = False

    # Check capitalization flags
    if data[0] == 0x0f:
        should_capitalize = True
    elif data[1] in [0x41, 0x49, 0x51, 0x59]:
        should_capitalize = True
    elif data[0] == 0x2f and data[1] == 0x59:
        should_capitalize = True

    # Apply capitalization to prefix
    if should_capitalize and prefix:
        # Capitalize first letter, handling Turkish characters
        if len(prefix) > 0:
            first_char = prefix[0]
            # Handle Turkish lowercase characters
            turkish_lower = {'ı': 'I', 'i': 'İ', 'ğ': 'Ğ', 'ü': 'Ü',
                           'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
            if first_char in turkish_lower:
                prefix = turkish_lower[first_char] + prefix[1:]
            else:
                prefix = prefix[0].upper() + prefix[1:]

    # Apply ğ -> k conversion (if needed)
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
        for i in range(item_index, item_index + count):
            suffix = GetSuffix(data, section4[i], base_offset)

            section6_index = section4[i][0] # TODO: related to [1] too?
            prefix, suffix = ApplyModifications(section6[section6_index], prefix, suffix)

            # Combine prefix and suffix to form the complete word
            word = prefix + suffix

            dictionary.append(word)

        item_index += count

def Import(dictionary, path):
    data = open(path, "rb").read()
    pos = 0

    # Skip magic number ("0x4D 0x47 0x32 0x1A")
    pos += 4

    # Read header
    header = []
    for i in range(0, 4):
        length = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        header.append(length)

    # A combination of English and Turkish letters. See the first 32 letters
    # of the alphabet definition above.
    letter_count = 32

    # 1st section (?)
    # May be a lookup table for letters. The final value ("0x92 0x0C" = 3218)
    # corresponds to the number of items in the 3rd section.
    section1 = []
    for i in range(0, letter_count + 1):
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section1.append(value)

    # 2nd section
    # A lookup table for two-letter prefixes. Values correspond to an offset in
    # the 4th section. If an offset is the same as the next one, it means there
    # are no entries that begin with that prefix. With that in mind, we will
    # store the number of entries for each prefix rather than the offsets.
    section2 = []
    for i in range(0, letter_count**2 + 1):
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section2.append(value)
    prefixes = []
    for prefix_index in range(0, len(section2) - 1):
        prefix = alphabet[prefix_index // letter_count]
        prefix += alphabet[prefix_index % letter_count]
        count = section2[prefix_index + 1] - section2[prefix_index]
        prefixes.append((prefix, count))

    # 3rd section (?)
    # Disrupting this section causes entries in Turkish-English and Türkçe Eş
    # Anlamlılar dictionaries to lose their suffixes (e.g. "abayı yakmak" ->
    # "aba yak"). Doesn't seem to affect Leb Demeden.
    section3 = []
    for i in range(0, header[1]): # 3218
        pos += 1
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        section3.append(value)
        pos += 11

    # 4th section
    # Contains instructions to form the entries in Türkçe Leb Demeden feature.
    # The first byte points to an index at the 6th section.
    # The second byte defines the length of the suffix and how it's formed.
    # The last two bytes are either alphabet letters or an offset to a suffix
    # that can be found in the 5th section.
    section4 = []
    for i in range(0, header[0]): # 26775
        section4.append(data[pos:pos + 4])
        pos += 4

    # 5th section
    # This section contains plain-text suffixes, encoded in a custom alphabet.
    # We're skipping this section for now, but we'll read from it later on.
    base_offset = pos
    pos += header[2] # 62800

    # 6th section
    # Seems to be controlling capitalization and other modifications.
    section6 = []
    for i in range(0, header[3]): # 910
        section6.append(data[pos:pos + 4])
        pos += 4

    # We're now ready to read the entries
    ReadDictionaryEntries(dictionary, data, base_offset, prefixes, section4, section6)

def Export(dictionary, path):
    with open(path, "w", encoding="utf-8") as file:
        for entry in dictionary:
            file.write(entry)
            file.write('\n')

def ImportTurkishEnglishDictionary(dictionary, path):
    """
    Imports Turkish-English dictionary entries from Section 3.
    Section 1 provides index ranges for each starting letter in Section 3.
    Section 3 entries reference Section 4 to build Turkish words.

    The 11-byte block in Section 3 contains English translation data.
    Format appears to be: [flags] [length] [english_text_bytes...]
    """
    data = open(path, "rb").read()
    pos = 0

    # Skip magic number
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

    # Read Section 1 - provides index ranges for each letter
    section1_start = pos
    section1 = []
    for i in range(0, letter_count + 1):
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        section1.append(value)
        pos += 2

    # Skip Section 2
    pos += (letter_count**2 + 1) * 2

    # Read Section 3
    section3_start = pos
    section3 = []
    for i in range(0, header[1]):
        byte0 = data[pos]
        pos += 1
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        bytes3_13 = data[pos:pos + 11]
        pos += 11
        section3.append((byte0, value, bytes3_13))

    # Read Section 4
    section4_start = pos
    section4 = []
    for i in range(0, header[0]):
        section4.append(data[pos:pos + 4])
        pos += 4

    # Section 5 (suffixes)
    base_offset = pos
    pos += header[2]

    # Section 6 (modifications)
    section6 = []
    for i in range(0, header[3]):
        section6.append(data[pos:pos + 4])
        pos += 4

    # Build all Turkish words from Section 4 first
    turkish_words = {}  # Map section4_index to turkish_word
    section2_count = letter_count**2

    # Re-read Section 2 to get proper counts
    pos = section1_start + (letter_count + 1) * 2
    section2 = []
    for i in range(section2_count + 1):
        value = struct.unpack("<H", data[pos:pos + 2])[0]
        section2.append(value)
        pos += 2

    prefixes = []
    for prefix_index in range(len(section2) - 1):
        prefix = alphabet[prefix_index // letter_count]
        prefix += alphabet[prefix_index % letter_count]
        count = section2[prefix_index + 1] - section2[prefix_index]
        prefixes.append((prefix, count))

    # Build Turkish words from Section 4
    item_index = 0
    for prefix, count in prefixes:
        if count == 0:
            continue
        for i in range(item_index, item_index + count):
            if i >= len(section4):
                break
            try:
                suffix = GetSuffix(data, section4[i], base_offset)
                section6_idx = section4[i][0]
                if section6_idx < len(section6):
                    prefix_mod, suffix_mod = ApplyModifications(section6[section6_idx], prefix, suffix)
                    word = prefix_mod + suffix_mod
                else:
                    word = prefix + suffix
                turkish_words[i] = word
            except (IndexError, ValueError):
                pass
        item_index += count

    # Process Section 3 entries to build Turkish-English pairs
    for letter_idx in range(letter_count):
        letter = alphabet[letter_idx]
        start_idx = section1[letter_idx]
        end_idx = section1[letter_idx + 1]

        if start_idx >= end_idx:
            continue

        for i in range(start_idx, end_idx):
            if i >= len(section3):
                break

            byte0, value, bytes3_13 = section3[i]

            # Get Turkish word from Section 4 reference
            turkish_word = None
            if value < len(turkish_words):
                turkish_word = turkish_words.get(value)

            if not turkish_word:
                continue

            # Parse English translation from bytes3_13
            # Format appears to be: [length_byte] [text_bytes...] or similar
            english = ""

            # Try different formats for the 11-byte block
            # Format 1: First byte is length
            if byte0 > 0 and byte0 <= 11:
                try:
                    english_bytes = bytes3_13[:byte0]
                    # Try CP857 encoding
                    english = english_bytes.decode("cp857", errors="ignore").strip()
                    if not english:
                        # Try custom alphabet
                        english = ""
                        for b in english_bytes:
                            if b < len(alphabet):
                                english += alphabet[b]
                except:
                    pass

            # Format 2: bytes3_13 contains direct text
            if not english:
                try:
                    # Find null terminator
                    null_pos = bytes3_13.find(b'\x00')
                    if null_pos > 0:
                        english_bytes = bytes3_13[:null_pos]
                    else:
                        english_bytes = bytes3_13

                    # Skip leading zeros
                    while len(english_bytes) > 0 and english_bytes[0] == 0:
                        english_bytes = english_bytes[1:]

                    if len(english_bytes) > 0:
                        # Try CP857
                        english = english_bytes.decode("cp857", errors="ignore").strip()
                        if not english:
                            # Try latin-1
                            english = english_bytes.decode("latin-1", errors="ignore").strip()
                except:
                    pass

            if english and english not in ["", "#", "-", "—"]:
                # Replace separators
                english = english.replace('#', '; ')
                dictionary.append((turkish_word, english))

def main():
    # MTU.TUR has multiple uses:
    # 1. Turkish-English dictionary (Section 3) - now implemented
    # 2. Turkish Synonyms dictionary (Section 3) - needs more analysis
    # 3. Turkish Leb Demeden (Section 4) - current implementation

    # Export Leb Demeden entries (Section 4)
    dictionary_lebdemeden = []
    Import(dictionary_lebdemeden, os.path.join("..", "data", "MTU.TUR"))
    Export(dictionary_lebdemeden, os.path.join("..", "output", "MTU.TUR.TXT"))
    print("Exported", len(dictionary_lebdemeden), "Leb Demeden entries.")

    # Export Turkish-English dictionary from Section 3
    dictionary_tr_en = []
    ImportTurkishEnglishDictionary(dictionary_tr_en, os.path.join("..", "data", "MTU.TUR"))
    with open(os.path.join("..", "output", "MTU.TUR_TR_EN.TXT"), "w", encoding="utf-8") as file:
        for turkish, english in dictionary_tr_en:
            file.write(f"{turkish:<30} {english}\n")
    print("Exported", len(dictionary_tr_en), "Turkish-English dictionary entries.")

if __name__ == "__main__":
    main()
