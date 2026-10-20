# -*- coding: utf-8 -*-
"""
engine/tur_lexicon.py — Exact port of the MTU.EXE MTU.TUR word builders

Ported from the decompiled Win16 routines in code segment 3:
  - FUN_1010_2e73: headword text for a TUR index (prefix + body + Section 6 flags)
  - FUN_1010_1bc4: body text from a Section 4 record
  - FUN_1010_2f55: suffix text from a Section 3 record
No phonetic rules are applied: the EXE concatenates these strings verbatim.
The word analyzer that uses these tables lives in engine/speller.py.
"""

import bisect
import os
import struct
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import DGROUP_FILE_OFFSET, project_path

_MUTATION_TABLE_DS = 0x1588  # final-letter mutation table (DGROUP 0x1588)

_UPPER = {"ı": "I", "i": "İ", "ğ": "Ğ", "ü": "Ü", "ş": "Ş", "ö": "Ö", "ç": "Ç", "â": "Â", "î": "Î", "û": "Û"}


def upper_tr(ch: str) -> str:
    return _UPPER.get(ch, ch.upper())


# DGROUP 0x09CA at runtime (filled by the EXE; read from the live DGROUP in data/ntvdm.exe.dmp):
# letter code → CP857 byte. c | 0x20 = circumflex, c | 0x80 = uppercase, 0x21 = space, 0x60 = apostrophe.
_CODE_TO_CP857 = bytes.fromhex(
    "6162638764656667a7688d696a6b6c6d6e6f94707172739f747581767778797a83200000000000000000008c0000000000000000000000000000960000000000"
    "8486c6a085828a8889a1d58ba4a29593e4a397ef91b19b000000000000000000274141414141454545454949494e4f4f4f4f55555941434f0000000000000000"
    "4142438044454647a64849984a4b4c4d4e4f99505152539e54559a565758595ab620000000150000000000d70000000000000000000000000000ea0000000000"
    "8e8fb6b5b790d4d2d3d6ded8a5e0e3e2e5e9ebee92b29d00000001000000000027fffc60ffffffff60fffffffffcfffcfffdfdfdfdfdfdfdfdfdfdfcfcffffff"
)


# DGROUP 0x0A8B at runtime: CP857 byte → letter class (code | 0x20 circumflex | 0x80 uppercase,
# 0x60 apostrophe, ≥ 0xFB separators). Read from the live DGROUP in data/ntvdm.exe.dmp.
_CP857_TO_CLASS = bytes.fromhex(
    "8fb6b5b790d4d2d3d6ded8a5e0e3e2e5e9ebee92b29d00000001000000000027fffc60ffffffff60fffffffffcfffcfffdfdfdfdfdfdfdfdfdfdfcfcfffffffc"
    "ff80818284858687898a8c8d8e8f90919394959698999b9c9d9e9fffffffffff6000010204050607090b0c0d0e0f10111314151618191b1c1d1e1fffffffffff"
    "831a4520404441034748464b2b0ac0c1c554d44f124e3a528b929a56ffd6971743494d514ccc8808fcfffffffffcffffff55d5ffb4c3a0c4ffffff60ffffffff"
    "ff60fcfcfcff42c2ffffffffffffffffffffc7c8c64ac9abcbffffffffffcaffcde1cfce50d0ffffffd1bad2ffffd353ffffffffffffffffffffffffffffffff"
)


def char_class(ch: str) -> int:
    """Letter class of a displayed character (DGROUP 0x0A8B)."""
    try:
        return _CP857_TO_CLASS[ch.encode("cp857")[0]]
    except (UnicodeEncodeError, IndexError):
        return 0xFF


def _code_char(c: int) -> str:
    b = _CODE_TO_CP857[c]
    if b < 0x20:
        return "?"
    try:
        return bytes([b]).decode("cp857")
    except UnicodeDecodeError:
        return "?"


_CODE_CHARS = [_code_char(c) for c in range(256)]


def code_char(c: int) -> str:
    """Letter code → character exactly as the EXE displays it (DGROUP 0x09CA)."""
    return _CODE_CHARS[c & 0xFF]


def codes_text(codes: List[int]) -> str:
    return "".join([_CODE_CHARS[c & 0xFF] for c in codes])


def unpack_body(code: int, b2: int, b3: int, area: bytes) -> List[int]:
    """
    FUN_1010_1bc4: letter codes of a 4-byte word record (MTU.TUR Section 4 or a *.SOZ record).
    `code` = flags >> 11: 0 none, 1–2 letters inline, 3–22 letters at area[b2|b3<<8],
    23+ = (code-23)//3 + 3 letters rotated by (code-23)%3. Final-letter mutation is the caller's.
    """
    if code == 0:
        return []
    if code == 1:
        return [b2]
    if code == 2:
        return [b2, b3]
    off = b2 | (b3 << 8)
    if code < 0x17:
        return list(area[off:off + code])
    n = (code - 0x17) // 3 + 3
    src = list(area[off:off + n])
    mode = (code - 0x17) % 3
    if mode == 0:
        return [src[-1]] + src[:-1]
    if mode == 1:
        return src[1:] + [src[0]]
    return src[::-1]


