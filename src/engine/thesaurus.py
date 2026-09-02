# -*- coding: utf-8 -*-
"""
engine/thesaurus.py — MoonStar Turkish Thesaurus Engine (Clean & Decoupled Architecture)
"""

from __future__ import annotations

import os
import struct
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

# Ensure src root is accessible for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import ALPHABET, NAMED_GROUPS, TOPIC_NAMES
from core.text import clean_tr_token, tr_lower
from engine.binary_parser import TesBinaryParser
from engine.suffix import SuffixEngine, get_suffix_table

# Global singleton suffix engine
_GLOBAL_SUFFIX_ENGINE = SuffixEngine()


def apply_tes_suffix_id(root: str, suf_id: int) -> str:
    """Backward compatible helper to apply a suffix ID to a root word."""
    return _GLOBAL_SUFFIX_ENGINE.apply_suffix(root, suf_id)


class ThesaurusEngine:
    """
    Decoupled Turkish Thesaurus Query & Navigation Engine.
    Maps MTU.TES binary records and MTU.TUR word streams to semantic synonym clusters.
    """

    def __init__(
        self,
        trk_path: Optional[str] = None,
        tur_txt_path: Optional[str] = None,
        tes_path: Optional[str] = None,
        suffix_engine: Optional[SuffixEngine] = None,
    ):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(project_root, "output")
        data_dir = os.path.join(project_root, "data")

        self.trk_path = trk_path or os.path.join(output_dir, "MTU.TRK.TXT")
        self.tur_txt_path = tur_txt_path or os.path.join(output_dir, "MTU.TUR.TXT")
        self.tes_path = tes_path or os.path.join(data_dir, "MTU.TES")

        self.suffix_engine = suffix_engine or _GLOBAL_SUFFIX_ENGINE

        self.all_vocab: Set[str] = set()
        self.tur_words: List[str] = []
        self.word_to_tur_idx: Dict[str, int] = {}
        self.word_to_tur_indices: Dict[str, List[int]] = defaultdict(list)
        self.tur_prefix_map: Dict[str, Set[str]] = defaultdict(set)

        self.tes_offsets: List[int] = []
        self.tes_data: bytes = b""

        self.subrecords: Dict[str, Tuple[int, int]] = {}

        self._load_tur()
        self._load_tes()

        self.parser = TesBinaryParser(
            tur_words=self.tur_words,
            tes_data=self.tes_data,
            tes_offsets=self.tes_offsets,
            apply_suffix_fn=self.suffix_engine.apply_suffix,
        )

        self._index_tes_derived_slots()
        self._index_tes_subrecords()

    def _load_tur(self):
        """Loads 26,775 Turkish headwords from output/MTU.TUR.TXT."""
        if not os.path.exists(self.tur_txt_path):
            return
        with open(self.tur_txt_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                w = tr_lower(line.strip())
                if w:
                    self.tur_words.append(w)
                    self.word_to_tur_indices[w].append(idx)
                    norm = w.replace("î", "i").replace("â", "a").replace("û", "u")
                    if norm != w:
                        self.word_to_tur_indices[norm].append(idx)
                    if w not in self.word_to_tur_idx:
                        self.word_to_tur_idx[w] = idx
                        if norm != w and norm not in self.word_to_tur_idx:
                            self.word_to_tur_idx[norm] = idx
                    self.all_vocab.add(w)
                    for i in range(2, min(len(w), 6)):
                        self.tur_prefix_map[w[:i]].add(w)

    def _load_tes(self):
        """Loads the 32,000-entry 24-bit relative offset table from MTU.TES."""
        if not os.path.exists(self.tes_path):
            return
        with open(self.tes_path, "rb") as f:
            self.tes_data = f.read()

        num_slots = 32000
        if len(self.tes_data) >= num_slots * 3:
            self.tes_offsets = [0] * num_slots
            for i in range(num_slots):
                off = struct.unpack("<L", self.tes_data[i * 3 : (i + 1) * 3] + b"\x00")[0]
                self.tes_offsets[i] = off

    def _index_tes_derived_slots(self):
        """Indexes slots starting with 0x80 morphological headers under derived headwords."""
        for s in range(min(len(self.tur_words), len(self.tes_offsets) - 1)):
            off1 = self.tes_offsets[s]
            off2 = self.tes_offsets[s + 1]
            if off2 - off1 >= 3 and self.tes_data[off1] == 0x80:
                p = off1 + 1
                root = self.tur_words[s]
                derived = root
                while p + 2 <= off2:
                    raw_suf = struct.unpack("<H", self.tes_data[p : p + 2])[0]
                    suf_id = raw_suf & 0x7FFF
                    has_more = bool(raw_suf & 0x8000)
                    p += 2
                    derived = self.suffix_engine.apply_suffix(derived, suf_id)
                    if not has_more:
                        break
                derived = tr_lower(derived)
                if derived and derived != root:
                    self.word_to_tur_indices[derived].append(s)
                    self.word_to_tur_idx[derived] = s
                    self.all_vocab.add(derived)

    def _index_tes_subrecords(self):
        """Indexes embedded deverbal sub-records prefixed by 0x40."""
        for s in range(min(len(self.tur_words), len(self.tes_offsets) - 1)):
            off1 = self.tes_offsets[s]
            off2 = self.tes_offsets[s + 1]
            if off2 - off1 < 6:
                continue

            slot = self.tes_data[off1:off2]
            pos = 0
            if slot[0] == 0x80:
                pos = 1
                while pos + 2 <= len(slot):
                    raw = struct.unpack("<H", slot[pos : pos + 2])[0]
                    has_more = bool(raw & 0x8000)
                    pos += 2
                    if not has_more:
                        break

            while pos < len(slot) - 3:
                if slot[pos] == 0x40:
                    p = pos + 1
                    raw_suf = struct.unpack("<H", slot[p : p + 2])[0]
                    p += 2
                    suf_id = raw_suf & 0x7FFF
                    has_more = bool(raw_suf & 0x8000)
                    root = self.tur_words[s]
                    derived = tr_lower(self.suffix_engine.apply_suffix(root, suf_id))
                    while has_more and p + 2 <= len(slot):
                        raw_suf2 = struct.unpack("<H", slot[p : p + 2])[0]
                        p += 2
                        suf_id2 = raw_suf2 & 0x7FFF
                        derived = tr_lower(self.suffix_engine.apply_suffix(derived, suf_id2))
                        has_more = bool(raw_suf2 & 0x8000)

                    if 0 < suf_id < 3218 and derived != root:
                        self.subrecords[derived] = (s, p)
                        self.all_vocab.add(derived)
                pos += 1

    def lookup(
        self,
        word: str,
        use_multi_hop: bool = True,
        max_hops: int = 2,
    ) -> List[Tuple[str, Set[str]]]:
        """
        Executes binary slot lookup directly against MTU.TES, applying runtime
        morphophonological reconstruction and semantic group dispatching.
        """
        query = tr_lower(word.strip())
        norm_query = query.replace("î", "i").replace("â", "a").replace("û", "u")

        indices = self.word_to_tur_indices.get(query, [])
        if not indices and norm_query != query:
            indices = self.word_to_tur_indices.get(norm_query, [])
        if not indices and query in self.word_to_tur_idx:
            indices = [self.word_to_tur_idx[query]]
        if not indices and norm_query in self.word_to_tur_idx:
            indices = [self.word_to_tur_idx[norm_query]]

        # Prefer primary slots over 3-byte alias stubs
        primary_slots = [
            idx for idx in indices
            if idx < len(self.tes_offsets) - 1 and (self.tes_offsets[idx + 1] - self.tes_offsets[idx] > 3)
        ]
        chosen_slots = [primary_slots[0]] if primary_slots else (indices[:1] if indices else [])

        result: List[Tuple[str, Set[str]]] = []
        for slot_idx in chosen_slots:
            slot_res = self.parser.decode_slot(slot_idx)
            result.extend(slot_res)

        if not result and (query in self.subrecords or norm_query in self.subrecords):
            sub_target = self.subrecords.get(query) or self.subrecords.get(norm_query)
            if sub_target:
                s_idx, s_pos = sub_target
                sub_res = self.parser.decode_subrecord(s_idx, s_pos)
                result.extend(sub_res)

        if result:
            # Lexical OCR corrections
            for _, ws in result:
                if "imtihal" in ws:
                    ws.discard("imtihal")
                    ws.add("imtihan")

            # Remove self query and its circumflex variants
            cleaned: List[Tuple[str, Set[str]]] = []
            for grp, ws in result:
                ws.discard(query)
                ws.discard(norm_query)
                for w in list(ws):
                    if w.replace("î", "i").replace("â", "a").replace("û", "u") == norm_query:
                        ws.discard(w)
                if ws:
                    cleaned.append((grp, ws))
            return cleaned

        return []

    def search_hop(self, word: str) -> Dict[str, Set[str]]:
        """Performs 1-hop bidirectional semantic exploration."""
        res: Dict[str, Set[str]] = defaultdict(set)
        direct = self.lookup(word)
        for grp, syns in direct:
            res[grp].update(syns)
        return dict(res)


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
    tes_path: Optional[str] = None,
) -> List[dict]:
    """Backward-compatible helper returning list of synonym dicts."""
    engine = ThesaurusEngine(trk_path, tur_txt_path, tes_path)
    entries: List[dict] = []

    for word_lower in sorted(engine.all_vocab, key=lambda s: s.lower()):
        groups_list = engine.lookup(word_lower)
        if not groups_list:
            continue

        formatted = []
        all_syns: Set[str] = set()

        for grp_name, syn_set in groups_list:
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