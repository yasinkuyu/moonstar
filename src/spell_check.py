import struct
import os

ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"

TURKISH_VOWELS_BACK = {'a', 'ı', 'o', 'u'}
TURKISH_VOWELS_FRONT = {'e', 'i', 'ö', 'ü'}
TURKISH_VOWELS = TURKISH_VOWELS_BACK | TURKISH_VOWELS_FRONT

SOFTEN_MAP = {
    'k': ('ğ', 'g'),
    't': 'd',
    'p': 'b',
    'ç': 'c',
}

HARDEN_MAP = {
    'ğ': 'k',
    'g': 'k',
    'd': 't',
    'b': 'p',
    'c': 'ç',
}

YOR_EXCEPTION_SUFFIXES = {'iyor', 'ıyor', 'uyor', 'üyor', 'yor'}

TURKISH_SUFFIXES = [
    # Plural
    'ler', 'lar',
    # Accusative
    'i', 'ı', 'u', 'ü',
    'yi', 'yı', 'yu', 'yü',
    'ni', 'nı', 'nu', 'nü',
    # Dative
    'e', 'a',
    'ye', 'ya',
    'ne', 'na',
    # Locative
    'de', 'da',
    'te', 'ta',
    'nde', 'nda',
    # Ablative
    'den', 'dan',
    'ten', 'tan',
    'nden', 'ndan',
    # Genitive
    'in', 'ın', 'un', 'ün',
    'nin', 'nın', 'nun', 'nün',
    # Instrumental / comitative
    'le', 'la',
    'yle', 'yla',
    # 1st person possessive
    'im', 'ım', 'um', 'üm',
    # 2nd person possessive
    'in', 'ın', 'un', 'ün',
    # 3rd person possessive
    'si', 'sı', 'su', 'sü',
    'i', 'ı', 'u', 'ü',
    # 1st person plural possessive
    'imiz', 'ımız', 'umuz', 'ümüz',
    'miz', 'mız', 'muz', 'müz',
    # 2nd person plural possessive
    'iniz', 'ınız', 'unuz', 'ünüz',
    'niz', 'nız', 'nuz', 'nüz',
    # 3rd person plural possessive
    'leri', 'ları',
    # Personal suffixes (present)
    'im', 'ım', 'um', 'üm',
    'sin', 'sın', 'sun', 'sün',
    'iz', 'ız', 'uz', 'üz',
    'siniz', 'sınız', 'sunuz', 'sünüz',
    'ler', 'lar',
    # Past tense
    'dim', 'dım', 'dum', 'düm',
    'tim', 'tım', 'tum', 'tüm',
    'din', 'dın', 'dun', 'dün',
    'tin', 'tın', 'tun', 'tün',
    'di', 'dı', 'du', 'dü',
    'ti', 'tı', 'tu', 'tü',
    'dik', 'dık', 'duk', 'dük',
    'tik', 'tık', 'tuk', 'tük',
    'diniz', 'dınız', 'dunuz', 'dünüz',
    'tiniz', 'tınız', 'tunuz', 'tünüz',
    'diler', 'dılar', 'dular', 'düler',
    'tiler', 'tılar', 'tular', 'tüler',
    # Evidential past
    'miş', 'mış', 'muş', 'müş',
    # Progressive / present continuous
    'iyor', 'ıyor', 'uyor', 'üyor',
    'yor',
    # Future
    'ecek', 'acak',
    'yecek', 'yacak',
    # Ability
    'ebil', 'abil',
    'yebil', 'yabil',
    # Necessitative
    'meli', 'malı',
    # Aorist
    'er', 'ar',
    'ir', 'ır', 'ur', 'ür',
    'r',
    'mez', 'maz',
    # Optative/subjunctive
    'e', 'a',
    'eyim', 'ayım',
    'esin', 'asın',
    'elim', 'alım',
    'eniz', 'anız',
    'eler', 'alar',
    # Compound person markers (past + personal)
    'dim', 'dım', 'dum', 'düm',
    'tim', 'tım', 'tum', 'tüm',
    'din', 'dın', 'dun', 'dün',
    'tin', 'tın', 'tun', 'tün',
    'di', 'dı', 'du', 'dü',
    'dik', 'dık', 'duk', 'dük',
    'diniz', 'dınız', 'dunuz', 'dünüz',
    'mişim', 'mışım', 'muşum', 'müşüm',
    'mişsin', 'mışsın', 'muşsun', 'müşsün',
    'miş', 'mış', 'muş', 'müş',
    'mişiz', 'mışız', 'muşuz', 'müşüz',
    'mişsiniz', 'mışsınız', 'muşsunuz', 'müşsünüz',
    'mişler', 'mışlar', 'muşlar', 'müşlar',
    # -ken (while)
    'ken',
    'yken',
    # -ki (relative)
    'ki',
    'ki',
    # -ce/-ca (adverb)
    'ce', 'ca',
    'çe', 'ça',
    'ince', 'ınca',
    # -li/-lı/-lu/-lü
    'li', 'lı', 'lu', 'lü',
    # -siz/-sız/-suz/-süz
    'siz', 'sız', 'suz', 'süz',
    # -lik/-lık/-luk/-lük
    'lik', 'lık', 'luk', 'lük',
    # -ci/-cı/-cu/-cü
    'ci', 'cı', 'cu', 'cü',
    'çi', 'çı', 'çu', 'çü',
    # -gil/-gıl
    'gil', 'gıl',
    # Copular suffixes
    'yim', 'yım', 'yum', 'yüm',
    'im', 'ım', 'um', 'üm',
    'sin', 'sın', 'sun', 'sün',
    'yiz', 'yız', 'yuz', 'yüz',
    'iz', 'ız', 'uz', 'üz',
    'siniz', 'sınız', 'sunuz', 'sünüz',
    'dir', 'dır', 'dur', 'dür',
    'tir', 'tır', 'tur', 'tür',
    'ydim', 'ydım', 'ydum', 'ydüm',
    'ydin', 'ydın', 'ydun', 'ydün',
    'ydi', 'ydı', 'ydu', 'ydü',
    'ymis', 'ymış', 'ymuş', 'ymüş',
    'ysem', 'ysam',
    'ysen', 'ysan',
    'yse', 'ysa',
    'ymisim', 'ymışım', 'ymuşum', 'ymüşüm',
    'ymissin', 'ymışsın', 'ymuşsun', 'ymüşsün',
    'ymisiz', 'ymışız', 'ymuşuz', 'ymüşüz',
    'ymissiniz', 'ymışsınız', 'ymuşsunuz', 'ymüşsünüz',
    'ymisler', 'ymışlar', 'ymuşlar', 'ymüşler',
    # With buffer consonant n
    'nca', 'nça',
    'nla', 'nle',
]

