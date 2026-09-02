# -*- coding: utf-8 -*-
"""
engine/phonetics.py — Turkish Phonetics, Vowel Harmony and Consonant Alternation
"""

import os
import sys
from typing import Optional

# Ensure src root is accessible for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import ALL_VOWELS, BACK_VOWELS, HARDEN_MAP, SOFTEN_MAP


def get_last_vowel(word: str) -> Optional[str]:
    """Returns the last Turkish vowel in the word, or None."""
    for ch in reversed(word):
        if ch in ALL_VOWELS:
            return ch
    return None


def is_back_vowel(vowel: str) -> bool:
    """Returns True if vowel follows Turkish back vowel harmony (a, ı, o, u, â, û)."""
    return vowel in BACK_VOWELS


def soften_final_consonant(stem: str) -> str:
    """
    Applies ünsüz yumuşaması (k->ğ, p->b, t->d, ç->c) to word ends before vowel-initial suffixes.
    Preserves monosyllabic invariant words ('ok', 'kök', 'ek', 'ak').
    """
    if not stem or len(stem) < 2:
        return stem
    if stem.endswith("k") and stem not in ["ok", "kök", "ek", "ak"]:
        return stem[:-1] + "ğ"
    last_ch = stem[-1]
    if last_ch in SOFTEN_MAP:
        return stem[:-1] + SOFTEN_MAP[last_ch]
    return stem


def harden_final_consonant(stem: str) -> str:
    """
    Applies consonant hardening for soft-stored stems in MTU.TUR
    (e.g., Ahdiatiğ -> Ahdiatik, ahenğ -> ahenk, ahfad -> ahfat).
    """
    if not stem:
        return stem
    last_ch = stem[-1]
    if last_ch in HARDEN_MAP and stem not in ["ağ", "bağ", "dağ", "sağ", "çağ", "yağ", "tuğ", "yeğ"]:
        return stem[:-1] + HARDEN_MAP[last_ch]
    return stem


def attach_suffix_phonetically(root: str, suffix_text: str) -> str:
    """
    Attaches a suffix to a root applying Turkish phonological rules:
    - Root-final consonant softening before vowels.
    - Buffer consonant ('y') between two adjacent vowels.
    """
    if not suffix_text:
        return root
    if not root:
        return suffix_text

    res = root
    first_suf_ch = suffix_text[0]

    # If suffix starts with vowel
    if first_suf_ch in ALL_VOWELS:
        if res.endswith("k") and res not in ["ok", "kök", "ek", "ak"]:
            res = res[:-1] + "ğ"
        elif res.endswith(tuple(ALL_VOWELS)):
            res = res + "y"

    return res + suffix_text
