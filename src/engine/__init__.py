# -*- coding: utf-8 -*-
"""
engine — MoonStar Core Reverse-Engineered Linguistic Engine
"""

from .binary_parser import TesBinaryParser
from .speller import Speller, UserDictionary
from .thesaurus import ThesaurusEngine
from .tur_lexicon import TurLexicon, get_suffix_table

__all__ = [
    "ThesaurusEngine",
    "Speller",
    "UserDictionary",
    "TesBinaryParser",
    "TurLexicon",
    "get_suffix_table",
]
