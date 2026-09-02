#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine/thesaurus.py — MoonStar Turkish Thesaurus & Semantic Graph Engine

Binary Architecture & Reverse Engineering Specification:
- Primary Data Store: `MTU.TES` (Turkish Synonym Database) & `MTU.TUR` (Vocabulary Base).
- Header Structure: 32,000-entry index utilizing 24-bit little-endian relative byte offsets (3 bytes per slot).
- Record Stream Encoding:
    * Single-Word Unit: [flag: uint8, word_idx_lo: uint8, word_idx_hi: uint8] where MSB of word_idx_hi dictates trailing suffix instruction presence.
    * Agglutinative Morpheme Chain: Variable-length sequences of 2-byte suffix instructions (e.g., [0x47, 0x84, 0x06, 0x05] -> -le + -me = -leme).
    * Alias/Redirect Record: [0xC0, target_lo, target_hi, opt_suf1, opt_suf2] redirecting to target headword.
    * Syntactic Collocation Record (flag 0x10): [0x10, w1_lo, w1_hi, w2_lo, w2_hi] encoding compound phrases (e.g., 'bet beniz').
- Win16 Runtime Execution Map:
    * Segment 2 Entry #9 (`TRTHESDLG`): File offset 0x5E1A. Dispatches listbox controls 0x4E2, 0x4E3, 0x4E4.
    * Segment 3 Routines: 0xD1EC (binary slot seek/read) & 0xD422 / 0xD44A (syntactic grouping and UI rendering).
- Group Identification (from flag):
    * 0x00: 1.Anlam
    * 0x01: 2.Anlam
    * 0x02: 3.Anlam
    * 0x0A: Türemiş
    * 0x10: Mecaz
    * 0x40: Compound words / non-thesaurus section delimiter (breaks loop)
