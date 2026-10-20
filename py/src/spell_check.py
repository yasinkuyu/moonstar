"""
spell_check.py — Turkish spell checker (Türkçe Denetim) for the web UI

Accept/reject decisions and suggestions come from engine.speller, the port of the
MTU.EXE spell checker (MTU.TUR + MTU.SOZ user dictionary). This module ports the
document loop around it:
  - FUN_1018_11e0: walks the text paragraph by paragraph, checks each word and
    runs the "Hatalı veya Bilinmeyen Sözcük" / "Noktalama Hatası" dialogs
  - FUN_1018_0f58: cuts the next word out of a paragraph
"""

import os
import sys
from typing import Iterable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.speller import SENTENCE_START, Speller, UserDictionary
from engine.tur_lexicon import char_class, default_lexicon

# DGROUP 0x1015 at runtime: editor format tags (<BL>, <IT>, …) skipped in front of a word.
# Read from the live DGROUP in data/ntvdm.exe.dmp (the file holds them encoded).
FORMAT_TAGS = frozenset(
    "BL IT UN SP SB TG RV OV OS BI DS AL SM MR FT CP OU PK FN CR BR IA TR OC FC BC PT RA TB DY MT DD MM YY".split())
PARAGRAPH_START = True    # DGROUP 0x00A1 = 1 (MTU.INI offset 0x4B): every paragraph starts a sentence
IGNORE_LIMIT = 0x7CFF     # FUN_1018_11e0: bytes available for the "Devam" list
_SEPARATOR = 0xFA         # letter classes above this end a word (space, digits, . , ! ? ; :)
_PUNCT = 0xFC             # class of . , ! ? ; :
_APOSTROPHE = 0x60        # class of ' ` "


def _ascii_upper(ch: str) -> str:
    """FUN_1018_091c: only ASCII a–z are uppercased."""
    return chr(ord(ch) - 0x20) if 0x60 < ord(ch) < 0x7F else ch


def next_word(line: str, pos: int):
    """
    FUN_1018_0f58: the next word of a paragraph from `pos`.
    Returns (start, text, end, joined) or None when only separators are left.
    `text` includes a period that follows the word. `joined` is True when the word runs into
    the next one through punctuation ("kitap,defter"): `text` is then the word, and the
    punctuation and the next letter are line[end], line[end + 1].
    """
    n = len(line)
    if line[pos:pos + 1] == "<" and "".join(_ascii_upper(c) for c in line[pos + 1:pos + 3]) in FORMAT_TAGS:
        pos += 3
    while pos < n and (char_class(line[pos]) > _SEPARATOR or char_class(line[pos]) == _APOSTROPHE):
        pos += 1
    if pos >= n:
        return None
    start = end = pos
    brk = None
    while end < n:
        ch, cls = line[end], char_class(line[end])
        after = end + 1
        if cls > _SEPARATOR or (cls == _APOSTROPHE and (after >= n or char_class(line[after]) > _SEPARATOR)):
            brk = ch
            break
        end += 1
    text = line[start:end]
    if brk is None:
        return start, text, end, False
    after = end + 1
    if (after >= n or char_class(brk) != _PUNCT or len(text) < 2
            or char_class(line[after]) > _SEPARATOR or char_class(line[after]) == _APOSTROPHE):
        if brk == ".":
            return start, text + ".", end + 1, False
        return start, text, end, False
    return start, text, end, True


def _paragraphs(text: str):
    """(offset, paragraph) for every line of the text."""
    pos = 0
    for line in text.split("\n"):
        yield pos, line[:-1] if line.endswith("\r") else line
        pos += len(line) + 1


