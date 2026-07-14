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
import sys

# MTU.TUR encodes all text in its own custom alphabet, where 0x00 is 'a', 0x01
# is 'b' and so on.
alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

# EXE lookup tables for Section 3 decoding (MTU.EXE file offsets)
# table_A: EXE 0x1B388 (DGROUP+0x1588) — extra index for double-lookup
# table_B: EXE 0x1A7CA (DGROUP+0x09CA) — main character lookup (CP857)
def LoadExeTables():
    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "MTU.EXE")
    with open(exe_path, "rb") as f:
        exe = f.read()
    table_A = list(exe[0x1B388:0x1B388+256])
    table_B = list(exe[0x1A7CA:0x1A7CA+256])
    return table_A, table_B

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

# Cached EXE tables (loaded once)
_EXE_TABLES = None

def GetExeTables():
    global _EXE_TABLES
    if _EXE_TABLES is None:
        _EXE_TABLES = LoadExeTables()
    return _EXE_TABLES

def DecodeSection3Entry(byte0, val, bytes11, section4_data, base_offset):
    """
    Decodes a Section 3 entry using the EXE's actual algorithm (seg3).
    
    === byte0 Control Field ===
    bits 0-6: count (bytes to decode, 0-127)
    bit 7:    double_lookup (last byte uses table_A -> table_B)
    
    === Data Source ===
    count < 3: 11-byte block itself (bytes11[:count])
    count >= 3: Section 4 suffix data at offset val
    
    === Character Decode ===
    for each byte b:
        if double_lookup and b is last_byte:
            ch = table_B[table_A[b]]
        else:
            ch = table_B[b]
    Output: CP857 bytes
    
    Tables in EXE:
      table_A @ file 0x1B388 (DGROUP+0x1588)
      table_B @ file 0x1A7CA (DGROUP+0x09CA)
    """
    table_A, table_B = GetExeTables()
    
    count = byte0 & 0x7F
    use_double = bool(byte0 & 0x80)
    
    if count == 0:
        return ''
    
    if count < 3:
        src = bytes11[:count]
    else:
        # Data from Section 4 (suffix instruction data) at offset val
        # val is an offset into section4 byte array
        src = section4_data[val:val+count] if val < len(section4_data) else b''
    
    if not src:
        return ''
    
    result = []
    for i, b in enumerate(src):
        if use_double and i == len(src) - 1:
            idx = table_A[b]
            ch = table_B[idx]
        else:
            ch = table_B[b]
        result.append(ch)
    
    try:
        return bytes(result).decode('cp857', errors='replace').strip()
    except:
        return ''

def ImportTurkishEnglishFromTRK(dictionary, trk_path, synonyms_dict=None):
    """
    Build Türkçe→İngilizce dictionary by reversing the TRK (İngilizce→Türkçe) file.

    MTU.TUR Section 3 is a SUFFIX STRIPPING TABLE for Leb Demeden (NOT TR_EN data):
      - Each entry = [byte0: count][val: Section5 offset][bytes11: morphological class]
      - Section5[val:val+count] = Turkish suffix string (e.g. 'acak', 'mak', 'ımdan')
      - Section1 = fast lookup index by first letter of suffix
      - bytes11[2] = grammatical class code (3=aorist, 5=future/ability stems, etc.)
      - DecodeSection3Entry() using table_A/table_B produces garbled output because
        Section3 stores suffix morphology instructions, NOT English character data.

    Correct TR_EN source: reverse the TRK file (İngilizce→Türkçe pairs).
    Each Turkish definition in TRK maps back to its English headword.

    For synonyms (ES_ANLAM): Turkish words sharing the same English translation
    are considered synonyms of each other.

    Coverage: ~25% of TUR words have a direct TR_EN match via TRK.
    Remaining 75% are proper nouns, compounds, or forms not in TRK.
    """
    if not os.path.exists(trk_path):
        return

    tr_to_en = {}   # turkish_meaning → [english_headword, ...]
    en_to_tr = {}   # english → set of turkish meanings (for synonyms)

    with open(trk_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            english, meanings = parts[0], parts[1]
            en_to_tr[english] = set()
            for meaning in meanings.split('|'):
                meaning = meaning.strip().lstrip('#').strip()
                if not meaning:
                    continue
                en_to_tr[english].add(meaning)
                if meaning not in tr_to_en:
                    tr_to_en[meaning] = []
                if english not in tr_to_en[meaning]:
                    tr_to_en[meaning].append(english)

    if synonyms_dict is not None:
        # ES_ANLAM: Turkish words sharing the same English headword are synonyms
        seen = set()
        for english, tr_words in en_to_tr.items():
            if len(tr_words) < 2:
                continue
            sorted_words = sorted(tr_words)
            key = '|'.join(sorted_words)
            if key in seen:
                continue
            seen.add(key)
            for i, tw in enumerate(sorted_words):
                others = [w for j, w in enumerate(sorted_words) if j != i]
                if tw not in synonyms_dict:
                    synonyms_dict[tw] = {'synonyms': others, 'via': english}
                else:
                    synonyms_dict[tw]['synonyms'] = list(
                        set(synonyms_dict[tw]['synonyms']) | set(others))
    else:
        # TR_EN: sorted by Turkish word
        for turkish, english_list in sorted(tr_to_en.items()):
            dictionary.append((turkish, ', '.join(english_list)))


def GetDataPath(filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, '..', 'data', filename)

def GetOutputPath(filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, '..', 'output', filename)

def main():
    data_path = GetDataPath('MTU.TUR')
    trk_path  = GetOutputPath('MTU.TRK.TXT')

    # 1) Export Leb Demeden entries (Turkish word list from Section 4)
    dictionary_lebdemeden = []
    Import(dictionary_lebdemeden, data_path)
    Export(dictionary_lebdemeden, GetOutputPath('MTU.TUR.TXT'))
    print(f'Exported {len(dictionary_lebdemeden)} Leb Demeden (Türkçe) entries.')

    if not os.path.exists(trk_path):
        print('MTU.TRK.TXT not found — run mtu_trk.py first to generate TR_EN/ES_ANLAM.')
        return

    # 2) Export TR_EN: Türkçe → İngilizce (from TRK reverse lookup)
    dictionary_tr_en = []
    ImportTurkishEnglishFromTRK(dictionary_tr_en, trk_path)
    with open(GetOutputPath('MTU.TUR_TR_EN.TXT'), 'w', encoding='utf-8') as f:
        for turkish, english in dictionary_tr_en:
            f.write(f'{turkish:<30} {english}\n')
    print(f'Exported {len(dictionary_tr_en)} Türkçe→İngilizce entries.')

    # 3) Export ES_ANLAM: Turkish synonym groups (from TRK)
    synonyms = {}
    ImportTurkishEnglishFromTRK([], trk_path, synonyms_dict=synonyms)
    with open(GetOutputPath('MTU.TUR_ES_ANLAM.TXT'), 'w', encoding='utf-8') as f:
        for turkish, data in sorted(synonyms.items()):
            syns = ' | '.join(sorted(data['synonyms']))
            f.write(f'{turkish:<30} {syns}  [{data["via"]}]\n')
    print(f'Exported {len(synonyms)} eş anlamlılar entries.')

if __name__ == '__main__':
    main()