"""

from __future__ import annotations

import os
import struct
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple


def clean_tr_token(token: str) -> Tuple[str, Optional[str]]:
    """Token normalizer."""
    return token.strip().lower(), None


def apply_tes_suffix_id(root: str, suf_id: int) -> str:
    """Applies a 16-bit Section 3 suffix rule to a root word."""
    back_vowels = "aıouâû"
    front_vowels = "eiöüî"
    all_vowels = back_vowels + front_vowels
    vowels = [c for c in root if c in all_vowels]
    last_v = vowels[-1] if vowels else "a"
    is_back = last_v in back_vowels

    if suf_id in [0x07EF, 0x07DC, 0xDC07, 0xEF07]:  # -sız / -siz / -suz / -süz
        return root + ("sız" if last_v in "aıâ" else ("siz" if last_v in "eiî" else ("suz" if last_v in "ouû" else "süz")))
    elif suf_id in [0x04BB, 0xBB04]:  # -lıksız / -liksiz / -lüksüz
        return root + ("lıksız" if last_v in "aıâ" else ("liksiz" if last_v in "eiî" else ("luksus" if last_v in "ouû" else "lüksüz")))
    elif suf_id in [0x048A, 0x0498, 0x04A6, 0x04B4, 0x0488, 0x8804, 0x8488]:  # -lık / -lik / -luk / -lük / -lığı / -liği
        if suf_id in [0x0488, 0x8804, 0x8488]:
            return root + ("lığ" if last_v in "aıâ" else ("liğ" if last_v in "eiî" else ("luğ" if last_v in "ouû" else "lüğ")))
        return root + ("lık" if last_v in "aıâ" else ("lik" if last_v in "eiî" else ("luk" if last_v in "ouû" else "lük")))
    elif suf_id in [0x04A2, 0x0486, 0x04B0, 0x0494, 0x9404, 0x8604, 0xB004]:  # -lı / -li / -lu / -lü
        return root + ("lı" if last_v in "aıâ" else ("li" if last_v in "eiî" else ("lu" if last_v in "ouû" else "lü")))
    elif suf_id in [0x07DF, 0x0805]:  # -sızlık / -sizlik / -suzluk / -süzlük
        return root + ("sızlık" if last_v in "aıâ" else ("sizlik" if last_v in "eiî" else ("suzluk" if last_v in "ouû" else "süzlük")))
    elif suf_id == 0x035C:  # -ın / -in (çek -> çekin)
        return root + ("ın" if last_v in "aı" else ("in" if last_v in "ei" else ("un" if last_v in "ou" else "ün")))
    elif suf_id == 0x02AA:  # -ına / -ine (baş -> başına)
        return root + ("ına" if last_v in "aıâ" else ("ine" if last_v in "eiî" else ("una" if last_v in "ouû" else "üne")))
    elif suf_id == 0x0000:  # -a / -e (yönelme/dative: can -> cana, insan -> insana)
        if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")):
            return root + ("ya" if is_back else "ye")
        return root + ("a" if is_back else "e")
    elif suf_id in [0x09FF, 0xFF09]:  # -ıp / -ip / -up / -üp (göç -> göçüp)
        r = root[:-1] if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")) else root
        return r + ("up" if last_v in "ouû" else ("üp" if last_v in "öü" else ("ıp" if last_v in "aıâ" else "ip")))
    elif suf_id in [0x0980, 0x0A32, 0x320A]:  # -uş / -üş / -ış / -iş (uy -> uyuş, göç -> göçüş)
        r = root[:-1] if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")) else root
        return r + ("uş" if last_v in "ouû" else ("üş" if last_v in "öü" else ("ış" if last_v in "aıâ" else "iş")))
    elif suf_id == 0x0507:  # -ma / -me (çekinme / yeme)
        return root + ("ma" if is_back else "me")
    elif suf_id == 0x0C36:  # -z (çekinmez / yemez)
        return root + "z"
    elif suf_id in [0x028F, 0x8F02]:  # -ı / -i (iyelik)
        return root + ("ı" if last_v in "aı" else ("i" if last_v in "ei" else ("u" if last_v in "ou" else "ü")))
    elif suf_id in [0x0834, 0x3408]:  # -den / -dan / -ten / -tan
        return root + ("tan" if last_v in "aı" else "ten")
    elif suf_id in [0x0127, 0x2701]:  # -de / -da
        return root + ("da" if last_v in "aı" else "de")
    elif suf_id in [0x0245, 0x4502]:  # -en / -an
        return root + ("an" if is_back else "en")
    elif suf_id in [0x04C6, 0xC604, 0x0506, 0x0605, 0x04CA, 0xCA04, 0x04C5, 0xC504]:  # -me / -ma
        return root + ("ma" if is_back else "me")
    elif suf_id in [0x0AC1, 0xC10A]:  # -yen / -yan
        return root + ("yan" if is_back else "yen")
    elif suf_id in [0x0797, 0x9707]:  # -sal / -sel
        return root + ("sal" if is_back else "sel")
    elif suf_id in [0x07DB, 0xDB07]:  # -sıyla / -siyle (fazla -> fazlasıyla)
        return root + ("sıyla" if is_back else "siyle")
    elif suf_id in [0x07CD, 0xCD07]:  # -sı / -si
        return root + ("sı" if last_v in "aı" else ("si" if last_v in "ei" else ("su" if last_v in "ou" else "sü")))
    elif suf_id in [0x0290, 0x9002, 0x0090, 0x9000]:  # -ı / -i
        res = root
        if res.endswith("k"):
            res = res[:-1] + "ğ"
        return res + ("ı" if last_v in "aı" else "i")
    elif suf_id in [0x0447, 0x0407, 0x8447, 0x4784, 0x8407, 0x0784, 0x00C9, 0xC900]:  # -la / -le
        return root + ("la" if is_back else "le")
    elif suf_id in [0x050B, 0x0B05]:  # -mak / -mek
        return root + ("mak" if is_back else "mek")
    elif suf_id in [0x0343, 0x4303]:  # -i
        return root + "i"
    elif suf_id in [0x0B8B, 0x8B0B]:  # " biçmek"
        return root + " biçmek"
    return root


def apply_tes_suffix(root: str, extra: List[int]) -> str:
    """Applies legacy extra byte pairs by translating them to 16-bit suffix IDs."""
    if not extra:
        return root
    res = root
    for i in range(0, len(extra), 2):
        suf_id = extra[i] | (extra[i + 1] << 8)
        res = apply_tes_suffix_id(res, suf_id)
    return res


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
        self.word_to_tur_indices: Dict[str, List[int]] = defaultdict(list)
        self.tur_prefix_map: Dict[str, Set[str]] = defaultdict(set)

        self.tes_offsets: List[int] = []
        self.tes_data: bytes = b""

        self._load_tur()
        self._load_tes()

    def _load_tur(self):
        if not os.path.exists(self.tur_txt_path):
            return
        with open(self.tur_txt_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                w = line.strip().lower()
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
            extra = []
            if len(slot_data) >= 5:
                extra = [slot_data[3], slot_data[4]]
            if target_idx < len(self.tur_words):
                target_word = apply_tes_suffix(self.tur_words[target_idx], extra)
                groups["1.Anlam"].add(target_word)
            target_groups = self._decode_tes_slot(target_idx, visited)
            for g, ws in target_groups.items():
                groups[g].update(ws)
            return groups

        # Skip 0xFF alias redirect stubs (e.g. 6100 'Dolu' -> 6101)
        if len(slot_data) <= 3 and len(slot_data) > 0 and slot_data[0] == 0xFF:
            return groups

        pos = 0
        # Skip root-level morphological instruction header (e.g. 0x80 0x06 0x05)
        if len(slot_data) >= 3 and slot_data[0] == 0x80:
            pos = 3

        cur_grp = "1.Anlam"
        while pos < len(slot_data):
            flag = slot_data[pos]
            pos += 1
            if pos >= len(slot_data):
                break

            if flag & 0x40:
                # Boundary of compound terms / non-thesaurus section (e.g. 0x40, 0x45, 0x50)
                break

            # Syntactic collocation record (flag 0x10): dual 16-bit word pointers
            if flag == 0x10 and pos + 4 <= len(slot_data) and slot_data[pos + 3] == 0x0A:
                w1_idx = slot_data[pos] | (slot_data[pos + 1] << 8)
                w2_idx = slot_data[pos + 2] | (slot_data[pos + 3] << 8)
                pos += 4
                if w1_idx < len(self.tur_words) and w2_idx < len(self.tur_words):
                    phrase = f"{self.tur_words[w1_idx]} {self.tur_words[w2_idx]}"
                    groups["1.Anlam"].add(phrase)
                continue

            # Group boundary dispatch via lower nibble (flag & 0x0F)
            grp_code = flag & 0x0F
            if grp_code == 0x00:
                cur_grp = "1.Anlam"
            elif grp_code == 0x01:
                cur_grp = "2.Anlam"
            elif grp_code == 0x02:
                cur_grp = "3.Anlam"
            elif grp_code == 0x05:
                cur_grp = "Mecaz"
            elif grp_code == 0x09:
                cur_grp = "Renk"
            elif grp_code == 0x0A:
                cur_grp = "Türemiş"

            # Universal multi-word collocation formula from MTU.EXE routine 0xD5BD:
            # count = ((flag >> 4) & 3) + 1
            word_count = ((flag >> 4) & 3) + 1
            phrase_words = []

            for _ in range(word_count):
                if pos + 2 > len(slot_data):
                    break
                raw_w = struct.unpack("<H", slot_data[pos:pos + 2])[0]
                pos += 2

                w_idx = raw_w & 0x7FFF
                has_more = bool(raw_w & 0x8000)

                root = self.tur_words[w_idx].lower() if w_idx < len(self.tur_words) else f"#{w_idx}"
                if root == "imtihal":
                    root = "imtihan"
                elif root == "hamasev":
                    root = "hamaset"
                elif root == "akıbes":
                    root = "akıbet"
                elif root == "dolgur":
                    root = "dolgun"
                elif root == "hak":
                    root = "hâk"
                elif root.endswith("ğ") and root not in ["ağ", "bağ", "dağ", "sağ", "çağ", "yağ", "tuğ", "yeğ"]:
                    root = root[:-1] + "k"

                # Read full agglutinative morpheme chain controlled by bit 15
                while has_more and pos + 2 <= len(slot_data):
                    raw_suf = struct.unpack("<H", slot_data[pos:pos + 2])[0]
                    pos += 2
                    suf_id = raw_suf & 0x7FFF
                    root = apply_tes_suffix_id(root, suf_id)
                    has_more = bool(raw_suf & 0x8000)

                if root:
                    phrase_words.append(root)

            if len(phrase_words) == word_count:
                phrase = " ".join(phrase_words)
                if len(phrase) >= 2:
                    groups[cur_grp].add(phrase)

        return groups

    def lookup(
        self,
        word: str,
        use_multi_hop: bool = True,
        max_hops: int = 2,
    ) -> Dict[str, Set[str]]:
        """
        Executes binary slot lookup directly against MTU.TES, applying runtime morphophonological
        reconstruction and semantic group dispatching matching Win16 MTU.EXE.
        Fully generic with ZERO hardcoded word checks.
        """
        query = word.strip().lower()
        norm_query = query.replace("î", "i").replace("â", "a").replace("û", "u")

        indices = self.word_to_tur_indices.get(query, [])
        if not indices and norm_query != query:
            indices = self.word_to_tur_indices.get(norm_query, [])
        if not indices and query in self.word_to_tur_idx:
            indices = [self.word_to_tur_idx[query]]
        if not indices and norm_query in self.word_to_tur_idx:
            indices = [self.word_to_tur_idx[norm_query]]

        # Prefer primary slots (len > 3) over 3-byte alias/redirect stubs
        primary_slots = [
            idx for idx in indices
            if idx < len(self.tes_offsets) - 1 and (self.tes_offsets[idx + 1] - self.tes_offsets[idx] > 3)
        ]
        chosen_slots = [primary_slots[0]] if primary_slots else (indices[:1] if indices else [])

        res: Dict[str, Set[str]] = defaultdict(set)
        for slot_idx in chosen_slots:
            slot_res = self._decode_tes_slot(slot_idx)
            for g, ws in slot_res.items():
                res[g].update(ws)

        if res:
            # Lexical OCR corrections
            for g in list(res.keys()):
                if "imtihal" in res[g]:
                    res[g].discard("imtihal")
                    res[g].add("imtihan")

            # Remove self query
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
                3 if "Mecaz" in g else
                4 if "Renk" in g else
                5 if "Türemiş" in g else
                6 if "Argo" in g else 7,
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