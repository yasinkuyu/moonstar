# -*- coding: utf-8 -*-
"""
engine/game.py — word pool of the Kelime Oyunu (hangman) window

Port of MTU.EXE FUN_1010_4b79: a random record of the main dictionary (MTU.TUR,
"Ana Sözlükten") or of user dictionary 0 (MTU.SOZ, "Kullanıcı Sözlükten") is
drawn until one passes the checks below; its letters are shown uppercase
through the runtime table ds:0x09CA (code & 0x1F | 0x80), circumflexes dropped.
"""

import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.tur_lexicon import TurLexicon, code_char

MAIN, USER = 0, 1   # DGROUP 0x0056: radio button 800 + source in the "Oyun Kelimeleri" dialog


def _playable(lexicon: TurLexicon, s6: int, length: int) -> bool:
    """FUN_1010_4b79 loop condition (FUN_1010_1e22 always accepts: option bit 3 is masked)."""
    b1, b2 = lexicon.sec6[s6 * 4 + 1], lexicon.sec6[s6 * 4 + 2]
    return 5 <= length <= 15 and not b2 & 0xC0 and not b1 & 0x80 and bool(b1 & 0x40)


def _upper(codes: List[int]) -> str:
    return "".join(code_char((c & 0x1F) | 0x80) for c in codes)


def game_words(lexicon: TurLexicon, user=None, source: int = MAIN) -> List[str]:
    """Every word the game can pick from the chosen dictionary, in dictionary order."""
    words = []
    if source == MAIN:
        k = 0
        for idx in range(lexicon.word_count):
            while lexicon.prefix_starts[k + 1] <= idx:
                k += 1
            codes = [k >> 5, k & 0x1F] + lexicon.body_codes(idx)
            if _playable(lexicon, lexicon.section6_index(idx), len(codes)):
                words.append(_upper(codes))
    elif user is not None:
        for i, codes in enumerate(user.codes):
            if _playable(lexicon, user.section6_index(i), len(codes)):
                words.append(_upper(codes))
    return words
