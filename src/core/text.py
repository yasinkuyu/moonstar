# -*- coding: utf-8 -*-
"""
core/text.py — Turkish Text Normalization and Sorting Utilities
"""

from typing import List


def tr_lower(s: str) -> str:
    """Proper Turkish lowercasing without Unicode combining dots."""
    return s.replace("İ", "i").replace("I", "ı").lower().replace("\u0307", "")


def fold_circumflex(s: str) -> str:
    """The EXE's circumflex letters are a / i / ü with bit 0x20 (DGROUP 0x0A8B), so "û" folds to "ü"."""
    return s.replace("â", "a").replace("î", "i").replace("û", "ü")


def turkish_sort_key(s: str) -> List[str]:
    """Türk alfabesi sıralama anahtarı (ç, ğ, ı, ö, ş, ü duyarlı)."""
    mapping = {
        "a": "a0", "A": "a0",
        "b": "b0", "B": "b0",
        "c": "c0", "C": "c0",
        "ç": "c1", "Ç": "c1",
        "d": "d0", "D": "d0",
        "e": "e0", "E": "e0",
        "f": "f0", "F": "f0",
        "g": "g0", "G": "g0",
        "ğ": "g1", "Ğ": "g1",
        "h": "h0", "H": "h0",
        "ı": "i0", "I": "i0",
        "i": "i1", "İ": "i1",
        "j": "j0", "J": "j0",
        "k": "k0", "K": "k0",
        "l": "l0", "L": "l0",
        "m": "m0", "M": "m0",
        "n": "n0", "N": "n0",
        "o": "o0", "O": "o0",
        "ö": "o1", "Ö": "o1",
        "p": "p0", "P": "p0",
        "r": "r0", "R": "r0",
        "s": "s0", "S": "s0",
        "ş": "s1", "Ş": "s1",
        "t": "t0", "T": "t0",
        "u": "u0", "U": "u0",
        "ü": "u1", "Ü": "u1",
        "v": "v0", "V": "v0",
        "y": "y0", "Y": "y0",
        "z": "z0", "Z": "z0",
    }
    return [mapping.get(c, c) for c in s]
