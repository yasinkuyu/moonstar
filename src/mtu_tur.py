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
import re
import struct
import sys
from collections import defaultdict

# MTU.TUR encodes all text in its own custom alphabet, where 0x00 is 'a', 0x01
# is 'b' and so on.
alphabet = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

def TurkishSortKey(s):
    mapping = {
        'a': 'a0', 'A': 'a0',
        'b': 'b0', 'B': 'b0',
        'c': 'c0', 'C': 'c0',
        'ç': 'c1', 'Ç': 'c1',
        'd': 'd0', 'D': 'd0',
        'e': 'e0', 'E': 'e0',
        'f': 'f0', 'F': 'f0',
        'g': 'g0', 'G': 'g0',
        'ğ': 'g1', 'Ğ': 'g1',
        'h': 'h0', 'H': 'h0',
        'ı': 'i0', 'I': 'i0',
        'i': 'i1', 'İ': 'i1',
        'j': 'j0', 'J': 'j0',
        'k': 'k0', 'K': 'k0',
        'l': 'l0', 'L': 'l0',
        'm': 'm0', 'M': 'm0',
        'n': 'n0', 'N': 'n0',
        'o': 'o0', 'O': 'o0',
        'ö': 'o1', 'Ö': 'o1',
        'p': 'p0', 'P': 'p0',
        'r': 'r0', 'R': 'r0',
        's': 's0', 'S': 's0',
        'ş': 's1', 'Ş': 's1',
        't': 't0', 'T': 't0',
        'u': 'u0', 'U': 'u0',
        'ü': 'u1', 'Ü': 'u1',
        'v': 'v0', 'V': 'v0',
        'y': 'y0', 'Y': 'y0',
        'z': 'z0', 'Z': 'z0'
    }
    return [mapping.get(c, c) for c in s.lower()]

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
    """
    Applies modifications to prefix and suffix based on Section 6 data.

    data[0] - Capitalization & Special Flags:
    - 0x0B, 0x0F, 0x2F, 0x4B, 0x4F, 0x6F: Proper nouns / Capitalize first letter
    - 0x20, 0x2F: Contains circumflex (â, î, û)
    - 0x80: Compound word flag

    data[1] - Morphology & Hardness:
    - bit 0 (0x01): Capitalization flag
    - bit 4 (0x10): Hardened stem indicator (e.g. 0x50, 0x51, 0x58, 0x59)

    data[2] - Suffix Class & Mutation:
    - bit 7 (0x80): Soft/mutated stem in morphological database (e.g. 0x8b, 0x8a)
    - 0x06, 0x07: Hard stem
    """
    # 1. Consonant hardening for base forms
    # When Section 6 indicates hard/base form (bit 7 of byte 2 not set, and hardened flag set)
    is_hard = (data[2] & 0x80 == 0) and ((data[1] & 0x10) != 0 or data[2] in [6, 7])
    if is_hard:
        if suffix.endswith('ğ'):
            suffix = suffix[:-1] + 'k'
        elif not suffix and prefix.endswith('ğ'):
            prefix = prefix[:-1] + 'k'
        elif suffix.endswith('b'):
            suffix = suffix[:-1] + 'p'
        elif not suffix and prefix.endswith('b'):
            prefix = prefix[:-1] + 'p'
        elif suffix.endswith('c'):
            suffix = suffix[:-1] + 'ç'
        elif not suffix and prefix.endswith('c'):
            prefix = prefix[:-1] + 'ç'
        elif suffix.endswith('d'):
            suffix = suffix[:-1] + 't'
        elif not suffix and prefix.endswith('d'):
            prefix = prefix[:-1] + 't'
        elif suffix.endswith('g'):
            suffix = suffix[:-1] + 'k'
        elif not suffix and prefix.endswith('g'):
            prefix = prefix[:-1] + 'k'

    # 2. Capitalization check
    should_capitalize = (data[0] in [0x0b, 0x0f, 0x2f, 0x4b, 0x4f, 0x6f]) or ((data[1] & 0x01) != 0)

    # Apply capitalization to prefix
    if should_capitalize and prefix:
        turkish_lower = {'ı': 'I', 'i': 'İ', 'ğ': 'Ğ', 'ü': 'Ü', 'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'}
        first_char = prefix[0]
        if first_char in turkish_lower:
            prefix = turkish_lower[first_char] + prefix[1:]
        else:
            prefix = prefix[0].upper() + prefix[1:]

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

    # 3rd section
    # Suffix stripping table for morphological analysis in Leb Demeden.
    # Contains 3,218 14-byte entries defining suffix rules, grammar classes,
    # and offsets into Section 5.
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
def clean_turkish_synonym(w):
    w = re.sub(r'\(.*?\)', '', w)
    w = re.sub(r'<.*?>', '', w)
    w = re.sub(r'\s*\(.*$', '', w)
    w = re.sub(r'^(mec\.|arg\.|esk\.|tıp\.|huk\.|tic\.|bot\.|hayv\.|anat\.|kim\.|fiz\.|astr\.|mat\.|den\.|ask\.|mus\.|dilb\.|edeb\.|biy\.|jeol\.|felsefe|sosyol\.|argo|mecaz|İİ|s\.|i\.|f\.|zf\.|zam\.|bağ\.|ünl\.|ed\.)\s*', '', w)
    w = re.sub(r'^[-\.][a-zçğıöşü]+\s*', '', w)
    w = re.sub(r'\s*ile$', '', w)
    w = w.strip(' ,;:.-\t\n\r/')
    return w

