# -*- coding: utf-8 -*-
"""
engine/ing.py — MTU.ING Turkish→English Dictionary (Türkçe İngilizce Sözlük)

Exact port of the MTU.EXE routine FUN_1010_3114 (code segment 3). MTU.ING
shares the MTU.TES slot table (32,000 × 3-byte offsets, indexed by MTU.TUR
word index, loaded by FUN_1010_2fec(1)). A slot holds Turkish entries (u16
word/suffix chains) each followed by its English meaning labels, which are
6-bit encoded text with an English morpheme table (DGROUP 0x1617).
"""

import os
import struct
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import ALPHABET, DGROUP_FILE_OFFSET, TOPIC_NAMES, project_path
from engine.binary_parser import TesBinaryParser
from engine.speller import Speller
from engine.tur_lexicon import TurLexicon, char_class, default_lexicon, upper_tr

_MORPHEME_TABLE_DS = 0x1617

# Label characters replaced by the 11-entry jump table at CS:0x361C (codes of
# Turkish-only letters, which English text never needs)
_SPECIAL_CODES = {
    0x03: " ", 0x08: ",", 0x0A: "?", 0x12: "/", 0x17: "(", 0x23: ".",
    0x28: "'", 0x2B: "!", 0x32: "-", 0x37: ")", 0x3A: "é",  # 0x3A → byte 0x82 = CP857 "é"
}


def topic_index(topic: int) -> Optional[int]:
    """Label topic byte (header bit 0x20) → index into TOPIC_NAMES: 1 = Anatomi (4) … 32 = Yerbilim (35)."""
    return topic + 3 if 1 <= topic and topic + 3 < len(TOPIC_NAMES) else None


def topic_name(topic: int) -> Optional[str]:
    idx = topic_index(topic)
    return TOPIC_NAMES[idx] if idx is not None else None


class IngDictionary:
    """Turkish→English entries decoded exactly like the MTU.EXE dictionary window."""

    def __init__(self, ing_path: Optional[str] = None, exe_path: Optional[str] = None,
                 lexicon: Optional[TurLexicon] = None):
        self.lexicon = lexicon or default_lexicon()
        with open(ing_path or project_path("data", "MTU.ING"), "rb") as f:
            self.data = f.read()
        with open(exe_path or project_path("data", "MTU.EXE"), "rb") as f:
            exe = f.read()
        self.morphemes = [self._exe_cstr(exe, self._exe_u16(exe, _MORPHEME_TABLE_DS + 2 * i)) for i in range(64)]
        self.slots = TesBinaryParser(self.lexicon, self.data)  # same slot table and loader as MTU.TES
        self.offsets = self.slots.tes_offsets
        self.analyzer = Speller.for_windows(self.lexicon)

    @staticmethod
    def _exe_u16(exe: bytes, ds_off: int) -> int:
        return struct.unpack("<H", exe[DGROUP_FILE_OFFSET + ds_off:DGROUP_FILE_OFFSET + ds_off + 2])[0]

    @staticmethod
    def _exe_cstr(exe: bytes, ds_off: int) -> str:
        start = DGROUP_FILE_OFFSET + ds_off
        return exe[start:exe.index(b"\x00", start)].decode("cp1254")

    def _label_text(self, slot: bytes, p: int) -> Tuple[str, int]:
        text = ""
        while p < len(slot):
            c = slot[p]
            p += 1
            e = c & 0x3F
            if c & 0x40:
                text += self.morphemes[e]
            elif e in _SPECIAL_CODES:
                text += _SPECIAL_CODES[e]
            elif c & 0x20:
                text += upper_tr(ALPHABET[e & 0x1F])
            else:
                text += ALPHABET[e]
            if c & 0x80:
                break
        return text, p

    def decode_slot(self, slot: bytes) -> List[Dict]:
        """FUN_1010_3114 record loop: entries with their meaning labels."""
        entries: List[Dict] = []
        p = 0
        numbered = 0
        while p < len(slot):
            b = slot[p]
            p += 1
            if not b & 0x80:
                words = []
                for _ in range(((b >> 4) & 3) + 1):
                    text, p = self.slots.chain(slot, p, first_is_word=True)
                    words.append(text)
                entries.append({"tr": " ".join(words), "labels": []})
                numbered = 0
                continue
            register = topic = 0
            if b & 0x10:
                register = slot[p]
                p += 1
            if b & 0x20:
                topic = slot[p]
                p += 1
            if b & 0x40:
                numbered += 1
                prefix = "%2d." % numbered
            else:
                prefix = "   " if numbered else ""
            text, p = self._label_text(slot, p)
            if not entries:
                entries.append({"tr": "", "labels": []})
            entries[-1]["labels"].append({
                "text": prefix + text,
                "pos": b & 0x0F,
                "register": register,
                "topic": topic,
            })
        return entries

    def entries_for_index(self, idx: int) -> List[Dict]:
        _, slot = self.slots.load_with_homonyms(idx)
        return self.decode_slot(slot) if slot else []

    def all_entries(self) -> List[Dict]:
        """Every Turkish entry in MTU.ING, in file order."""
        result: List[Dict] = []
        for idx in range(min(self.lexicon.word_count, len(self.offsets) - 1)):
            off1, off2 = self.offsets[idx], self.offsets[idx + 1]
            slot = self.data[off1:off2] if off2 > off1 else b""
            if not slot or (len(slot) == 3 and slot[0] == 0xFF):
                continue
            result.extend(self.decode_slot(slot))
        return result

    def lookup(self, word: str) -> Optional[Dict]:
        """The entry the EXE window selects for the typed word (FUN_1010_3114 selection)."""
        idx, typed = self.analyzer.window_index(word.strip())
        if idx is None:
            return None
        entries = self.entries_for_index(idx)
        if not entries:
            return None
        keys = [[char_class(ch) & 0x1F for ch in e["tr"]] for e in entries]
        n = len(typed)
        selected = 0
        for i, key in enumerate(keys):
            if len(key) >= n and key[:n] == typed:
                selected = i
                break
        if selected == 0:
            best = 0
            for i, key in enumerate(keys):
                common = 0
                while common < min(len(key), n) and key[common] == typed[common]:
                    common += 1
                if common > best:
                    selected, best = i, common
        return entries[selected]
