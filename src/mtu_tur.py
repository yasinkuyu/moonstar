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

# The word list is built by engine.tur_lexicon, an exact port of the MTU.EXE
# routines FUN_1010_2e73 / FUN_1010_1bc4 (prefix table, Section 4 body,
# 10-bit Section 6 index, final-letter mutation via EXE table DGROUP 0x1588).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.tur_lexicon import TurLexicon

def Import(dictionary, path):
    dictionary.extend(TurLexicon(tur_path=path).words)

def Export(dictionary, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for entry in dictionary:
            file.write(entry)
            file.write('\n')

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
    """
    Build Türkçe→İngilizce dictionary by reversing the TRK (İngilizce→Türkçe) file.

    MTU.TUR Section 3 is a SUFFIX STRIPPING TABLE for Leb Demeden (NOT TR_EN data):
      - Each entry = [byte0: count][val: Section5 offset][bytes11: morphological class]
      - Section5[val:val+count] = Turkish suffix string (e.g. 'acak', 'mak', 'ımdan')
      - Section1 = fast lookup index by first letter of suffix
      - bytes11[2] = grammatical class code (3=aorist, 5=future/ability stems, etc.)

    Correct TR_EN source: reverse the TRK file (İngilizce→Türkçe pairs).
    Each Turkish definition in TRK maps back to its English headword.

    For synonyms (ES_ANLAM): Turkish words sharing the same English translation
    are considered synonyms of each other. This is a SEPARATE, simpler
    English-block co-occurrence method, unrelated to the MTU.TES thesaurus
    decoded by engine.thesaurus (the EXE's Türkçe Eş Anlamlı Sözcükler window).

    Coverage: ~25% of TUR words have a direct TR_EN match via TRK.
    Remaining 75% are proper nouns, compounds, or forms not in TRK — these
    words (e.g. beniz, vecih, sima) cannot get synonyms from this method at all,
    confirmed missing in the RAM-dump ground truth (test_comparison.py test_04).
    """
    if not os.path.exists(trk_path):
        return

    tr_to_en = {}
    en_meanings = defaultdict(list)

    with open(trk_path, 'r', encoding='utf-8') as f:
        for line in f:
            # MTU.TRK.TXT uses a fixed 30-column English headword field;
            # headwords may contain spaces (e.g. "believe in").
            line = line.rstrip('\r\n')
            english, tr_raw = line[:30].rstrip(), line[30:].strip()
            if not english or not tr_raw:
                continue
            
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