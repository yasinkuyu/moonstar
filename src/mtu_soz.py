#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""
mtu_soz.py — MTU.SOZ user dictionary exporter (Denetim Opsiyonlar → kullanıcı sözlüğü)

*.SOZ is the MTU.EXE user dictionary format (load FUN_1010_0391, save FUN_1010_04b9):
    "MG2\\x1a"  u16 word count  u16 text length  [text area]  [count × 4-byte word records]
Records use the MTU.TUR Section 4 layout without the 2-letter prefix; bit 10 selects
the dictionary's own text area instead of MTU.TUR Section 5. MTU.SOZ holds 2,193
proper names (places, people, abbreviations); KONTROL.SOZ holds one word.
Decoded by engine.speller.UserDictionary.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.speller import UserDictionary
from engine.tur_lexicon import default_lexicon


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lexicon = default_lexicon()
    for name in ("MTU.SOZ", "KONTROL.SOZ"):
        path = os.path.join(base_dir, "data", name)
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
        words = UserDictionary(path, lexicon).words
        out_path = os.path.join(base_dir, "output", name + ".TXT")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(words) + "\n")
        print(f"Exported {len(words)} words from {name} to {out_path}")


if __name__ == "__main__":
    main()
