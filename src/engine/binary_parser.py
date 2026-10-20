# -*- coding: utf-8 -*-
"""
engine/binary_parser.py — MTU.TES Binary Stream & Slot Parser

Exact port of the MTU.EXE thesaurus routines (code segment 3):
  - FUN_1010_2fec: slot loader (24-bit offset table, 0xFF redirect stubs)
  - FUN_1010_256c: record decoder, sub-record selection and grouping
Headword and suffix strings come from engine.tur_lexicon (FUN_1010_2e73 /
FUN_1010_2f55) and are concatenated verbatim, exactly like the EXE.
"""

import struct
from typing import List, Optional, Tuple

from core.constants import ALPHABET, TOPIC_NAMES
from core.text import fold_circumflex, tr_lower
from engine.tur_lexicon import TurLexicon

SLOT_COUNT = 32000

# Group label table at DGROUP 0x15CD: index by record group code
_GROUP_LABELS = ["1.Anlam", "Mecaz", "Argo", "Renk", "Türemiş"] + TOPIC_NAMES[4:]


def match_key(text: str) -> str:
    """Letter-class key used by the EXE comparisons (DGROUP 0xA8B & 0x1F): ignores case and circumflex."""
    return fold_circumflex(tr_lower(text))


def read_slot_table(data: bytes) -> List[int]:
    """The 32,000 × 3-byte little-endian offsets at the start of MTU.TES / MTU.ING (FUN_1010_2fec)."""
    if len(data) < SLOT_COUNT * 3:
        return []
    return [data[i * 3] | (data[i * 3 + 1] << 8) | (data[i * 3 + 2] << 16) for i in range(SLOT_COUNT)]


def sort_key(text: str) -> List[int]:
    """FUN_1010_2e13: letters compare by alphabet class + 0x21, anything else as a space (0x20)."""
    key = []
    for ch in match_key(text):
        pos = ALPHABET.find(ch)
        key.append(pos + 0x21 if 0 <= pos < 32 else 0x20)
    return key


def group_label(code: int, anlam_no: int) -> str:
    """Group name for a group code, as built at the end of FUN_1010_256c."""
    if code >= 0x10:
        return TOPIC_NAMES[code - 0x10 + 4] if code - 0x10 + 4 < len(TOPIC_NAMES) else f"#{code:02X}"
    if code < 5:
        return f"{anlam_no}.Anlam"
    if code < 7:
        return _GROUP_LABELS[1]
    if code < 9:
        return _GROUP_LABELS[2]
    return _GROUP_LABELS[code - 6] if code - 6 < len(_GROUP_LABELS) else f"#{code:02X}"


