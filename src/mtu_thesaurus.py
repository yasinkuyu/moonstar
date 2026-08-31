#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtu_thesaurus.py — MoonStar Türkçe Eş Anlamlılar Motoru v3

Orijinal MTU.EXE'nin dinamik semantik ağ mimarisini taklit eder.

Çalışma Prensibi (EXE ile birebir):
  1. MTU.TRK'daki her İngilizce başlık → Türkçe tanımlar ters indekslenir.
  2. Aynı İngilizce başlık altında geçen Türkçe kelimeler birbirinin eş anlamlısıdır.
  3. Multi-hop TRK traversal: synonim zincirleri boyunca derin arama (BFS).
  4. Türemiş kelime üretimi: TRK kelimelerine ek ekleyerek yeni türetmeler.
  5. bileşik kelime bağlantıları: compound phrase bileşenleri arası köprü.
  6. TUR morfolojik kök türetmeleri: kök kelime listesi ile bağlantı.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

MECAZ_KW = ("(mec", "mec.", "argo", "arg.")

TURKISH_SUFFIXES = [
    "laştırma", "leşme", "laşma", "leme", "lame",
    "cılık", "çilik", "çülük",
    "lıkçı", "likçi", "lükçı", "lükci",
    "lık", "lik", "luk", "lük",
    "sız", "siz", "suz", "süz",
    "cı", "ci", "cu", "cü",
    "çı", "çi", "çu", "çü",
    "lı", "li", "lu", "lü",
    "lıkda", "likte",
    "dan", "den", "tan", "ten",
    "da", "de", "ta", "te",
    "nın", "nin", "nun", "nün",
    "yla", "yle",
    "maz", "mez",
    "ma", "me",
    "mek", "mak",
]

DERIVATION_SUFFIXES = [
    "leştirme", "leşme", "laşma",
    "lendirmek", "landırmak",
    "leme", "lame",
    "lemek", "lamak", "leşmek", "laşmak",
    "lanma", "lenme", "lanmak", "lenmek",
    "laşma", "leşme",
    "cılık", "çilik",
    "sız", "siz", "suz", "süz",
    "sızca", "sizce", "suzca", "süzce",
    "ca", "ce",
    "lık", "lik", "luk", "lük",
    "sımızlık", "sizlik", "suzluk", "süzlük",
    "lı", "li", "lu", "lü",
    "cı", "ci", "cu", "cü",
    "çı", "çi", "çu", "çü",
    "dan", "den", "tan", "ten",
    "madan", "meden",
    "maz", "mez",
    "ma", "me",
    "mak", "mek",
    "mı", "mi", "mu", "mü",
    "semek", "samak",
    "lanma", "lenme",
    "lanmadan", "lenmeden",
]


def clean_tr_token(token: str) -> str:
    token = token.strip()
    while "(" in token and ")" in token:
        token = re.sub(r"\(.*?\)", "", token).strip()
    while "[" in token and "]" in token:
        token = re.sub(r"\[.*?\]", "", token).strip()
    while "<" in token and ">" in token:
        token = re.sub(r"<.*?>", "", token).strip()
    token = re.sub(
        r"^(arg\.|mec\.|esk\.|tıp\.|huk\.|tic\.|bot\.|hayv\.|anat\.|kim\.|fiz\.|"
        r"astr\.|mat\.|den\.|ask\.|mus\.|dilb\.|edeb\.|biy\.|jeol\.|felsefe|"
        r"sosyol\.|argo|mecaz|İİ|s\.|i\.|f\.|zf\.|zam\.|bağ\.|ünl\.|ed\.)\s*",
        "",
        token,
        flags=re.IGNORECASE,
    )
    token = re.sub(r"^[-\.][a-zçğıöşü]+\s*", "", token, flags=re.IGNORECASE)
    token = token.replace("*", "").replace("#", "").strip(" ,;:.-\t\n\r/").lower()
    if not token or len(token) < 2 or len(token) > 35:
        return ""
    return token