def is_clean_turkish_synonym(w):
    if not w or len(w) < 2 or len(w) > 25:
        return False
    if any(ch in w for ch in ['/', '\\', ':', ';', '!', '?', '=', '<', '>', '{', '}', '_', '@', '%', '$']):
        return False
    allowed = set("abcçdefgğhıijklmnoöpqrsştuüvwxyzABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ -'")
    return all(c in allowed for c in w)

def ImportTurkishEnglishFromTRK(dictionary, trk_path, synonyms_dict=None):
    if not os.path.exists(trk_path):
        return

    tr_to_en = {}
    en_meanings = defaultdict(list)

    with open(trk_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            english, tr_raw = parts[0], parts[1]
            
            # TR_EN mapping
            for m_block in tr_raw.split('#'):
                for m in m_block.split('|'):
                    m_clean = m.strip()
                    if m_clean.startswith('(') and len(m_clean) > 20:
                        continue
                    cw = clean_turkish_synonym(m_clean)
                    if is_clean_turkish_synonym(cw) and len(cw.split()) <= 4:
                        tr_to_en.setdefault(cw, []).append(english)

            # Synonym extraction per meaning block (never merge across '#')
            for m_block in tr_raw.split('#'):
                m_words = set()
                for it in m_block.split('|'):
                    cw = clean_turkish_synonym(it)
                    if is_clean_turkish_synonym(cw):
                        m_words.add(cw)
                if len(m_words) >= 2:
                    en_meanings[english].append(m_words)

    if synonyms_dict is not None:
        for en, meanings in en_meanings.items():
            for m_words in meanings:
                sorted_words = sorted(m_words)
                for i, tw in enumerate(sorted_words):
                    others = [w for j, w in enumerate(sorted_words) if j != i]
                    if tw not in synonyms_dict:
                        synonyms_dict[tw] = {'synonyms': set(others), 'via': [en]}
                    else:
                        synonyms_dict[tw]['synonyms'].update(others)
                        if en not in synonyms_dict[tw]['via']:
                            synonyms_dict[tw]['via'].append(en)
    else:
        for turkish, english_list in sorted(tr_to_en.items(), key=lambda x: TurkishSortKey(x[0])):
            unique_ens = sorted(list(dict.fromkeys(english_list)))
            dictionary.append((turkish, ', '.join(unique_ens)))


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
            via_str = ', '.join(data['via'])
            f.write(f'{turkish:<30} {syns}  [{via_str}]\n')
    print(f'Exported {len(synonyms)} eş anlamlılar entries.')

if __name__ == '__main__':
    main()
