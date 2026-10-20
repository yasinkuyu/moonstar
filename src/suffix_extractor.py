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
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.tur_lexicon import TurLexicon

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TUR_PATH = os.path.join(_PROJECT_ROOT, "data", "MTU.TUR")
DEFAULT_SUFFIXES_PATH = os.path.join(_PROJECT_ROOT, "data", "suffixes.json")


def extract_suffixes(tur_path: str = DEFAULT_TUR_PATH) -> List[str]:
    """Section 3 suffix texts exactly as MTU.EXE builds them (FUN_1010_2f55, incl. the
    final-letter mutation through EXE table DGROUP 0x1588 when byte0 bit 7 is set)."""
    lexicon = TurLexicon(tur_path=tur_path)
    return [lexicon.suffix(sid) for sid in range(lexicon.suffix_count)]


def export_suffixes_json(
    tur_path: str = DEFAULT_TUR_PATH,
    output_path: str = DEFAULT_SUFFIXES_PATH,
) -> None:
    suffixes = extract_suffixes(tur_path)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(suffixes, f, ensure_ascii=False, indent=2)
    print(f"Başarıyla {len(suffixes)} adet ek dışa aktarıldı: {output_path}")


if __name__ == "__main__":
    export_suffixes_json()
