# -*- coding: utf-8 -*-
"""
engine/trk.py — MTU.TRK English→Turkish dictionary window (İngilizce Türkçe Sözlük)

Exact port of the MTU.EXE routine FUN_1010_397b (code segment 3), which the
dictionary dialog (DICTDLG) calls whenever the typed text changes:
  - the first two typed letters (ASCII a–z, case folded) pick one of the 676
    blocks of the 2,031-byte header (3-byte block offsets, the first one zero);
  - every word of that block that starts with the typed text is listed, in
    file order, and the first one is selected;
  - the Turkish text of the selected word is split into the lines of the
    "Türkçe Karşılıklar" list, and its first line fills "Türkçe Karşılık".
"""

import os
import struct
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import DGROUP_FILE_OFFSET, project_path

_HEADER = 0x7EF               # bytes FUN_1010_0391(3) reads into DGROUP 0x93F7 (3 + 676 × 3)
_SUFFIX_TABLE_DS = 0x1697     # pointers to the English suffixes ("ability", …)
_SUFFIX_COUNT = 195
_NUMBER = "%2d."              # ds:0x1E63
_INDENT = "   "               # ds:0x1E68
_STATIC_WIDTH = 0x3C          # "Türkçe Karşılık" shows 60 characters


class TrkDictionary:
    """MTU.TRK as the MTU.EXE İngilizce Türkçe Sözlük window reads it."""

    def __init__(self, trk_path: Optional[str] = None, exe_path: Optional[str] = None):
        with open(trk_path or project_path("data", "MTU.TRK"), "rb") as f:
            self.data = f.read()
        with open(exe_path or project_path("data", "MTU.EXE"), "rb") as f:
            exe = f.read()
        self.suffixes = []
        for i in range(_SUFFIX_COUNT):
            p = DGROUP_FILE_OFFSET + struct.unpack_from("<H", exe, DGROUP_FILE_OFFSET + _SUFFIX_TABLE_DS + 2 * i)[0]
            self.suffixes.append(exe[p:exe.index(b"\0", p)])
        self._blocks = {}

    def _block_range(self, k: int) -> Tuple[int, int]:
        start = struct.unpack("<I", self.data[k * 3:k * 3 + 3] + b"\0")[0]
        end = struct.unpack("<I", self.data[k * 3 + 3:k * 3 + 6] + b"\0")[0]
        return start, end

    def block(self, k: int) -> List[Tuple[bytes, bool, int]]:
        """Entries of 2-letter block k: (word after the prefix, capitalized, Turkish text offset)."""
        if k not in self._blocks:
            start, end = self._block_range(k)
            data, pos, stop = self.data, _HEADER + start, _HEADER + end
            prev, out = b"", []
            while pos < stop:
                flags = data[pos]
                pos += 1
                text = prev[:flags & 0x1F] if flags & 0x40 else b""
                suffix = None
                if flags & 0x80:
                    suffix = data[pos]
                    pos += 1
                end_text = data.index(b"\xFF", pos)
                text += data[pos:end_text]
                pos = end_text + 1
                if suffix is not None:
                    text += self.suffixes[suffix]
                ptr = data[pos] << 16 | data[pos + 1] | data[pos + 2] << 8
                pos += 3
                out.append((text, bool(flags & 0x20), ptr))
                prev = text
            self._blocks[k] = out
        return self._blocks[k]

    @staticmethod
    def _fold(text: str) -> bytes:
        """Typed text as FUN_1010_397b compares it: CP857, only A–Z lowercased."""
        raw = text.encode("cp857", errors="replace")
        return bytes(b + 0x20 if 0x40 < b < 0x5B else b for b in raw)

    def lookup(self, typed: str) -> List[dict]:
        """Words listed for the typed text, in the EXE's order (the first one is selected)."""
        key = self._fold(typed)
        if len(key) < 2 or not (0x60 < key[0] < 0x7B and 0x60 < key[1] < 0x7B):
            return []
        k = (key[0] - 0x61) * 26 + key[1] - 0x61
        prefix = key[:2]
        result = []
        for text, capital, ptr in self.block(k):
            if text[:len(key) - 2] != key[2:]:
                continue
            word = prefix + text
            if capital and 0x60 < word[0] < 0x7F:
                word = bytes([word[0] - 0x20]) + word[1:]
            result.append({"en": word.decode("cp857"), "ptr": ptr})
        return result

    def entries(self) -> List[dict]:
        """Every word in the EXE's order (2-letter blocks aa…zz, file order inside a block)."""
        out = []
        for k in range(676):
            prefix = bytes([0x61 + k // 26, 0x61 + k % 26])
            for text, capital, ptr in self.block(k):
                key = prefix + text
                word = bytes([key[0] - 0x20]) + key[1:] if capital else key
                lines = self.meaning_lines(ptr)
                out.append({"en": word.decode("cp857", errors="replace"),
                            "key": key.decode("cp857", errors="replace"), "lines": lines})
        return out

    def meaning_lines(self, ptr: int) -> List[str]:
        """FUN_1010_397b (second call): lines of the "Türkçe Karşılıklar" list."""
        # 14 words point at corrupt text; the EXE shows it as it is, undecodable bytes become U+FFFD
        return [line.decode("cp857", errors="replace") for line in self._meaning_bytes(ptr)]

    def _meaning_bytes(self, ptr: int) -> List[bytes]:
        pos = _HEADER + ptr
        n = struct.unpack("<H", self.data[pos:pos + 2])[0]
        raw = self.data[pos + 2:pos + 2 + n].split(b"\0")[0]
        lines, cur, number, i = [], b"", 1, 0
        numbered = raw[:1] == b"\xFF"
        if numbered:
            i = 1
        while True:
            if i >= len(raw):
                lines.append(cur)
                return lines
            if numbered:
                cur += (_NUMBER % number).encode()
                number += 1
            while i < len(raw) and raw[i] != 0xFF:
                if raw[i] == 0x7C:  # '|'
                    i += 1
                    lines.append(cur)
                    cur = _INDENT.encode() if numbered and (i >= len(raw) or raw[i] != 0xFF) else b""
                else:
                    cur += raw[i:i + 1]
                    i += 1
            if i >= len(raw):
                lines.append(cur)
                return lines
            i += 1  # 0xFF: next numbered meaning

    @staticmethod
    def first_meaning(lines: List[str]) -> str:
        """The "Türkçe Karşılık" text: the first line without its number, at most 60 characters."""
        text = lines[0] if lines else ""
        if text[:1] == " " or "1" <= text[:1] <= "8":
            text = text[3:]
        return text[:_STATIC_WIDTH]