class TurkishSpellChecker:
    def __init__(self, data_dir=None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir or os.path.join(script_dir, '..', 'data')
        self.lexicon = default_lexicon()
        self.speller = Speller(self.lexicon, user_dictionary=os.path.join(self.data_dir, 'MTU.SOZ'))
        # User dictionary 1 ("Kontrol sözlük"); the EXE loads the one chosen in its dialog
        control = os.path.join(self.data_dir, 'KONTROL.SOZ')
        self.control = UserDictionary(control, self.lexicon) if os.path.exists(control) else None

    def check(self, word, prev=None):
        """
        Checks one word with the MTU.EXE rules. `prev` is the sentence state left by the
        previous word (None = word checked on its own, SENTENCE_START = first word of a sentence).
        Suggestions are listed in the EXE's order; `best` is the one the EXE preselects.
        """
        word = word.strip().replace('’', "'")
        if not word:
            return {'valid': False, 'word': '', 'suggestions': [], 'best': None}

        exe = self.speller.check(word, prev)
        suggestions, best = [], None
        if not exe['valid']:
            sug = self.speller.suggest(word, prev)
            suggestions = [{'word': w, 'method': 'exe'} for w in sug['suggestions']]
            best = sug['best']

        return {
            'valid': exe['valid'],
            'word': word,
            'reason': exe['reason'],
            'source': exe['source'],
            'state': exe['state'],
            'is_proper': word[0].isupper(),
            'stem': suggestions[best]['word'] if best is not None else None,
            'suggestions': suggestions,
            'best': best,
        }

    # ─── FUN_1018_11e0 ───

    def _replacement(self, word: str, text: str) -> dict:
        """'Değiştir' with `text`: characters replaced and the sentence state that follows."""
        replace_len = len(word)
        if text[-1:] not in ("?", ".") and word.endswith("."):
            replace_len -= 1  # the period after the word stays in the text
        return {'word': text, 'state': self.speller.sentence_state(text), 'replace_len': replace_len}

    def next_error(self, text: str, pos: int = 0, state: int = SENTENCE_START,
                   ignore: Iterable[str] = (), user_words: Iterable[str] = (),
                   punct_continue: Optional[int] = None) -> dict:
        """
        Runs the EXE's check loop from `pos` with sentence state `state` up to the next error.

        `ignore` holds the words "Devam" was pressed for (compared exactly, like the EXE).
        `user_words` are words added with "Sözlük"; they are accepted as written.
        `punct_continue` is the start of a word whose "Noktalama Hatası" got "Devam".

        Returns {'error': None, 'checked': n} at the end of the text, or {'error': {...}, 'checked': n}:
          kind 'word':  start/end, word, suggestions [{word, state, replace_len}], best, and
                        'continue' {pos, state} for "Devam" (the word joins the ignore list)
          kind 'punct': start/end of the selection, word, replacement ("kitap, d")
        """
        ignore = set(ignore)
        user = {w.lower() for w in user_words}
        checked = 0
        for offset, line in _paragraphs(text):
            if offset + len(line) < pos:
                continue
            if offset >= pos and offset > 0 and PARAGRAPH_START:
                state = SENTENCE_START  # FUN_1010_0723(0) on a new paragraph
            p = max(pos - offset, 0)
            while True:
                tok = next_word(line, p)
                if tok is None:
                    break
                start, word, end, joined = tok
                if joined:
                    if self.speller.is_roman(line[start:end + 2]):
                        p = end
                        continue
                    if punct_continue != offset + start:
                        sel = line[start:end + 2]
                        return {'checked': checked, 'error': {
                            'kind': 'punct', 'start': offset + start, 'end': offset + end + 2, 'word': sel,
                            'replacement': line[start:end + 1] + ' ' + line[end + 1], 'state': state,
                        }}
                checked += 1
                p = end
                if word.rstrip('.').lower() in user:
                    state = self.speller.sentence_state(word)
                    continue
                result = self.speller.check(word, state)
                if result['valid']:
                    state = result['state']
                    continue
                if word in ignore:
                    state = self.speller.sentence_state(word)
                    continue
                sug = self.speller.suggest(word, state)
                return {'checked': checked, 'error': {
                    'kind': 'word', 'start': offset + start, 'end': offset + end, 'word': word,
                    'reason': result['reason'], 'state': state,
                    'suggestions': [self._replacement(word, s) for s in sug['suggestions']],
                    'best': sug['best'],
                    'continue': {'pos': offset + end, 'state': self.speller.sentence_state(word)},
                }}
        return {'checked': checked, 'error': None}

    def check_text(self, text: str) -> List[dict]:
        """
        The whole text as the EXE checks it when every error is answered with "Devam":
        one entry per error, in order. Repeats of a word already passed with "Devam" are
        accepted by the EXE and are not listed.
        """
        errors, ignore = [], []
        pos, state, punct = 0, SENTENCE_START, None
        while True:
            err = self.next_error(text, pos, state, ignore, punct_continue=punct)['error']
            if err is None:
                return errors
            errors.append(err)
            if err['kind'] == 'punct':
                pos, punct = err['start'], err['start']
            else:
                ignore.append(err['word'])
                pos, state, punct = err['continue']['pos'], err['continue']['state'], None

    def start_state(self, text: str, pos: int) -> int:
        """
        Sentence state the check starts with at `pos`: FUN_1010_0723 on the word before the
        cursor in its paragraph (DGROUP 0x69AA), SENTENCE_START when there is none.
        """
        for offset, line in _paragraphs(text):
            if not offset <= pos <= offset + len(line):
                continue
            last, p = None, 0
            while (tok := next_word(line, p)) is not None and offset + tok[2] <= pos:
                last, p = tok, tok[2]
            return self.speller.sentence_state(last[1]) if last else SENTENCE_START
        return SENTENCE_START

    def control_match(self, text: str, pos: int = 0) -> Optional[dict]:
        """
        FUN_1018_10c4 ("Sözlük kontrol"): the first word from `pos` that is a form of a
        control dictionary entry, or None. Words of one letter are not looked up.
        """
        if self.control is None:
            return None
        for offset, line in _paragraphs(text):
            if offset + len(line) < pos:
                continue
            p = max(pos - offset, 0)
            while (tok := next_word(line, p)) is not None:
                start, word, end, joined = tok
                p = end
                if len(word.rstrip('.')) < 2 and not joined:
                    continue
                looked_up = line[start:end + 2] if joined else word
                if self.speller.in_dictionary(looked_up, self.control):
                    return {'start': offset + start, 'end': offset + end, 'word': word}
        return None

    @staticmethod
    def words(text: str) -> List[str]:
        """The words the check loop visits, in order."""
        out = []
        for _, line in _paragraphs(text):
            p = 0
            while (tok := next_word(line, p)) is not None:
                out.append(tok[1])
                p = tok[2]
        return out


def text_check_response(checker: TurkishSpellChecker, path: str, body: dict) -> dict:
    """Web API: POST /api/check/text (whole text) and /api/check/next (one step of the check loop)."""
    def strings(name):
        v = body.get(name)
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []

    def number(name, default):
        v = body.get(name, default)
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else default

    text = body.get("text", "")
    if not isinstance(text, str):
        text = ""
    if path == "/api/check/text":
        return {"errors": checker.check_text(text), "words": checker.words(text)}
    if path == "/api/check/control":
        return {"match": checker.control_match(text, number("pos", 0))}
    if path == "/api/check/complete":
        return {"words": checker.speller.completions(text)}
    if path == "/api/check/start":
        return {"state": checker.start_state(text, number("pos", 0))}
    return checker.next_error(text, number("pos", 0), number("state", SENTENCE_START) & 0xFF,
                              strings("ignore"), strings("user_words"), number("punct_continue", None))


if __name__ == '__main__':
    checker = TurkishSpellChecker()
    test_words = [
        'okullarda', 'kitaplar', 'çiçeği', 'Ahmet', 'abajur', 'yanlış',
        'kitapp', 'ankara', 'Ankarada', 'evlerimizdne', 'kitapokudum', 'gidiyorumm',
    ]
    for w in test_words:
        r = checker.check(w)
        sug = ', '.join(s['word'] for s in r['suggestions'][:5])
        print(f"  {w:20s} -> {'✓' if r['valid'] else '✗'}  suggestions: {sug or '(none)'}")
