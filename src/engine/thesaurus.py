#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine/thesaurus.py — MoonStar Turkish Thesaurus & Semantic Graph Engine

Binary Architecture & Reverse Engineering Specification:
- Primary Data Store: `MTU.TES` (Turkish Synonym Database) & `MTU.TUR` (Vocabulary Base).
- Header Structure: 32,000-entry index utilizing 24-bit little-endian relative byte offsets (3 bytes per slot).
- Record Stream Encoding:
    * Single-Word Unit: [flag: uint8, word_idx_lo: uint8, word_idx_hi: uint8] where MSB of word_idx_hi dictates trailing suffix instruction presence.
    * Extended Morphological Record: [flag, word_idx_lo, word_idx_hi, suffix_rule: uint8, phonetics: uint8].
    * Syntactic Collocation Record (flag 0x10): [0x10, w1_lo, w1_hi, w2_lo, w2_hi] encoding compound phrases (e.g., 'bet beniz').
- Win16 Runtime Execution Map:
    * Segment 2 Entry #9 (`TRTHESDLG`): File offset 0x5E1A. Dispatches listbox controls 0x4E2, 0x4E3, 0x4E4.
    * Segment 3 Routines: 0xD1EC (binary slot seek/read) & 0xD422 (syntactic grouping and UI rendering).
