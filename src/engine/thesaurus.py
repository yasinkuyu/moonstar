# -*- coding: utf-8 -*-
"""
engine/thesaurus.py — MoonStar Turkish Thesaurus Engine (Türkçe Eş Anlamlı Sözcükler)

Reproduces the MTU.EXE thesaurus window: the typed word is recognised with the
EXE's Leb Demeden analyzer (FUN_1010_0a0e), and its MTU.TES slot is decoded
with the EXE's record decoder (FUN_1010_256c).
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional, Set, Tuple

# Ensure src root is accessible for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import project_path
from engine.binary_parser import TesBinaryParser, sort_key
from engine.speller import Speller
from engine.tur_lexicon import TurLexicon, default_lexicon


class ThesaurusEngine:
    """Turkish thesaurus lookups with the same results as the MTU.EXE window."""

    def __init__(self, tes_path: Optional[str] = None, tur_path: Optional[str] = None):
        self.lexicon = TurLexicon(tur_path) if tur_path else default_lexicon()
        with open(tes_path or project_path("data", "MTU.TES"), "rb") as f:
            self.parser = TesBinaryParser(self.lexicon, f.read())
        self.analyzer = Speller.for_windows(self.lexicon)
        self.all_vocab: Set[str] = self._collect_vocab()

    def _collect_vocab(self) -> Set[str]:
        """Headwords plus the derived sub-record titles stored inside MTU.TES slots."""
        offsets = self.parser.tes_offsets
        vocab: Set[str] = set()
        for idx in range(min(self.lexicon.word_count, len(offsets) - 1)):
            if offsets[idx + 1] <= offsets[idx]:
                continue
            entries, codes, alias_depth, _ = self.parser.build_buffer(idx)
            if not entries or alias_depth:
                continue
            vocab.add(entries[0])
            vocab.update(text for text, code in zip(entries, codes) if code & 0x80)
        return vocab

    def find_index(self, word: str) -> Optional[int]:
        """TUR index the thesaurus window opens for the typed word (FUN_1010_0a0e as run by FUN_1010_256c)."""
        return self.analyzer.window_index(word.strip())[0]

    def lookup_ordered(self, word: str) -> List[Tuple[str, List[str]]]:
        """[(group label, synonyms)] in the order the EXE shows groups and words."""
        idx = self.find_index(word)
        return self.parser.decode(idx, word.strip()) if idx is not None else []

    def lookup(self, word: str) -> List[Tuple[str, Set[str]]]:
        return [(grp, set(words)) for grp, words in self.lookup_ordered(word)]


def load_all_synonyms(tes_path: Optional[str] = None) -> List[dict]:
    """One dict per vocabulary word with its synonym groups, in the EXE's sort order."""
    engine = ThesaurusEngine(tes_path)
    entries: List[dict] = []

    # Ties (case / circumflex variants) are broken by the text itself so the order is stable
    for word in sorted(engine.all_vocab, key=lambda w: (sort_key(w), w)):
        groups_list = engine.lookup_ordered(word)
        if not groups_list:
            continue
        formatted = []
        all_syns: Set[str] = set()
        for grp_name, syn_list in groups_list:
            formatted.append(f"{grp_name}::{','.join(syn_list)}")
            all_syns.update(syn_list)
        entries.append({
            "word": word,
            "synonyms": " | ".join(sorted(all_syns, key=sort_key)),
            "groups": " | ".join(formatted),
        })

    return entries
