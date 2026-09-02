#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine — MoonStar Tersine Mühendislik Çekirdek Motor Paketi
"""

from .morphology import (
    apply_compound_possessive,
    get_morphological_stems,
    normalize_turkish,
)
from .thesaurus import (
    ThesaurusEngine,
    clean_tr_token,
)

__all__ = [
    "ThesaurusEngine",
    "normalize_turkish",
    "get_morphological_stems",
    "apply_compound_possessive",
    "clean_tr_token",
]
