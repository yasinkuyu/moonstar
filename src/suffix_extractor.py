#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suffix_extractor.py — MTU.TUR Section 3 & 5 Suffix Table Extractor

Extracts all 3,218 pre-computed morphological suffixes from MTU.TUR
using MoonStar's 32-letter Turkish alphabet table.
"""

from __future__ import annotations

import json
import os
import struct
from typing import Dict, List

ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"


def extract_suffixes(tur_path: str = "data/MTU.TUR") -> List[str]:
    with open(tur_path, "rb") as f:
        data = f.read()

    hdr = struct.unpack("<HHHH", data[4:12])
    word_count = hdr[0]
    sec3_count = hdr[1]
    sec5_len = hdr[2]

    letter_count = 32
    sec1_size = (letter_count + 1) * 2
    sec2_size = (letter_count ** 2 + 1) * 2
    sec3_off = 12 + sec1_size + sec2_size
    sec4_off = sec3_off + sec3_count * 14
    sec5_off = sec4_off + word_count * 4
    sec5 = data[sec5_off : sec5_off + sec5_len]

    suffixes: List[str] = []

    for sid in range(sec3_count):
        entry = data[sec3_off + sid * 14 : sec3_off + (sid + 1) * 14]
        b0 = entry[0]
        count = b0 & 0x7F

        if count == 0:
            suffixes.append("")
            continue

        if count < 3:
            indices = entry[1 : 1 + count]
        else:
            val = struct.unpack("<H", entry[1:3])[0]
            indices = sec5[val : val + count]

        text = "".join(
            ALPHABET[idx] if idx < len(ALPHABET) and ALPHABET[idx] != "." else ""
            for idx in indices
        )
        suffixes.append(text)

    return suffixes


def export_suffixes_json(
    tur_path: str = "data/MTU.TUR",
    output_path: str = "data/suffixes.json",
) -> None:
    suffixes = extract_suffixes(tur_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(suffixes, f, ensure_ascii=False, indent=2)
    print(f"Başarıyla {len(suffixes)} adet ek dışa aktarıldı: {output_path}")


if __name__ == "__main__":
    export_suffixes_json()
