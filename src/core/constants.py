# -*- coding: utf-8 -*-
"""
core/constants.py — MoonStar System Constants & Tables
"""

from typing import Dict, List

# 32-letter custom MoonStar alphabet used across MTU.TUR and MTU.SOZ
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

# Static named groups mapped from lower nibble (flag & 0x0F)
NAMED_GROUPS: Dict[int, str] = {
    0x05: "Mecaz",
    0x06: "Mecaz",
    0x07: "Argo",
    0x09: "Renk",
    0x0A: "Türemiş",
}

# Consonant softening rules
SOFTEN_MAP: Dict[str, str] = {
    "k": "ğ",
    "p": "b",
    "t": "d",
    "ç": "c",
}

# Consonant hardening rules (Section 6 morphology)
HARDEN_MAP: Dict[str, str] = {
    "ğ": "k",
    "g": "k",
    "b": "p",
    "c": "ç",
    "d": "t",
}

# Vowel classifications
BACK_VOWELS = "aıouâû"
FRONT_VOWELS = "eiöüî"
ALL_VOWELS = BACK_VOWELS + FRONT_VOWELS
