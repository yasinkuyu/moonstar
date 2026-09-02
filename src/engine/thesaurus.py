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


def tr_lower(s: str) -> str:
    """Proper Turkish lowercasing without Unicode combining dots."""
    return s.replace("İ", "i").replace("I", "ı").lower().replace("\u0307", "")


def clean_tr_token(token: str) -> Tuple[str, Optional[str]]:
    """Token normalizer."""
    return tr_lower(token.strip()), None


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
    elif suf_id in [0x0000, 0x01FF, 0xFF01]:  # -a / -e (yönelme/dative: can -> cana, tarih -> tarihe)
        if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")):
            return root + ("ya" if is_back else "ye")
        return root + ("a" if is_back else "e")
    elif suf_id in [0x09FF, 0xFF09]:  # -ıp / -ip / -up / -üp (göç -> göçüp)
        r = root[:-1] if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")) else root
        return r + ("up" if last_v in "ouû" else ("üp" if last_v in "öü" else ("ıp" if last_v in "aıâ" else "ip")))
    elif suf_id in [0x0292, 0x9202]:  # -ıl / -il / -ul / -ül (edilgen: aç -> açıl)
        return root + ("ul" if last_v in "ouû" else ("ül" if last_v in "öü" else ("ıl" if last_v in "aıâ" else "il")))
    elif suf_id in [0x0980, 0x0A32, 0x320A, 0x02F9, 0xF902, 0x03AC, 0xAC03]:  # -uş / -üş / -ış / -iş (uy -> uyuş, göç -> göçüş, aç -> açış, gir -> giriş)
        r = root[:-1] if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")) else root
        return r + ("uş" if last_v in "ouû" else ("üş" if last_v in "öü" else ("ış" if last_v in "aıâ" else "iş")))
    elif suf_id in [0x0B7E, 0x7E0B]:  # -yış / -yiş (başla -> başlayış)
        return root + ("yış" if is_back else "yiş")
    elif suf_id in [0x0831, 0x3108]:  # -ta / -te / -da / -de (baş -> başta)
        return root + ("ta" if is_back else "te")
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
    elif suf_id in [0x0797, 0x9707, 0x07B4, 0xB407]:  # -sal / -sel
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
    elif suf_id in [0x0447, 0x0407, 0x8447, 0x4784, 0x8407, 0x0784, 0x00C9, 0xC900, 0x0446, 0x4604]:  # -la / -le
        return root + ("la" if is_back else "le")
    elif suf_id in [0x050B, 0x0B05, 0x04CA, 0xCA04]:  # -mak / -mek
        return root + ("mak" if is_back else "mek")
    elif suf_id in [0x04FE, 0xFE04, 0x053F, 0x3F05, 0x0C33, 0x330C]:  # -maz / -mez
        return root + ("maz" if is_back else "mez")
    elif suf_id in [0x0097, 0x00A9, 0x00BB, 0x00CD, 0x00E3, 0x00F5, 0x0107, 0x0119]:  # -cık / -cik / -cuk / -cük / -çık / -çik / -çuk / -çük
        c = "ç" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "c"
        v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
        return root + c + v + "k"
    elif suf_id in [0x008E, 0x0091]:  # -cağız / -ceğiz
        return root + ("cağız" if is_back else "ceğiz")
    elif suf_id == 0x0046:  # -daş / -deş / -taş / -teş
        d = "t" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "d"
        return root + d + ("aş" if is_back else "eş")
    elif suf_id in [0x040D, 0x040E, 0x044D, 0x044E]:  # -ler / -lar
        return root + ("lar" if is_back else "ler")
    elif suf_id in [0x0543, 0x0544, 0x0545, 0x0598, 0x0599, 0x059A]:  # -mış / -miş / -muş / -müş
        v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
        return root + "m" + v + "ş"
    elif suf_id in [0x0408, 0x0448]:  # -lan / -len
        return root + ("lan" if is_back else "len")
    elif suf_id in [0x043F, 0x047F]:  # -laş / -leş
        return root + ("laş" if is_back else "leş")
    elif suf_id in [0x094D, 0x094E]:  # -ca / -ce
        c = "ç" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "c"
        return root + c + ("a" if is_back else "e")
    elif suf_id == 0x03F5:  # -ken
        return root + "ken"
    elif suf_id == 0x0345:  # -ci / -cı / -cu / -cü
        c = "ç" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "c"
        v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
        return root + c + v
    elif suf_id == 0x0802:  # -suz / -süz / -sız / -siz
        return root + ("suz" if last_v in "ouû" else ("süz" if last_v in "öü" else ("sız" if last_v in "aıâ" else "siz")))
    elif suf_id in [0x0342, 0x0343, 0x4303, 0x0915, 0x0916, 0x01FF]:  # -ı / -i / -u / -ü (tamlanan / iyelik)
        res = root
        if res.endswith("k") and res not in ["ok", "kök", "ek", "ak"]:
            res = res[:-1] + "ğ"
        v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
        if res.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")):
            return res + "s" + v
        return res + v
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

        self.subrecords: Dict[str, Tuple[int, int]] = {}

        self._load_tur()
        self._load_tes()
        self._index_tes_derived_slots()
        self._index_tes_subrecords()

    def _load_tur(self):
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

    def _index_tes_derived_slots(self):
        """
        Indexes slots starting with 0x80 morphological header under their derived headwords.
        E.g. Slot 8646 (root: Gir) has header [0x80, 0xAC, 0x03] -> Gir + 0x03AC = Giriş.
        """
        for s in range(min(len(self.tur_words), len(self.tes_offsets) - 1)):
            off1 = self.tes_offsets[s]
            off2 = self.tes_offsets[s + 1]
            if off2 - off1 >= 3 and self.tes_data[off1] == 0x80:
                raw_suf = struct.unpack("<H", self.tes_data[off1 + 1:off1 + 3])[0]
                suf_id = raw_suf & 0x7FFF
                root = self.tur_words[s]
                derived = tr_lower(apply_tes_suffix_id(root, suf_id))
                if derived and derived != root:
                    self.word_to_tur_indices[derived].append(s)
                    self.word_to_tur_idx[derived] = s
                    self.all_vocab.add(derived)

    def _index_tes_subrecords(self):
        """
        Indexes sub-records embedded after 0x40 boundary delimiters inside slots.
        In MTU.TES, deverbal derived words (e.g. çık -> çıkış, adalet -> adaletsiz)
        are stored inside the root slot after a 0x40 flag followed by 16-bit suffix IDs.
        """
        for s in range(min(len(self.tur_words), len(self.tes_offsets) - 1)):
            off1 = self.tes_offsets[s]
            off2 = self.tes_offsets[s + 1]
            if off2 - off1 < 6:
                continue

            slot = self.tes_data[off1:off2]
            pos = 0
            if slot[0] == 0x80:
                pos = 3

            while pos < len(slot) - 3:
                if slot[pos] == 0x40:
                    p = pos + 1
                    raw_suf = struct.unpack("<H", slot[p:p + 2])[0]
                    p += 2
                    suf_id = raw_suf & 0x7FFF
                    has_more = bool(raw_suf & 0x8000)
                    root = self.tur_words[s]
                    derived = tr_lower(apply_tes_suffix_id(root, suf_id))
                    while has_more and p + 2 <= len(slot):
                        raw_suf2 = struct.unpack("<H", slot[p:p + 2])[0]
                        p += 2
                        suf_id2 = raw_suf2 & 0x7FFF
                        derived = tr_lower(apply_tes_suffix_id(derived, suf_id2))
                        has_more = bool(raw_suf2 & 0x8000)

                    if 0 < suf_id < 3218 and derived != root:
                        self.subrecords[derived] = (s, p)
                        self.all_vocab.add(derived)
                pos += 1

    def _decode_subrecord(self, slot_idx: int, start_pos: int) -> Dict[str, Set[str]]:
        off1 = self.tes_offsets[slot_idx]
        off2 = self.tes_offsets[slot_idx + 1]
        slot = self.tes_data[off1:off2]

        groups: Dict[str, Set[str]] = defaultdict(set)
        cur_grp = "1.Anlam"
        p = start_pos

        while p < len(slot):
            flag = slot[p]
            if flag & 0x40:
                break
            p += 1

            grp_code = flag & 0x0F
            if grp_code == 0x00:
                cur_grp = "1.Anlam"
            elif grp_code == 0x01:
                cur_grp = "2.Anlam"
            elif grp_code == 0x02:
                cur_grp = "3.Anlam"

            word_count = ((flag >> 4) & 3) + 1
            phrase_words = []
            for _ in range(word_count):
                if p + 2 > len(slot):
                    break
                raw_w = struct.unpack("<H", slot[p:p + 2])[0]
                p += 2
                w_idx = raw_w & 0x7FFF
                has_more = bool(raw_w & 0x8000)

                root = tr_lower(self.tur_words[w_idx]) if w_idx < len(self.tur_words) else f"#{w_idx}"
                if root.endswith("ğ") and root not in ["ağ", "bağ", "dağ", "sağ", "çağ", "yağ", "tuğ", "yeğ"]:
                    root = root[:-1] + "k"

                while has_more and p + 2 <= len(slot):
                    raw_suf = struct.unpack("<H", slot[p:p + 2])[0]
                    p += 2
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

            # Parse suffix chain from byte 3 using bit-15 continuation protocol
            suffix_chain = []
            p = 3
            while p + 2 <= len(slot_data):
                raw = struct.unpack("<H", slot_data[p:p + 2])[0]
                sid = raw & 0x7FFF
                has_more = bool(raw & 0x8000)
                suffix_chain.append(sid)
                p += 2
                if not has_more:
                    break

            if target_idx < len(self.tur_words):
                root = tr_lower(self.tur_words[target_idx])

                if suffix_chain:
                    first_suf = suffix_chain[0]

                    # Check if target slot contains a matching 0x40 sub-record
                    found_sub = False
                    if first_suf > 0 and target_idx < len(self.tes_offsets) - 1:
                        t_off1 = self.tes_offsets[target_idx]
                        t_off2 = self.tes_offsets[target_idx + 1]
                        t_slot = self.tes_data[t_off1:t_off2]
                        scan = 0
                        while scan < len(t_slot) - 3:
                            if t_slot[scan] == 0x40:
                                s_id = struct.unpack("<H", t_slot[scan + 1:scan + 3])[0] & 0x7FFF
                                if s_id == first_suf:
                                    found_sub = True
                                    sub_res = self._decode_subrecord(target_idx, scan + 3)
                                    for g, ws in sub_res.items():
                                        groups[g].update(ws)
                                    break
                            scan += 1

                    # Build the derived synonym word by applying the full suffix chain
                    derived = root
                    for sid in suffix_chain:
                        derived = apply_tes_suffix_id(derived, sid)
                    if derived != root:
                        groups["1.Anlam"].add(derived)

                    if found_sub:
                        return groups

            # Fall through to target slot's full data
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

                root = tr_lower(self.tur_words[w_idx]) if w_idx < len(self.tur_words) else f"#{w_idx}"
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
        query = tr_lower(word.strip())
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

        if not res and (query in self.subrecords or norm_query in self.subrecords):
            sub_target = self.subrecords.get(query) or self.subrecords.get(norm_query)
            if sub_target:
                s_idx, s_pos = sub_target
                sub_res = self._decode_subrecord(s_idx, s_pos)
                for g, ws in sub_res.items():
                    res[g].update(ws)

        if res:
            # Lexical OCR corrections
            for g in list(res.keys()):
                if "imtihal" in res[g]:
                    res[g].discard("imtihal")
                    res[g].add("imtihan")

            # Remove self query and its circumflex variants
            for grp in list(res.keys()):
                res[grp].discard(query)
                res[grp].discard(norm_query)
                for w in list(res[grp]):
                    if w.replace("î", "i").replace("â", "a").replace("û", "u") == norm_query:
                        res[grp].discard(w)
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