class TesBinaryParser:
    """Decodes MTU.TES slots into the EXE's string buffer and synonym groups."""

    def __init__(self, lexicon: TurLexicon, tes_data: bytes, tes_offsets: Optional[List[int]] = None):
        self.lex = lexicon
        self.tes_data = tes_data
        self.tes_offsets = tes_offsets if tes_offsets is not None else read_slot_table(tes_data)
        self._buffers = {}  # build_buffer() per TUR index: decoding a slot does not depend on anything else

    # FUN_1010_2fec
    def load_slot(self, idx: int) -> Tuple[int, bytes]:
        redirected = False
        seen = set()
        while 0 <= idx < len(self.tes_offsets) - 1:
            off1, off2 = self.tes_offsets[idx], self.tes_offsets[idx + 1]
            slot = self.tes_data[off1:off2] if off2 >= off1 else b""
            if len(slot) == 3 and slot[0] == 0xFF:
                # A redirect to an empty slot just before itself loops forever in the EXE
                # (MTU.ING "ahfat", "itburun" hang the dictionary window); report no data instead.
                if (idx, redirected) in seen:
                    return idx, b""
                seen.add((idx, redirected))
                idx = slot[1] | (slot[2] << 8)
                redirected = True
                continue
            if not slot and redirected:
                idx += 1
                redirected = False
                continue
            return idx, slot
        return idx, b""

    def load_with_homonyms(self, idx: int) -> Tuple[int, bytes]:
        """Advances through same-spelled homonyms while their slots are empty (FUN_1010_256c loop)."""
        key = match_key(self.lex.word(idx))
        while True:
            if idx + 1 >= self.lex.word_count:
                return idx, b""
            idx2, slot = self.load_slot(idx)
            if slot:
                return idx2, slot
            idx += 1
            if match_key(self.lex.word(idx)) != key:
                return idx, b""

    def chain(self, slot: bytes, p: int, first_is_word: bool) -> Tuple[str, int]:
        text = ""
        first = first_is_word
        while p + 2 <= len(slot):
            raw = struct.unpack("<H", slot[p:p + 2])[0]
            p += 2
            text += self.lex.word(raw & 0x7FFF) if first else self.lex.suffix(raw & 0x7FFF)
            first = False
            if not raw & 0x8000:
                break
        return text, p

    def build_buffer(self, idx: int) -> Tuple[List[str], List[int], int, str]:
        """
        Decodes a slot into the EXE string buffer (cached; callers must not modify the lists).
        Returns (entries, codes, alias_depth, alias_target): entries[0] is the
        headword; codes[i] is the group code of entries[i] (0x80 = sub-record title).
        """
        if idx not in self._buffers:
            self._buffers[idx] = self._build_buffer(idx)
        return self._buffers[idx]

    def _build_buffer(self, idx: int) -> Tuple[List[str], List[int], int, str]:
        start_idx = idx
        idx, slot = self.load_with_homonyms(idx)
        if not slot:
            return [], [], 0, ""

        # Some homonym classes keep the originally matched headword (Section 6 check in FUN_1010_256c)
        flags = self.lex.section6_flags(idx)
        cls = self.lex.sec6[self.lex.section6_index(idx) * 4 + 2]
        keep_start = ((flags & 0x4000) and (cls & 0x0C) == 0x08) or (not flags & 0x4000 and (cls & 0x30) == 0x20)
        headword = self.lex.word(start_idx if keep_start and start_idx != idx else idx)
        query_word = headword
        entries: List[str] = []
        codes: List[int] = [0]
        current = headword
        alias_depth = 0
        alias_target = ""

        if slot[0] == 0xC0:
            entries.append(current)
            alias_depth = 1
            p = 1
            target_idx = None
            while p + 2 <= len(slot):
                raw = struct.unpack("<H", slot[p:p + 2])[0]
                p += 2
                if target_idx is None:
                    target_idx = raw & 0x7FFF
                    alias_target += self.lex.word(target_idx)
                else:
                    alias_target += self.lex.suffix(raw & 0x7FFF)
                    alias_depth += 1
                if not raw & 0x8000:
                    break
            idx, slot = self.load_with_homonyms(target_idx)
            headword = self.lex.word(idx)
            current = headword
            codes.append(0)
        if not slot:
            return [], [], 0, ""

        if not slot[0] & 0x80:
            entries.append(current)
            current = ""

        last_topic = 0
        topic_code = 0
        p = 0
        while p < len(slot):
            b = slot[p]
            p += 1
            code = b & 0x0F
            if b & 0x80:
                text, p = self.chain(slot, p, first_is_word=False)
                current += text
            elif not b & 0x40:
                if code > 0x0B:
                    if code != last_topic:
                        topic_code = slot[p] + 0x10 if p < len(slot) else 0x10
                        p += 1
                        last_topic = code
                    code = topic_code
                words = []
                for _ in range(((b & 0x30) >> 4) + 1):
                    text, p = self.chain(slot, p, first_is_word=True)
                    words.append(text)
                current += " ".join(words)
            else:
                code |= 0x80
                last_topic = 0
                text, p = self.chain(slot, p, first_is_word=False)
                current += headword + text

            if alias_depth == 0 or current != query_word:
                if len(codes) <= len(entries):
                    codes.append(code)
                else:
                    codes[len(entries)] = code
                entries.append(current)
            current = ""

        if alias_depth and len(codes) > 2:
            codes[1] = codes[2]
        return entries, codes[:len(entries)], alias_depth, alias_target

    def decode(self, idx: int, typed: Optional[str] = None) -> List[Tuple[str, List[str]]]:
        """Returns the synonym groups the EXE displays for TUR index idx and the typed text."""
        entries, codes, alias_depth, alias_target = self.build_buffer(idx)
        if not entries:
            return []
        typed_key = match_key(typed if typed is not None else self.lex.word(idx))

        # Sub-record selection
        start = 0
        for i, (text, code) in enumerate(zip(entries, codes)):
            if not code & 0x80:
                continue
            if alias_depth < 2:
                n = (code & 0x0F) or len(text)
                if n <= len(typed_key) and match_key(text)[:n] == typed_key[:n]:
                    start = i
                    break
            elif text == alias_target:
                codes = codes[:i] + [codes[i + 1] if i + 1 < len(codes) else 0] + codes[i + 1:]
                entries = entries[:1] + entries[i:]
                codes = codes[:1] + codes[i:]
                start = 0
                break

        # The title entry at `start` is skipped; its members follow until the next sub-record
        members = []
        for text, code in zip(entries[start + 1:], codes[start + 1:]):
            if code & 0x80:
                break
            if text:  # an out-of-range suffix ID (one corrupt slot: "güvenoy") yields nothing
                members.append((text, code))

        groups: List[Tuple[int, List[str]]] = []
        for text, code in members:
            if groups and groups[-1][0] == code:
                groups[-1][1].append(text)
            else:
                groups.append((code, [text]))

        result: List[Tuple[str, List[str]]] = []
        anlam_no = 0
        for code, words in groups:
            if code < 5:
                anlam_no += 1
            result.append((group_label(code, anlam_no), sorted(words, key=sort_key)))
        return result