class TurLexicon:
    """MTU.TUR headwords, word bodies and suffixes exactly as MTU.EXE builds them."""

    def __init__(self, tur_path: Optional[str] = None, exe_path: Optional[str] = None):
        with open(tur_path or project_path("data", "MTU.TUR"), "rb") as f:
            data = f.read()
        with open(exe_path or project_path("data", "MTU.EXE"), "rb") as f:
            exe = f.read()
        start = DGROUP_FILE_OFFSET + _MUTATION_TABLE_DS
        self.mutation = exe[start:start + 256]

        pos = 4  # "MG2\x1a"
        self.word_count, self.suffix_count, sec5_len, sec6_count = struct.unpack("<4H", data[pos:pos + 8])
        pos += 8
        pos += 33 * 2  # Section 1: per-letter index into Section 3
        self.prefix_starts = list(struct.unpack("<1025H", data[pos:pos + 1025 * 2]))
        pos += 1025 * 2
        self.sec3 = data[pos:pos + self.suffix_count * 14]
        pos += self.suffix_count * 14
        self.sec4 = data[pos:pos + self.word_count * 4]
        pos += self.word_count * 4
        self.sec5 = data[pos:pos + sec5_len]
        pos += sec5_len
        self.sec6 = data[pos:pos + sec6_count * 4]

        # Decoded once; callers must not modify these lists
        self._bodies = [self._unpack_word(i) for i in range(self.word_count)]
        self._suffix_codes = [self._unpack_suffix(i) for i in range(self.suffix_count)]
        self._suffixes = [codes_text(c) for c in self._suffix_codes]
        self._words: List[str] = [self._build_word(i) for i in range(self.word_count)]

    # FUN_1010_1bc4 (Section 4 branch: bit 10 mutates the final letter of 3–22 letter bodies)
    def _unpack_word(self, idx: int) -> List[int]:
        b0, b1, b2, b3 = self.sec4[idx * 4:idx * 4 + 4]
        flags = b0 | (b1 << 8)
        body = unpack_body(flags >> 11, b2, b3, self.sec5)
        if flags & 0x400 and 3 <= flags >> 11 < 0x17:
            body[-1] = self.mutation[body[-1]]
        return body

    def body_codes(self, idx: int) -> List[int]:
        """Letter codes of the word body after the 2-letter prefix (shared list: do not modify)."""
        return self._bodies[idx]

    def section6_index(self, idx: int) -> int:
        return (self.sec4[idx * 4] | (self.sec4[idx * 4 + 1] << 8)) & 0x3FF

    def section6_flags(self, idx: int) -> int:
        s = self.section6_index(idx) * 4
        return self.sec6[s] | (self.sec6[s + 1] << 8)

    # FUN_1010_2e73
    def _build_word(self, idx: int) -> str:
        k = bisect.bisect_right(self.prefix_starts, idx, 0, 1024) - 1
        codes = [k >> 5, k & 0x1F] + self._bodies[idx]
        flags = self.section6_flags(idx)
        if flags & 0x40:
            for i in range(2):
                if codes[i] in (0x00, 0x0B, 0x1A):
                    codes[i] |= 0x20
        text = codes_text(codes)
        if flags & 0x100 and text:
            text = upper_tr(text[0]) + text[1:]
        return text

    def word(self, idx: int) -> str:
        return self._words[idx] if 0 <= idx < self.word_count else ""

    @property
    def words(self) -> List[str]:
        return self._words

    # FUN_1010_2f55
    def _unpack_suffix(self, suf_id: int) -> List[int]:
        e = self.sec3[suf_id * 14:suf_id * 14 + 14]
        n = e[0] & 0x7F
        codes = list(e[1:1 + n]) if n < 3 else list(self.sec5[(e[1] | (e[2] << 8)):(e[1] | (e[2] << 8)) + n])
        if codes and e[0] & 0x80:
            codes[-1] = self.mutation[codes[-1]]
        return codes

    def suffix_record(self, suf_id: int) -> bytes:
        """The 14-byte Section 3 record (text + morphological class data)."""
        return self.sec3[suf_id * 14:suf_id * 14 + 14]

    def suffix_codes(self, suf_id: int) -> List[int]:
        """Letter codes of a suffix (shared list: do not modify)."""
        return self._suffix_codes[suf_id] if 0 <= suf_id < self.suffix_count else []

    def suffix(self, suf_id: int) -> str:
        return self._suffixes[suf_id] if 0 <= suf_id < self.suffix_count else ""


_DEFAULT_LEXICON: Optional[TurLexicon] = None


def default_lexicon() -> TurLexicon:
    """Shared lexicon for data/MTU.TUR (loaded once)."""
    global _DEFAULT_LEXICON
    if _DEFAULT_LEXICON is None:
        _DEFAULT_LEXICON = TurLexicon()
    return _DEFAULT_LEXICON


def get_suffix_table() -> List[str]:
    """The 3,218 Section 3 suffix texts, indexed by suffix ID."""
    lexicon = default_lexicon()
    return [lexicon.suffix(i) for i in range(lexicon.suffix_count)]
