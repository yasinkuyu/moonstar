# -*- coding: utf-8 -*-
"""
core/constants.py — MoonStar System Constants & Tables
"""

import os
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def project_path(*parts: str) -> str:
    """Path inside the repository (data/, output/, …)."""
    return os.path.join(PROJECT_ROOT, *parts)


# File offset of DGROUP (NE segment 6) in MTU.EXE: ds:xxxx = file 0x19E00 + xxxx
DGROUP_FILE_OFFSET = 0x19E00

# 32-letter MoonStar alphabet used across MTU.TUR and MTU.SOZ; code | 0x20 selects
# the circumflex variant (â = 0x20, î = 0x2B, û = 0x3A)
ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

# 36 official categories compiled at MTU.EXE offset 0x1B63A (DGROUP: 0x183A)
TOPIC_NAMES: List[str] = [
    "Mecaz", "Argo", "Renk", "Türemiş", "Anatomi", "Askerlik", "Bitkibilim", "Biyoloji",
    "Coğrafya", "Denizcilik", "Dilbilgisi, dilbilim", "Dinsel", "Ekonomi", "Elektrik, elektronik",
    "Felsefe", "Fizik", "Gökbilim (astronomi)", "Hayvanbilim", "Hekimlik", "Hukuk",
    "İskambil", "Kimya", "Mantık", "Matematik", "Meteoroloji", "Mimarlık", "Müzik",
    "Otomobil, otomotiv", "Ruhbilim (psikoloji)", "Sinema", "Spor", "Teknik, teknoloji",
    "Ticaret", "Tiyatro", "Yazın (edebiyat)", "Yerbilim (jeoloji)"
]
