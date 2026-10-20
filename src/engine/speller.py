# -*- coding: utf-8 -*-
"""
engine/speller.py — MTU.EXE spell checker (Türkçe Denetim): word decisions and suggestions

Port of the spell-check path in code segment 3:
  - FUN_1010_0842: check one word (minimum length, capitalization, sentence state)
  - FUN_1010_0a0e: stem search in MTU.TUR, then in the user dictionary (MTU.SOZ)
  - FUN_1010_1d8b / 1e22 / 1f1e / 1f9c / 20de / 234d: validation. Spell mode uses
    DGROUP 0x8B8C = 0; suggestion mode (0x8B8C = 0x40) accepts and repairs instead
    (option byte DGROUP 0x7A1B = 0x94 as stored in MTU.INI)
  - FUN_1010_07bf: Roman numerals
  - FUN_1010_0ba3 / 0f93 / 10e4 / 116c / 1396 / 144d / 158a: suggestions
  - FUN_1010_0391 / 04b9: *.SOZ user dictionary file format
"""

import os
import struct
from typing import Dict, Iterator, List, Optional, Tuple

from core.constants import ALPHABET, project_path
from core.text import fold_circumflex, tr_lower
from engine.tur_lexicon import TurLexicon, code_char, codes_text, default_lexicon, unpack_body, upper_tr

SENTENCE_START = 0x80          # DGROUP 0x8B8B state before the first word of a sentence
DEFAULT_OPTIONS = 0x94         # DGROUP 0x009E → 0x7A1B (MTU.INI offset 0x48); bit 7 = suggestions on
DEFAULT_MIN_LENGTH = 2         # DGROUP 0x009F (MTU.INI offset 0x49)

# DGROUP 0x15AD: vowel harmony class per letter code (bit 7 = consonant)
_HARMONY = bytes.fromhex("178080c2801ec08080c0131280c88080800100c18080c0c0c401008080c08080")
# DGROUP 0x15A9: high vowel for each harmony class (ü u i ı), used to repair enclitics
_HIGH_VOWEL = bytes.fromhex("1a190b0a")
# DGROUP 0x1568: keyboard/sound position per letter code; |difference| = suggestion score
_KEY_POSITION = bytes.fromhex("112504043c120c0e0e3814140f1f1e202222262a282c2c3c323236383a372f00")
# FUN_1010_0ba3: hardened letter for a softened stem end (b→p, c→ç, d→t, ğ→k)
_HARDEN = {0x01: 0x13, 0x02: 0x03, 0x04: 0x18, 0x08: 0x0D}
# FUN_1010_07bf (CS:0x0826): letters a Roman numeral may contain
_ROMAN = {0x02, 0x0E, 0x0F, 0x1B, 0x1D}           # c l m v x
_ROMAN_UPPER_I, _ROMAN_LOWER_I = 0x0A, 0x0B       # I (typed uppercase) / i (typed lowercase)
_O_PRONOUN_CLASSES = (0x373, 0x28D)               # FUN_1010_0a0e special case for "o"
_PLACEHOLDER = 0x1D                               # letter put in an inserted slot before trying all 32
_SPACE = 0x21                                     # DGROUP 0x09CA[0x21] = ' ' (word split)
_APOSTROPHE = 0x60


def harmony_state(codes: List[int]) -> int:
    """FUN_1010_0746: harmony class of the last vowel (used after tokens that are not analysed)."""
    for c in reversed(codes):
        v = _HARMONY[c & 0x1F]
        if not v & 0x80:
            return v & 3
    return 0


def _key_distance(a: int, b: int) -> int:
    return abs(_KEY_POSITION[a & 0x1F] - _KEY_POSITION[b & 0x1F])


class UserDictionary:
    """A *.SOZ user dictionary: "MG2\\x1a", u16 count, u16 text length, text area, count × 4-byte records."""

    def __init__(self, path: str, lexicon: TurLexicon):
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] != b"MG2\x1a":
            raise ValueError(f"{path}: not a MoonStar dictionary")
        count, text_len = struct.unpack("<HH", data[4:8])
        self.lexicon = lexicon
        self.text = data[8:8 + text_len]
        rec = data[8 + text_len:8 + text_len + count * 4]
        self.records = [struct.unpack("<HH", rec[i * 4:i * 4 + 4]) for i in range(count)]
        # FUN_1010_1bc4, user-dictionary branch: bit 10 selects the dictionary's own text area
        # (in MTU.TUR the same bit means final-letter mutation); no prefix, no mutation
        self.codes = [unpack_body(flags >> 11, value & 0xFF, value >> 8,
                                  self.text if flags & 0x400 else lexicon.sec5)
                      for flags, value in self.records]

    def section6_index(self, i: int) -> int:
        return self.records[i][0] & 0x3FF

    def word(self, i: int) -> str:
        text = codes_text(self.codes[i])
        s = self.section6_index(i) * 4
        if self.lexicon.sec6[s + 1] & 0x01 and text:
            text = upper_tr(text[0]) + text[1:]
        return text

    @property
    def words(self) -> List[str]:
        return [self.word(i) for i in range(len(self.records))]