class SemanticThesaurus:
    def __init__(self, trk_path: str, tur_txt_path: str):
        self.trk_path = trk_path
        self.tur_txt_path = tur_txt_path

        self.en_blocks: Dict[str, List[Tuple[int, Set[str]]]] = defaultdict(list)
        self.tr_to_en: Dict[str, Set[str]] = defaultdict(set)
        self.en_to_all_tr: Dict[str, Set[str]] = defaultdict(set)
        self.tur_vocab: Set[str] = set()
        self.all_vocab: Set[str] = set()
        self.phrases_by_first_word: Dict[str, Set[str]] = defaultdict(set)
        self.word_to_peers: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        self.root_to_derived: Dict[str, Set[str]] = defaultdict(set)
        self.compound_phrases: Set[str] = set()
        self.trk_tr_words: Set[str] = set()
        self._trk_headword_all_tr: Dict[str, Set[str]] = {}
        self._trk_adjacent_to: Dict[str, Set[str]] = defaultdict(set)
        self._compound_root_to_phrase_words: Dict[str, Set[str]] = defaultdict(set)

        self._build()

    def _build(self):
        self._load_tur_vocab()
        self._build_morphological_roots()
        self._build_trk_inverted_index()
        self._build_tur_trk_cross_references()
        self._build_single_hop_connections()
        self._build_compound_connections()
        self._build_trk_phrase_extraction()
        self._build_compound_index()
        self._build_tur_morphological_connections()
        self._build_morphological_derivations()
        self._index_phrases()

    def _load_tur_vocab(self):
        if not os.path.exists(self.tur_txt_path):
            return
        with open(self.tur_txt_path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w and len(w) >= 2:
                    self.tur_vocab.add(w)
                    self.all_vocab.add(w)

    def _build_morphological_roots(self):
        for word in self.tur_vocab:
            for suffix in TURKISH_SUFFIXES:
                if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                    root = word[:-len(suffix)]
                    if root in self.tur_vocab or len(root) >= 3:
                        self.root_to_derived[root].add(word)
                        self.root_to_derived[word].add(root)

    def _build_trk_inverted_index(self):
        if not os.path.exists(self.trk_path):
            return
        self._trk_raw_defs = {}
        with open(self.trk_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                en, tr_raw = parts[0], parts[1]
                self._trk_raw_defs[en] = tr_raw

                blocks = [b.strip() for b in tr_raw.split("#") if b.strip()]
                for b_idx, b in enumerate(blocks):
                    cleaned_tokens = []
                    for t in b.split("|"):
                        ct = clean_tr_token(t)
                        if ct:
                            cleaned_tokens.append(ct)

                    unique_tokens = list(dict.fromkeys(cleaned_tokens))
                    if not unique_tokens:
                        continue

                    self.en_blocks[en].append((b_idx, set(unique_tokens)))
                    self.en_to_all_tr[en].update(unique_tokens)

                    for w in unique_tokens:
                        self.all_vocab.add(w)
                        self.trk_tr_words.add(w)
                        self.tr_to_en[w].add(en)

                    for w in unique_tokens:
                        if " " in w:
                            self.compound_phrases.add(w)
                            for comp in w.split():
                                comp = comp.strip()
                                if len(comp) >= 2:
                                    self.all_vocab.add(comp)
                                    self.trk_tr_words.add(comp)
                                    self.tr_to_en[comp].add(en)
                                    self.word_to_peers[comp]["Bileşik"].add(w)
                                    for other_w in unique_tokens:
                                        if other_w != w and other_w != comp:
                                            self.word_to_peers[comp]["Çapraz"].add(other_w)
                                    for suffix in TURKISH_SUFFIXES:
                                        if comp.endswith(suffix) and len(comp) - len(suffix) >= 3:
                                            root = comp[:-len(suffix)]
                                            if len(root) >= 2:
                                                self.all_vocab.add(root)
                                                self.trk_tr_words.add(root)
                                                self.tr_to_en[root].add(en)
                                                self.word_to_peers[root]["Bileşik"].add(comp)

                    for w in unique_tokens:
                        if " " not in w:
                            for suffix in TURKISH_SUFFIXES:
                                if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                                    root = w[:-len(suffix)]
                                    if len(root) >= 2:
                                        self.all_vocab.add(root)
                                        self.trk_tr_words.add(root)
                                        self.tr_to_en[root].add(en)
                                        self.word_to_peers[root]["Bileşik"].add(w)

    def _build_tur_trk_cross_references(self):
        """Connect TUR words to TRK definitions via substring matching.

        EXE mechanism: for each TUR word, search all TRK raw definitions.
        If the TUR word appears as a substring in a TRK definition, connect
        that TUR word to the TRK headword's synonym network.
        This is how beniz, vecih, sima etc. get connected to 'yüz'.
        """
        trk_lower_cache = {}
        for en, tr_raw in self._trk_raw_defs.items():
            trk_lower_cache[en] = tr_raw.lower()

        for tur_word in list(self.tur_vocab):
            if len(tur_word) < 3:
                continue
            tw = tur_word.lower()
            for en, tr_lower in trk_lower_cache.items():
                if tw in tr_lower:
                    self.trk_tr_words.add(tur_word)
                    self.tr_to_en[tur_word].add(en)
                    self.en_to_all_tr[en].add(tur_word)
                    self.all_vocab.add(tur_word)
                    for peer in self.en_to_all_tr[en]:
                        if peer != tur_word:
                            self.word_to_peers[tur_word]["Çapraz"].add(peer)
                    break

    def _build_single_hop_connections(self):
        """Single-hop: within-block + cross-block via shared headwords."""
        for en, blocks in self.en_blocks.items():
            for b_idx, words in blocks:
                is_mec = any(
                    en.lower().startswith(k) or any(k in w for w in words)
                    for k in ("mec", "argo")
                )
                grp = "Mecaz" if is_mec else ("1.Anlam" if b_idx == 0 else "2.Anlam")
                for w in words:
                    for p in words:
                        if p != w:
                            self.word_to_peers[w][grp].add(p)

        for en, b_list in self.en_blocks.items():
            all_tr_in_en = set()
            for b_idx, words in b_list:
                all_tr_in_en.update(words)
            for w in all_tr_in_en:
                for other in all_tr_in_en:
                    if other != w:
                        self.word_to_peers[w]["Çapraz"].add(other)

        for word in self.tur_vocab:
            for related in self.root_to_derived.get(word, set()):
                if related in self.tur_vocab and related != word:
                    self.word_to_peers[word]["Türemiş"].add(related)

    def _build_compound_connections(self):
        """Connect compound phrase components to their synonym networks."""
        for phrase in list(self.all_vocab):
            if " " not in phrase:
                continue
            components = phrase.split()
            for comp in components:
                if len(comp) >= 2:
                    self.word_to_peers[phrase]["Bileşik"].add(comp)

    def _build_trk_phrase_extraction(self):
        """Extract multi-word phrases from TRK definitions.

        EXE mechanism: when building thesaurus for a word, it scans TRK definitions
        for multi-word phrases containing that word's synonyms. These phrases become
        compound phrase entries in the thesaurus.
        """
        import re
        for en, tr_raw in self._trk_raw_defs.items():
            if en not in self.en_blocks:
                continue
            phrases = re.findall(
                r'[\wçğıöşüÇĞİÖŞÜ]+(?:\s+[\wçğıöşüÇĞİÖŞÜ]+)+', tr_raw
            )
            for phrase in phrases:
                pl = phrase.lower().strip()
                if len(pl) < 5 or len(pl) > 50:
                    continue
                parts = pl.split()
                if any(p in self.trk_tr_words or p in self.tur_vocab for p in parts if len(p) >= 2):
                    self.all_vocab.add(pl)
                    for b_idx, words in self.en_blocks.get(en, []):
                        for w in words:
                            self.word_to_peers[pl]["Bileşik"].add(w)

    def _build_compound_index(self):
        """Pre-compute indices for compound generation at query time.

        1. _trk_headword_all_tr: maps each TRK headword to ALL Turkish words
           across all blocks (used for co-occurrence compound generation).
        2. _trk_adjacent_to: maps each word to words adjacent to it in raw TRK text.
        3. _compound_root_to_phrase_words: maps root words extracted from compound
           phrase components to expanded words sharing the same TRK headword.
        4. _trk_substring_index: maps each TRK word to compound phrases whose
           components contain it as a substring.
        """
        import re
        for en, blocks in self.en_blocks.items():
            all_tr = set()
            for b_idx, words in blocks:
                all_tr.update(words)
            self._trk_headword_all_tr[en] = all_tr

        for en, tr_raw in self._trk_raw_defs.items():
            tl = tr_raw.lower()
            tokens = re.findall(r'[\wçğıöşüÇĞİÖŞÜ]+', tl)
            for i in range(len(tokens) - 1):
                t1, t2 = tokens[i], tokens[i + 1]
                if len(t1) >= 2 and len(t2) >= 2:
                    self._trk_adjacent_to[t1].add(t2)
                    self._trk_adjacent_to[t2].add(t1)

        for phrase in list(self.compound_phrases):
            parts = phrase.split()
            for part in parts:
                for suffix in TURKISH_SUFFIXES:
                    if part.endswith(suffix) and len(part) - len(suffix) >= 2:
                        root = part[:-len(suffix)]
                        if len(root) >= 2:
                            self._compound_root_to_phrase_words[root].add(part)
                            for comp in parts:
                                if comp != part:
                                    self._compound_root_to_phrase_words[root].add(comp)

        self._trk_substring_index = defaultdict(set)
        comp_components = set()
        for phrase in self.compound_phrases:
            for comp in phrase.split():
                comp_components.add(comp)
        for tw in list(self.trk_tr_words):
            if len(tw) < 2 or len(tw) > 6:
                continue
            for comp in comp_components:
                if tw != comp and tw in comp:
                    self._trk_substring_index[comp].add(tw)

    def _build_tur_morphological_connections(self):
        """Connect TUR-only words through shared morphological roots.

        For words like fizyonomi, hicap, mahcubiyet, satıh, vecih that are
        NOT in TRK at all, we connect them to the thesaurus network through
        shared morphological roots with words that ARE connected.
        """
        all_connected = self.trk_tr_words | set(
            w for w in self.all_vocab if w in self.tr_to_en
        )
        for tur_word in list(self.tur_vocab):
            if tur_word in all_connected:
                continue
            for root, derived in self.root_to_derived.items():
                if tur_word in derived and root in all_connected:
                    self.all_vocab.add(tur_word)
                    self.word_to_peers[tur_word]["Türemiş"].add(root)
                    break
                if tur_word == root:
                    for d in derived:
                        if d in all_connected:
                            self.all_vocab.add(tur_word)
                            self.word_to_peers[tur_word]["Türemiş"].add(d)
                            break
                    break

    def _build_morphological_derivations(self):
        """Generate on-the-fly morphological derivatives for TRK words.

        Only adds derivatives that exist in TUR vocabulary or are common
        Turkish formations.
        """
        all_trk = set()
        for en, blocks in self.en_blocks.items():
            for b_idx, words in blocks:
                all_trk.update(words)

        for word in list(all_trk):
            for suffix in DERIVATION_SUFFIXES:
                derived = word + suffix
                if 3 <= len(derived) <= 30:
                    if derived in self.tur_vocab or derived in self.trk_tr_words:
                        self.all_vocab.add(derived)
                        self.word_to_peers[derived]["Türemiş"].add(word)

        for word in list(all_trk):
            for suffix in TURKISH_SUFFIXES:
                if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                    root = word[:-len(suffix)]
                    if len(root) >= 2 and (root in self.tur_vocab or root in self.trk_tr_words):
                        self.all_vocab.add(root)
                        self.word_to_peers[word]["Türemiş"].add(root)

    def _index_phrases(self):
        for w in list(self.all_vocab):
            if " " in w:
                first_word = w.split()[0]
                self.phrases_by_first_word[first_word].add(w)

    def expand_synonyms(self, seed_words: Set[str], max_hops: int = 5) -> Set[str]:
        """BFS multi-hop expansion from seed words through TRK synonym graph."""
        visited = set(seed_words)
        frontier = set(seed_words)
        for _ in range(max_hops):
            next_frontier = set()
            en_headwords = set()
            for word in frontier:
                if word not in self.tr_to_en:
                    continue
                for en in self.tr_to_en[word]:
                    en_headwords.add(en)
                    for b_idx, words in self.en_blocks.get(en, []):
                        for w in words:
                            if w not in visited:
                                next_frontier.add(w)
                                visited.add(w)
                    for other_word in self.en_to_all_tr.get(en, set()):
                        if other_word not in visited:
                            next_frontier.add(other_word)
                            visited.add(other_word)
            for en in en_headwords:
                for w in self.en_to_all_tr.get(en, set()):
                    if w not in visited:
                        next_frontier.add(w)
                        visited.add(w)
            frontier = next_frontier
            if not frontier:
                break
        return visited

    def lookup(self, word_lower: str, use_multi_hop: bool = False, max_hops: int = 5) -> Dict[str, Set[str]]:
        res: Dict[str, Set[str]] = {}

        for grp, p_set in self.word_to_peers.get(word_lower, {}).items():
            res.setdefault(grp, set()).update(p_set)

        for phrase in self.phrases_by_first_word.get(word_lower, ()):
            for grp, p_set in self.word_to_peers.get(phrase, {}).items():
                res.setdefault(grp, set()).update(p_set)

        if use_multi_hop:
            seed = set()
            for peers in res.values():
                seed.update(peers)
            seed.add(word_lower)
            expanded = self.expand_synonyms(seed, max_hops=max_hops)

            for w in expanded:
                if w == word_lower:
                    continue
                for grp, p_set in self.word_to_peers.get(w, {}).items():
                    res.setdefault(grp, set()).update(p_set)
                if w in self.all_vocab:
                    res.setdefault("Multi-Hop", set()).add(w)

            for phrase in self.compound_phrases:
                parts = phrase.split()
                if any(p in expanded for p in parts):
                    for grp, p_set in self.word_to_peers.get(phrase, {}).items():
                        res.setdefault(grp, set()).update(p_set)
                    res.setdefault("Bileşik", set()).add(phrase)
            for phrase in self.all_vocab:
                if " " in phrase:
                    parts = phrase.split()
                    if any(p in expanded for p in parts):
                        for grp, p_set in self.word_to_peers.get(phrase, {}).items():
                            res.setdefault(grp, set()).update(p_set)
                        res.setdefault("Bileşik", set()).add(phrase)

            expanded_trk = expanded & self.trk_tr_words
            for en, blocks in self.en_blocks.items():
                all_tr = set()
                for b_idx, words in blocks:
                    all_tr.update(words)
                overlap = all_tr & expanded_trk
                if len(overlap) >= 2:
                    import re
                    for tr_raw in [tr for b in blocks for tr in b[1]]:
                        for phrase in re.findall(r'[\wçğıöşüÇĞİÖŞÜ]+(?:\s+[\wçğıöşüÇĞİÖŞÜ]+){1,5}', tr_raw.lower()):
                            parts = phrase.split()
                            if len(parts) >= 2 and all(p in expanded or p in self.tur_vocab for p in parts):
                                res.setdefault("Bileşik", set()).add(phrase)

            for en, all_tr in self._trk_headword_all_tr.items():
                overlap = all_tr & expanded_trk
                if len(overlap) >= 2:
                    words_list = sorted(overlap)
                    for i in range(len(words_list)):
                        for j in range(i + 1, len(words_list)):
                            compound = f"{words_list[i]} {words_list[j]}"
                            res.setdefault("Bileşik", set()).add(compound)

            for w in expanded:
                for neighbor in self._trk_adjacent_to.get(w, set()):
                    if neighbor in expanded and w != neighbor:
                        pair = tuple(sorted([w, neighbor]))
                        compound = f"{pair[0]} {pair[1]}"
                        res.setdefault("Bileşik", set()).add(compound)

            compound_roots = set()
            for phrase in expanded:
                if " " not in phrase:
                    continue
                for comp in phrase.split():
                    for suffix in TURKISH_SUFFIXES:
                        if comp.endswith(suffix) and len(comp) - len(suffix) >= 2:
                            root = comp[:-len(suffix)]
                            if root in expanded and root != comp:
                                compound_roots.add(root)
                    if comp in expanded:
                        compound_roots.add(comp)
            compound_roots_list = sorted(compound_roots)
            for i in range(len(compound_roots_list)):
                for j in range(i + 1, len(compound_roots_list)):
                    r1, r2 = compound_roots_list[i], compound_roots_list[j]
                    if len(r1) <= 8 and len(r2) <= 8:
                        compound = f"{r1} {r2}"
                        res.setdefault("Bileşik", set()).add(compound)

            substr_words = set()
            for phrase in expanded:
                comps = phrase.split() if " " in phrase else [phrase]
                for comp in comps:
                    if comp in self._trk_substring_index:
                        for sub in self._trk_substring_index[comp]:
                            if sub in expanded:
                                substr_words.add(sub)
            short_substr = [w for w in substr_words if len(w) <= 6]
            short_substr.sort()
            for i in range(len(short_substr)):
                for j in range(i + 1, len(short_substr)):
                    w1, w2 = short_substr[i], short_substr[j]
                    compound = f"{w1} {w2}"
                    res.setdefault("Bileşik", set()).add(compound)

            for w in list(expanded):
                stems = {w}
                if w.endswith('mak') and len(w) > 4:
                    stems.add(w[:-3])
                if w.endswith('mek') and len(w) > 4:
                    stems.add(w[:-3])
                for stem in stems:
                    for suffix in DERIVATION_SUFFIXES:
                        derived = stem + suffix
                        if 3 <= len(derived) <= 30:
                            res.setdefault("Türemiş", set()).add(derived)
                for suffix in TURKISH_SUFFIXES:
                    if w.endswith(suffix) and len(w) - len(suffix) >= 2:
                        root = w[:-len(suffix)]
                        if len(root) >= 2:
                            res.setdefault("Türemiş", set()).add(root)
                            for dsuffix in DERIVATION_SUFFIXES:
                                derived_from_root = root + dsuffix
                                if 3 <= len(derived_from_root) <= 30:
                                    res.setdefault("Türemiş", set()).add(derived_from_root)

            res_words_sample = list(seed)[:500]
            for w in res_words_sample:
                stems = {w}
                if w.endswith('mak') and len(w) > 4:
                    stems.add(w[:-3])
                if w.endswith('mek') and len(w) > 4:
                    stems.add(w[:-3])
                for stem in stems:
                    for suffix in DERIVATION_SUFFIXES:
                        derived = stem + suffix
                        if 3 <= len(derived) <= 30:
                            res.setdefault("Türemiş", set()).add(derived)

        for grp in list(res.keys()):
            res[grp].discard(word_lower)
            if not res[grp]:
                del res[grp]

        return res


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
) -> List[dict]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trk_path = trk_path or os.path.join(script_dir, "..", "output", "MTU.TRK.TXT")
    tur_txt_path = tur_txt_path or os.path.join(script_dir, "..", "output", "MTU.TUR.TXT")

    engine = SemanticThesaurus(trk_path, tur_txt_path)
    entries: List[dict] = []

    for word_lower in sorted(engine.all_vocab, key=lambda s: s.lower()):
        groups_dict = engine.lookup(word_lower, use_multi_hop=False)

        formatted = []
        all_syns: Set[str] = set()

        for grp_name in ["1.Anlam", "2.Anlam", "Mecaz", "Türemiş", "Çapraz", "Bileşik"]:
            if grp_name in groups_dict and groups_dict[grp_name]:
                syn_list = sorted(groups_dict[grp_name], key=lambda s: s.lower())
                formatted.append(f"{grp_name}::{','.join(syn_list)}")
                all_syns.update(syn_list)

        entries.append({
            "word": word_lower,
            "synonyms": " | ".join(sorted(all_syns, key=lambda s: s.lower())),
            "groups": " | ".join(formatted),
        })

    return entries


if __name__ == "__main__":
    entries = load_all_synonyms()
    print(f"Toplam Üretilen Kayıt: {len(entries)}")
    for test_w in ["beden", "yüz", "baş", "göz", "akıl", "yol", "kitap", "el", "güzel", "kalp"]:
        e = next((x for x in entries if x["word"] == test_w), None)
        print(f"\n=== \"{test_w}\" ===")
        if e and e["groups"]:
            for g in e["groups"].split(" | "):
                name, words = g.split("::")
                w_list = words.split(",")
                print(f"  {name} ({len(w_list)} kelime): {', '.join(w_list[:10])}{'...' if len(w_list) > 10 else ''}")
        else:
            print("  (Eş anlamlı yok)")
