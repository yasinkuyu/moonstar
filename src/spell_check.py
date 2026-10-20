"""
spell_check.py — Turkish spell checker (Türkçe Denetim) for the web UI

Accept/reject decisions and suggestions come from engine.speller, the port of the
MTU.EXE spell checker (MTU.TUR + MTU.SOZ user dictionary). This module adds the
text-level loop that carries the sentence state from word to word.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.speller import SENTENCE_START, Speller
from engine.tur_lexicon import default_lexicon

# Words, with apostrophe-separated suffixes kept attached (Ankara'dan), like the EXE tokenizer
WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû]+(?:['’`][A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû]+)*")
SENTENCE_END = ".!?"


class TurkishSpellChecker:
    def __init__(self, data_dir=None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir or os.path.join(script_dir, '..', 'data')
        self.lexicon = default_lexicon()
        self.speller = Speller(self.lexicon, user_dictionary=os.path.join(self.data_dir, 'MTU.SOZ'))

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

    def check_text(self, text):
        """
        Checks running text, carrying the EXE's sentence state from word to word
        (capital letter after . ! ?, enclitics like "mı" / "de" agreeing with the previous word).
        Returns every word with its offsets and result.
        """
        tokens = []
        prev = SENTENCE_START
        pos = 0
        for m in WORD_RE.finditer(text):
            gap = text[pos:m.start()]
            # A period right after a digit is an ordinal or a decimal point ("2. kat", "6.5"), not a sentence end
            ends = [i for i, ch in enumerate(gap) if ch in SENTENCE_END
                    and not (ch == '.' and (i > 0 and gap[i - 1].isdigit() or i + 1 < len(gap) and gap[i + 1].isdigit()))]
            if ends:
                prev = SENTENCE_START
            elif any(ch.isdigit() for ch in gap):
                prev = None  # numbers are not analysed here; do not guess their harmony
            # A period right after the word is part of it for the EXE: it ends the sentence,
            # or completes an abbreviation (Prof., Dr., vb.)
            period = text[m.end():m.end() + 1] == '.'
            result = self.check(m.group(0) + ('.' if period else ''), prev)
            result.update({'word': m.group(0), 'start': m.start(), 'end': m.end()})
            tokens.append(result)
            prev = result['state']
            pos = m.end() + (1 if period else 0)
        return tokens


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