class TypedWord:
    """FUN_1010_18f3: letter codes and case flags of a typed word (DGROUP 0x8B10, 0x8B8A, 0x8B8F)."""

    def __init__(self, raw: str):
        self.raw = raw
        self.codes: List[int] = []
        self.case = 0          # 0x8B8A: 1 first upper, 2 all upper, 4 mixed, 8 backquote
        self.circ = 0          # 0x8B8F: 0x08 circumflex in the first two letters, 0x40 later
        self.period = False    # 0x8B8C & 4
        upper = letters = 0
        backquote = False
        for ch in raw:
            if ch == ".":
                self.period = True
                break
            if ch in ("'", "`"):
                backquote |= ch == "`"
                self.codes.append(_APOSTROPHE)
                continue
            low = tr_lower(ch)
            plain = fold_circumflex(low)
            pos = ALPHABET.find(plain)
            if not low or pos < 0 or pos >= 32:
                continue
            if low != ch:
                upper += 1
                if not self.codes:
                    self.case = 1
            if plain != low:
                self.circ |= 0x08 if len(self.codes) < 2 else 0x40
            letters += 1
            self.codes.append(pos)
        if upper == letters:
            self.case = 2
        elif upper != self.case:
            self.case |= 4
        if backquote:
            self.case |= 8
        stripped = raw.lstrip()
        self.first_upper = bool(stripped) and stripped[0] != stripped[0].lower()

    def variant(self, codes: List[int]) -> "TypedWord":
        """The same typed word with other letter codes (suggestion candidates keep the case flags)."""
        other = TypedWord.__new__(TypedWord)
        other.__dict__.update(self.__dict__)
        other.codes = list(codes)
        other.raw = codes_text(codes)
        return other


class _Suggestions:
    """FUN_1010_0f93 list: unique candidates, best = lowest score (DGROUP 0x8ADA / 0x8ADC)."""

    def __init__(self):
        self.items: List[str] = []
        self.best = None
        self.best_score = 0xFF

    def add(self, text: str, score: int):
        if text in self.items:
            if self.best_score == 0:
                return
            self.best = self.items.index(text)
            self.best_score = 1 if score else 0
            return
        self.items.append(text)
        if score < self.best_score:
            self.best_score = score
            self.best = len(self.items) - 1


