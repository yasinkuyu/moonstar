# -*- coding: utf-8 -*-
"""
engine — MoonStar Core Reverse-Engineered Linguistic Engine
"""

from .binary_parser import TesBinaryParser
from .phonetics import (
    attach_suffix_phonetically,
    get_last_vowel,
    harden_final_consonant,
    is_back_vowel,
    soften_final_consonant,
)
from .suffix import SuffixEngine, get_suffix_table
from .thesaurus import ThesaurusEngine

__all__ = [
    "ThesaurusEngine",
    "TesBinaryParser",
    "SuffixEngine",
    "get_suffix_table",
    "soften_final_consonant",
    "harden_final_consonant",
    "attach_suffix_phonetically",
    "is_back_vowel",
    "get_last_vowel",
]
