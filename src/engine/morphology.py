#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine/morphology.py — Türkçe Morfolojik Analiz, Ses Olayları ve Bileşik Kelime Motoru
"""

from __future__ import annotations

import re
from typing import Set, Tuple


def normalize_turkish(text: str) -> str:
    """Türkçe karakterleri arama için normalleştirir (ı->i, ş->s, ç->c, ö->o, ü->u, ğ->g)."""
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "I": "i",
        "ş": "s", "Ş": "s",
        "ç": "c", "Ç": "c",
        "ö": "o", "Ö": "o",
        "ü": "u", "Ü": "u",
        "ğ": "g", "Ğ": "g",
        "â": "a", "Â": "a",
        "î": "i", "Î": "i",
        "û": "u", "Û": "u",
    })
    return text.lower().translate(tr_map)


def get_morphological_stems(word: str) -> Set[str]:
    """
    Türkçe çekim eklerini ve ünsüz yumuşamalarını çözümler.
    (Örn: 'kitabı' -> {'kitap', 'kitab', 'kitabı'})
    """
    w = word.lower()
    suffixes = ["ları", "leri", "lar", "ler", "ı", "i", "u", "ü"]
    stems = {w}
    for suf in suffixes:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[:-len(suf)]
            stems.add(stem)
            if stem.endswith("b"):
                stems.add(stem[:-1] + "p")
            elif stem.endswith("c"):
                stems.add(stem[:-1] + "ç")
            elif stem.endswith("d"):
                stems.add(stem[:-1] + "t")
            elif stem.endswith("ğ"):
                stems.add(stem[:-1] + "k")
    return stems


def apply_compound_possessive(stem: str) -> str:
    """
    Bitişik Türkçe bileşik isim gövdelerine 3. tekil iyelik eki uygular.
    Örn: 'elkitab' -> 'elkitabı', 'amerikaelma' -> 'amerikaelması', 'kirazelma' -> 'kirazelması'
    """
    s = stem.lower()
    vowels = "aeıioöuüâîû"
    
    # Son harf ünlü mü?
    if s[-1] in vowels:
        last_v = s[-1]
        # Kalın ünlüler: a, ı, o, u -> -sı
        # İnce ünlüler: e, i, ö, ü -> -si
        if last_v in "aıouâ":
            return s + "sı"
        else:
            return s + "si"
    else:
        # Son harf ünsüz -> ünsüz yumuşaması kontrolü ve -ı/-i eki
        last_char = s[-1]
        base = s[:-1]
        
        # Yumuşama kuralları: p->b, ç->c, t->d, k->ğ/g
        if last_char == "p":
            base = base + "b"
        elif last_char == "ç":
            base = base + "c"
        elif last_char == "t":
            base = base + "d"
        elif last_char == "k":
            base = base + "ğ"
        else:
            base = s
            
        # Son ünlüye göre ek seç
        stem_vowels = [ch for ch in s if ch in vowels]
        last_v = stem_vowels[-1] if stem_vowels else "a"
        
        if last_v in "aıâ":
            return base + "ı"
        elif last_v in "eiî":
            return base + "i"
        elif last_v in "ouû":
            return base + "u"
        else:
            return base + "ü"