class Speller:
    """Accepts, rejects and corrects words exactly like the MTU.EXE spell checker."""

    def __init__(self, lexicon: Optional[TurLexicon] = None, user_dictionary: Optional[str] = None,
                 options: int = DEFAULT_OPTIONS, min_length: int = DEFAULT_MIN_LENGTH,
                 use_user_dictionary: bool = True):
        self.lex = lexicon or default_lexicon()
        self.options = options
        self.min_length = min_length
        path = user_dictionary or project_path("data", "MTU.SOZ")
        self.user = UserDictionary(path, self.lex) if use_user_dictionary and os.path.exists(path) else None
        # DGROUP 0x8B8D / 0x8B82 are globals: they keep the values of the last candidate
        # analysed even when the analysis fails, and FUN_1010_0ba3 relies on that.
        self._last_state: dict = {"d": 0}
        self._pos82: Optional[int] = None
        self._c8c = 0  # DGROUP 0x8B8C bits 2 (period seen) and 3 (uncertain), shared by all candidates
        self._8b8e = 0  # DGROUP 0x8B8E: case/circumflex bits of the body compared last by FUN_1010_1b3e
        self._8ade = [0] * 256  # DGROUP 0x8ADE: last body (or suffix) unpacked by FUN_1010_1bc4 / 158a
        self._8b80 = 0  # DGROUP 0x8B80: body length FUN_1010_1f9c compares or copies (not always 0x8ADE's)

        # FUN_1010_1ac5 + 225f over Section 3: contiguous suffix records spelling each text
        self._suffix_runs: Dict[Tuple[int, ...], List[int]] = {}
        lex = self.lex
        for j in range(lex.suffix_count):
            key = tuple(lex.suffix_codes(j))
            if key not in self._suffix_runs:
                run, k = [], j
                while k < lex.suffix_count and lex.suffix_codes(k) == lex.suffix_codes(j):
                    run.append(k)
                    k += 1
                self._suffix_runs[key] = run

    def _load_8ade(self, codes: List[int]) -> int:
        self._8ade[:len(codes)] = codes
        return len(codes)

    # ─── FUN_1010_234d / 20de: suffix chains ───

    def _suffix_compatible(self, e: bytes, st: dict) -> bool:
        """FUN_1010_234d: Section 3 record `e` may follow the current morphological state."""
        e5 = e[5] | (e[6] << 8)
        e7 = e[7] | (e[8] << 8)
        bit = lambda n: (1 << n) if 0 <= n < 16 else 0
        if not e5 & bit(st["lo"] & 0x0F):
            return False
        if (e[3] & 0x0F) and not bit((e[3] & 0x0F) - 1) & st["f96"]:
            return False
        if not st["f95"] & bit((e[3] >> 4) - 1):
            return False
        if (e[4] & 0x0F) and not bit((e[4] & 0x0F) - 1) & st["f94"]:
            return False
        hi, f93 = st["hi"], st["f93"]
        if hi & 0x08:
            ok = e[10] & 0x01
        elif hi & 0x10:
            ok = e[10] & 0x04
        else:
            ok = e[10] & 0x02
        if not ok or not (0x10 << (f93 & 3)) & e[10]:
            return False
        if (hi >> 1) & 1 and not e7 & 0x10:
            return False
        if hi & 0x01 and not (e7 & (0x20 if hi & 0x80 else 0x40)):
            return False
        if (f93 & 0x0C) == 0x04 and not e7 & 0x400:
            return False
        if (f93 & 0x0C) == 0x08 and not e7 & 0x800:
            return False
        if (f93 & 0x30) == 0x10 and not e7 & 0x1000:
            return False
        if (f93 & 0x30) == 0x20 and not e7 & 0x2000:
            return False
        if not e7 & (0x4000 if hi & 0x20 else 0x8000):
            return False
        return bool(e[12] & (0x02 if f93 & 0x40 else 0x01))

    def _suffix_chain(self, rest: List[int], st: dict) -> bool:
        """FUN_1010_20de: `rest` splits into a compatible chain of Section 3 suffixes."""
        saved = dict(st)
        if rest[0] == _APOSTROPHE:
            if not st["hi"] & 0x40 or st["hi"] & 0x80 or (st["f93"] & 0x0C) == 0x08:
                return False
            rest = rest[1:]
            if not rest:
                return False
            st["hi"] |= 0x80
        for n in range(len(rest), 0, -1):
            for j in self._suffix_runs.get(tuple(rest[:n]), ()):
                e = self.lex.suffix_record(j)
                if not self._suffix_compatible(e, st):
                    continue
                st["f94"] = 0
                st["lo"] &= 0xF0
                st["f95"] = e[9]
                st["f96"] = e[11]
                st["hi"] = (st["hi"] & 0xC0) | (e[12] & 0x18)
                st["f93"] = e[13]
                if n >= len(rest) or self._suffix_chain(rest[n:], st):
                    return True
                st.clear()
                st.update(saved)
        return False

    # ─── FUN_1010_1e22 / 1f1e / 1f9c / 1d8b ───
    # `out` is DGROUP 0x8B10: in suggestion mode (lenient) the analysis repairs it in place.

    def _begin(self, s6: int, word: TypedWord, lenient: bool, stem_end: int) -> Optional[dict]:
        b0, b1, b2, b3 = self.lex.sec6[s6 * 4:s6 * 4 + 4]
        st = {"lo": b0, "hi": b1, "f93": b2, "f94": b3, "d": 0, "pos82": None}
        st["f95"], st["f96"] = (0x53, 0xBF) if b1 & 0x40 else (0xAC, 0x00)
        self._last_state = st
        st["f"] = (word.circ & 0x58) | (self._8b8e & 0xA0)
        if b1 & 0x80:
            st["f"] |= 4
        else:
            if self.options & 0x08 and b0 & 0x80:
                self._last_state = {"d": 0}
                return None
            if b1 & 0x01:
                st["f"] |= 1
                if not lenient and not word.first_upper:
                    st["d"] = 2  # proper noun typed in lower case
                if (b2 & 0x0C) == 0x08:
                    if self.options & 0x04 and b2 & 0x80:
                        st["pos82"] = self._pos82 = stem_end - 1
                        st["d"] |= 8
                    st["hi"] &= 0xFE
                else:
                    st["f93"] &= 0xF3
        return st

    def _final_check(self, st: dict, word: TypedWord, offset: int, lenient: bool, out: List[int]) -> bool:
        """FUN_1010_1f9c: compares (or, in suggestion mode, copies) DGROUP 0x8ADE[:0x8B80]."""
        if st["f93"] & 0x80:
            return False
        f, lo = st["f"], st["lo"]
        if not f & 4:
            if (not f & 0x08 or lo & 0x40) and (not f & 0x40 or f & 0x20):
                mode = (self.options & 0x30) >> 4
                if mode != 2 and (mode == 0 or lo & 0x20):
                    return True
                if lo & 0x40 and not f & 0x08:
                    st["d"] |= 4  # the word needs a circumflex on its first letters
                    for i in range(min(2, len(out))):
                        if out[i] in (0x00, 0x0B, 0x1A):
                            out[i] |= 0x20
                if not f & 0x20:
                    return True
        elif st["hi"] & 0x04 and not self._c8c & 4:
            st["d"] |= 4
            self._c8c |= 4
        for i in range(self._8b80):
            c = self._8ade[i]
            pos = offset + i
            if lenient:
                if pos < len(out):
                    out[pos] = c  # copy the stored spelling (circumflexes included)
            elif pos >= len(word.raw) or code_char(c) != word.raw[pos]:
                st["d"] |= 4
                return False
        return True

    def _accepts(self, s6: int, word: TypedWord, rest: List[int], offset: int,
                 prev: Optional[int], lenient: bool, out: List[int], stem_end: int) -> Optional[dict]:
        """FUN_1010_1d8b: the final state when the stem + remainder is accepted."""
        st = self._begin(s6, word, lenient, stem_end)
        if st is None:
            return None
        if not rest:
            # FUN_1010_1f1e
            if not st["f93"] & 0x40:
                ok = self._final_check(st, word, offset, lenient, out)
            elif prev is None:
                ok = True  # enclitic checked without a preceding word
            elif prev & 0x80:
                ok = False
            elif word.codes[:2] in ([4, 5], [4, 0]):  # "de" / "da" agree with the previous word
                ok = not ((prev if word.codes[1] == 5 else ~prev) & 1)
            else:
                if (st["f93"] & 3) != prev:
                    st["d"] |= 0x10
                if self._c8c & 4:
                    st["d"] |= 4
                    self._c8c |= 8
                ok = True
        else:
            if not self._suffixes_allowed(st, rest):
                return None
            if not self._suffix_chain(rest, st):
                return None
            ok = self._final_check(st, word, offset, lenient, out)
        if not ok or (st["d"] and not lenient):
            return None
        return st

    def _suffixes_allowed(self, st: dict, rest: List[int]) -> bool:
        if st["hi"] & 0x04:
            return False
        if st["hi"] & 0x80:
            if rest[0] != _APOSTROPHE:
                return False
            st["hi"] &= 0x7F
        if rest[0] == _APOSTROPHE and not st["hi"] & 0x01 and self.options & 0x40:
            return False
        return True

    # ─── FUN_1010_1b3e / 1ac5 / 1a3c: dictionary search with the DGROUP 0x8B8E side effect ───

    def _body(self, source: str, idx: int) -> List[int]:
        if source == "tur":
            return self.lex.body_codes(idx) if 0 <= idx < self.lex.word_count else []
        return self.user.codes[idx] if 0 <= idx < len(self.user.codes) else []

    def _cmp(self, source: str, idx: int, key: List[int]) -> int:
        """FUN_1010_1b3e: compare a stored body with the typed stem; sets DGROUP 0x8B8E."""
        body = self._body(source, idx)
        self._load_8ade(body)
        acc = diff = i = 0
        while i < min(len(body), len(key)) and diff == 0:
            acc |= body[i]
            diff = (body[i] & 0x5F) - (key[i] & 0x5F)
            i += 1
        self._8b8e = acc & 0xA0
        return diff if diff else len(body) - len(key)

    def _search(self, source: str, lo: int, hi: int, key: List[int]) -> int:
        """FUN_1010_1ac5: binary search, then back to the first equal entry (0x8B8E of the probe that hit)."""
        while True:
            if hi < lo:
                return -1
            mid = (lo + hi) >> 1
            r = self._cmp(source, mid, key)
            if r == 0:
                break
            if r < 0:
                lo = mid + 1
            else:
                hi = mid - 1
        saved = self._8b8e
        while mid != 0 and self._cmp(source, mid - 1, key) == 0:
            mid -= 1
        self._8b8e = saved
        return mid

    def _find_stem(self, lo: int, hi: int, stem: List[int]) -> int:
        """FUN_1010_1a3c: first MTU.TUR word of the prefix range whose body is `stem`."""
        if not stem:
            # No range check: an empty prefix range looks at the first word of the next prefix
            if lo < self.lex.word_count and (self.lex.sec4[lo * 4 + 1] >> 3) == 0:
                self._8b80 = 0
                return lo
            return -1
        idx = self._search("tur", lo, hi, stem)
        if idx >= 0:
            self._8b80 = self._load_8ade(self._body("tur", idx))
        return idx

    def _homonyms(self, source: str, idx: int, key: List[int]) -> Iterator[int]:
        """Yields idx and the following entries while FUN_1010_1b3e still matches (sets 0x8B8E)."""
        limit = self.lex.word_count if source == "tur" else len(self.user.codes)
        while True:
            yield idx
            idx += 1
            if idx >= limit or self._cmp(source, idx, key) != 0:
                return

    def _tur_stems(self, codes: List[int], body_lens) -> Iterator[Tuple[int, int]]:
        """(MTU.TUR index, stem end) for each stem tried, longest first (FUN_1010_1a3c + homonyms)."""
        k = codes[0] * 32 + codes[1]
        lo, hi = self.lex.prefix_starts[k], self.lex.prefix_starts[k + 1] - 1
        for body_len in body_lens:
            stem = codes[2:2 + body_len]
            idx = self._find_stem(lo, hi, stem)
            if idx >= 0:
                for idx in self._homonyms("tur", idx, stem):
                    yield idx, 2 + body_len

    def _soz_stems(self, codes: List[int], stem_lens) -> Iterator[Tuple[int, int]]:
        """(user-dictionary record, stem end) for each stem tried (FUN_1010_1ac5 + 1bc4 + homonyms)."""
        for stem_len in stem_lens:
            key = codes[:stem_len]
            first = self._search("soz", 0, len(self.user.codes), key)
            if first >= 0:
                self._8b80 = self._load_8ade(self.user.codes[first])
                for i in self._homonyms("soz", first, key):
                    yield i, stem_len

    # ─── FUN_1010_0a0e ───

    def _analyze(self, word: TypedWord, prev: Optional[int], lenient: bool = False):
        """Returns (source, index, state, repaired codes) or None."""
        codes = word.codes
        n = len(codes)
        lex = self.lex
        out = list(codes)  # DGROUP 0x8B10: candidates that fail can still leave changes in it
        # FUN_1010_19c7: no MTU.TUR search when the prefix range is empty
        k = codes[0] * 32 + codes[1] if n >= 2 else 0
        if n >= 2 and _APOSTROPHE not in codes[:2] and lex.prefix_starts[k] < lex.prefix_starts[k + 1]:
            for idx, end in self._tur_stems(codes, range(n - 2, -1, -1)):
                st = self._accepts(lex.section6_index(idx), word, codes[end:], 2, prev, lenient, out, end)
                if st:
                    return "tur", idx, st, out
        if self.user and self.user.records:
            if codes and codes[0] == 0x11:  # "o" (pronoun) with its own Section 6 classes
                for s6, case_bits in zip(_O_PRONOUN_CLASSES, (0x00, 0x80)):
                    self._8b8e = case_bits
                    st = self._accepts(s6, word, codes[1:], 0, prev, lenient, out, 1)
                    if st:
                        return "o", s6, st, out
            for i, end in self._soz_stems(codes, range(n, 0, -1)):
                st = self._accepts(self.user.section6_index(i), word, codes[end:], 0, prev, lenient, out, end)
                if st:
                    return "soz", i, st, out
        return None

    # ─── Dictionary windows (thesaurus FUN_1010_256c, Türkçe İngilizce FUN_1010_3114) ───

    @classmethod
    def for_windows(cls, lexicon: Optional[TurLexicon] = None) -> "Speller":
        """The analyzer as the dictionary windows run it: options & 0xC3, no user dictionary."""
        return cls(lexicon, options=DEFAULT_OPTIONS & 0xC3, use_user_dictionary=False)

    def window_index(self, raw: str) -> Tuple[Optional[int], List[int]]:
        """
        FUN_1010_18f3 + 0a0e in suggestion mode (DGROUP 0x8B8C = 0x40) and the homonym step that
        follows them: a typed circumflex (0x8B8F & 0x48) moves to the next entry with the same body.
        Returns (MTU.TUR index or None, DGROUP 0x8B10 after the analysis).
        """
        word = TypedWord(raw)
        self._c8c = 4 if word.period else 0
        found = self._analyze(word, 0, lenient=True) if len(word.codes) >= 2 else None
        if found is None or found[0] != "tur":
            return None, list(word.codes)
        idx, out = found[1], found[3]
        if word.circ & 0x48 and idx + 1 < self.lex.word_count:
            stem = word.codes[2:2 + len(self.lex.body_codes(idx))]
            if self._cmp("tur", idx + 1, stem) == 0:
                idx += 1
        return idx, out

    # ─── FUN_1010_0842 ───

    def check(self, raw: str, prev: Optional[int] = None) -> dict:
        """
        Checks one word. `prev` is the sentence state left by the previous word
        (SENTENCE_START at the start of a sentence, None when checking a word on its own).
        Returns {"valid", "state", "source", "index", "reason"}; "state" is passed to the next word.
        """
        word = TypedWord(raw)
        self._c8c = 4 if word.period else 0
        n = len(word.codes)
        if n < self.min_length:
            state = SENTENCE_START if n == 0 or (n > 1 and word.period) else harmony_state(word.codes)
            return {"valid": True, "state": state, "source": None, "index": None, "reason": "short"}
        found = self._analyze(word, prev)
        if found is None:
            valid = (word.case & 0x0C) == 0 and self._roman(word)
            return {"valid": valid, "state": harmony_state(word.codes), "source": "roman" if valid else None,
                    "index": None, "reason": None if valid else "unknown"}
        source, index, st, _ = found
        if not st["f"] & 4:
            state = SENTENCE_START if self._c8c & 4 else st["f93"] & 3
            prev_flags = prev or 0
            if not prev_flags & SENTENCE_START or word.case:
                valid = (word.case & 0x0C) == 0
                reason = None if valid else "case"
            else:
                valid, reason = False, "sentence-start"
        else:
            state = st["f93"] & 3
            valid = not word.case & 0x08
            reason = None if valid else "case"
        return {"valid": valid, "state": state, "source": source, "index": index, "reason": reason}

    @staticmethod
    def _roman(word: TypedWord) -> bool:
        """FUN_1010_07bf."""
        for c in word.codes:
            if c == _ROMAN_UPPER_I:
                if not word.case:
                    return False
            elif c == _ROMAN_LOWER_I:
                if word.case:
                    return False
            elif c not in _ROMAN:
                return False
        return True

    # ─── Suggestions: FUN_1010_0842 (case fix) and FUN_1010_0ba3 ───

    def suggest(self, raw: str, prev: Optional[int] = None) -> dict:
        """
        Suggestions the EXE offers for a word rejected by check().
        Returns {"suggestions": [...], "best": index of the preselected suggestion or None}.
        """
        word = TypedWord(raw)
        result = _Suggestions()
        self._c8c = 4 if word.period else 0
        strict = self._analyze(word, prev) if len(word.codes) >= self.min_length else None
        if strict is not None:
            # FUN_1010_0842: a known word with a case error — offer its stored spelling with fixed case
            source, index, st, out = strict
            codes = list(out)
            if not st["f"] & 4:
                self._stored_body(source, index, codes)
            self._add(result, word, prev, codes, strict, 0)
            return {"suggestions": result.items, "best": result.best}

        self._c8c = 4 if word.period else 0  # FUN_1010_0ba3 re-reads the word (0x8B8C = 0x40 + period)
        found = self._analyze(word, prev, lenient=True)
        leftover_d = self._last_state["d"]
        if found is not None and not leftover_d & 0x08:
            # A known word that broke a rule: offer it repaired (case, circumflex, enclitic vowel)
            source, index, st, out = found
            if st["f"] & 1:
                out[0] |= 0x80
            if st["d"] & 0x10 and prev is not None:
                vowel = _HIGH_VOWEL[prev & 3]
                out = [vowel if not _HARMONY[c & 0x1F] & 0x80 else c for c in out]
                st["d"] &= ~0x10
            self._add(result, word, prev, out, found, 0)
            return {"suggestions": result.items, "best": result.best}

        if not self.options & 0x80:
            return {"suggestions": [], "best": None}
        codes = list(word.codes)
        if leftover_d & 0x08 and self._pos82 is not None and self._pos82 < len(codes):
            # Proper-noun softening (option bit 2): continue with the hardened spelling
            codes[self._pos82] = _HARDEN.get(codes[self._pos82], codes[self._pos82])
        n = len(codes)
        if n == 1:
            result.add(codes_text([0x11]), 0)
        # DGROUP 0x8B42 holds the raw typed text with the letter codes copied over its start;
        # FUN_1010_116c / 158a compare past the end of the word into what remains there.
        raw = list(word.raw.encode("cp857", errors="replace")) + [0]
        self._buf = codes + raw[n:]
        self._edits(result, word, prev, codes)
        return {"suggestions": result.items, "best": result.best}

    def _try(self, result: _Suggestions, word: TypedWord, prev, codes: List[int], score: int):
        found = self._analyze(word.variant(codes), prev, lenient=True)
        if found is not None:
            self._add(result, word, prev, found[3], found, score)

    def _add(self, result: _Suggestions, word: TypedWord, prev, codes: List[int], found, score: int):
        """FUN_1010_0f93: format a candidate with the typed word's case and add it."""
        source, index, st, _ = found
        if st["d"] & 0x58:
            return
        codes = list(codes)
        if st["f"] & 4:
            case = 0
            self._stored_body(source, index, codes)
        else:
            case = word.case
            if st["d"] & 2 or (prev or 0) & SENTENCE_START:
                case |= 1
            if word.case & 4:
                case = 1
        text = codes_text(self._apply_case(codes, case))
        uncertain = self._c8c & 8
        self._c8c &= ~8
        if uncertain:
            text += "?"
        if st["hi"] & 0x80 and st["hi"] & 0x04:
            text += "."
        result.add(text, score)

    def _stored_body(self, source: str, index: int, codes: List[int]):
        if source == "tur":
            body, offset = self.lex.body_codes(index), 2
        elif source == "soz":
            body, offset = self.user.codes[index], 0
        else:
            return
        codes[offset:offset + len(body)] = body

    @staticmethod
    def _apply_case(codes: List[int], case: int) -> List[int]:
        return [c | 0x80 if (case & 1 and i == 0) or case & 2 else c for i, c in enumerate(codes)]

    def _edits(self, result: _Suggestions, word: TypedWord, prev, typed: List[int]):
        n = len(typed)
        # Deletions and transpositions (score 8)
        for i in range(n):
            self._try(result, word, prev, typed[:i] + typed[i + 1:], 8)
        for i in range(n - 1):
            swapped = list(typed)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            self._try(result, word, prev, swapped, 8)
        # FUN_1010_10e4: every letter in the first two positions (inserted or replaced)
        self._letters_at(result, word, prev, [_PLACEHOLDER] + typed, 0)
        self._letters_at(result, word, prev, typed[:1] + [_PLACEHOLDER] + typed[1:], 1)
        self._letters_at(result, word, prev, list(typed), 0)
        self._letters_at(result, word, prev, list(typed), 1)
        if n <= 2:
            return
        # FUN_1010_116c: one missing / one wrong letter against every word of the same prefix
        k = typed[0] * 32 + typed[1]
        if _APOSTROPHE not in typed[:2]:
            for idx in range(self.lex.prefix_starts[k], self.lex.prefix_starts[k + 1]):
                self._near_word(result, word, prev, typed, "tur", idx, self.lex.body_codes(idx),
                                self.lex.section6_index(idx), 2)
        if self.user:
            for i, body in enumerate(self.user.codes):
                self._near_word(result, word, prev, typed, "soz", i, body, self.user.section6_index(i), 0)
        # FUN_1010_1396: exact stems with a damaged suffix chain, missing apostrophe or a missing space
        plain = [c for c in typed if c != _APOSTROPHE]
        m = len(plain)
        self._buf[:m] = plain
        if m <= 3:
            return
        # No range check here: an empty prefix range still reaches FUN_1010_1a3c (see _find_stem)
        for idx, end in self._tur_stems(plain, range(m - 3, -1, -1)):
            self._stem_repairs(result, word, prev, plain, "tur", idx, self.lex.section6_index(idx), end)
        if self.user:
            for i, end in self._soz_stems(plain, range(m - 1, 1, -1)):
                self._stem_repairs(result, word, prev, plain, "soz", i, self.user.section6_index(i), end)

    def _b(self, i: int) -> int:
        return self._buf[i] if 0 <= i < len(self._buf) else 0

    def _letters_at(self, result, word, prev, codes: List[int], pos: int):
        """FUN_1010_10e4."""
        if pos >= len(codes):
            return
        original = codes[pos]
        for letter in range(32):
            codes[pos] = letter
            self._try(result, word, prev, codes, _key_distance(original, letter))

    def _near_word(self, result, word, prev, typed, source, index, body, s6, offset):
        """FUN_1010_116c: the typed word lacks one letter of `body`, or has one wrong letter."""
        rest = typed[offset:]
        self._8b80 = self._load_8ade(body)
        if not body or len(body) > len(rest) + 1:
            return
        # One letter of the stored body missing in the typed word
        mism, at, j, k = 0, 0, 0, 0
        while j < len(body) and mism < 2:
            if (body[j] & 0x5F) == self._b(offset + k):
                k += 1
            else:
                mism += 1
                at = j
            j += 1
        if mism == 1:
            cand = typed[:offset + at] + [body[at]] + typed[offset + at:]
            self._near_candidate(result, word, prev, cand, source, index, body, s6, offset, 8)
        # One wrong letter
        if len(body) <= len(rest):
            diffs = [j for j in range(len(body)) if (body[j] & 0x5F) != rest[j]]
            if len(diffs) == 1:
                at = diffs[0]
                cand = list(typed)
                cand[offset + at] = body[at]
                self._near_candidate(result, word, prev, cand, source, index, body, s6, offset,
                                     _key_distance(body[at], rest[at]))

    def _near_candidate(self, result, word, prev, cand, source, index, body, s6, offset, score):
        out = list(cand)
        variant = word.variant(cand)
        st = self._accepts(s6, variant, cand[offset + len(body):], offset, prev, True, out, offset + len(body))
        if st:
            self._add(result, word, prev, out, (source, index, st, out), score)

    def _stem_repairs(self, result, word, prev, typed, source, index, s6, stem_end):
        """FUN_1010_1396: the stem is right; try a word split, an apostrophe and suffix repairs."""
        variant = word.variant(typed)
        st = self._begin(s6, variant, True, stem_end)
        if st is None:
            return
        cand = list(typed[:stem_end])
        if st["f"] & 1:
            cand[0] |= 0x80
        rest = typed[stem_end:]
        # FUN_1010_1f9c in suggestion mode writes the stored stem spelling into the candidate
        if self._final_check(st, variant, 2 if source == "tur" else 0, True, cand):
            self._split(result, word, prev, cand, rest, st, 0)
        if st["hi"] & 0x04:
            return
        if st["f"] & 5:
            if st["f"] & 1:
                self._suffix_repairs(result, word, prev, cand, rest, dict(st), source, index, stem_end)
            st["hi"] |= 0x80
            cand = cand + [_APOSTROPHE]
        self._suffix_repairs(result, word, prev, cand, rest, dict(st), source, index, stem_end)

    def _split(self, result, word, prev, head: List[int], rest: List[int], st: dict, score: int):
        """FUN_1010_144d: `rest` is a word of its own — suggest "head rest"."""
        if not rest:
            return
        tail = word.variant(rest)
        tail.case = 0
        tail.first_upper = False
        saved_c8c = self._c8c
        self._c8c &= ~8
        found = self._analyze(tail, st["f93"] & 3, lenient=True)
        if found is None or found[2]["d"] & 0x18:
            self._c8c = saved_c8c
            return
        out = list(found[3])
        if found[2]["f"] & 1:
            out[0] |= 0x80
        # FUN_1010_0f93 runs with the head's flags (0x8B8F, 0x8B8D) but the tail's word index,
        # offset and Section 6 state: after an abbreviation head it overwrites the space (EXE quirk)
        joined = head + [_SPACE] + out
        fmt = dict(found[2], f=st["f"], d=st["d"])
        self._add(result, word, prev, joined, (found[0], found[1], fmt, joined), score)
        self._c8c = saved_c8c

    def _suffix_repairs(self, result, word, prev, cand: List[int], rest: List[int], st: dict, source, index,
                        start: int):
        """FUN_1010_158a: one missing or wrong letter in the suffix chain after an exact stem."""
        lex = self.lex
        n_rest = len(rest)
        for sid in range(lex.suffix_count):
            e = lex.suffix_record(sid)
            sfx = lex.suffix_codes(sid)
            n = len(sfx)
            if n > n_rest + 1:
                continue
            self._load_8ade(sfx)
            # One letter of the suffix missing in the typed word
            mism, at, k = 0, 0, 0
            for j in range(n):
                if mism >= 2:
                    break
                if sfx[j] == self._b(start + k):
                    k += 1
                else:
                    mism += 1
                    at = j
            if mism == 1:
                full = sfx + rest[n - 1:]
                trial = dict(st)
                if self._suffix_chain(full, trial) and not trial["f93"] & 0x80:
                    self._add(result, word, prev, cand + full, (source, index, trial, cand + full), 8)
            if n > n_rest:
                continue
            diffs = [j for j in range(n) if sfx[j] != rest[j]]
            if len(diffs) >= 2 or not self._suffix_compatible(e, st):
                continue
            # Unlike FUN_1010_20de, FUN_1010_158a sets 0x8B92 to e[12] & 0x18 (drops bits 0x40 / 0x80)
            nxt = dict(st)
            nxt.update({"f94": 0, "lo": st["lo"] & 0xF0, "f95": e[9], "f96": e[11],
                        "hi": e[12] & 0x18, "f93": e[13]})
            after = rest[n:]
            ok_state = dict(nxt)
            if (not after or self._suffix_chain(after, ok_state)) and not ok_state["f93"] & 0x80:
                score = _key_distance(sfx[diffs[0]], rest[diffs[0]]) if diffs else 0
                full = cand + sfx + after
                self._add(result, word, prev, full, (source, index, ok_state, full), score)
            if not diffs and after:
                # The EXE continues with the state FUN_1010_20de left behind (the last suffix of a
                # successful chain), not with the state right after this suffix
                if not ok_state["f93"] & 0x80:
                    self._split(result, word, prev, cand + sfx, after, ok_state, 1)
                self._suffix_repairs(result, word, prev, cand + sfx, after, dict(ok_state), source, index, start + n)
