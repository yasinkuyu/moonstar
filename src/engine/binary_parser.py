# -*- coding: utf-8 -*-
"""
engine/binary_parser.py — MTU.TES Binary Stream & Slot Parser
"""

import os
import struct
import sys
from typing import Callable, List, Optional, Set, Tuple

# Ensure src root is accessible for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import NAMED_GROUPS, TOPIC_NAMES
from core.text import clean_tr_token, tr_lower


class TesBinaryParser:
    """
    Parses binary record streams for MTU.TES corresponding to
    Borland C++ Win16 routines 0xD1EC, 0xD422, and 0xD5BD.
    """

    def __init__(
        self,
        tur_words: List[str],
        tes_data: bytes,
        tes_offsets: List[int],
        apply_suffix_fn: Callable[[str, int], str],
    ):
        self.tur_words = tur_words
        self.tes_data = tes_data
        self.tes_offsets = tes_offsets
        self.apply_suffix_fn = apply_suffix_fn

    def decode_subrecord(self, slot_idx: int, start_pos: int) -> List[Tuple[str, Set[str]]]:
        """Decodes an embedded deverbal subrecord initiated by a 0x40 delimiter."""
        if slot_idx >= len(self.tes_offsets) - 1:
            return []
        off1 = self.tes_offsets[slot_idx]
        off2 = self.tes_offsets[slot_idx + 1]
        slot = self.tes_data[off1:off2]

        result: List[Tuple[str, Set[str]]] = []
        cur_grp = "1.Anlam"
        anlam_counter = 1
        prev_grp_code = None
        cur_grp_idx: int = -1
        p = start_pos

        while p < len(slot):
            flag = slot[p]
            if flag & 0x40:
                break
            p += 1

            grp_code = flag & 0x0F
            if grp_code == 0x0C and p < len(slot):
                top_id = slot[p]
                p += 1
                if top_id + 4 < len(TOPIC_NAMES):
                    cur_grp = TOPIC_NAMES[top_id + 4]
                else:
                    cur_grp = "1.Anlam"
                prev_grp_code = (grp_code, top_id)
                cur_grp_idx = len(result)
                result.append((cur_grp, set()))
            elif grp_code != prev_grp_code:
                prev_grp_code = grp_code
                if grp_code in NAMED_GROUPS:
                    cur_grp = NAMED_GROUPS[grp_code]
                else:
                    cur_grp = f"{anlam_counter}.Anlam"
                    anlam_counter += 1
                cur_grp_idx = len(result)
                result.append((cur_grp, set()))

            word_count = ((flag >> 4) & 3) + 1
            phrase_words: List[str] = []
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
                    root = self.apply_suffix_fn(root, suf_id)
                    has_more = bool(raw_suf & 0x8000)

                if root:
                    phrase_words.append(root)

            if len(phrase_words) == word_count:
                phrase = " ".join(phrase_words)
                if len(phrase) >= 2 and cur_grp_idx >= 0:
                    result[cur_grp_idx][1].add(phrase)

        return result

    def decode_slot(
        self,
        slot_idx: int,
        visited: Optional[Set[int]] = None,
    ) -> List[Tuple[str, Set[str]]]:
        """
        Parses binary record streams for the specified slot.
        Returns List[Tuple[str, Set[str]]] preserving order and allowing duplicate group names.
        """
        if visited is None:
            visited = set()
        if slot_idx in visited or slot_idx >= len(self.tes_offsets) - 1:
            return []
        visited.add(slot_idx)

        off1 = self.tes_offsets[slot_idx]
        off2 = self.tes_offsets[slot_idx + 1]
        if off1 >= off2 or off2 > len(self.tes_data):
            return []

        slot_data = self.tes_data[off1:off2]
        result: List[Tuple[str, Set[str]]] = []
        cur_grp_idx: int = -1

        def _start_group(grp_name: str) -> None:
            nonlocal cur_grp_idx
            cur_grp_idx = len(result)
            result.append((grp_name, set()))

        def _add_word(word: str) -> None:
            if cur_grp_idx >= 0:
                result[cur_grp_idx][1].add(word)

        def _merge_result(ext: List[Tuple[str, Set[str]]]) -> None:
            for g, ws in ext:
                found = False
                for i, (eg, ews) in enumerate(result):
                    if eg == g:
                        ews.update(ws)
                        found = True
                        break
                if not found:
                    result.append((g, set(ws)))

        # Alias/Redirect Record: flag & 0xC0 == 0xC0
        if len(slot_data) >= 3 and (slot_data[0] & 0xC0) == 0xC0:
            target_idx = slot_data[1] | ((slot_data[2] & 0x7F) << 8)
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
                                    sub_res = self.decode_subrecord(target_idx, scan + 3)
                                    _merge_result(sub_res)
                                    break
                            scan += 1

                    # Build the derived synonym word by applying the full suffix chain
                    derived = root
                    for sid in suffix_chain:
                        derived = self.apply_suffix_fn(derived, sid)
                    if derived != root:
                        _start_group("1.Anlam")
                        _add_word(derived)

                    if found_sub:
                        return result
                else:
                    _start_group("1.Anlam")
                    _add_word(root)

            # Fall through to target slot's full data
            target_groups = self.decode_slot(target_idx, visited)
            _merge_result(target_groups)
            return result

        pos = 0

        # Skip morphological header (0x80)
        if len(slot_data) >= 3 and slot_data[0] == 0x80:
            pos = 1
            while pos + 2 <= len(slot_data):
                raw = struct.unpack("<H", slot_data[pos:pos + 2])[0]
                has_more = bool(raw & 0x8000)
                pos += 2
                if not has_more:
                    break

        cur_grp = "1.Anlam"
        anlam_counter = 1
        prev_grp_code = None

        while pos < len(slot_data):
            flag = slot_data[pos]
            pos += 1
            if pos >= len(slot_data):
                break

            if flag & 0x40:
                break

            # Syntactic dual collocation
            if flag == 0x10 and pos + 4 <= len(slot_data) and slot_data[pos + 3] == 0x0A:
                w1_idx = slot_data[pos] | (slot_data[pos + 1] << 8)
                w2_idx = slot_data[pos + 2] | (slot_data[pos + 3] << 8)
                pos += 4
                if w1_idx < len(self.tur_words) and w2_idx < len(self.tur_words):
                    phrase = f"{self.tur_words[w1_idx]} {self.tur_words[w2_idx]}"
                    _add_word(phrase)
                continue

            grp_code = flag & 0x0F
            if grp_code == 0x0C and pos < len(slot_data):
                top_id = slot_data[pos]
                pos += 1
                if top_id + 4 < len(TOPIC_NAMES):
                    cur_grp = TOPIC_NAMES[top_id + 4]
                else:
                    cur_grp = "1.Anlam"
                prev_grp_code = (grp_code, top_id)
                _start_group(cur_grp)
            elif grp_code != prev_grp_code:
                prev_grp_code = grp_code
                if grp_code in NAMED_GROUPS:
                    cur_grp = NAMED_GROUPS[grp_code]
                else:
                    cur_grp = f"{anlam_counter}.Anlam"
                    anlam_counter += 1
                _start_group(cur_grp)

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

                while has_more and pos + 2 <= len(slot_data):
                    raw_suf = struct.unpack("<H", slot_data[pos:pos + 2])[0]
                    pos += 2
                    suf_id = raw_suf & 0x7FFF
                    root = self.apply_suffix_fn(root, suf_id)
                    has_more = bool(raw_suf & 0x8000)

                if root:
                    phrase_words.append(root)

            if len(phrase_words) == word_count:
                phrase = " ".join(phrase_words)
                if len(phrase) >= 2:
                    _add_word(phrase)

        return result