class TurkishSpellChecker:
    def __init__(self, data_dir=None, output_dir=None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir or os.path.join(script_dir, '..', 'data')
        self.output_dir = output_dir or os.path.join(script_dir, '..', 'output')

        self.word_set = set()
        self.word_lower = {}
        self.section3_suffixes = []
        self.all_suffixes = []
        self.all_suffixes_by_len = []

        self._load()

    def _load(self):
        tur_path = os.path.join(self.data_dir, 'MTU.TUR')
        tur_txt_path = os.path.join(self.output_dir, 'MTU.TUR.TXT')

        if os.path.exists(tur_txt_path):
            with open(tur_txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    w = line.strip()
                    if w:
                        self.word_set.add(w)
                        self.word_lower[w.lower()] = w

        if os.path.exists(tur_path):
            self._load_suffix_table(tur_path)

        self._build_suffix_list()

    def _build_suffix_list(self):
        seen = set()
        for s in self.section3_suffixes:
            if s not in seen:
                seen.add(s)
                self.all_suffixes.append(s)

        for s in TURKISH_SUFFIXES:
            if s not in seen:
                seen.add(s)
                self.all_suffixes.append(s)

        self.all_suffixes_by_len = sorted(self.all_suffixes, key=lambda x: -len(x))

    def _decode_alphabet(self, raw):
        return ''.join(
            ALPHABET[b] if b < len(ALPHABET) and ALPHABET[b] != '.' else ''
            for b in raw
        )

    def _load_suffix_table(self, path):
        data = open(path, 'rb').read()
        hdr = struct.unpack('<HHHH', data[4:12])
        word_count = hdr[0]
        sec3_count = hdr[1]
        sec5_len = hdr[2]

        letter_count = 32
        sec1_size = (letter_count + 1) * 2
        sec2_size = (letter_count ** 2 + 1) * 2
        sec3_off = 12 + sec1_size + sec2_size
        sec4_off = sec3_off + sec3_count * 14
        sec5_off = sec4_off + word_count * 4
        sec5 = data[sec5_off:sec5_off + sec5_len]

        for i in range(sec3_count):
            entry = data[sec3_off + i * 14:sec3_off + i * 14 + 14]
            b0 = entry[0]
            val = struct.unpack('<H', entry[1:3])[0]
            count = b0 & 0x7F
            if count == 0:
                continue
            if count < 3:
                raw = entry[3:3 + count]
            else:
                if val + count <= sec5_len:
                    raw = sec5[val:val + count]
                else:
                    continue
            suffix = self._decode_alphabet(raw)
            if suffix:
                self.section3_suffixes.append(suffix)

    def _get_last_vowel(self, word):
        for ch in reversed(word):
            if ch in TURKISH_VOWELS:
                return ch
        return None

    def _get_vowel_type(self, word):
        for ch in reversed(word):
            if ch in TURKISH_VOWELS_BACK:
                return 'back'
            if ch in TURKISH_VOWELS_FRONT:
                return 'front'
        return 'back'

    def _match_vowel_harmony(self, stem, suffix):
        if not stem or not suffix:
            return True

        for ex in YOR_EXCEPTION_SUFFIXES:
            idx = suffix.find(ex)
            if idx >= 0:
                before = suffix[:idx]
                if before and any(ch in TURKISH_VOWELS for ch in before):
                    stem_vowel = self._get_vowel_type(stem)
                    if stem_vowel == 'back':
                        if any(ch not in TURKISH_VOWELS_BACK for ch in before if ch in TURKISH_VOWELS):
                            return False
                    else:
                        if any(ch not in TURKISH_VOWELS_FRONT for ch in before if ch in TURKISH_VOWELS):
                            return False
                return True

        stem_vowel = self._get_vowel_type(stem)
        if stem_vowel == 'back':
            return all(ch not in TURKISH_VOWELS_FRONT for ch in suffix if ch in TURKISH_VOWELS)
        else:
            return all(ch not in TURKISH_VOWELS_BACK for ch in suffix if ch in TURKISH_VOWELS)

    def _harden_final(self, word):
        if not word:
            return word, False
        last = word[-1]
        if last in HARDEN_MAP:
            return word[:-1] + HARDEN_MAP[last], True
        if last == 'k':
            if len(word) > 1 and word[-2] in TURKISH_VOWELS:
                return word[:-1] + 'ğ', True
            return word[:-1] + 'g', True
        return word, False

    def _strip_one_suffix(self, word, depth=0):
        if depth > 5 or len(word) < 2:
            return []

        results = []

        for suffix in self.all_suffixes_by_len:
            if len(suffix) >= len(word):
                continue
            if not word.endswith(suffix):
                continue

            stem = word[:-len(suffix)]
            if len(stem) < 2:
                continue
            if not self._match_vowel_harmony(stem, suffix):
                continue

            if stem in self.word_lower:
                score = max(10, 50 - depth * 15)
                results.append((self.word_lower[stem], suffix, score, depth))

            hardened_stem, did_harden = self._harden_final(stem)
            if did_harden and hardened_stem in self.word_lower:
                score = max(10, 45 - depth * 15)
                results.append((self.word_lower[hardened_stem], suffix, score, depth))

            deeper = self._strip_one_suffix(stem, depth + 1)
            for d_stem, d_suf, d_score, d_depth in deeper:
                score = max(5, d_score - 10)
                results.append((d_stem, d_suf, score, d_depth))

        return results

    def check(self, word):
        word = word.strip().split("'")[0]
        if not word:
            return {'valid': False, 'word': '', 'suggestions': []}

        original_word = word
        word_lower = word.lower()
        is_proper = word[0].isupper()

        stems = self._strip_one_suffix(word_lower)
        has_depth0_stem = any(d == 0 for _, _, _, d in stems)
        has_any_stem = len(stems) > 0

        is_valid = (word in self.word_set or word_lower in self.word_lower or
                    has_any_stem)

        is_inflected = has_any_stem and not (word in self.word_set or word_lower in self.word_lower)

        seen = set()
        suggestions = []
        for stem_word, suffix, score, depth in sorted(stems, key=lambda x: -x[2]):
            if stem_word.lower() == word_lower:
                is_valid = True
                continue
            if stem_word not in seen:
                seen.add(stem_word)
                if depth == 0:
                    method = f"stem:{suffix}"
                else:
                    method = f"iter:{suffix}(d{depth})"
                suggestions.append({
                    'word': stem_word,
                    'method': method,
                    'score': score,
                })

        if not is_valid and not is_proper:
            for j in range(len(word_lower) - 1, -1, -1):
                ch = word_lower[j]
                if ch in HARDEN_MAP:
                    cand = word_lower[:j] + HARDEN_MAP[ch] + word_lower[j+1:]
                elif ch == 'k':
                    cand = word_lower[:j] + 'ğ' + word_lower[j+1:]
                elif ch == 'g':
                    cand = word_lower[:j] + 'k' + word_lower[j+1:]
                else:
                    continue
                if cand in self.word_lower and cand not in seen:
                    seen.add(cand)
                    suggestions.insert(0, {
                        'word': self.word_lower[cand],
                        'method': 'harden',
                        'score': 65,
                    })
                break

            if 'y' in word_lower:
                for src, dst in [('y', 'i'), ('y', 'ı')]:
                    c = word_lower.replace(src, dst)
                    if c in self.word_lower and c not in seen:
                        seen.add(c)
                        suggestions.append({
                            'word': self.word_lower[c],
                            'method': 'letter',
                            'score': 30,
                        })

        suggestions = suggestions[:15]

        return {
            'valid': is_valid,
            'word': original_word,
            'is_proper': is_proper,
            'is_inflected': is_inflected,
            'stem': suggestions[0]['word'] if suggestions and not is_valid else None,
            'suggestions': suggestions,
            'stem_count': len(stems),
        }

    def check_text(self, text):
        import re
        words = re.findall(r'[a-zA-ZçÇğĞışİöÖşŞüÜâîû]+', text)
        results = []
        for w in words:
            result = self.check(w)
            if not result['valid']:
                results.append(result)
        return results


if __name__ == '__main__':
    checker = TurkishSpellChecker()
    test_words = [
        'okullarda', 'kitaplar', 'çiçeği', 'Ahmet', 'abajur', 'yanlış',
        'okula', 'geliyorum', 'ellerinde', 'başladı', 'okuldan', 'kitabı',
        'geldim', 'gördüm', 'almış', 'yazıyorum', 'sözlükte', 'kışın',
    ]
    for w in test_words:
        r = checker.check(w)
        sug = ', '.join(s['word'] for s in r['suggestions'][:5])
        print(f"  {w:20s} -> {'✓' if r['valid'] else '✗'}  stems: {sug or '(none)'}")