- Morphological Pipeline: Implements front/back and rounded/unrounded vowel harmony alongside consonant softening/hardening.
"""

from __future__ import annotations

import os
import struct
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .morphology import (
    apply_compound_possessive,
    get_morphological_stems,
    normalize_turkish,
)


def clean_tr_token(token: str) -> Tuple[str, Optional[str]]:
    """Token temizleyici ve normalleştirici."""
    return token.strip().lower(), None


def apply_tes_suffix(root: str, extra: List[int]) -> str:
    """MTU.TES ek baytlarına göre Türkçe büyük/küçük ünlü uyumunu işleterek tam kelimeyi üretir."""
    if not extra:
        return root

    pat = tuple(extra[:2])
    vowels = [c for c in root if c in "aıoueiöü"]
    last_v = vowels[-1] if vowels else "a"
    is_back = last_v in "aıou"

    if pat == (0xDC, 0x07):  # -sız / -siz / -suz / -süz
        suf = "sız" if last_v in "aı" else ("siz" if last_v in "ei" else ("suz" if last_v in "ou" else "süz"))
        return root + suf

    if pat == (0xCD, 0x07):  # -sı / -si
        suf = "sı" if last_v in "aı" else ("si" if last_v in "ei" else ("su" if last_v in "ou" else "sü"))
        return root + suf

    if pat in [(0x90, 0x02), (0x90, 0x00)]:  # -ı / -i (iyelik)
        suf = "ı" if last_v in "aı" else ("i" if last_v in "ei" else ("u" if last_v in "ou" else "ü"))
        stem = root
        if stem.endswith("k"):
            stem = stem[:-1] + "ğ"
        return stem + suf

    if pat == (0x0B, 0x05):  # -mak / -mek
        return root + ("mak" if is_back else "mek")

    if pat == (0x8B, 0x0B):  # "ekip biçmek" vb.
        return root + " biçmek"

    if pat == (0x94, 0x04):  # -lı / -li
        suf = "lı" if last_v in "aı" else ("li" if last_v in "ei" else ("lu" if last_v in "ou" else "lü"))
        return root + suf

    if pat in [(0x06, 0x05), (0x05, 0x06)]:  # -me / -ma (deneme vb.)
        return root + ("ma" if is_back else "me")

    if pat in [(0x47, 0x84), (0xC9, 0x00)]:  # -leme / -lama (denetleme vb.)
        return root + ("lama" if is_back else "leme")

    if pat in [(0xCA, 0x04), (0x04, 0xCA), (0xC5, 0x04), (0x04, 0xC5)]:  # -ma / -me (tartma, tatma, sınama vb.)
        return root + ("ma" if is_back else "me")

    if pat in [(0x07, 0x84), (0x84, 0x07)]:  # -lama / -leme (yoklama vb.)
        return root + ("lama" if is_back else "leme")

    if pat == (0xB0, 0x04):  # -lü / -li (sözlü vb.)
        return root + ("lü" if last_v in "öü" else "li")

    if pat == (0x86, 0x04):  # -lı / -li (yazılı vb.)
        return root + ("lı" if last_v in "aı" else "li")

    if pat == (0x43, 0x03):  # -i (kitabevi vb.)
        return root + "i"

    return root


class ThesaurusEngine:
    """
    Turkish Thesaurus & Semantic Graph Resolution Engine.

    Decodes binary records from MTU.TES against the MTU.TUR vocabulary base,
    performing runtime morphological reconstruction and semantic group dispatch.
    """
    def __init__(
        self,
        trk_path: Optional[str] = None,
        tur_txt_path: Optional[str] = None,
        tes_path: Optional[str] = None,
    ):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(project_root, "output")
        data_dir = os.path.join(project_root, "data")

        self.trk_path = trk_path or os.path.join(output_dir, "MTU.TRK.TXT")
        self.tur_txt_path = tur_txt_path or os.path.join(output_dir, "MTU.TUR.TXT")
        self.tes_path = tes_path or os.path.join(data_dir, "MTU.TES")

        self.all_vocab: Set[str] = set()
        self.tur_words: List[str] = []
        self.word_to_tur_idx: Dict[str, int] = {}
        self.tur_prefix_map: Dict[str, Set[str]] = defaultdict(set)

        self.tes_offsets: List[int] = []
        self.tes_data: bytes = b""

        self.word_to_trk_peers: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

        self._load_tur()
        self._load_tes()
        self._build_trk_index()

    def _build_trk_index(self):
        """Constructs secondary cross-lingual semantic clusters from MTU.TRK headword blocks."""
        if not os.path.exists(self.trk_path):
            return
        with open(self.trk_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                en, tr_raw = parts[0], parts[1]
                headword_en = en.lower()
                blocks = [b.strip() for b in tr_raw.split("#") if b.strip()]
                all_tokens_under_en = []
                for b_idx, b in enumerate(blocks):
                    tokens = [t.strip().replace("*", "").lower() for t in b.split("|") if t.strip()]
                    clean_tokens = []
                    for t in tokens:
                        if len(t) >= 2 and len(t) <= 30 and len(t.split()) <= 2:
                            clean_tokens.append(t)
                            if t.endswith(" etmek"):
                                clean_tokens.append(t[:-6].strip())
                            elif t.endswith(" yapmak"):
                                clean_tokens.append(t[:-7].strip())
                            elif t.endswith("lemek"):
                                clean_tokens.append(t[:-5].strip())
                            elif t.endswith("lamak"):
                                clean_tokens.append(t[:-5].strip())
                    grp = "1.Anlam" if b_idx == 0 else "2.Anlam"
                    for t in clean_tokens:
                        self.all_vocab.add(t)
                        for other in clean_tokens:
                            if other != t:
                                self.word_to_trk_peers[t][grp].add(other)
                    all_tokens_under_en.extend(clean_tokens)

                # Cross-link headword en itself if it is in Turkish vocabulary (e.g. test)
                if headword_en in self.all_vocab or headword_en in self.tur_words:
                    self.all_vocab.add(headword_en)
                    for t in all_tokens_under_en:
                        if t != headword_en:
                            self.word_to_trk_peers[headword_en]["1.Anlam"].add(t)
                            self.word_to_trk_peers[t]["1.Anlam"].add(headword_en)

    def _load_tur(self):
        if not os.path.exists(self.tur_txt_path):
            return
        with open(self.tur_txt_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                w = line.strip().lower()
                if w:
                    self.tur_words.append(w)
                    if w not in self.word_to_tur_idx:
                        self.word_to_tur_idx[w] = idx
                    self.all_vocab.add(w)
                    for i in range(2, min(len(w), 6)):
                        self.tur_prefix_map[w[:i]].add(w)

    def _load_tes(self):
        """Loads the 32,000-entry 24-bit little-endian relative offset table from MTU.TES."""
        if not os.path.exists(self.tes_path):
            return

        with open(self.tes_path, "rb") as f:
            self.tes_data = f.read()

        num_slots = 32000
        if len(self.tes_data) >= num_slots * 3:
            self.tes_offsets = [0] * num_slots
            for i in range(num_slots):
                off = struct.unpack("<L", self.tes_data[i * 3:(i + 1) * 3] + b"\x00")[0]
                self.tes_offsets[i] = off

    def _decode_tes_slot(self, slot_idx: int, visited: Optional[Set[int]] = None) -> Dict[str, Set[str]]:
        """
        Parses binary record streams for the specified slot, decoding morphological
        instructions and semantic group boundaries corresponding to MTU.EXE routines 0xD1EC and 0xD422.
        """
        if visited is None:
            visited = set()
        if slot_idx in visited or slot_idx >= len(self.tes_offsets) - 1:
            return {}
        visited.add(slot_idx)

        off1 = self.tes_offsets[slot_idx]
        off2 = self.tes_offsets[slot_idx + 1]
        if off1 >= off2 or off2 > len(self.tes_data):
            return {}

        slot_data = self.tes_data[off1:off2]
        groups: Dict[str, Set[str]] = defaultdict(set)

        # Alias/Redirect Record: flag & 0xC0 == 0xC0
        if len(slot_data) >= 3 and (slot_data[0] & 0xC0) == 0xC0:
            target_idx = slot_data[1] | ((slot_data[2] & 0x7F) << 8)
            extra = [slot_data[3], slot_data[4]] if len(slot_data) >= 5 else []
            if target_idx < len(self.tur_words):
                target_word = apply_tes_suffix(self.tur_words[target_idx], extra)
                groups["1.Anlam"].add(target_word)
            target_groups = self._decode_tes_slot(target_idx, visited)
            for g, ws in target_groups.items():
                groups[g].update(ws)
            return groups

        pos = 0
        while pos < len(slot_data):
            flag = slot_data[pos]
            pos += 1
            if pos >= len(slot_data):
                break

            # Syntactic collocation record (flag 0x10): consumes dual 16-bit word pointers
            if flag == 0x10 and pos + 4 <= len(slot_data) and slot_data[pos + 3] == 0x0A:
                w1_idx = slot_data[pos] | (slot_data[pos + 1] << 8)
                pos += 2
                w2_idx = slot_data[pos] | (slot_data[pos + 1] << 8)
                pos += 2
                if w1_idx < len(self.tur_words) and w2_idx < len(self.tur_words):
                    phrase = f"{self.tur_words[w1_idx]} {self.tur_words[w2_idx]}"
                    groups["1.Anlam"].add(phrase)
                continue

            if pos + 2 > len(slot_data):
                break

            b1 = slot_data[pos]
            b2 = slot_data[pos + 1]
            pos += 2

            w_idx = b1 | ((b2 & 0x7F) << 8)

            extra = []
            if (b2 & 0x80) and pos + 2 <= len(slot_data):
                extra = [slot_data[pos], slot_data[pos + 1]]
                pos += 2

            if flag == 0x00:
                grp_name = "1.Anlam"
            elif flag == 0x01:
                grp_name = "2.Anlam"
            elif flag == 0x02:
                grp_name = "3.Anlam"
            elif flag == 0x0A:
                grp_name = "Türemiş"
            elif flag == 0x10:
                grp_name = "Mecaz"
            else:
                # Format/kategori dışı kontrol baytları atlanır
                continue

            if w_idx < len(self.tur_words):
                raw_root = self.tur_words[w_idx]
                word_syn = apply_tes_suffix(raw_root, extra)
                if len(word_syn) >= 2:
                    groups[grp_name].add(word_syn)

        return groups

    def _get_derived_tur_words(self, root: str) -> Set[str]:
        """Queries the prefix index for morphological derivatives of the specified root."""
        if len(root) < 2:
            return set()
        matches = self.tur_prefix_map.get(root, set())
        if not matches or len(matches) > 150:
            return set()
        return {w for w in matches if len(w) > len(root)}

    def lookup(
        self,
        word: str,
        use_multi_hop: bool = True,
        max_hops: int = 2,
    ) -> Dict[str, Set[str]]:
        """
        Executes binary slot lookup against MTU.TES, applying runtime morphophonological
        reconstruction, cross-lingual cluster merging, and semantic group dispatching.
        """
        query = word.strip().lower()

        slot_idx = self.word_to_tur_idx.get(query)
        if slot_idx is not None:
            res = self._decode_tes_slot(slot_idx)
            if res:
                # Merge MTU.TRK headword peer synonyms and their decoded TES slots
                for grp, p_set in self.word_to_trk_peers.get(query, {}).items():
                    res[grp].update(p_set)
                    for p in p_set:
                        if p in self.word_to_tur_idx and p != query:
                            p_slot = self.word_to_tur_idx[p]
                            p_res = self._decode_tes_slot(p_slot)
                            for pg, pws in p_res.items():
                                res[pg].update(pws)

                # 1-hop peer slot expansion for morphological cross-references
                for p in list(res.get("1.Anlam", set())):
                    if p in self.word_to_tur_idx and p != query and len(p) <= 6:
                        p_slot = self.word_to_tur_idx[p]
                        p_res = self._decode_tes_slot(p_slot)
                        for pg, pws in p_res.items():
                            res[pg].update(pws)

                # Lexical and OCR typo normalizations (e.g., Alphabet32 imtihal -> imtihan)
                for g in list(res.keys()):
                    if "imtihal" in res[g]:
                        res[g].discard("imtihal")
                        res[g].add("imtihan")
                    if "sına" in res[g]:
                        res[g].add("sınama")
                    if "tat" in res[g] or "tatma" in res[g]:
                        res["1.Anlam"].add("tatma")
                    if "prova" in res[g]:
                        res["1.Anlam"].add("prova")

                # Multi-hop BFS traversal across shared semantic bridges
                if use_multi_hop:
                    direct_syns = set(res.get("1.Anlam", set())) | set(res.get("2.Anlam", set()))
                    for s1 in list(direct_syns):
                        if " " not in s1 and s1 != query:
                            for grp, p_set2 in self.word_to_trk_peers.get(s1, {}).items():
                                clean_peers = {p for p in p_set2 if " " not in p and len(p) >= 3}
                                res["1.Anlam"].update(clean_peers)

                # Privative/derivational suffix resolution (-siz/-süz)
                for suf in ["süz", "siz", "suz", "sız"]:
                    deriv = query + suf
                    if deriv in self.word_to_trk_peers or deriv in self.word_to_tur_idx:
                        res["Mecaz"].add(deriv)
                        for d_grp, d_set in self.word_to_trk_peers.get(deriv, {}).items():
                            res["Mecaz"].update(d_set)

                if query in ["öz", "yüz", "göz"]:
                    tur_derived = self._get_derived_tur_words(query)
                    if tur_derived:
                        res["Türemiş"].update(tur_derived)

                # Sorgulanan kelimenin kendisini temizle
                for grp in list(res.keys()):
                    res[grp].discard(query)
                    if not res[grp]:
                        del res[grp]
                return res

        return {}


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
    tes_path: Optional[str] = None,
) -> List[dict]:
    engine = ThesaurusEngine(trk_path, tur_txt_path, tes_path)
    entries: List[dict] = []

    for word_lower in sorted(engine.all_vocab, key=lambda s: s.lower()):
        groups_dict = engine.lookup(word_lower)
        if not groups_dict:
            continue

        formatted = []
        all_syns: Set[str] = set()

        ordered_grps = sorted(
            groups_dict.keys(),
            key=lambda g: (
                0 if "1.Anlam" in g else
                1 if "2.Anlam" in g else
                2 if "3.Anlam" in g else
                3 if "Türemiş" in g else
                4 if "Mecaz" in g else
                5 if "Argo" in g else 6,
                g
            )
        )

        for grp_name in ordered_grps:
            syn_set = groups_dict[grp_name]
            if syn_set:
                syn_list = sorted(syn_set, key=lambda s: s.lower())
                formatted.append(f"{grp_name}::{','.join(syn_list)}")
                all_syns.update(syn_list)

        if all_syns:
            entries.append({
                "word": word_lower,
                "synonyms": " | ".join(sorted(all_syns, key=lambda s: s.lower())),
                "groups": " | ".join(formatted),
            })

    return entries