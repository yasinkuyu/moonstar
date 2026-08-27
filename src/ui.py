#! /usr/bin/python3

# MoonStar Data Explorer — Web UI Server
# Serves all decoded MoonStar data through a browser interface
#
# @yasinkuyu

import os
import sys
import re
import json
import struct
import time
import signal
import http.server
import urllib.parse
from collections import defaultdict

from spell_check import TurkishSpellChecker

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")

def normalize_tr(s):
    """Normalize Turkish characters to ASCII for search matching."""
    tr_to_ascii = str.maketrans('ıİşŞçÇöÖüÜğĞ', 'iIsScCoOuUgG')
    return s.lower().translate(tr_to_ascii)


def turkish_sort_key(s):
    """Map Turkish characters to weights for correct alphabetical sorting."""
    mapping = {
        'a': 'a0', 'A': 'a0',
        'b': 'b0', 'B': 'b0',
        'c': 'c0', 'C': 'c0',
        'ç': 'c1', 'Ç': 'c1',
        'd': 'd0', 'D': 'd0',
        'e': 'e0', 'E': 'e0',
        'f': 'f0', 'F': 'f0',
        'g': 'g0', 'G': 'g0',
        'ğ': 'g1', 'Ğ': 'g1',
        'h': 'h0', 'H': 'h0',
        'ı': 'i0', 'I': 'i0',
        'i': 'i1', 'İ': 'i1',
        'j': 'j0', 'J': 'j0',
        'k': 'k0', 'K': 'k0',
        'l': 'l0', 'L': 'l0',
        'm': 'm0', 'M': 'm0',
        'n': 'n0', 'N': 'n0',
        'o': 'o0', 'O': 'o0',
        'ö': 'o1', 'Ö': 'o1',
        'p': 'p0', 'P': 'p0',
        'r': 'r0', 'R': 'r0',
        's': 's0', 'S': 's0',
        'ş': 's1', 'Ş': 's1',
        't': 't0', 'T': 't0',
        'u': 'u0', 'U': 'u0',
        'ü': 'u1', 'Ü': 'u1',
        'v': 'v0', 'V': 'v0',
        'y': 'y0', 'Y': 'y0',
        'z': 'z0', 'Z': 'z0'
    }
    return [mapping.get(c, c) for c in s]


def get_clean_turkish_word(s):
    """Strip leading '#' and leading parenthetical prefixes (e.g. '(about ile)') for clean index keys."""
    s = s.lstrip('#').strip()
    while s.startswith('('):
        end = s.find(')')
        if end != -1:
            s = s[end+1:].strip()
        else:
            break
    return s


PORT = 8080


# ─── Data Loaders ───────────────────────────────────────────────────────────

def load_trk():
    """Load TRK English→Turkish dictionary."""
    entries = []
    path = os.path.join(OUTPUT_DIR, "MTU.TRK.TXT")
    if not os.path.exists(path):
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    entries.append({"en": parts[0], "tr": parts[1]})
    return entries


def load_tur():
    """Load TUR Turkish→Turkish (Leb Demeden) dictionary (words only)."""
    entries = []
    path = os.path.join(OUTPUT_DIR, "MTU.TUR.TXT")
    if not os.path.exists(path):
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            word = line.strip()
            if word:
                entries.append({"word": word})
    return sorted(entries, key=lambda x: turkish_sort_key(x["word"]))


def is_valid_turkish_word(w):
    if not w or len(w) < 2 or len(w) > 30:
        return False
    if any(ch in w for ch in ["'", '"', '(', ')', '/', '\\', ':', ';', '.', '!', '?', '=']):
        return False
    allowed = set("abcçdefgğhıijklmnoöpqrsştuüvwxyzABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ -")
    return all(c in allowed for c in w)


def clean_turkish_synonym(w):
    w = re.sub(r'\(.*?\)', '', w)
    w = re.sub(r'\[.*?\]', '', w)
    w = w.replace('#', '').replace('*', '').strip()
    w = re.sub(r'\b(arg|mec|sp|müz|fiz|kim|biy|mat|tic|ask|den|coğ|anat|tıp|ed|mim|felsefe|bot|zool|jeol|ast|dilb|İİ|Aİ)\b\.?', '', w)
    w = re.sub(r'^[-\.][a-zçğıöşü]+\s*', '', w)
    w = re.sub(r'\s*ile$', '', w)
    w = w.strip(' ,;:.-\t\n\r/')
    return w


def is_clean_turkish_synonym(w):
    if not w or len(w) < 2 or len(w) > 25:
        return False
    if any(ch in w for ch in ['/', '\\', ':', ';', '!', '?', '=', '<', '>', '{', '}', '_', '@', '%', '$']):
        return False
    allowed = set("abcçdefgğhıijklmnoöpqrsştuüvwxyzABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ -'")
    return all(c in allowed for c in w)


def load_synonyms():
    """
    Universal Turkish Thesaurus Engine:
    Parses exact intra-meaning (#) synonym groups from MTU.TRK across all 17,988 entries,
    cleaning all grammar annotations dynamically with 100% data-driven extraction.
    """
    entries = []
    path = os.path.join(OUTPUT_DIR, "MTU.TRK.TXT")

    word_to_groups = defaultdict(list)
    word_to_all_syns = defaultdict(set)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                en, tr_raw = parts[0], parts[1]

                meanings = tr_raw.split('#')
                anlam_idx = 0
                for m in meanings:
                    m_raw = m.strip()
                    if not m_raw:
                        continue

                    is_mecaz = bool(re.search(r'\b(mecaz|mec)\b', m_raw, re.I))
                    is_argo = bool(re.search(r'\b(argo|arg)\b', m_raw, re.I))

                    if is_mecaz:
                        tag = 'Mecaz'
                    elif is_argo:
                        tag = 'Argo'
                    else:
                        anlam_idx += 1
                        tag = f'{anlam_idx}.Anlam'

                    raw_items = m_raw.split('|')
                    items = []
                    for it in raw_items:
                        cw = clean_turkish_synonym(it)
                        if is_clean_turkish_synonym(cw):
                            items.append(cw)

                    seen = set()
                    unique_items = [x for x in items if not (x.lower() in seen or seen.add(x.lower()))]

                    if len(unique_items) >= 2:
                        cluster_str = en + '::' + tag + '::' + ','.join(unique_items)
                        for w in unique_items:
                            w_key = w.lower()
                            if cluster_str not in word_to_groups[w_key]:
                                word_to_groups[w_key].append(cluster_str)
                            for s in unique_items:
                                if s.lower() != w_key:
                                    word_to_all_syns[w_key].add(s)

    # Build entries — one per word, sorted by Turkish alphabet
    for word_key, group_list in word_to_groups.items():
        first_cluster = group_list[0].split('::', 2)[2].split(',')
        rep_word = next((w for w in first_cluster if w.lower() == word_key), word_key)
        syns = sorted(word_to_all_syns[word_key], key=turkish_sort_key)
        groups = ' | '.join(group_list)
        entries.append({"word": rep_word, "synonyms": ' | '.join(syns), "groups": groups})

    return sorted(entries, key=lambda x: turkish_sort_key(x["word"]))

    # Build entries — one per word, sorted by Turkish alphabet
    for word_key, group_list in word_to_groups.items():
        first_cluster = group_list[0].split('::', 2)[2].split(',')
        rep_word = next((w for w in first_cluster if w.lower() == word_key), word_key)
        syns = sorted(word_to_all_syns[word_key], key=turkish_sort_key)
        groups = ' | '.join(group_list)
        entries.append({"word": rep_word, "synonyms": ' | '.join(syns), "groups": groups})

    return sorted(entries, key=lambda x: turkish_sort_key(x["word"]))


def get_turkish_stem(word):
    word = get_clean_turkish_word(word).lower()
    suffixes = [
        'lerindeki', 'larındaki', 'lerindeki',
        'lerinde', 'larında', 'lerinden', 'larından',
        'leriyle', 'larıyla',
        'leri', 'ları',
        'iniz', 'ınız', 'umuz', 'ümüz',
        'nin', 'nın', 'nun', 'nün',
        'in', 'ın', 'un', 'ün',
        'im', 'ım', 'um', 'üm',
        'ye', 'ya', 'yi', 'yı', 'yu', 'yü',
        'de', 'da', 'te', 'ta',
        'den', 'dan', 'ten', 'tan',
        'le', 'la',
        'ce', 'ca',
        'se', 'sa',
        'i', 'ı', 'u', 'ü', 'e', 'a'
    ]
    if len(word) <= 3:
        return word
    for suf in suffixes:
        if word.endswith(suf):
            stem = word[:-len(suf)]
            if len(stem) >= 3:
                return stem
    return word


def load_trk_reverse():
    """
    Load Turkish→English (reverse of TRK) merged with TUR word list.
    
    NOTE: TUR word list is authoritative for what words exist.
    TRK reverse provides English meanings where available.
    Words in TUR but not in TRK appear with empty English field.
    """
    trk_defs = {}
    pairs = {}
    path = os.path.join(OUTPUT_DIR, "MTU.TRK.TXT")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        en, tr = parts[0], parts[1]
                        # Store groups and their condition status
                        groups = []
                        for grp in tr.split('#'):
                            grp = grp.strip()
                            if grp:
                                # A group starting with parenthetical is conditional (e.g. phrasal verb meaning)
                                is_cond = grp.startswith('(') or grp.startswith('#(')
                                meanings = [get_clean_turkish_word(m) for m in grp.split('|') if get_clean_turkish_word(m)]
                                if meanings:
                                    groups.append((meanings, is_cond))
                        if groups:
                            trk_defs[en] = groups

                        # Normal flat lookup registration (with stemming)
                        for grp_words, is_cond in groups:
                            for m in grp_words:
                                m_clean = m.lower()
                                if en not in pairs.setdefault(m_clean, []):
                                    pairs[m_clean].append(en)
                                # Register stemmed words to support morphological lookup
                                for word in m_clean.split():
                                    stem = get_turkish_stem(word)
                                    if stem and stem != m_clean:
                                        if en not in pairs.setdefault(stem, []):
                                            pairs[stem].append(en)

    # Build en_to_trs mapping for synonym resolution, excluding conditional translations (with stemming)
    en_to_trs = defaultdict(set)
    for en, groups in trk_defs.items():
        for grp_words, is_cond in groups:
            if not is_cond:
                for m in grp_words:
                    m_clean = m.lower()
                    en_to_trs[en].add(m_clean)
                    for word in m_clean.split():
                        stem = get_turkish_stem(word)
                        if stem:
                            en_to_trs[en].add(stem)

    precise_en_to_trs = {en: trs for en, trs in en_to_trs.items() if len(trs) <= 9}

    # Build en_str for each TRK-reverse pair using synonym-aware lookup
    trk_rev_entries = {}
    for tr_word, en_list in pairs.items():
        # Get Hop-1 synonyms (words sharing at least one translation)
        hop1 = set()
        for en in en_list:
            hop1.update(precise_en_to_trs.get(en, []))
        hop1.discard(tr_word)

        all_syns = hop1
        if len(all_syns) > 100:
            all_syns = set(list(all_syns)[:100])

        # Candidate English translations and their specificity-weighted synonym scores
        candidate_scores = defaultdict(float)
        
        # Score Hop-1 synonym translations
        for s in hop1:
            for en in pairs.get(s, []):
                spec = 1.0 / max(1, len(en_to_trs[en]))
                candidate_scores[en] = max(candidate_scores[en], 10.0 * spec)

        # Remove direct translations from candidate scores so we can score them separately
        for en in en_list:
            candidate_scores.pop(en, None)

        # Rank synonym candidates by score
        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Keep direct translations, and append at most 12 highest scoring synonyms (with score >= 0.5)
        expanded_ens = list(en_list)
        syn_added = 0
        for en, score in sorted_candidates:
            if score >= 0.5 and syn_added < 12:
                expanded_ens.append(en)
                syn_added += 1

        # Group the English words based on their definitions structure in trk_defs
        grp_to_ens = {}
        for en in expanded_ens:
            defn = trk_defs.get(en, [])
            matched_grp = 1
            found = False
            for grp_idx, (grp_words, is_cond) in enumerate(defn):
                if any(tr_word == w or tr_word in w or w in all_syns for w in grp_words):
                    matched_grp = grp_idx + 1
                    found = True
                    break
            if not found:
                matched_grp = len(grp_to_ens) + 1
            if matched_grp not in grp_to_ens:
                grp_to_ens[matched_grp] = []
            grp_to_ens[matched_grp].append(en)

        # Flat format: each English word on its own pipe-separated item
        # renderMeanings will add 1. 2. 3. numbers automatically
        flat_ens = []
        for g in sorted(grp_to_ens.keys()):
            flat_ens.extend(sorted(list(set(grp_to_ens[g]))))
        en_str = '|'.join(flat_ens) if flat_ens else '|'.join(sorted(expanded_ens))
        trk_rev_entries[tr_word] = en_str

    # Load TUR word list as the authoritative source
    tur_words = []
    tur_path = os.path.join(OUTPUT_DIR, "MTU.TUR.TXT")
    if os.path.exists(tur_path):
        with open(tur_path, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    tur_words.append(word)

    # Merge: all TUR words + TRK-only words, both sorted by Turkish collation
    all_tr_words = set(tur_words) | set(trk_rev_entries.keys())
    entries = []
    for tr_word in sorted(all_tr_words, key=turkish_sort_key):
        en_str = trk_rev_entries.get(tr_word, "")
        entries.append({"tr": tr_word, "en": en_str})
    return entries



def load_ing_with_trk():
    """Load ING quiz entries merged with TRK words."""
    # First load TRK words
    trk_path = os.path.join(OUTPUT_DIR, "MTU.TRK.TXT")
    trk_words = []
    trk_dict = {}
    if os.path.exists(trk_path):
        with open(trk_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        trk_words.append(parts[0])
                        trk_dict[idx] = parts[1]
                    else:
                        trk_words.append(parts[0])
                        trk_dict[idx] = ""

    # Topic names (36 topics)
    exe_path = os.path.join(DATA_DIR, "MTU.EXE")
    EXE_DATA = open(exe_path, "rb").read()
    area = EXE_DATA[0x1b600:0x1b800]
    string_data = area[28:]
    topic_names = []
    i = 0
    while i < len(string_data):
        end = string_data.find(b'\x00', i)
        if end == -1:
            s = string_data[i:]
            if len(s) >= 2:
                topic_names.append(s)
            break
        s = string_data[i:end]
        if len(s) >= 2:
            topic_names.append(s)
        i = end + 1

    def cp857(b):
        m = {0x80: 'Ç', 0x81: 'ü', 0x87: 'ç', 0x8D: 'ı', 0x90: 'Ğ',
             0x91: 'ğ', 0x94: 'ö', 0x98: 'İ', 0x99: 'Ö', 0x9A: 'ö',
             0x9B: 'Ü', 0x9D: 'İ', 0x9E: 'Ş', 0x9F: 'ş', 0xA7: 'ğ'}
        return m.get(b, chr(b) if 0x20 <= b <= 0x7E else f'[{b:02x}]')
    decoded_topics = [''.join(cp857(b) for b in raw) for raw in topic_names]

    # Load ING
    ing_path = os.path.join(DATA_DIR, "MTU.ING")
    ing_data = open(ing_path, "rb").read()
    table_size = struct.unpack("<L", ing_data[0:3] + b'\x00')[0]
    data_start = 3 + table_size
    num_slots = table_size // 3

    offsets = []
    for i in range(num_slots):
        off = struct.unpack("<L", ing_data[3 + i*3: 3 + (i+1)*3] + b'\x00')[0]
        offsets.append(off)

    quizzes = []
    for si in range(len(offsets) - 1):
        start = offsets[si]
        end = offsets[si + 1]
        if start >= end or start < data_start:
            continue
        if start + 3 > len(ing_data) or ing_data[start] != 0x00:
            continue
        header_idx = ing_data[start + 1]
        flag = ing_data[start + 2]

        trk_idx = si if header_idx == (si + 1) % 256 else (header_idx - 1) % 256
        topic_idx = flag % 36
        topic_name = decoded_topics[topic_idx + 2] if topic_idx + 2 < len(decoded_topics) else f"Topic_{topic_idx}"
        en_word = trk_words[trk_idx] if 0 <= trk_idx < len(trk_words) else "???"
        tr_text = trk_dict.get(trk_idx, "")
        is_variant = flag >= 0x80

        quizzes.append({
            "slot": si,
            "en": en_word,
            "tr": tr_text,
            "topic": topic_name,
            "topic_idx": topic_idx,
            "variant": is_variant,
        })

    return quizzes, decoded_topics


# ─── Load all data ──────────────────────────────────────────────────────────

print("Loading data...")
TRK_DATA = load_trk()
TUR_DATA = load_tur()
SYN_DATA = load_synonyms()
REV_DATA = load_trk_reverse()
QUIZ_DATA, TOPIC_NAMES = load_ing_with_trk()

CHECKER = TurkishSpellChecker()

print(f"  TRK: {len(TRK_DATA)} entries")
print(f"  TUR: {len(TUR_DATA)} entries")
print(f"  SYN: {len(SYN_DATA)} entries")
print(f"  REV: {len(REV_DATA)} entries")
print(f"  QUIZ: {len(QUIZ_DATA)} entries")
print(f"  Topics: {len([t for t in TOPIC_NAMES if len(t) > 1])}")


# ─── HTTP Handler ───────────────────────────────────────────────────────────

class MoonStarHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == "/":
                self.serve_html()
            elif path == "/api/stats":
                self.json_response(self.get_stats())
            elif path == "/api/trk":
                self.json_response(self.paginate(TRK_DATA, params))
            elif path == "/api/trk/search":
                self.json_response(self.search_trk(params))
            elif path == "/api/tur":
                self.json_response(self.paginate(TUR_DATA, params))
            elif path == "/api/tur/search":
                self.json_response(self.search_tur(params))
            elif path == "/api/syn":
                self.json_response(self.paginate(SYN_DATA, params))
            elif path == "/api/syn/search":
                self.json_response(self.search_syn(params))
            elif path == "/api/rev":
                self.json_response(self.paginate(REV_DATA, params))
            elif path == "/api/rev/search":
                self.json_response(self.search_rev(params))
            elif path == "/api/quiz/topics":
                self.json_response(self.get_quiz_topics())
            elif path == "/api/quiz":
                self.json_response(self.get_quiz_entries(params))
            elif path == "/api/quiz/search":
                self.json_response(self.search_quiz(params))
            elif path == "/api/hangman/word":
                self.json_response(self.get_hangman_word(params))
            elif path == "/api/check":
                self.json_response(self.search_check(params))
            elif path == "/api/check/bulk":
                q = params.get("q", [""])[0]
                words = [w.strip() for w in q.split(",") if w.strip()]
                results = {}
                for w in words:
                    results[w] = CHECKER.check(w)
                self.json_response(results)
            elif path == "/api/editor/demo":
                try:
                    p = os.path.join(DATA_DIR, "TEST")
                    if os.path.exists(p):
                        with open(p, "r", encoding="cp857", errors="replace") as f:
                            content = f.read()
                        self.json_response({"content": content, "filename": "TEST"})
                    else:
                        self.json_response({"error": "TEST file not found"}, status=404)
                except Exception as e:
                    self.json_response({"error": str(e)}, status=500)
            elif path.startswith("/assets/"):
                self.serve_asset(path)
            else:
                self.send_error(404)
        except Exception as e:
            import traceback
            print(f"Error handling path {path}: {e}")
            traceback.print_exc()
            self.send_error(500, message=str(e))

    ASSETS_DIR = os.path.join(SCRIPT_DIR, "..", "assets")

    def serve_asset(self, path):
        if not path.startswith("/assets/"):
            self.send_error(404)
            return
        relative = path[len("/assets/"):]
        filepath = os.path.normpath(os.path.join(self.ASSETS_DIR, relative))
        if not filepath.startswith(os.path.normpath(self.ASSETS_DIR)):
            self.send_error(403)
            return
        ext = os.path.splitext(filepath)[1].lower()
        mime = {
            ".ico": "image/x-icon",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".wav": "audio/wav",
        }.get(ext, "application/octet-stream")
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def paginate(self, data, params):
        page = int(params.get("page", [1])[0])
        per_page = int(params.get("per_page", [50])[0])
        total = len(data)
        start = (page - 1) * per_page
        end = start + per_page
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "data": data[start:end],
        }

    def search_trk(self, params):
        q = params.get("q", [""])[0]
        if not q:
            return {"data": [], "total": 0}
        qn = normalize_tr(q)
        results = [e for e in TRK_DATA if normalize_tr(e["en"]).startswith(qn)]
        return {"data": results[:100], "total": len(results)}

    def search_tur(self, params):
        q = params.get("q", [""])[0]
        if not q:
            return {"data": [], "total": 0}
        qn = normalize_tr(q)
        results = [e for e in TUR_DATA if normalize_tr(e["word"]).startswith(qn)]
        return {"data": results[:100], "total": len(results)}

    def search_rev(self, params):
        q = params.get("q", [""])[0]
        if not q:
            return {"data": [], "total": 0}
        qn = normalize_tr(q)
        results = [e for e in REV_DATA if normalize_tr(e["tr"]).startswith(qn)]
        return {"data": results[:100], "total": len(results)}

    def search_syn(self, params):
        q = params.get("q", [""])[0]
        if not q:
            return {"data": [], "total": 0}
        qn = normalize_tr(q)
        results = [e for e in SYN_DATA if normalize_tr(e["word"]).startswith(qn)]
        return {"data": results[:100], "total": len(results)}

    def search_check(self, params):
        q = params.get("q", [""])[0]
        if not q:
            return {"valid": False, "word": "", "suggestions": []}
        result = CHECKER.check(q)
        result["dictionary"] = {
            "total": len(CHECKER.word_set),
            "suffix_count": len(CHECKER.all_suffixes),
        }
        return result

    def get_stats(self):
        # Topic distribution
        topic_counts = {}
        for q in QUIZ_DATA:
            t = q["topic_idx"]
            topic_counts[t] = topic_counts.get(t, 0) + 1
        topics_by_idx = {}
        for q in QUIZ_DATA:
            if q["topic_idx"] not in topics_by_idx:
                topics_by_idx[q["topic_idx"]] = q["topic"]

        topic_stats = []
        for idx in sorted(topic_counts.keys()):
            name = topics_by_idx.get(idx, f"Topic_{idx}")
            topic_stats.append({"name": name, "count": topic_counts[idx]})

        return {
            "trk": {"total": len(TRK_DATA)},
            "tur": {"total": len(TUR_DATA)},
            "syn": {"total": len(SYN_DATA)},
            "rev": {"total": len(REV_DATA)},
            "quiz": {"total": len(QUIZ_DATA)},
            "topics": topic_stats,
            "topic_names": [t for t in TOPIC_NAMES if len(t) > 1],
        }

    def get_quiz_topics(self):
        topic_counts = {}
        topics_by_idx = {}
        for q in QUIZ_DATA:
            t = q["topic_idx"]
            topic_counts[t] = topic_counts.get(t, 0) + 1
            if t not in topics_by_idx:
                topics_by_idx[t] = q["topic"]
        result = []
        for idx in sorted(topic_counts.keys()):
            name = topics_by_idx.get(idx, "")
            topic_name_idx = idx + 2
            if topic_name_idx < len(TOPIC_NAMES) and len(TOPIC_NAMES[topic_name_idx]) > 1:
                name = TOPIC_NAMES[topic_name_idx]
            result.append({
                "idx": idx,
                "name": name,
                "count": topic_counts[idx],
            })
        return {"topics": result}

    def get_quiz_entries(self, params):
        topic = int(params.get("topic", [0])[0])
        page = int(params.get("page", [1])[0])
        per_page = int(params.get("per_page", [50])[0])

        filtered = [q for q in QUIZ_DATA if q["topic_idx"] == topic]
        total = len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "data": filtered[start:end],
        }

    def search_quiz(self, params):
        q = params.get("q", [""])[0].lower()
        if not q:
            return {"data": [], "total": 0}
        results = []
        for entry in QUIZ_DATA:
            if q in entry["en"].lower() or q in entry["tr"].lower():
                results.append(entry)
                if len(results) >= 100:
                    break
        return {"data": results, "total": len(results)}

    def get_hangman_word(self, params):
        import random
        import re
        topic_param = params.get("topic", [None])[0]
        # Hangman uses Turkish alphabet keys → word must be Turkish.
        # ING slots map to TRK pairs; take a clean single Turkish lemma from definitions.
        letters = set("ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZabcçdefgğhıijklmnoöprsştuüvyz")

        def hangman_candidates(tr_text):
            cands = []
            if not tr_text:
                return cands
            for part in re.split(r'[|/#]', tr_text):
                part = part.strip()
                if not part:
                    continue
                # drop parenthetical noise, keep letter runs
                part = re.sub(r'\([^)]*\)', ' ', part)
                for token in re.split(r'[\s,;:]+', part):
                    token = token.strip(".-'")
                    if 3 <= len(token) <= 14 and all(ch in letters for ch in token):
                        cands.append(token)
            return cands

        topic = None
        if topic_param is not None and topic_param != "" and topic_param != "-1":
            try:
                topic = int(topic_param)
            except ValueError:
                topic = None

        pool = []
        for q in QUIZ_DATA:
            if topic is not None and q["topic_idx"] != topic:
                continue
            if not q.get("en") or q["en"] in ("???", "?"):
                continue
            for w in hangman_candidates(q.get("tr") or ""):
                pool.append((w, q))
                break  # one candidate per quiz entry
        if not pool:
            return {"error": "Kelime bulunamadı"}
        word, q = random.choice(pool)
        return {
            "word": word,
            "en": q["en"],
            "tr": q["tr"],
            "hint": q["en"],
            "topic": q.get("topic", ""),
            "topic_idx": q.get("topic_idx", 0),
        }


# ─── HTML Page ──────────────────────────────────────────────────────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" type="image/x-icon" href="/assets/moonstar.ico">
<link rel="shortcut icon" type="image/x-icon" href="/assets/moonstar.ico">
<title>MoonStar Türkçe Dil Kılavuzu</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
label { font-weight: 600; }

/* Win16 Classic Theme */
body {
  font-family: 'MS Sans Serif', 'Microsoft Sans Serif', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  font-size: 14px;
  background: #008080;
  color: #000;
  overflow: hidden;
  height: 100vh;
}

/* Desktop */
.desktop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #008080;
  overflow: hidden;
}

/* Main application window */
.main-win {
  width: 100% !important;
  height: 100% !important;
  display: flex;
  flex-direction: column;
  min-width: 640px;
  min-height: 480px;
  overflow: hidden;
  box-sizing: border-box;
  background: #008080;
  border: none;
}
.main-win > .win-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 0 !important;
  overflow: hidden;
}

/* Menu Bar */
.menu-bar {
  flex-shrink: 0;
  background: #c0c0c0;
  padding: 1px 2px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0;
  border-bottom: 1px solid #808080;
}
.menu-items-group {
  display: flex;
  align-items: center;
  gap: 0;
}
.menu-bar .menu-item {
  padding: 3px 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  user-select: none;
}
.menu-bar .menu-item:hover {
  border-color: #fff #808080 #808080 #fff;
}
.menu-bar .menu-item.open {
  background: #000080;
  color: #fff;
  border-color: #808080 #fff #fff #808080;
}
.retro-zoom-controls {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  padding-right: 4px;
}
.retro-zoom-label {
  font-size: 11px;
  font-weight: bold;
  color: #333;
  margin-right: 2px;
  font-family: 'MS Sans Serif', Tahoma, sans-serif;
}
.retro-zoom-btn {
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: bold;
  font-family: 'MS Sans Serif', Tahoma, sans-serif;
  cursor: pointer;
  line-height: 14px;
  color: #000;
}
.retro-zoom-btn:active {
  border-color: #808080 #fff #fff #808080;
}
.retro-zoom-btn.active {
  background: #000080;
  color: #fff;
  border-color: #808080 #fff #fff #808080;
}

/* Main work area — Win95 desktop surface */
.work-area {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  position: relative;
  background: #008080;
}

/* Win16-style window frame */
.win-window {
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #404040 #404040 #fff;
  box-shadow: 2px 2px 0 rgba(0,0,0,0.4);
  display: flex;
  flex-direction: column;
  min-width: 280px;
  box-sizing: border-box;
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
}
.win-title {
  flex-shrink: 0;
  background: #000080;
  color: #fff;
  padding: 4px 6px;
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: default;
}
.win-title.inactive {
  background: #808080;
}
.win-title-text { flex: 1; }
.win-title-icon {
  width: 16px;
  height: 16px;
  display: block;
  flex-shrink: 0;
  object-fit: contain;
  background: url('/assets/moonstar_icon.png?v=2') center / 16px 16px no-repeat;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
}
.win-title-btns { display: flex; gap: 2px; margin-left: auto; }
.win-title-btns button {
  width: 18px; height: 16px;
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  font-size: 9px;
  font-weight: bold;
  line-height: 1;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  padding: 0;
}
.win-title-btns button:active {
  border-color: #808080 #fff #fff #808080;
}
.win-body {
  padding: 6px;
  font-size: 14px;
}
.win-status {
  background: #c0c0c0;
  border-top: 1px solid #808080;
  padding: 3px 6px;
  font-size: 13px;
  color: #444;
}

/* Win16-style buttons */
.win-btn {
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  padding: 3px 16px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  outline: none;
  min-width: 60px;
}
.win-btn:active {
  border-color: #808080 #fff #fff #808080;
}
.win-btn.primary {
  font-weight: 700;
}
.win-btn.small {
  padding: 5px 12px;
  font-size: 14px;
  min-width: auto;
}

/* Win16-style input */
.win-input {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  padding: 5px 6px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  background: #fff;
}

/* Win16 listbox */
.win-list {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  background: #fff;
  overflow-y: auto;
  position: relative;
}

/* Dictionary split pane */
.dict-word {
  padding: 3px 6px;
  cursor: pointer;
  border-bottom: 1px dotted #ddd;
  font-size: 14px;
  font-weight: bold;
}
.dict-word:hover { background: #e8e8ff; }

.dict-sel { background: #000080; color: #fff; }
.dict-sel:hover { background: #000080; }
.dict-meaning {
  padding: 4px 6px;
  border-bottom: 1px solid #ccc;
  cursor: pointer;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.dict-meaning:hover { background: #e8e8ff; }
.dict-meaning .row-num { flex-shrink: 0; min-width: 24px; color: #888; }
.dict-meaning .meaning-content { flex: 1; display: flex; flex-direction: column; }
.meaning-sel { background: #000080; color: #fff; }
.meaning-sel .row-num { color: #88aaff; }
.meaning-sel:hover { background: #000080; }

/* 3D group box */
.group-box {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  padding: 8px 4px 4px 4px;
  margin-top: 4px;
  position: relative;
}
.group-box legend {
  position: absolute;
  top: -9px;
  left: 8px;
  background: #c0c0c0;
  padding: 0 6px;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}
.win-list table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.win-list th {
  background: #c0c0c0;
  text-align: left;
  padding: 3px 6px;
  font-weight: 600;
  border-bottom: 1px solid #808080;
  white-space: nowrap;
}
.win-list td {
  padding: 2px 6px;
  border-bottom: 1px solid #e0e0e0;
  white-space: nowrap;
}
.win-list tr.sel td {
  background: #000080;
  color: #fff;
}
.win-list tr:hover td {
  background: #d0d0ff;
}

/* Tab strip (win16 common control) */
.tab-strip {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #808080;
  margin-bottom: 4px;
}
.tab-strip a {
  padding: 3px 12px;
  border: 1px solid #808080;
  border-bottom: none;
  background: #c0c0c0;
  text-decoration: none;
  color: #000;
  font-size: 12px;
  cursor: pointer;
  margin-bottom: -1px;
}
.tab-strip a.active {
  background: #fff;
  border-bottom: 1px solid #fff;
  font-weight: bold;
}

/* Group box */
.group-box {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  padding: 12px 6px 6px;
  margin: 6px 0;
  position: relative;
}
.group-box legend {
  background: #c0c0c0;
  padding: 0 6px;
  position: absolute;
  top: -8px;
  left: 6px;
  font-size: 14px;
  font-weight: 700;
}

/* Win16 status bar */
.status-bar {
  flex-shrink: 0;
  background: #c0c0c0;
  border-top: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  padding: 0 8px;
  display: flex;
  font-size: 13px;
  height: 24px;
  min-height: 24px;
  max-height: 24px;
  line-height: 24px;
  align-items: center;
  box-sizing: border-box;
}
.status-bar .status-sep {
  width: 2px;
  height: 14px;
  background: #808080;
  margin: 0 6px;
  border-left: 1px solid #fff;
}

/* Scrollbar-like areas */
.scroll-area {
  overflow-y: auto;
  max-height: 400px;
}

/* Welcome screen — matches EXE toolbar dialog (104×50 btns + 98×98 Acer banner) */
.welcome-body {
  padding: 10px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  background: #c0c0c0;
  box-sizing: border-box;
}
.welcome-panel {
  border: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  background: #c0c0c0;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-sizing: border-box;
}
.welcome-grid {
  display: grid;
  grid-template-columns: repeat(3, 104px);
  grid-template-rows: repeat(2, 50px);
  gap: 6px;
  justify-content: center;
  flex-shrink: 0;
  line-height: 0;
}
.welcome-btn {
  width: 104px;
  height: 50px;
  padding: 0;
  margin: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  display: block;
  line-height: 0;
  user-select: none;
  -webkit-user-drag: none;
  outline: none;
}
.welcome-btn:focus,
.welcome-btn:focus-visible {
  outline: none;
}
.welcome-btn img {
  width: 104px;
  height: 50px;
  display: block;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  pointer-events: none;
  -webkit-user-drag: none;
}
.welcome-sep {
  height: 2px;
  border-top: 1px solid #808080;
  border-bottom: 1px solid #fff;
  margin: 0 2px;
  flex-shrink: 0;
}
.welcome-banner {
  width: 328px;
  height: 102px;
  margin: 0 auto;
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  background: #800000;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  box-sizing: border-box;
  flex-shrink: 0;
}
.welcome-banner-logo {
  width: 98px;
  height: 98px;
  flex-shrink: 0;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  display: block;
}
.welcome-banner-brand {
  flex: 1;
  min-width: 0;
  height: 98px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 10px 6px;
  box-sizing: border-box;
  gap: 4px;
}
.welcome-banner-svg {
  width: 100%;
  height: 48px;
  display: block;
  object-fit: contain;
  object-position: center;
}
.welcome-banner-sub {
  margin: 0;
  padding: 0;
  color: #fff;
  font-family: 'Times New Roman', 'MS Serif', serif;
  font-size: 18px;
  font-style: italic;
  font-weight: 400;
  line-height: 1;
  white-space: nowrap;
  text-align: center;
  letter-spacing: 0;
}

/* Hangman — pixel sizes match EXE assets: 25 / 52×76 / 98 / 63×39 */
.hm-main {
  display: flex; flex-direction: column;
  width: 330px; padding: 6px 8px 6px; gap: 6px;
  background: #c0c0c0; box-sizing: border-box;
}
.hm-upper {
  display: flex; flex-direction: row; gap: 10px;
  align-items: flex-start;
}
.hm-left {
  display: flex; flex-direction: column; gap: 1px;
  width: 59px; padding: 2px; line-height: 0;
  border: 2px solid; border-color: #808080 #fff #fff #808080;
  background: #c0c0c0; box-sizing: border-box; flex-shrink: 0;
  align-items: center;
}
.hm-keyrow { display: flex; gap: 1px; line-height: 0; justify-content: center; }
.hm-key {
  width: 25px; height: 25px; padding: 0; margin: 0; border: 0;
  box-sizing: border-box;
  background: transparent; cursor: pointer; display: block;
  image-rendering: pixelated; image-rendering: crisp-edges;
}
.hm-key.used {
  cursor: default;
  opacity: 0.65;
  filter: contrast(0.85);
  outline: 1px dotted #808080;
  outline-offset: -2px;
}
.hm-key.idle { cursor: default; }
.kbd-grid { display: grid; grid-template-columns: repeat(5,auto); gap: 4px; justify-content: center; }
.kbd-key { cursor: pointer; width: 25px; height: 25px; padding: 0; margin: 0; border: 0; background: transparent; image-rendering: pixelated; image-rendering: crisp-edges; }
.kbd-key:hover { filter: brightness(1.1); }
.hm-right {
  width: 250px;
  height: 397px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  flex-shrink: 0;
}
.hm-brand {
  width: 250px;
  height: 86px;
  box-sizing: border-box;
  background: #800000;
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 10px 6px;
  gap: 4px;
  flex-shrink: 0;
  overflow: hidden;
}
.hm-brand-svg {
  width: 100%;
  height: 48px;
  display: block;
  object-fit: contain;
  object-position: center;
}
.hm-brand-sub {
  margin: 0;
  padding: 0;
  color: #fff;
  font-family: 'Times New Roman', 'MS Serif', serif;
  font-size: 18px;
  font-style: italic;
  font-weight: 400;
  line-height: 1;
  white-space: nowrap;
  text-align: center;
  letter-spacing: 0;
}
.hm-status {
  display: flex; flex-direction: column;
  gap: 0; flex-shrink: 0;
  width: 250px;
  margin-top: 6px;
}
.hm-status-row {
  display: flex; flex-direction: row;
  align-items: flex-start; gap: 10px;
  width: 100%;
}
.hm-gallows {
  width: 60px; height: 84px; box-sizing: border-box;
  margin-top: 20px;
  border: 2px solid; border-color: #808080 #fff #fff #808080;
  background: #c0c0c0; padding: 2px; line-height: 0; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.hm-gallows img {
  width: 52px; height: 76px; display: block;
  image-rendering: pixelated; image-rendering: crisp-edges;
}
.hm-scorecol {
  width: 98px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-left: auto;
}
.hm-scorelabel {
  height: 16px; line-height: 16px;
  font-size: 13px; font-weight: 700;
  font-family: 'MS Sans Serif', Tahoma, sans-serif;
  margin-left: 4px;
}
.hm-scorebox {
  width: 100%; box-sizing: border-box;
  border: 2px solid; border-color: #808080 #fff #fff #808080;
  background: #c0c0c0; padding: 12px 8px;
  font-size: 18px; font-weight: 700;
  font-family: 'MS Sans Serif', Tahoma, sans-serif;
  display: flex; align-items: center; justify-content: center;
}
.hm-ad {
  width: 98px; height: 98px; line-height: 0; flex-shrink: 0;
  align-self: flex-end;
}
.hm-ad img {
  width: 98px; height: 98px; display: block;
  image-rendering: pixelated; image-rendering: crisp-edges;
}
.hm-wordbox {
  width: 250px; height: 38px; box-sizing: border-box;
  border: 2px solid; border-color: #808080 #fff #fff #808080;
  background: #c0c0c0; padding: 4px 6px;
  font-size: 18px; font-weight: 800;
  letter-spacing: 4px;
  color: #000;
  font-family: 'MS Sans Serif', 'Microsoft Sans Serif', Tahoma, 'Arial Black', sans-serif;
  display: flex; align-items: center; justify-content: center;
  white-space: nowrap; overflow: hidden;
  margin-top: auto;
  flex-shrink: 0;
}
.hm-btns {
  display: flex; flex-direction: row; gap: 8px;
  line-height: 0; flex-shrink: 0;
  justify-content: center;
  width: 250px;
  margin-top: 8px;
  margin-bottom: 0;
}
.hm-btn {
  width: 63px; height: 39px; padding: 0; margin: 0; border: 0;
  background: transparent; cursor: pointer; display: block;
  image-rendering: pixelated; image-rendering: crisp-edges;
}
.hm-btn:active { filter: brightness(0.92); }
.hm-btn.disabled {
  opacity: 0.45;
  filter: grayscale(1) contrast(0.85);
  cursor: default;
  pointer-events: none;
}

/* Other */
.hidden { display: none; }
.loading { padding: 20px; text-align: center; color: #666; }
.pagination { display: flex; gap: 4px; align-items: center; justify-content: center; padding: 4px 0; font-size: 13px; }
.pagination button { background: #c0c0c0; border: 1px solid; border-color: #fff #808080 #808080 #fff; padding: 2px 10px; font-size: 13px; cursor: pointer; font-family: inherit; }
.pagination button:active { border-color: #808080 #fff #fff #808080; }
.pagination button:disabled { opacity: .5; cursor: default; }
.pagination span { padding: 0 4px; }
.flag { display: inline-block; padding: 0 4px; font-size: 10px; }
.flag-normal { color: #080; }
.flag-variant { color: #800; }

/* Quiz topic selection — Klavye Seçimi style: list left, buttons right */
.quiz-topic-panel {
  display: flex;
  flex-direction: row;
  gap: 10px;
  align-items: stretch;
  min-height: 0;
  height: 100%;
}
.quiz-topic-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.quiz-topic-prompt {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  flex-shrink: 0;
}
.quiz-topic-list {
  flex: 1;
  min-height: 180px;
  max-height: 280px;
  overflow-y: auto;
  background: #fff;
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  box-shadow: inset 1px 1px 0 #000;
  padding: 1px;
  outline: none;
}
.quiz-topic-row {
  padding: 1px 4px;
  font-size: 13px;
  line-height: 16px;
  cursor: default;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.quiz-topic-row.selected {
  background: #000080;
  color: #fff;
}
.quiz-topic-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
  line-height: 0;
  padding-top: 18px;
}
.quiz-topic-btn {
  width: 63px;
  height: 39px;
  border: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  cursor: pointer;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  display: block;
}
.quiz-topic-btn:active {
  filter: brightness(0.92);
}
#quizTopicDialog .win-window {
  width: 340px;
  height: auto;
  position: relative;
  top: auto;
  left: auto;
  transform: none;
}

/* Dropdown menu */
.dropdown {
  display: none;
  position: absolute;
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  z-index: 1000;
  padding: 2px;
  min-width: 180px;
  box-shadow: 2px 2px 0 rgba(0,0,0,0.3);
}
.dropdown.open { display: block; }
.dropdown-item {
  padding: 3px 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid transparent;
}
.dropdown-item:hover {
  background: #000080;
  color: #fff;
  border-color: #fff #808080 #808080 #fff;
}
.dropdown-sep {
  border-top: 1px solid #808080;
  border-bottom: 1px solid #fff;
  margin: 2px 4px;
}

/* Dialog overlay */
.dialog-overlay {
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4);
  z-index: 9999;
}
.dialog-overlay.open { display: flex; align-items: center; justify-content: center; }

/* Context help */
.help-text { font-size: 11px; color: #444; padding: 8px; }
</style>
</head>
<body>

<div class="desktop">
  <!-- Main Application Window -->
  <div class="main-win" id="mainWin">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar Türkçe Dil Kılavuzu</span></div>
    <div class="win-body" style="padding:0;">
      <!-- Menu Bar -->
      <div class="menu-bar" id="menuBar">
        <div class="menu-items-group">
          <div class="menu-item" onclick="toggleMenu('fileMenu', event)">Dosya</div>
          <div class="menu-item" onclick="toggleMenu('editMenu', event)">Düzen</div>
          <div class="menu-item" onclick="toggleMenu('searchMenu', event)">Ara</div>
          <div class="menu-item" onclick="toggleMenu('checkMenu', event)">Denetim</div>
          <div class="menu-item" onclick="toggleMenu('dictMenu', event)">Sözlük</div>
          <div class="menu-item" onclick="toggleMenu('gameMenu', event)">Oyun</div>
          <div class="menu-item" onclick="toggleMenu('statsMenu', event)">İstatistik</div>
          <div class="menu-item" onclick="toggleMenu('optionsMenu', event)">Seçenekler</div>
          <div class="menu-item" onclick="toggleMenu('helpMenu', event)">Yardım</div>
        </div>
        <div class="retro-zoom-controls">
          <span class="retro-zoom-label">🔍 Ölçek:</span>
          <button class="retro-zoom-btn active" onclick="setUiScale(1.0)" id="zoomBtn-1_0" title="%100 Orijinal">1x</button>
          <button class="retro-zoom-btn" onclick="setUiScale(1.25)" id="zoomBtn-1_25" title="%125 Orta">1.25x</button>
          <button class="retro-zoom-btn" onclick="setUiScale(1.5)" id="zoomBtn-1_5" title="%150 Geniş">1.5x</button>
          <button class="retro-zoom-btn" onclick="setUiScale(2.0)" id="zoomBtn-2_0" title="%200 Büyük">2x</button>
        </div>
      </div>

      <!-- Dropdown Menus -->
      <div class="dropdown" id="fileMenu">
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">&Yeni</div>
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Dosya &Açma</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Çıkış</div>
      </div>
      <div class="dropdown" id="editMenu">
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Kopyala</div>
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Yapıştır</div>
      </div>
      <div class="dropdown" id="searchMenu">
        <div class="dropdown-item" onclick="showFindDialog()">Al ve bul</div>
        <div class="dropdown-item" onclick="showReplaceDialog()">Değiştir</div>
      </div>
      <div class="dropdown" id="checkMenu">
        <div class="dropdown-item" onclick="openTextEditor()">Türkçe Denetim Editörü</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="showCheckOptions()">Denetim Opsiyonları</div>
      </div>
      <div class="dropdown" id="dictMenu">
        <div class="dropdown-item" onclick="openWindow('ing-tr')">Leb demeden (İngilizce → Türkçe)</div>
        <div class="dropdown-item" onclick="openWindow('tr-ing')">Leb demeden (Türkçe → İngilizce)</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="openWindow('synonyms')">Eş Anlamlı kelimeler</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="openWindow('tr-tr')">Türkçe Leb Demeden</div>
      </div>
      <div class="dropdown" id="gameMenu">
        <div class="dropdown-item" onclick="openWindow('quiz')">Kelime Oyunu</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="showOyunKelimeleriDialog()">Oyun Kelimeleri...</div>
      </div>
      <div class="dropdown" id="statsMenu">
        <div class="dropdown-item" onclick="openStatsWindow()">Metin İstatistik</div>
      </div>
      <div class="dropdown" id="optionsMenu">
        <div class="dropdown-item" onclick="openCharacterList('win-kbd-select')">Karakter Listesi</div>
        <div class="dropdown-item" onclick="showKeyboardModule()">Klavye Seçimi</div>
        <div class="dropdown-item" onclick="showVirtualKeyboard()">Klavye Harita Göstergesi</div>
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Genel tanımlar</div>
      </div>
      <div class="dropdown" id="helpMenu">
        <div class="dropdown-item" onclick="showAbout()">MoonStar Hakkında</div>
      </div>

      <!-- Client Area for Child Windows -->
      <div class="work-area" id="workArea" style="flex:1 1 0;min-height:0;">
        <!-- Windows will be added here dynamically -->
      </div>
    </div>

    <!-- Status Bar -->
    <div class="status-bar">
      <span>MoonStar Veri Gezgini</span>
      <span class="status-sep"></span>
      <span id="statusText">TRK: 17.975 | TUR: 26.775 | SYN: 10.640 | REV: 37.043 | KELİME OYUNU: 12.437</span>
    </div>
  </div>
</div>

<!-- About Dialog -->
<div class="dialog-overlay" id="aboutDialog">
  <div class="win-window" style="width:380px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar Hakkında</span>
      <div class="win-title-btns"><button onclick="closeDialog('aboutDialog')">✕</button></div>
    </div>
    <div class="win-body" style="padding:16px 12px;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;font-size:12px;display:flex;flex-direction:column;gap:12px;box-sizing:border-box;">
      <!-- Row 1: MoonStar info -->
      <div style="display:flex;gap:12px;align-items:center;">
        <!-- Left column container aligned with Row 2's Acer logo width -->
        <div style="width:102px;display:flex;justify-content:center;align-items:center;flex-shrink:0;">
          <div style="border: 2px solid; border-color: #808080 #fff #fff #808080; padding: 4px; background: #c0c0c0; display: inline-block;">
            <img src="/assets/moonstar_icon.png?v=2" width="32" height="32" style="image-rendering: pixelated; display: block;">
          </div>
        </div>
        <div style="line-height:1.3;font-weight:bold;">
          <div style="font-weight:bold;font-size:13px;margin-bottom:2px;">MoonStar Türkçe Dil Kılavuzu</div>
          <div>CopyRight &copy; 1994-1995 MoonStar</div>
          <div>Tel : (0212) 230 21 95 - 231 96 24</div>
          <div>Fax : (0212) 231 59 34</div>
        </div>
      </div>
      
      <!-- Row 2: İhlas / Acer info -->
      <div style="display:flex;gap:12px;align-items:flex-start;">
        <div style="width:102px;flex-shrink:0;display:flex;justify-content:flex-start;">
          <div style="border: 2px solid; border-color: #808080 #fff #fff #808080; background: #c0c0c0; display: inline-block;">
            <img src="/assets/moonstar_banner.png?v=2" width="98" height="98" style="image-rendering: pixelated; display: block;">
          </div>
        </div>
        <div style="line-height:1.3;font-weight:bold;margin-top:4px;">
          <div style="font-weight:bold;font-size:13px;margin-bottom:2px;">İHLAS Bilgi İşlem ve Ticaret A.Ş.</div>
          <div>Tel : (0212) 552 45 41</div>
          <div>Fax : (0212) 652 87 45</div>
        </div>
      </div>
      
      <!-- Box 3: Dikkat warning -->
      <div style="border: 2px solid; border-color: #808080 #fff #fff #808080; padding: 10px 8px; font-size: 11px; line-height: 1.4; background: #c0c0c0; text-align: center; font-weight:bold;">
        <div style="font-weight:bold; font-size:12px; margin-bottom: 8px; letter-spacing: 4px;">D İ K K A T</div>
        <div style="margin-bottom: 6px;">
          Bu ürün MoonStar A.Ş. tarafından üretilmiş olup, sadece İHLAS A.Ş.'nin pazarladığı bilgisayarlar üzerinde profesyonel olmayan amaçlar için kullanılabilir.
        </div>
        <div>
          Aksi 5846 sayılı Fikir ve Sanat Eserleri kanunu göre suç teşkil edecektir.
        </div>
      </div>
      
      <!-- Bottom row: Tamam button -->
      <div style="display:flex; justify-content:center; margin-top: 4px;">
        <img class="quiz-topic-btn" width="63" height="39" 
             src="/assets/extracted/img_02ae00_63x39_4bpp.png" 
             data-normal="/assets/extracted/img_02ae00_63x39_4bpp.png" 
             data-pressed="/assets/extracted/img_039800_63x39_4bpp.png"
             onmousedown="this.src=this.dataset.pressed" 
             onmouseup="this.src=this.dataset.normal" 
             onmouseleave="this.src=this.dataset.normal"
             onclick="closeDialog('aboutDialog')"
             style="cursor:pointer; image-rendering:pixelated; flex-shrink: 0;">
      </div>
    </div>
  </div>
</div>

<!-- Find Dialog -->
<div class="dialog-overlay" id="findDialog">
  <div class="win-window" style="min-width:350px;">
    <div class="win-title inactive"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Al ve bul</span>
      <div class="win-title-btns"><button onclick="closeDialog('findDialog')">✕</button></div>
    </div>
    <div class="win-body" style="padding:12px;">
      <div style="margin-bottom:8px;">
        <label>Bulunacak:</label><br>
        <input class="win-input" type="text" id="findInput" style="width:100%;" onkeyup="if(event.key==='Enter') doFind()">
      </div>
      <div style="margin-bottom:8px;">
        <label>Bulma tipleri:</label><br>
        <label><input type="radio" name="findType" checked onclick="document.getElementById('findInput').placeholder='Kelime girin...'"> Tüm sözlükler</label><br>
        <label><input type="radio" name="findType" onclick="document.getElementById('findInput').placeholder='İngilizce kelime girin...'"> İngilizce → Türkçe</label><br>
        <label><input type="radio" name="findType" onclick="document.getElementById('findInput').placeholder='Türkçe kelime girin...'"> Türkçe → Türkçe</label><br>
        <label><input type="radio" name="findType" onclick="document.getElementById('findInput').placeholder='Konu veya kelime...'"> Adam Asma</label>
      </div>
      <div style="margin-top:8px;text-align:right;">
        <button class="win-btn primary" onclick="doFind()">Bul</button>
        <button class="win-btn" onclick="closeDialog('findDialog')">İptal</button>
      </div>
      <div id="findResults" style="margin-top:8px;max-height:200px;overflow-y:auto;font-size:13px;"></div>
    </div>
  </div>
</div>

<!-- Spell Check Dialog -->
<div class="dialog-overlay" id="spellCheckDialog">
  <div class="win-window" style="width:380px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Yazım Denetimi</span>
      <div class="win-title-btns"><button onclick="closeSpellCheck()">✕</button></div>
    </div>
    <div class="win-body" style="padding:10px;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;font-size:12px;display:flex;gap:12px;box-sizing:border-box;">
      <!-- Left side (Fields and List) -->
      <div style="flex:1;display:flex;flex-direction:column;gap:8px;min-height:0;">
        <div>
          <div style="font-weight:bold;margin-bottom:2px;">Hatalı Sözcük:</div>
          <input class="win-input" type="text" id="spell-err-word" style="width:100%;font-weight:bold;background:#d8d8d8;color:#555;" readonly>
        </div>
        <div>
          <div style="font-weight:bold;margin-bottom:2px;">Öneri:</div>
          <input class="win-input" type="text" id="spell-sug-word" style="width:100%;font-weight:bold;background:#fff;">
        </div>
        <div style="flex:1;display:flex;flex-direction:column;min-height:0;">
          <div style="font-weight:bold;margin-bottom:2px;">Alternatifler:</div>
          <div class="win-list" id="spell-suggestions" style="flex:1;overflow-y:auto;background:#fff;height:120px;"></div>
        </div>
      </div>
      <!-- Right side (Actions) -->
      <div style="width:75px;display:flex;flex-direction:column;gap:10px;justify-content:flex-start;align-items:center;padding-top:14px;flex-shrink:0;">
        <!-- Yoksay Button -->
        <button class="win-btn" onclick="spellCheckIgnore()" style="width:68px;height:24px;font-size:11px;font-weight:bold;">Yoksay</button>
        <!-- Değiştir Button -->
        <button class="win-btn primary" onclick="spellCheckReplace()" style="width:68px;height:24px;font-size:11px;font-weight:bold;">Değiştir</button>
        <!-- Ekle Button -->
        <button class="win-btn" onclick="spellCheckAdd()" style="width:68px;height:24px;font-size:11px;font-weight:bold;">Ekle</button>
        <!-- Kapat Button -->
        <button class="win-btn" onclick="closeSpellCheck()" style="width:68px;height:24px;font-size:11px;font-weight:bold;margin-top:10px;">Kapat</button>
      </div>
    </div>
  </div>
</div>

<!-- Character List Dialog -->
<div class="dialog-overlay" id="charListDialog">
  <div class="win-window" style="width:460px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Karakter Listesi</span>
      <div class="win-title-btns"><button onclick="closeCharacterList()">✕</button></div>
    </div>
    <div class="win-body" style="padding:10px;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;font-size:12px;display:flex;flex-direction:column;gap:10px;box-sizing:border-box;">
      
      <!-- Character Grid Container -->
      <div style="border:2px solid;border-color:#808080 #fff #fff #808080;background:#808080;padding:2px;display:flex;justify-content:center;align-items:center;">
        <div id="char-grid-holder" style="display:grid;grid-template-columns:repeat(16, 26px);gap:1px;background:#808080;"></div>
      </div>
      
      <!-- Bottom Details and Button -->
      <div style="display:flex;justify-content:space-between;align-items:center;user-select:none;padding-top:4px;">
        <div style="font-family:'Courier New', monospace;font-size:13px;font-weight:bold;line-height:1.4;color:#000;text-shadow:0.5px 0.5px #fff;">
          <div>ASCII = <span id="char-ascii-val">32</span></div>
          <div>HEX   = <span id="char-hex-val">20</span></div>
        </div>
        
        <!-- Tamam Button using original thumbs-up asset -->
        <img class="quiz-topic-btn" id="char-btn-tamam" width="63" height="39" 
             src="/assets/extracted/img_02ae00_63x39_4bpp.png" 
             data-normal="/assets/extracted/img_02ae00_63x39_4bpp.png" 
             data-pressed="/assets/extracted/img_039800_63x39_4bpp.png"
             onmousedown="this.src=this.dataset.pressed" 
             onmouseup="this.src=this.dataset.normal" 
             onmouseleave="this.src=this.dataset.normal"
             onclick="confirmCharacterSelection()"
             style="cursor:pointer; image-rendering:pixelated; flex-shrink: 0;"
             alt="Tamam" title="Tamam">
      </div>
      
    </div>
  </div>
</div>

<!-- Kelime Oyunu topic picker (EXE-style listbox + Tamam/İptal) -->
<div class="dialog-overlay" id="quizTopicDialog">
  <div class="win-window">
    <div class="win-title inactive"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Kelime Oyunu</span>
      <div class="win-title-btns"><button onclick="closeQuizTopicDialog()">✕</button></div>
    </div>
    <div class="win-body" style="padding:8px;height:320px;">
      <div class="quiz-topic-panel">
        <div class="quiz-topic-main">
          <div class="quiz-topic-prompt">Kelime Oyunu oynamak için bir konu seçin.</div>
          <div class="quiz-topic-list" id="quizTopicList" tabindex="0"
               onkeydown="quizTopicKeydown(event)"></div>
        </div>
        <div class="quiz-topic-actions">
          <img class="quiz-topic-btn" width="63" height="39" src="/assets/btn_tamam.png" alt="Tamam" title="Tamam" onclick="confirmQuizTopic()">
          <img class="quiz-topic-btn" width="63" height="39" src="/assets/btn_iptal.png" alt="İptal" title="İptal" onclick="closeQuizTopicDialog()">
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Oyun Kelimeleri Dialog (EXE offset 0x5F400) -->
<div class="dialog-overlay" id="oyunKelimeleriDialog">
  <div class="win-window" style="width:280px;">
    <div class="win-title inactive"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Oyun Kelimeleri</span>
      <div class="win-title-btns"><button onclick="closeOyunKelimeleriDialog()">✕</button></div>
    </div>
    <div class="win-body" style="padding:12px;background:#c0c0c0;">
      <div class="group-box" style="padding:10px 14px;margin-bottom:12px;">
        <legend>Kelime Kaynağı</legend>
        <div style="display:flex;flex-direction:column;gap:8px;font-size:13px;">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="radio" name="oyunKelimeKaynagi" value="main" checked> Ana Sözlükten
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="radio" name="oyunKelimeKaynagi" value="user"> Kullanıcı Sözlükten
          </label>
        </div>
      </div>
      <div style="display:flex;justify-content:center;gap:12px;">
        <img class="quiz-topic-btn" width="63" height="39" src="/assets/btn_tamam.png" alt="Tamam" title="Tamam" onclick="confirmOyunKelimeleri()">
        <img class="quiz-topic-btn" width="63" height="39" src="/assets/btn_iptal.png" alt="İptal" title="İptal" onclick="closeOyunKelimeleriDialog()">
      </div>
    </div>
  </div>
</div>

<script>
// ─── State & UI Scaling ───────────────────────────────────────────────────
let state = {
  windows: {},
  nextWindowId: 0,
  pageCache: {},
  uiScale: 1.0
};

function setUiScale(scale) {
  scale = Number(scale) || 1.0;
  state.uiScale = scale;
  try {
    localStorage.setItem('moonstar_ui_scale', scale);
  } catch(e) {}

  document.body.style.zoom = scale;

  document.querySelectorAll('.retro-zoom-btn').forEach(btn => btn.classList.remove('active'));
  const btnId = 'zoomBtn-' + (scale === 1 ? '1_0' : (scale === 1.25 ? '1_25' : (scale === 1.5 ? '1_5' : '2_0')));
  const btn = document.getElementById(btnId);
  if (btn) btn.classList.add('active');
}

(function initUiScale() {
  let scale = 1.0;
  try {
    const saved = localStorage.getItem('moonstar_ui_scale');
    if (saved) scale = parseFloat(saved);
  } catch(e) {}
  setUiScale(scale || 1.0);
})();

// Keyboard shortcuts for zooming (Ctrl/Cmd + +, -, 0)
window.addEventListener('keydown', function(ev) {
  if (ev.ctrlKey || ev.metaKey) {
    if (ev.key === '+' || ev.key === '=') {
      ev.preventDefault();
      const scales = [1.0, 1.25, 1.5, 2.0];
      const cur = state.uiScale || 1.0;
      const next = scales.find(s => s > cur) || 2.0;
      setUiScale(next);
    } else if (ev.key === '-' || ev.key === '_') {
      ev.preventDefault();
      const scales = [2.0, 1.5, 1.25, 1.0];
      const cur = state.uiScale || 1.0;
      const prev = scales.find(s => s < cur) || 1.0;
      setUiScale(prev);
    } else if (ev.key === '0') {
      ev.preventDefault();
      setUiScale(1.0);
    }
  }
});

// ─── Win16 Alert Dialog ──────────────────────────────────────────────────
function winAlert(msg) {
  const id = 'alert-' + Date.now();
  const ov = document.createElement('div');
  ov.className = 'dialog-overlay open';
  ov.id = id;
  ov.innerHTML = `<div class="win-window" style="min-width:300px;max-width:400px;">
    <div class="win-title inactive"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar</span>
      <div class="win-title-btns"><button onclick="document.getElementById('${id}').remove()">✕</button></div>
    </div>
    <div class="win-body" style="padding:20px;text-align:center;">
      <div style="font-size:14px;margin-bottom:16px;">${msg}</div>
      <button class="win-btn" onclick="document.getElementById('${id}').remove()">Tamam</button>
    </div>
  </div>`;
  document.body.appendChild(ov);
}

// ─── Menu System ──────────────────────────────────────────────────────────
function closeAllMenus() {
  document.querySelectorAll('.dropdown').forEach(m => m.classList.remove('open'));
  document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('open'));
}

function toggleMenu(id, event) {
  event.stopPropagation();
  const menu = document.getElementById(id);
  const isOpen = menu.classList.contains('open');
  closeAllMenus();
  if (!isOpen) {
    menu.classList.add('open');
    event.target.classList.add('open');
    // Position menu below menu item
    const rect = event.target.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.top = (rect.bottom + 1) + 'px';
  }
}

document.addEventListener('click', function(e) {
  if (!e.target.closest('.menu-item') && !e.target.closest('.dropdown')) {
    closeAllMenus();
  }
});

// ─── Windows System ──────────────────────────────────────────────────────
function closeAllWindows() {
  closeQuizTopicDialog();
  Object.keys(state.windows).forEach(k => {
    const el = document.getElementById(k);
    if (el) el.remove();
    delete state.windows[k];
  });
}

function openWindow(type, opts) {
  opts = opts || {};
  closeAllMenus();
  if (type === 'quiz') {
    openHangman();
    return;
  }
  if (!opts.keep) closeAllWindows();
  const id = 'win-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');
  
  let config = { title: 'Pencere', content: '<div class="loading">Yükleniyor...</div>', width: 'auto', height: 'auto' };
  
  switch(type) {
    case 'ing-tr':
      config = { title: 'İngilizce Türkçe Sözlük', type: 'trk', w: 560, h: 380 };
      break;
    case 'tr-ing':
      config = { title: 'Türkçe İngilizce Sözlük', type: 'rev', w: 560, h: 380 };
      break;
    case 'synonyms':
      config = { title: 'Türkçe Eş Anlamlı Sözcükler', type: 'syn', w: 600, h: 420 };
      break;
    case 'tr-tr':
      config = { title: 'Türkçe Leb Demeden', type: 'tur', w: 480, h: 380 };
      break;
    case 'stats':
      config = { title: 'Metin İstatistik', type: 'stats', w: 480, h: 340 };
      break;
    default:
      config = { title: 'Pencere', type: 'trk', w: 400, h: 300 };
  }

  let html = `<div class="win-window" id="${id}" style="width:${config.w}px;height:${config.h}px;${opts.keep ? 'top:36px;left:48px;transform:none;' : ''}">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">${config.title}</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  
  if (config.type === 'trk' || config.type === 'rev') {
    html += `<div class="win-body" style="padding:10px;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:8px;">
      
      <!-- Top Search row: Sözcük label, input field and Tamam button -->
      <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-shrink:0;gap:8px;">
        <div style="flex:1;display:flex;flex-direction:column;gap:4px;">
          <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">Sözcük</div>
          <input class="win-input" type="text" style="width:100%;background:#c0c0c0;" id="${id}-search" oninput="dictSearchDebounced('${id}')" onkeydown="if(event.key==='Enter') closeWindow('${id}')">
        </div>
        <img class="quiz-topic-btn" width="63" height="39" src="/assets/btn_tamam.png" alt="Tamam" title="Tamam" onclick="closeWindow('${id}')" style="cursor:pointer; image-rendering:pixelated; flex-shrink:0;">
      </div>

      <!-- Mid lists row: left listbox and right listbox -->
      <div style="display:flex;gap:12px;flex:1;min-height:0;">
        <div style="flex:1;display:flex;flex-direction:column;gap:4px;min-height:0;">
          <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">${config.type==='trk'?'İngilizce Sözcükler':'Türkçe Sözcükler'}</div>
          <div class="win-list" style="flex:1;overflow-y:auto;" id="${id}-list"></div>
        </div>
        <div style="flex:1;display:flex;flex-direction:column;gap:4px;min-height:0;">
          <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">${config.type==='trk'?'Türkçe Karşılıklar':'İngilizce Karşılıklar'}</div>
          <div class="win-list" style="flex:1;overflow-y:auto;" id="${id}-defn"></div>
        </div>
      </div>
      
      <!-- Bottom detail row: label and read-only text field -->
      <div style="flex-shrink:0;display:flex;flex-direction:column;gap:4px;">
        <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">${config.type==='trk'?'Türkçe Karşılık':'İngilizce Karşılık'}</div>
        <input class="win-input" type="text" readonly style="width:100%;background:#c0c0c0;color:#000;" id="${id}-detail">
      </div>
      
      <!-- Status bar -->
      <div class="win-status" id="${id}-status" style="flex-shrink:0;padding:2px 4px;border-top:1px solid #808080;font-size:11px;"></div>
    </div>`;
  } else if (config.type === 'syn') {
    html += `<div class="win-body" style="padding:10px;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:8px;box-sizing:border-box;">
      
      <div style="display:flex;gap:12px;flex:1;min-height:0;">
        <!-- Left Column -->
        <div style="width:230px;display:flex;flex-direction:column;gap:8px;flex-shrink:0;min-height:0;">
          <!-- Sözcük Row -->
          <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0;">
            <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">Sözcük</div>
            <input class="win-input" type="text" style="width:100%;background:#c0c0c0;font-weight:bold;font-family:inherit;" id="${id}-search" oninput="synTriggerSearch('${id}')" onkeydown="if(event.key==='Enter'){event.preventDefault();synTriggerSearch('${id}');}">
          </div>
          
          <!-- Kök Sözcük Row -->
          <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0;">
            <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">Kök Sözcük</div>
            <input class="win-input" type="text" readonly style="width:100%;background:#c0c0c0;color:#000;font-weight:bold;font-family:inherit;" id="${id}-stem">
          </div>
          
          <!-- Anlam Grupları Group Box -->
          <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin-top:4px;"><legend style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;padding:0 4px;">Anlam Grupları</legend>
            <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-groups"></div>
          </div>
          
          <!-- Bottom Buttons Row (Centered under Left Column) -->
          <div style="display:flex;gap:20px;flex-shrink:0;margin-top:-2px;margin-bottom:2px;justify-content:center;align-items:center;width:100%;">
            <!-- Tamam Button using original asset - closes window -->
            <img class="quiz-topic-btn" id="${id}-btn-tamam" width="63" height="39" 
                 src="/assets/extracted/img_02ae00_63x39_4bpp.png" 
                 data-normal="/assets/extracted/img_02ae00_63x39_4bpp.png" 
                 data-pressed="/assets/extracted/img_039800_63x39_4bpp.png"
                 onmousedown="this.src=this.dataset.pressed" 
                 onmouseup="this.src=this.dataset.normal" 
                 onmouseleave="this.src=this.dataset.normal"
                 onclick="closeWindow('${id}')"
                 style="cursor:pointer; image-rendering:pixelated; flex-shrink:0;">
                 
            <!-- Değiştir Button using original asset - permanently disabled -->
            <img class="quiz-topic-btn disabled" id="${id}-btn-degistir" width="63" height="39" 
                 src="/assets/extracted/img_04d600_63x39_4bpp.png" 
                 data-normal="/assets/extracted/img_04d600_63x39_4bpp.png" 
                 data-disabled="/assets/extracted/img_04d600_63x39_4bpp.png"
                 style="cursor:not-allowed; opacity:0.6; pointer-events:none; image-rendering:pixelated; flex-shrink:0;">
          </div>
        </div>
        
        <!-- Right Column (Eş Anlamları Group Box) -->
        <div class="group-box" style="flex:1;display:flex;flex-direction:column;margin-top:0;"><legend style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;padding:0 4px;">Eş Anlamları</legend>
          <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-defn"></div>
        </div>
      </div>
    </div>`;
  } else if (config.type === 'tur') {
    html += `<div class="win-body" style="padding:4px;flex:1;display:flex;flex-direction:column;min-height:0;">
      <div style="margin-bottom:4px;flex-shrink:0;">
        <input class="win-input" type="text" placeholder="Sözcük ara..." style="width:100%;" id="${id}-search" oninput="dictSearchDebounced('${id}')">
      </div>
      <div class="group-box" style="flex:1;display:flex;flex-direction:column;margin-bottom:4px;"><legend>Türkçe Sözcükler</legend>
        <div class="win-list" style="flex:1;overflow-y:auto;" id="${id}-list"></div>
      </div>
      <div class="win-status" id="${id}-status" style="flex-shrink:0;"></div>
    </div>`;
  } else if (config.type === 'stats') {
    html += `<div class="win-body" id="${id}-body" style="padding:4px;flex:1;display:flex;flex-direction:column;min-height:0;overflow:auto;"><div class="loading">Yükleniyor...</div></div>`;
  }
  
  html += `</div>`;
  
  // Insert at beginning of work area
  workArea.insertAdjacentHTML('afterbegin', html);
  
  // Load data
  state.windows[id] = { type: config.type, id: id };
  
  switch(config.type) {
    case 'trk': loadWindowDict(id, 'trk', '/api/trk'); break;
    case 'rev': loadWindowDict(id, 'rev', '/api/rev'); break;
    case 'syn': loadWindowDict(id, 'syn', '/api/syn'); break;
    case 'tur': loadWindowDict(id, 'tur', '/api/tur'); break;
    case 'stats': loadWindowStats(id); break;
  }
}

function closeWindow(id) {
  const win = document.getElementById(id);
  if (win) win.remove();
  delete state.windows[id];
  if (state.activeHangmanId === id) state.activeHangmanId = null;
  if (Object.keys(state.windows).length === 0) {
    showWelcomeWindow();
  }
}

// ─── Turkish Stemming Helper ──────────────────────────────────────────────
function getTurkishStem(word) {
  word = word.trim().replace(/^#/, '').toLowerCase();
  const suffixes = [
    'lerindeki', 'larındaki',
    'lerinde', 'larında', 'lerinden', 'larından',
    'leriyle', 'larıyla',
    'leri', 'ları',
    'iniz', 'ınız', 'umuz', 'ümüz',
    'nin', 'nın', 'nun', 'nün',
    'in', 'ın', 'un', 'ün',
    'im', 'ım', 'um', 'üm',
    'ye', 'ya', 'yi', 'yı', 'yu', 'yü',
    'de', 'da', 'te', 'ta',
    'den', 'dan', 'ten', 'tan',
    'le', 'la',
    'ce', 'ca',
    'se', 'sa',
    'i', 'ı', 'u', 'ü', 'e', 'a'
  ];
  if (word.length <= 3) return word;
  for (let suf of suffixes) {
    if (word.endsWith(suf)) {
      const stem = word.slice(0, -suf.length);
      if (stem.length >= 3) return stem;
    }
  }
  return word;
}

// ─── Synonyms Trigger & Search Logic ──────────────────────────────────────
function synTriggerSearch(winId) {
  const input = document.getElementById(winId + '-search');
  const q = input ? input.value.trim() : '';
  if (!q) return;
  
  const fullData = state.windowData && state.windowData[winId];
  if (!fullData || !fullData.length) return;
  
  const qnNorm = normalizeSearch(q);
  // Exact match first, then stem match, then prefix match
  let match = fullData.find(e => normalizeSearch(e.word) === qnNorm);
  if (!match) {
    const stemNorm = normalizeSearch(getTurkishStem(q));
    match = fullData.find(e => normalizeSearch(e.word) === stemNorm);
  }
  if (!match) {
    match = fullData.find(e => normalizeSearch(e.word).startsWith(qnNorm));
  }
  
  if (match) {
    // Update inputs: Sözcük shows user input, Kök Sözcük shows the root word
    document.getElementById(winId + '-search').value = q;
    document.getElementById(winId + '-stem').value = match.word;
    
    // Populate Anlam Grupları
    const grp = document.getElementById(winId + '-groups');
    const groups = match.groups || '';
    if (groups) {
      const parts = groups.split(' | ').filter(Boolean);
      const clusters = parts.map(p => {
        const segs = p.split('::');
        if (segs.length < 2) return null;
        const enWord = segs[0];
        const tag = segs.length >= 3 ? segs[1] : '1.Anlam';
        const trWords = (segs.length >= 3 ? segs[2] : segs[1]).split(',').filter(Boolean);
        return { en: enWord, tag: tag, tr: trWords };
      }).filter(Boolean);
      
      state.synClusters = state.synClusters || {};
      state.synClusters[winId] = clusters;
      
      if (clusters.length === 0) {
        grp.innerHTML = '<div style="color:#888;padding:8px;">Grup yok</div>';
      } else {
        let anlamCount = 0;
        grp.innerHTML = clusters.map((c, ci) => {
          let label = '';
          if (c.tag && (c.tag.includes('.Anlam') || c.tag === 'Mecaz' || c.tag === 'Argo')) {
            label = c.tag;
          } else if (c.tag === 'Mecaz' || c.en.toLowerCase().includes('mecaz')) {
            label = 'Mecaz';
          } else if (c.tag === 'Argo' || c.en.toLowerCase().includes('argo')) {
            label = 'Argo';
          } else {
            anlamCount++;
            label = anlamCount + '.Anlam';
          }
          return `<div class="dict-meaning${ci===0?' meaning-sel':''}" title="${c.en}" style="cursor:pointer; border-bottom:none; font-weight:bold; font-family:inherit;"
            onclick="synFilterGroup('${winId}', ${ci}, this)">${label}</div>`;
        }).join('');
        // Show first cluster's synonyms by default
        synFilterGroup(winId, 0, grp.querySelector('.dict-meaning'));
      }
    } else {
      grp.innerHTML = '<div style="color:#888;padding:8px;">Grup yok</div>';
      document.getElementById(winId + '-defn').innerHTML = '<div style="color:#888;padding:8px;">Eş anlamlı yok</div>';
      synSetReplaceEnabled(winId, false);
    }
  } else {
    // Not found
    document.getElementById(winId + '-stem').value = '';
    document.getElementById(winId + '-groups').innerHTML = '<div style="color:#888;padding:8px;">Sonuç bulunamadı</div>';
    document.getElementById(winId + '-defn').innerHTML = '<div style="color:#888;padding:8px;">Sonuç bulunamadı</div>';
    synSetReplaceEnabled(winId, false);
  }
}

// Called when user clicks an Anlam Grubu — filters Eş Anlamları to that cluster
function synFilterGroup(winId, clusterIdx, el) {
  const clusters = state.synClusters && state.synClusters[winId];
  if (!clusters || !clusters[clusterIdx]) return;

  // Highlight selected group
  const grp = document.getElementById(winId + '-groups');
  if (grp) {
    grp.querySelectorAll('.dict-meaning').forEach(e => e.classList.remove('meaning-sel'));
    if (el) el.classList.add('meaning-sel');
  }

  // Show only the Turkish synonyms from this cluster
  const df = document.getElementById(winId + '-defn');
  if (!df) return;
  const trWords = clusters[clusterIdx].tr;
  if (!trWords || !trWords.length) {
    df.innerHTML = '<div style="color:#888;padding:8px;">Eş anlamlı yok</div>';
    synSetReplaceEnabled(winId, false);
    return;
  }
  
  const currentWord = (document.getElementById(winId + '-search').value || '').trim();
  const synList = trWords.filter(w => w.toLowerCase() !== currentWord.toLowerCase());
  const displayWords = (synList.length > 0 ? synList : trWords).slice().sort((a, b) => a.localeCompare(b, 'tr'));

  df.innerHTML = displayWords.map((m, i) => {
    return `<div class="dict-word${i===0?' dict-sel':''}" style="border-bottom:none; font-weight:bold; font-family:inherit; cursor:pointer;" onclick="synonymSelect('${winId}',${i},'${m}')" ondblclick="synonymDblClick('${winId}','${m}')">${m}</div>`;
  }).join('');
  
  // Set default selected word to the first one in the cluster
  state.synSelectedWord = state.synSelectedWord || {};
  state.synSelectedWord[winId] = displayWords[0] || '';
  synSetReplaceEnabled(winId, false);
}

function synonymDblClick(winId, word) {
  const input = document.getElementById(winId + '-search');
  if (input) {
    input.value = word;
    synTriggerSearch(winId);
  }
}

function synonymSelect(winId, idx, word) {
  document.querySelectorAll(`#${winId}-defn .dict-word`).forEach(el => el.classList.remove('dict-sel'));
  const items = document.querySelectorAll(`#${winId}-defn .dict-word`);
  if (items[idx]) items[idx].classList.add('dict-sel');
  
  state.synSelectedWord = state.synSelectedWord || {};
  state.synSelectedWord[winId] = word;
  synSetReplaceEnabled(winId, false);
}

function synSetReplaceEnabled(winId, enabled) {
  const btn = document.getElementById(winId + '-btn-degistir');
  if (!btn) return;
  btn.classList.add('disabled');
  btn.src = btn.dataset.disabled;
  btn.style.cursor = 'not-allowed';
}

function synTriggerReplace(winId) {
  // Değiştir is disabled
}

// ─── Dictionary Window ───────────────────────────────────────────────────
// ─── Dictionary Window ───────────────────────────────────────────────────
function loadWindowDict(winId, type, apiUrl) {
  const key1 = { trk: 'en', rev: 'tr', syn: 'word', tur: 'word' }[type];
  const key2 = { trk: 'tr', rev: 'en', syn: 'synonyms' }[type];
  
  fetch(apiUrl + `?page=1&per_page=99999`)
    .then(r=>r.json())
    .then(d=>{
      state.windowData = state.windowData || {};
      state.windowData[winId] = d.data;
      state.activeData = state.activeData || {};
      state.activeData[winId] = []; // Start empty
      
      const listEl = document.getElementById(winId + '-list');
      if (listEl) {
        listEl.innerHTML = ''; // Start empty
      }
      const defnEl = document.getElementById(winId + '-defn');
      if (defnEl) {
        defnEl.innerHTML = ''; // Start empty
      }
      const dt = document.getElementById(winId + '-detail');
      if (dt) {
        dt.value = ''; // Start empty
      }
      
      // Synonym window specific initialization
      if (type === 'syn') {
        const stemEl = document.getElementById(winId + '-stem');
        if (stemEl) {
          stemEl.value = '';
        }
        const groupsEl = document.getElementById(winId + '-groups');
        if (groupsEl) {
          groupsEl.innerHTML = '';
        }
        const statusEl = document.getElementById(winId + '-status');
        if (statusEl) {
          statusEl.textContent = `${d.total.toLocaleString()} kayıt`;
        }
      } else {
        const statusEl = document.getElementById(winId + '-status');
        if (statusEl) {
          statusEl.textContent = `${d.total.toLocaleString()} kayıt`;
        }
      }
    });
}

function renderMeanings(winId, meanings) {
  const parts = meanings.replace(/^#/, '').split('|').map(s => s.replace(/^#/, '').trim()).filter(Boolean);
  const df = document.getElementById(winId + '-defn');
  if (!df) return;
  if (!parts.length) {
    df.innerHTML = '<div style="color:#888;padding:8px;">Anlam yok</div>';
    return;
  }
  _meaningWin = _meaningWin || {};
  _meaningWin[winId] = { parts: parts, sel: 0 };
  df.innerHTML = parts.map((m, i) => {
    // Always assign sequential numbers to every item (like Win16 original)
    const numText = (i + 1) + '.';
    const content = m.replace(/^\d+\.\s*/, '').trim();  // strip any existing prefix numbers
    
    return `<div class="dict-meaning${i===0?' meaning-sel':''}" onclick="selectMeaning('${winId}',${i})">
      <span class="row-num">${numText}</span>
      <div class="meaning-content"><div>${content}</div></div>
    </div>`;
  }).join('');
  const dt = document.getElementById(winId + '-detail');
  if (dt) {
    dt.value = parts[0].replace(/^\d+\.\s*/, '').replace(/\n\s*/g, ', ');
  }
}

let _meaningWin = {};
function selectMeaning(winId, idx) {
  const mw = _meaningWin[winId];
  if (!mw || !mw.parts[idx]) return;
  mw.sel = idx;
  document.querySelectorAll(`#${winId}-defn .dict-meaning`).forEach(el => el.classList.remove('meaning-sel'));
  const items = document.querySelectorAll(`#${winId}-defn .dict-meaning`);
  if (items[idx]) items[idx].classList.add('meaning-sel');
  const dt = document.getElementById(winId + '-detail');
  if (dt) {
    dt.value = mw.parts[idx].replace(/^\d+\.\s*/, '').replace(/\n\s*/g, ', ');
  }
}

function dictSelect(winId, key2, idx) {
  const isSyn = key2 === 'synonyms';
  document.querySelectorAll(`#${winId}-list .dict-word`).forEach(el => el.classList.remove('dict-sel'));
  const items = document.querySelectorAll(`#${winId}-list .dict-word`);
  if (items[idx]) items[idx].classList.add('dict-sel');
  
  const wd = (state.activeData && state.activeData[winId]) || (state.windowData && state.windowData[winId]);
  if (wd && wd[idx]) {
    const val = wd[idx][key2] || '';
    if (isSyn) {
      renderSynonyms(winId, val);
    } else {
      renderMeanings(winId, val);
    }
  }
  // Anlam Grupları: show Turkish synonym sub-clusters (grouped by shared English concept)
  // Format: "en_word::tr1,tr2,tr3" — show only Turkish words, use en_word as tooltip
  const grp = document.getElementById(winId + '-groups');
  if (grp && wd && wd[idx]) {
    const groups = wd[idx]['groups'] || '';
    if (groups && isSyn) {
      const parts = groups.split(' | ').filter(Boolean);
      const clusters = parts.map(p => {
        const sep = p.indexOf('::');
        if (sep === -1) return null;
        const enWord = p.substring(0, sep);
        const trWords = p.substring(sep + 2).split(',').filter(Boolean);
        return { en: enWord, tr: trWords };
      }).filter(Boolean);

      if (clusters.length === 0) {
        grp.innerHTML = '<div style="color:#888;padding:8px;">Grup yok</div>';
      } else {
        grp.innerHTML = clusters.map((c, ci) =>
          `<div class="dict-meaning${ci===0?' meaning-sel':''}" title="${c.en}" style="cursor:pointer"
            onclick="synFilterGroup('${winId}', ${ci}, this)">${c.tr.join(' · ')}</div>`
        ).join('');
        // Show first cluster's synonyms by default
        if (clusters.length > 0) {
          synFilterGroup(winId, 0, grp.querySelector('.dict-meaning'));
        }
      }

      // Store clusters on window state for filtering
      state.synClusters = state.synClusters || {};
      state.synClusters[winId] = clusters;
    } else if (grp) {
      grp.innerHTML = '';
    }
  }
}

function normalizeSearch(s) {
  return s.toLowerCase().replace(/ı/g,'i').replace(/ş/g,'s').replace(/ç/g,'c').replace(/ö/g,'o').replace(/ü/g,'u').replace(/ğ/g,'g');
}
function dictSearch(winId) {
  const input = document.getElementById(winId + '-search');
  const q = input ? input.value.trim() : '';
  const win = state.windows[winId];
  if (!win) return;

  const key1 = { trk: 'en', rev: 'tr', syn: 'word', tur: 'word' }[win.type];
  const key2 = { trk: 'tr', rev: 'en', syn: 'synonyms' }[win.type];
  const fullData = state.windowData && state.windowData[winId];
  if (!fullData || !fullData.length) return;

  state.activeData = state.activeData || {};

  if (!q) {
    state.activeData[winId] = [];
    document.getElementById(winId + '-list').innerHTML = '';
    const defnEl = document.getElementById(winId + '-defn');
    if (defnEl) defnEl.innerHTML = '';
    const dt = document.getElementById(winId + '-detail');
    if (dt) dt.value = '';
    return;
  }

  // Win16 davranışı: Türkçe küçük harf normalizasyonu + prefix eşleşmesi
  const turkishLowercase = (s) => s.replace(/İ/g, 'i').replace(/I/g, 'ı').toLowerCase();
  const qnStrict = turkishLowercase(q);

  // 1. Birebir prefix eşleşmesi (Türkçe küçük harf)
  let filtered = fullData.filter(e => turkishLowercase(e[key1] || '').startsWith(qnStrict));

  // 2. Sadece bulunamazsa: ş→s, ç→c, ö→o vb. normalize eşleşmesi
  if (filtered.length === 0) {
    const qnNorm = normalizeSearch(q);
    filtered = fullData.filter(e => normalizeSearch(e[key1] || '').startsWith(qnNorm));
  }

  // Sıralama: tam eşleşme önce, sonra Türkçe alfabetik
  const turkishSortKey = (s) => {
    const w = { 'a':1,'b':2,'c':3,'ç':4,'d':5,'e':6,'f':7,'g':8,'ğ':9,'h':10,
                'ı':11,'i':12,'j':13,'k':14,'l':15,'m':16,'n':17,'o':18,'ö':19,
                'p':20,'r':21,'s':22,'ş':23,'t':24,'u':25,'ü':26,'v':27,'y':28,'z':29 };
    return s.split('').map(c => String.fromCharCode(65 + (w[c] || 0))).join('');
  };

  filtered.sort((a, b) => {
    const va = turkishLowercase(a[key1] || '');
    const vb = turkishLowercase(b[key1] || '');
    if (va === qnStrict && vb !== qnStrict) return -1;
    if (vb === qnStrict && va !== qnStrict) return 1;
    return turkishSortKey(va).localeCompare(turkishSortKey(vb));
  });

  state.activeData[winId] = filtered;

  const listEl = document.getElementById(winId + '-list');
  if (filtered.length === 0) {
    if (listEl) listEl.innerHTML = '<div style="color:#888;padding:8px;">Sonuç bulunamadı</div>';
    const defnEl = document.getElementById(winId + '-defn');
    if (defnEl) defnEl.innerHTML = '';
    const dt = document.getElementById(winId + '-detail');
    if (dt) dt.value = '';
    return;
  }

  const listHtml = filtered.map((e, i) => {
    const label = e[key1] || '';
    return `<div class="dict-word${i===0?' dict-sel':''}" onclick="dictSelect('${winId}','${key2||''}',${i})">${label}</div>`;
  }).join('');

  if (listEl) {
    listEl.innerHTML = listHtml;
    listEl.scrollTop = 0;
  }

  dictSelect(winId, key2, 0);
}

let _searchTimer = {};
function dictSearchDebounced(winId) {
  clearTimeout(_searchTimer[winId]);
  _searchTimer[winId] = setTimeout(() => dictSearch(winId), 150);
}

// ─── Quiz Topics Dialog (EXE listbox: select → Tamam / İptal) ─────────────
let quizTopicState = { topics: [], selected: null, hostId: null, typePrefix: '', lastTopicIdx: null };

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showQuizTopicDialog(hostId) {
  quizTopicState.hostId = hostId;
  const dlg = document.getElementById('quizTopicDialog');
  const list = document.getElementById('quizTopicList');
  list.innerHTML = '<div style="padding:8px;color:#666;">Yükleniyor...</div>';
  dlg.classList.add('open');

  fetch('/api/quiz/topics').then(r=>r.json()).then(d=>{
    const topics = d.topics || [];
    quizTopicState.topics = topics;
    const prevIdx = quizTopicState.lastTopicIdx;
    const hasPrev = prevIdx != null && topics.some(t => t.idx === prevIdx);
    quizTopicState.selected = hasPrev ? prevIdx : (topics.length ? topics[0].idx : null);
    quizTopicState.typePrefix = '';
    list.innerHTML = '';
    topics.forEach((t, i) => {
      const row = document.createElement('div');
      const sel = t.idx === quizTopicState.selected;
      row.className = 'quiz-topic-row' + (sel ? ' selected' : '');
      row.dataset.idx = String(t.idx);
      row.dataset.name = t.name;
      row.textContent = t.name;
      row.onclick = () => selectQuizTopic(t.idx);
      row.ondblclick = () => confirmQuizTopic();
      list.appendChild(row);
    });
    list.focus();
  });
}

function closeQuizTopicDialog() {
  document.getElementById('quizTopicDialog').classList.remove('open');
  quizTopicState.typePrefix = '';
}

function selectQuizTopic(idx) {
  quizTopicState.selected = idx;
  const list = document.getElementById('quizTopicList');
  list.querySelectorAll('.quiz-topic-row').forEach(row => {
    const on = Number(row.dataset.idx) === idx;
    row.classList.toggle('selected', on);
    if (on) row.scrollIntoView({ block: 'nearest' });
  });
}

function confirmQuizTopic() {
  const hostId = quizTopicState.hostId;
  const idx = quizTopicState.selected;
  if (idx == null || !hostId) return;
  quizTopicState.lastTopicIdx = idx;
  const topic = (quizTopicState.topics || []).find(t => t.idx === idx);
  closeQuizTopicDialog();
  startHangmanRound(hostId, idx, topic ? topic.name : '');
}

function showOyunKelimeleriDialog() {
  closeAllMenus();
  SoundFX.playClick();
  document.getElementById('oyunKelimeleriDialog').classList.add('open');
}

function closeOyunKelimeleriDialog() {
  SoundFX.playClick();
  document.getElementById('oyunKelimeleriDialog').classList.remove('open');
}

function confirmOyunKelimeleri() {
  SoundFX.playClick();
  const rad = document.querySelector('input[name="oyunKelimeKaynagi"]:checked');
  state.hangmanSource = rad ? rad.value : 'main';
  closeOyunKelimeleriDialog();
}

function quizTopicKeydown(ev) {
  const topics = quizTopicState.topics || [];
  if (!topics.length) return;
  let i = topics.findIndex(t => t.idx === quizTopicState.selected);
  if (i < 0) i = 0;

  if (ev.key === 'ArrowDown') {
    ev.preventDefault();
    selectQuizTopic(topics[Math.min(i + 1, topics.length - 1)].idx);
  } else if (ev.key === 'ArrowUp') {
    ev.preventDefault();
    selectQuizTopic(topics[Math.max(i - 1, 0)].idx);
  } else if (ev.key === 'Home') {
    ev.preventDefault();
    selectQuizTopic(topics[0].idx);
  } else if (ev.key === 'End') {
    ev.preventDefault();
    selectQuizTopic(topics[topics.length - 1].idx);
  } else if (ev.key === 'PageDown') {
    ev.preventDefault();
    selectQuizTopic(topics[Math.min(i + 10, topics.length - 1)].idx);
  } else if (ev.key === 'PageUp') {
    ev.preventDefault();
    selectQuizTopic(topics[Math.max(i - 10, 0)].idx);
  } else if (ev.key === 'Enter') {
    ev.preventDefault();
    confirmQuizTopic();
  } else if (ev.key === 'Escape') {
    ev.preventDefault();
    closeQuizTopicDialog();
  } else if (ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
    // Win16 listbox type-ahead
    ev.preventDefault();
    const now = Date.now();
    if (!quizTopicState._typeAt || now - quizTopicState._typeAt > 900) {
      quizTopicState.typePrefix = '';
    }
    quizTopicState._typeAt = now;
    quizTopicState.typePrefix += ev.key;
    const qn = normalizeSearch(quizTopicState.typePrefix);
    const hit = topics.find(t => normalizeSearch(t.name).startsWith(qn));
    if (hit) selectQuizTopic(hit.idx);
  }
}

// ─── Retro Sound Effects (Web Audio API) ──────────────────────────────────
const SoundFX = (function() {
  let ctx = null;
  function getContext() {
    if (!ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) ctx = new AudioCtx();
    }
    if (ctx && ctx.state === 'suspended') {
      ctx.resume();
    }
    return ctx;
  }

  function playTone(freq, type, duration, gainVal, delay) {
    try {
      const ac = getContext();
      if (!ac) return;
      delay = delay || 0;
      const now = ac.currentTime + delay;
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.type = type || 'sine';
      osc.frequency.setValueAtTime(freq, now);
      gain.gain.setValueAtTime(gainVal || 0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.start(now);
      osc.stop(now + duration + 0.05);
    } catch(e) {}
  }

  return {
    playClick: function() {
      playTone(900, 'triangle', 0.03, 0.08);
    },
    playCorrect: function() {
      // Pleasant double bell chime (E5 -> G5)
      playTone(659.25, 'sine', 0.09, 0.16, 0);
      playTone(783.99, 'sine', 0.18, 0.20, 0.07);
    },
    playWrong: function() {
      // Retro low error buzz (sawtooth 160Hz -> 90Hz)
      try {
        const ac = getContext();
        if (!ac) return;
        const now = ac.currentTime;
        const osc = ac.createOscillator();
        const gain = ac.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(160, now);
        osc.frequency.linearRampToValueAtTime(80, now + 0.15);
        gain.gain.setValueAtTime(0.16, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.16);
        osc.connect(gain);
        gain.connect(ac.destination);
        osc.start(now);
        osc.stop(now + 0.17);
      } catch(e) {}
    },
    playHint: function() {
      // Magic mystery shimmer
      playTone(523.25, 'sine', 0.08, 0.14, 0);
      playTone(659.25, 'sine', 0.08, 0.14, 0.06);
      playTone(880.00, 'sine', 0.18, 0.18, 0.12);
    },
    playWin: function() {
      // Classic Win3.1 victory fanfare (C5 -> E5 -> G5 -> C6)
      playTone(523.25, 'triangle', 0.12, 0.20, 0);
      playTone(659.25, 'triangle', 0.12, 0.20, 0.10);
      playTone(783.99, 'triangle', 0.14, 0.24, 0.20);
      playTone(1046.50, 'triangle', 0.35, 0.28, 0.32);
    },
    playLose: function() {
      // Classic game over descending sad tones (G4 -> F4 -> D#4 -> C4)
      playTone(392.00, 'sawtooth', 0.14, 0.16, 0);
      playTone(349.23, 'sawtooth', 0.14, 0.16, 0.12);
      playTone(311.13, 'sawtooth', 0.16, 0.18, 0.24);
      playTone(261.63, 'sawtooth', 0.35, 0.20, 0.38);
    },
    playStart: function() {
      // New round start chime
      playTone(440, 'triangle', 0.08, 0.14, 0);
      playTone(880, 'triangle', 0.14, 0.18, 0.08);
    }
  };
})();

// ─── Hangman (Kelime Oyunu) ─────────────────────────────────────────────
// Original EXE: left col A…L, right col M…Z then ?
const HM_LETTERS = 'ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ?';
const HM_KEYS = [
  ['A', 'M'], ['B', 'N'], ['C', 'O'], ['Ç', 'Ö'], ['D', 'P'],
  ['E', 'R'], ['F', 'S'], ['G', 'Ş'], ['Ğ', 'T'], ['H', 'U'],
  ['I', 'Ü'], ['İ', 'V'], ['J', 'Y'], ['K', 'Z'], ['L', '?'],
];
const HM_START_SCORE = 10000;

function hmKeyIndex(letter) {
  return HM_LETTERS.indexOf(letter);
}

function openHangman() {
  closeAllWindows();
  closeQuizTopicDialog();
  const id = 'win-hm-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');

  let html = `<div class="win-window" id="${id}" style="width:360px;height:auto;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Kelime Oyunu</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:0;display:block;background:#c0c0c0;">`;
  html += `<div class="hm-main" id="${id}-game"></div>`;
  html += `</div></div>`;

  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = {
    type: 'hangman', id: id, topicIdx: null, topicName: '',
    hangman: {
      word: '', hint: '', topicIdx: null,
      guessed: [], wrong: 0, maxWrong: 9, done: false, id: id,
      score: HM_START_SCORE, started: false
    }
  };
  state.activeHangmanId = id;
  renderHangman(id);
}

function hangmanBasla(id) {
  SoundFX.playClick();
  startHangmanRound(id);
}

function hangmanSozluk(id) {
  showOyunKelimeleriDialog();
}

function toTrUpper(s) {
  return String(s || '')
    .replace(/i/g, 'İ')
    .replace(/ı/g, 'I')
    .toLocaleUpperCase('tr-TR');
}

function hangmanKeyFromEvent(ev) {
  if (ev.key === '?' || (ev.key === '/' && ev.shiftKey)) return '?';
  if (ev.key.length !== 1 || ev.ctrlKey || ev.metaKey || ev.altKey) return null;
  // Preserve dotted / dotless I distinction from the physical key
  if (ev.key === 'i') return 'İ';
  if (ev.key === 'ı') return 'I';
  if (ev.key === 'I') return 'I';
  if (ev.key === 'İ') return 'İ';
  const up = toTrUpper(ev.key);
  return HM_LETTERS.includes(up) ? up : null;
}

function activeHangmanId() {
  if (state.activeHangmanId && state.windows[state.activeHangmanId]) {
    return state.activeHangmanId;
  }
  for (const id of Object.keys(state.windows)) {
    if (state.windows[id].type === 'hangman') return id;
  }
  return null;
}

document.addEventListener('keydown', function(ev) {
  if (document.getElementById('quizTopicDialog')?.classList.contains('open')) return;
  if (document.querySelector('.dialog-overlay.open')) return;
  const tag = (ev.target && ev.target.tagName) || '';
  if (tag === 'INPUT' || tag === 'TEXTAREA' || ev.target?.isContentEditable) return;

  const id = activeHangmanId();
  if (!id) return;
  const info = state.windows[id].hangman;
  if (!info) return;

  if (!info.started || !info.word) {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      hangmanBasla(id);
    }
    return;
  }
  if (info.done) {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      hangmanBasla(id);
    }
    return;
  }
  const letter = hangmanKeyFromEvent(ev);
  if (!letter) return;
  ev.preventDefault();
  guessLetter(id, letter);
});

function startHangmanRound(id, topicIdx, topicName) {
  const win = state.windows[id];
  if (!win) return;
  win.topicIdx = topicIdx;
  win.topicName = topicName || '';

  const src = state.hangmanSource || 'main';
  let url = '/api/hangman/word?source=' + encodeURIComponent(src);
  if (topicIdx != null && topicIdx !== '') {
    url += '&topic=' + encodeURIComponent(topicIdx);
  }
  fetch(url)
    .then(r => r.json()).then(d => {
      if (!state.windows[id]) return;
      if (d.error) {
        document.getElementById(id + '-game').innerHTML =
          '<p style="color:#800;padding:8px;">' + escHtml(d.error) + '</p>';
        // keep board playable — reopen empty state
        if (win.hangman) {
          win.hangman.started = false;
          win.hangman.word = '';
          renderHangman(id);
        }
        return;
      }
      const word = toTrUpper(d.word || '');
      initHangmanGame(id, word, d.hint || d.en || '', topicIdx);
      SoundFX.playStart();
    });
}

function initHangmanGame(id, word, hint, topicIdx) {
  const wordUpper = toTrUpper(word);
  const prev = (state.windows[id] && state.windows[id].hangman) || {};
  const info = {
    word: wordUpper, hint: hint, topicIdx: topicIdx,
    guessed: [], wrong: 0, maxWrong: 9, done: false, id: id,
    score: (typeof prev.score === 'number' ? prev.score : HM_START_SCORE),
    started: true
  };
  state.windows[id].hangman = info;
  state.activeHangmanId = id;
  renderHangman(id);
}

function renderHangman(id) {
  const info = state.windows[id] && state.windows[id].hangman;
  if (!info) return;
  const started = !!info.started && !!info.word;
  const won = started && !info.word.split('').some(c => !info.guessed.includes(c));
  const lost = started && info.wrong >= info.maxWrong;
  if (won || lost) info.done = true;

  const displayWord = started
    ? (info.done
        ? info.word.split('').join(' ')
        : info.word.split('').map(c => info.guessed.includes(c) ? c : '_').join(' '))
    : '';

  const stage = started ? Math.min(info.wrong, 9) : 0;

  let html = `<div class="hm-main">`;

  // Upper: letter keys | banner + gallows/puan/acer
  html += `<div class="hm-upper">`;

  html += `<div class="hm-left">`;
  for (let r = 0; r < HM_KEYS.length; r++) {
    html += `<div class="hm-keyrow">`;
    for (let c = 0; c < 2; c++) {
      const letter = HM_KEYS[r][c];
      const idx = hmKeyIndex(letter);
      // Disabled if round not started yet, or game round is over, or letter was already guessed
      const disabled = !started || info.done || info.guessed.includes(letter);
      const prefix = disabled ? 'p' : 'n';
      const cls = disabled ? ' used' : '';
      const onClick = disabled ? '' : `guessLetter('${id}','${letter}')`;

      html += `<img class="hm-key${cls}" width="25" height="25" src="/assets/keys/${prefix}_${String(idx).padStart(2,'0')}.png?v=14" ` +
        `alt="${letter}" title="${letter}" onclick="${onClick}">`;
    }
    html += `</div>`;
  }
  html += `</div>`;

  html += `<div class="hm-right">`;
  html += `<div class="hm-brand">`;
  html += `<img class="hm-brand-svg" src="/assets/MoonStar.svg?v=3" alt="MoonStar">`;
  html += `<div class="hm-brand-sub">“Özgün programlar yaratır”</div>`;
  html += `</div>`;
  html += `<div class="hm-status">`;
  html += `<div class="hm-status-row">`;
  html += `<div class="hm-gallows"><img width="52" height="76" src="/assets/hm_${stage}.png" alt=""></div>`;
  html += `<div class="hm-scorecol">`;
  html += `<div class="hm-scorelabel">Puan</div>`;
  html += `<div class="hm-scorebox" id="${id}-score">${info.score}</div>`;
  html += `</div></div>`;
  html += `<div class="hm-ad"><img width="98" height="98" src="/assets/logo_acer.png?v=1" alt="Acer"></div>`;
  html += `</div>`;
  
  html += `<div class="hm-wordbox">${displayWord}</div>`;
  
  const isPlaying = started && !info.done;
  const sozlukCls = isPlaying ? 'hm-btn disabled' : 'hm-btn';
  const sozlukClick = isPlaying ? '' : `onclick="hangmanSozluk('${id}')"`;
  const baslaCls = isPlaying ? 'hm-btn disabled' : 'hm-btn';
  const baslaClick = isPlaying ? '' : `onclick="hangmanBasla('${id}')"`;

  html += `<div class="hm-btns">`;
  html += `<img class="${sozlukCls}" width="63" height="39" src="/assets/btn_sozluk.png" alt="Sözlük" title="Sözlük" ${sozlukClick}>`;
  html += `<img class="${baslaCls}" width="63" height="39" src="/assets/btn_basla.png" alt="Başla" title="Başla" ${baslaClick}>`;
  html += `<img class="hm-btn" width="63" height="39" src="/assets/btn_iptal.png" alt="İptal" title="İptal" onclick="SoundFX.playClick();closeWindow('${id}')">`;
  html += `</div>`;
  
  html += `</div>`; // hm-right
  html += `</div>`; // hm-upper
  html += `</div>`; // hm-main

  document.getElementById(id+'-game').innerHTML = html;
}

function guessLetter(id, letter) {
  const info = state.windows[id] && state.windows[id].hangman;
  if (!info || !info.started || !info.word || info.done || info.guessed.includes(letter)) return;
  if (letter === '?') {
    // Hint: reveal one unrevealed letter (costs a wrong step and halves score)
    let revealed = false;
    for (const c of info.word) {
      if (!info.guessed.includes(c)) {
        info.guessed.push(c);
        revealed = true;
        break;
      }
    }
    if (revealed) {
      info.wrong = Math.min(info.wrong + 1, info.maxWrong);
      info.score = Math.floor(info.score / 2);
      SoundFX.playHint();
    }
  } else {
    info.guessed.push(letter);
    if (!info.word.includes(letter)) {
      info.wrong++;
      info.score = Math.floor(info.score / 2);
      SoundFX.playWrong();
    } else {
      SoundFX.playCorrect();
    }
  }
  const won = !info.word.split('').some(c => !info.guessed.includes(c));
  const lost = info.wrong >= info.maxWrong;
  if (won || lost) {
    info.done = true;
    if (lost) {
      info.score = 0;
      setTimeout(() => SoundFX.playLose(), 160);
    } else if (won) {
      setTimeout(() => SoundFX.playWin(), 160);
    }
  }
  renderHangman(id);
}

function openRawWindow(id, title, w, h, bodyHtml) {
  const workArea = document.getElementById('workArea');
  let html = `<div class="win-window" id="${id}" style="width:${w}px;height:${h}px;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">${title}</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:4px;flex:1;display:flex;flex-direction:column;min-height:0;overflow:auto;">`;
  html += bodyHtml;
  html += `</div></div>`;
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'raw', id: id };
}

// ─── Welcome Screen ───────────────────────────────────────────────────────
function welcomeBtnPress(img, pressed) {
  if (!img) return;
  img.src = pressed ? img.dataset.p : img.dataset.n;
}

function showWelcomeWindow() {
  closeAllWindows();
  const id = 'win-welcome';
  const workArea = document.getElementById('workArea');
  state.windows[id] = { type: 'welcome', id: id };

  // EXE module order (3×2): Denetim | TR→EN | Eş Anlam / Klavye | EN→TR | Adam Asma
  // Cache-bust so browsers don't keep old pressed bitmaps for btn_*.png
  const v = '3';
  const modules = [
    { label: 'Türkçe Denetim', base: 'btn_denetim', action: 'openTextEditor()' },
    { label: 'Türkçe / İngilizce', base: 'btn_tr_en', action: "openWindow('tr-ing')" },
    { label: 'Türkçe Eş Anlamlılar', base: 'btn_esanlam', action: "openWindow('synonyms')" },
    { label: 'Klavye', base: 'btn_klavye', action: 'showKeyboardModule()' },
    { label: 'İngilizce / Türkçe', base: 'btn_en_tr', action: "openWindow('ing-tr')" },
    { label: 'Adam Asma', base: 'btn_adam_asma', action: "openWindow('quiz')" },
  ];

  let html = `<div class="win-window" id="${id}" style="width:372px;height:auto;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar Türkçe Dil Kılavuzu</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body welcome-body" style="padding:6px;">`;
  html += `<div class="welcome-panel">`;
  html += `<div class="welcome-grid">`;
  modules.forEach(m => {
    const n = `/assets/${m.base}.png?v=${v}`;
    const p = `/assets/${m.base}_p.png?v=${v}`;
    html += `<button type="button" class="welcome-btn" title="${m.label}" onclick="${m.action}"` +
      ` onpointerdown="welcomeBtnPress(this.querySelector('img'),true)"` +
      ` onpointerup="welcomeBtnPress(this.querySelector('img'),false)"` +
      ` onpointerleave="welcomeBtnPress(this.querySelector('img'),false)"` +
      ` onpointercancel="welcomeBtnPress(this.querySelector('img'),false)"` +
      ` onblur="welcomeBtnPress(this.querySelector('img'),false)">` +
      `<img src="${n}" width="104" height="50" data-n="${n}" data-p="${p}" alt="${m.label}" draggable="false">` +
      `</button>`;
  });
  html += `</div>`;
  html += `<div class="welcome-sep"></div>`;
  html += `<div class="welcome-banner" onclick="showAbout()" style="cursor:pointer;">` +
    `<img src="/assets/logo_acer.png?v=${v}" class="welcome-banner-logo" width="98" height="98" alt="Acer">` +
    `<div class="welcome-banner-brand">` +
      `<img src="/assets/MoonStar.svg?v=${v}" class="welcome-banner-svg" alt="MoonStar">` +
      `<div class="welcome-banner-sub">“Özgün programlar yaratır”</div>` +
    `</div>` +
  `</div>`;
  html += `</div></div></div>`;
  workArea.insertAdjacentHTML('afterbegin', html);
}

function showKeyboardModule() {
  closeAllWindows();
  const id = 'win-kbd-select';
  if (document.getElementById(id)) return;
  
  openRawWindow(id, 'Klavye Seçimi', 330, 320, `
    <div class="win-body" style="padding:10px;flex:1;display:flex;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:12px;box-sizing:border-box;height:100%;">
      <!-- Left Column -->
      <div style="flex:1;display:flex;flex-direction:column;gap:8px;min-height:0;height:100%;">
        <!-- 1.Klavye Group Box -->
        <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin:0;"><legend>1.Klavye</legend>
          <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-kbd1">
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 1, 'F', this)">Türkçe F-Klavye</div>
            <div class="dict-word dict-sel" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 1, 'Q', this)">Türkçe Q-Klavye</div>
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 1, 'EN', this)">İngilizce Q-Klavye</div>
          </div>
        </div>
        
        <!-- 2.Klavye Group Box -->
        <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin:0;"><legend>2.Klavye</legend>
          <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-kbd2">
            <div class="dict-word dict-sel" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 2, 'F', this)">Türkçe F-Klavye</div>
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 2, 'Q', this)">Türkçe Q-Klavye</div>
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 2, 'EN', this)">İngilizce Q-Klavye</div>
          </div>
        </div>
        
        <!-- Dikkat Group Box -->
        <div class="group-box" style="flex-shrink:0;padding:6px;margin:0;text-align:center;font-size:11px;line-height:1.4;font-weight:bold;"><legend>Dikkat</legend>
          <div>Klavyeler arasında geçiş</div>
          <div>CTRL+F1 tuşu ile yapılır</div>
        </div>
      </div>
      
      <!-- Right Column -->
      <div style="width:75px;display:flex;flex-direction:column;gap:12px;flex-shrink:0;justify-content:flex-start;align-items:center;padding-top:8px;">
        <!-- Edit Button using original asset -->
        <img class="quiz-topic-btn" id="${id}-btn-edit" width="63" height="39" 
             src="/assets/extracted/img_02c600_63x39_4bpp.png" 
             data-normal="/assets/extracted/img_02c600_63x39_4bpp.png" 
             data-pressed="/assets/extracted/img_03bc00_63x39_4bpp.png"
             onmousedown="this.src=this.dataset.pressed" 
             onmouseup="this.src=this.dataset.normal" 
             onmouseleave="this.src=this.dataset.normal"
             onclick="showVirtualKeyboard('${id}')"
             style="cursor:pointer; image-rendering:pixelated; flex-shrink:0;"
             alt="Edit" title="Edit">
             
        <!-- Tamam Button using original asset -->
        <img class="quiz-topic-btn" id="${id}-btn-tamam" width="63" height="39" 
             src="/assets/extracted/img_02ae00_63x39_4bpp.png" 
             data-normal="/assets/extracted/img_02ae00_63x39_4bpp.png" 
             data-pressed="/assets/extracted/img_039800_63x39_4bpp.png"
             onmousedown="this.src=this.dataset.pressed" 
             onmouseup="this.src=this.dataset.normal" 
             onmouseleave="this.src=this.dataset.normal"
             onclick="closeWindow('${id}')"
             style="cursor:pointer; image-rendering:pixelated; flex-shrink:0;"
             alt="Tamam" title="Tamam">
             
        <!-- İptal Button using original asset -->
        <img class="quiz-topic-btn" id="${id}-btn-iptal" width="63" height="39" 
             src="/assets/extracted/img_02ba00_63x39_4bpp.png" 
             data-normal="/assets/extracted/img_02ba00_63x39_4bpp.png" 
             data-pressed="/assets/extracted/img_03a400_63x39_4bpp.png"
             onmousedown="this.src=this.dataset.pressed" 
             onmouseup="this.src=this.dataset.normal" 
             onmouseleave="this.src=this.dataset.normal"
             onclick="closeWindow('${id}')"
             style="cursor:pointer; image-rendering:pixelated; flex-shrink:0;"
             alt="İptal" title="İptal">
      </div>
    </div>
  `);
}

function selectKbdLayout(winId, kbdNum, layoutCode, el) {
  const container = document.getElementById(winId + '-kbd' + kbdNum);
  if (!container) return;
  container.querySelectorAll('.dict-word').forEach(e => e.classList.remove('dict-sel'));
  el.classList.add('dict-sel');
  console.log(`Keyboard ${kbdNum} set to ${layoutCode}`);
  
  if (kbdNum === 1) {
    const kbdWin = document.getElementById('win-kbd');
    if (kbdWin) {
      const titleText = kbdWin.querySelector('.win-title-text');
      if (titleText) {
        titleText.textContent = el.textContent.trim();
      }
    }
  }
}

// ─── Virtual Keyboard Mappings & Editor ──────────────────────────────────────
let virtualKeyboardState = {
  keys: [
    // Row 1 (13 keys)
    { normal: '"', shift: 'é', alt: '<' },
    { normal: '1', shift: '!', alt: '>' },
    { normal: '2', shift: "'", alt: '£' },
    { normal: '3', shift: '^', alt: '#' },
    { normal: '4', shift: '+', alt: '$' },
    { normal: '5', shift: '%', alt: '½' },
    { normal: '6', shift: '&', alt: '¾' },
    { normal: '7', shift: '/', alt: '{' },
    { normal: '8', shift: '(', alt: '[' },
    { normal: '9', shift: ')', alt: ']' },
    { normal: '0', shift: '=', alt: '}' },
    { normal: '*', shift: '?', alt: '\\' },
    { normal: '-', shift: '_', alt: '|' },
    // Row 2 (12 keys)
    { normal: 'q', shift: 'Q', alt: '@' },
    { normal: 'w', shift: 'W', alt: 'w' },
    { normal: 'e', shift: 'E', alt: '€' },
    { normal: 'r', shift: 'R', alt: 'r' },
    { normal: 't', shift: 'T', alt: 't' },
    { normal: 'y', shift: 'Y', alt: 'y' },
    { normal: 'u', shift: 'U', alt: 'u' },
    { normal: 'ı', shift: 'I', alt: 'ı' },
    { normal: 'o', shift: 'O', alt: 'o' },
    { normal: 'p', shift: 'P', alt: 'p' },
    { normal: 'ğ', shift: 'Ğ', alt: '¨' },
    { normal: 'ü', shift: 'Ü', alt: '~' },
    // Row 3 (12 keys)
    { normal: 'a', shift: 'A', alt: 'æ' },
    { normal: 's', shift: 'S', alt: 'ß' },
    { normal: 'd', shift: 'D', alt: 'd' },
    { normal: 'f', shift: 'F', alt: 'f' },
    { normal: 'g', shift: 'G', alt: 'g' },
    { normal: 'h', shift: 'H', alt: 'h' },
    { normal: 'j', shift: 'J', alt: 'j' },
    { normal: 'k', shift: 'K', alt: 'k' },
    { normal: 'l', shift: 'L', alt: 'l' },
    { normal: 'ş', shift: 'Ş', alt: '´' },
    { normal: 'i', shift: 'İ', alt: '`' },
    { normal: ',', shift: ';', alt: '`' },
    // Row 4 (11 keys)
    { normal: '<', shift: '>', alt: '|' },
    { normal: 'z', shift: 'Z', alt: 'z' },
    { normal: 'x', shift: 'X', alt: 'x' },
    { normal: 'c', shift: 'C', alt: '¢' },
    { normal: 'v', shift: 'V', alt: 'v' },
    { normal: 'b', shift: 'B', alt: 'b' },
    { normal: 'n', shift: 'N', alt: 'n' },
    { normal: 'm', shift: 'M', alt: 'm' },
    { normal: 'ö', shift: 'Ö', alt: 'ö' },
    { normal: 'ç', shift: 'Ç', alt: 'ç' },
    { normal: '.', shift: ':', alt: '.' }
  ],
  selectedKeyIdx: 1, // key '2' selected by default like screenshot
  layers: { caps: true, shift: false, alt: false } // CapsLock selected like screenshot
};

function getKbdKeyChar(key, layers) {
  if (layers.alt) return key.alt;
  if (layers.shift) return key.shift;
  if (layers.caps) {
    return key.normal.toUpperCase();
  }
  return key.normal;
}

function showVirtualKeyboard(parentId) {
  const id = 'win-kbd';
  if (document.getElementById(id)) {
    const win = document.getElementById(id);
    win.parentNode.appendChild(win);
    return;
  }
  
  let titleName = "Türkçe Q-Klavye";
  const selEl = document.querySelector('#win-kbd-select-kbd1 .dict-sel');
  if (selEl) {
    titleName = selEl.textContent.trim();
  }
  openRawWindow(id, titleName, 415, 230, `
    <div class="win-body" style="padding:10px;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:8px;box-sizing:border-box;height:100%;">
      
      <!-- Keyboard Keys Grid in Recessed Border Frame -->
      <div style="border:2px solid;border-color:#808080 #fff #fff #808080;padding:8px 6px;background:#c0c0c0;flex-shrink:0;box-sizing:border-box;">
        <div id="${id}-kbd-grid" style="display:flex;flex-direction:column;gap:3px;flex-shrink:0;"></div>
      </div>
      
      <!-- Bottom Actions Row -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;flex-shrink:0;user-select:none;padding:0 2px;">
        <!-- Checkboxes -->
        <div style="display:flex;gap:12px;font-weight:bold;font-size:12px;">
          <label style="display:flex;align-items:center;gap:3px;cursor:pointer;">
            <input type="checkbox" id="${id}-caps" ${virtualKeyboardState.layers.caps?'checked':''} onchange="drawVirtualKeyboardKeys('${id}')"> CapsLock
          </label>
          <label style="display:flex;align-items:center;gap:3px;cursor:pointer;">
            <input type="checkbox" id="${id}-shift" ${virtualKeyboardState.layers.shift?'checked':''} onchange="drawVirtualKeyboardKeys('${id}')"> Shift
          </label>
          <label style="display:flex;align-items:center;gap:3px;cursor:pointer;">
            <input type="checkbox" id="${id}-alt" ${virtualKeyboardState.layers.alt?'checked':''} onchange="drawVirtualKeyboardKeys('${id}')"> Alt
          </label>
        </div>
        
        <!-- Buttons -->
        <div style="display:flex;gap:10px;align-items:center;">
          <!-- Tamam Button using standard thumbs-up asset -->
          <img class="quiz-topic-btn" id="${id}-btn-tamam" width="63" height="39" 
               src="/assets/extracted/img_02ae00_63x39_4bpp.png" 
               data-normal="/assets/extracted/img_02ae00_63x39_4bpp.png" 
               data-pressed="/assets/extracted/img_039800_63x39_4bpp.png"
               onmousedown="this.src=this.dataset.pressed" 
               onmouseup="this.src=this.dataset.normal" 
               onmouseleave="this.src=this.dataset.normal"
               onclick="closeWindow('${id}')"
               style="cursor:pointer; image-rendering:pixelated; flex-shrink:0;"
               alt="Tamam" title="Tamam">
        </div>
      </div>
    </div>
  `);
  
  drawVirtualKeyboardKeys(id);
}

function drawVirtualKeyboardKeys(winId) {
  const container = document.getElementById(winId + '-kbd-grid');
  if (!container) return;
  
  const caps = document.getElementById(winId + '-caps').checked;
  const shift = document.getElementById(winId + '-shift').checked;
  const alt = document.getElementById(winId + '-alt').checked;
  
  const state = virtualKeyboardState;
  state.layers = { caps, shift, alt };
  
  let html = '';
  const rows = [
    { start: 0, end: 13, indent: 0 },
    { start: 13, end: 25, indent: 15 },
    { start: 25, end: 37, indent: 22 },
    { start: 37, end: 48, indent: 10 }
  ];
  
  rows.forEach((row) => {
    html += `<div style="display:flex;gap:3px;margin-left:${row.indent}px;margin-bottom:3px;">`;
    for (let i = row.start; i < row.end; i++) {
      const key = state.keys[i];
      const ch = getKbdKeyChar(key, state.layers);
      const isSelected = state.selectedKeyIdx === i;
      const keyStyle = isSelected 
        ? 'border-color: #404040 #fff #fff #404040; background: #555555; color: #fff; box-shadow: inset 1px 1px 2px rgba(0,0,0,0.5);' 
        : 'border-color: #fff #404040 #404040 #fff; background: #7c7c7c; color: #fff;';
      
      html += `<div class="kbd-key-3d" onclick="selectVirtualKeyboardKey('${winId}', ${i})" ` +
        `style="width:25px;height:25px;border:2px solid;${keyStyle}display:flex;justify-content:center;align-items:center;font-size:12px;font-weight:bold;cursor:pointer;user-select:none;font-family:'Courier New',monospace;box-sizing:border-box;image-rendering:pixelated;">` +
        `${ch}` +
        `</div>`;
    }
    html += `</div>`;
  });
  
  container.innerHTML = html;
}

function selectVirtualKeyboardKey(winId, i) {
  virtualKeyboardState.selectedKeyIdx = i;
  drawVirtualKeyboardKeys(winId);
}

// ─── Character List Dialog Logic ─────────────────────────────────────────────
let charListState = {
  kbdWinId: null,
  selectedCode: 75 // 'K' default selected
};

// Turkish CP1254/Windows-1254 character set array for codes 0-255
const cp1254Chars = (function() {
  const arr = [];
  for (let i = 0; i < 256; i++) {
    if (i < 32) {
      arr.push('');
    } else if (i >= 128 && i <= 159) {
      const map = {
        130: '‚', 131: 'ƒ', 132: '„', 133: '…', 134: '†', 135: '‡',
        136: 'ˆ', 137: '‰', 138: 'Š', 139: '‹', 140: 'Œ',
        145: '‘', 146: '’', 147: '“', 148: '”', 149: '•', 150: '–', 151: '—',
        152: '˜', 153: '™', 154: 'š', 155: '›', 156: 'œ', 159: 'Ÿ'
      };
      arr.push(map[i] || '');
    } else {
      const mapTurkish = {
        208: 'Ğ', 221: 'İ', 222: 'Ş',
        240: 'ğ', 253: 'ı', 254: 'ş'
      };
      arr.push(mapTurkish[i] || String.fromCharCode(i));
    }
  }
  return arr;
})();

function openCharacterList(kbdWinId) {
  charListState.kbdWinId = kbdWinId;
  
  const holder = document.getElementById('char-grid-holder');
  if (!holder) return;
  
  let html = '';
  for (let i = 32; i < 256; i++) {
    const ch = cp1254Chars[i];
    const isSelected = charListState.selectedCode === i;
    const cellStyle = isSelected
      ? 'background: #000080; color: #fff;'
      : 'background: #fff; color: #000;';
    
    html += `<div class="char-cell" onclick="selectCharacterCell(${i}, this)" ondblclick="confirmCharacterSelection()" ` +
      `style="width:24px;height:24px;border:1px solid #808080;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:bold;cursor:pointer;box-sizing:border-box;user-select:none;font-family:'Courier New',monospace;${cellStyle}">` +
      `${ch}` +
      `</div>`;
  }
  holder.innerHTML = html;
  
  selectCharacterCell(charListState.selectedCode, null);
  document.getElementById('charListDialog').classList.add('open');
}

function selectCharacterCell(code, el) {
  charListState.selectedCode = code;
  
  const holder = document.getElementById('char-grid-holder');
  if (holder) {
    holder.querySelectorAll('.char-cell').forEach(c => {
      c.style.background = '#fff';
      c.style.color = '#000';
    });
  }
  
  if (el) {
    el.style.background = '#000080';
    el.style.color = '#fff';
  } else if (holder) {
    const idx = code - 32;
    const targetCell = holder.children[idx];
    if (targetCell) {
      targetCell.style.background = '#000080';
      targetCell.style.color = '#fff';
    }
  }
  
  document.getElementById('char-ascii-val').textContent = code;
  document.getElementById('char-hex-val').textContent = code.toString(16).toUpperCase().padStart(2, '0');
}

function confirmCharacterSelection() {
  const code = charListState.selectedCode;
  const ch = cp1254Chars[code];
  const winId = charListState.kbdWinId;
  
  const state = virtualKeyboardState;
  const idx = state.selectedKeyIdx;
  if (idx !== null && idx >= 0 && idx < state.keys.length) {
    const key = state.keys[idx];
    if (state.layers.alt) {
      key.alt = ch;
    } else if (state.layers.shift) {
      key.shift = ch;
    } else {
      key.normal = ch;
    }
    console.log(`Updated key ${idx} to ${ch}`);
    drawVirtualKeyboardKeys(winId);
  }
  
  closeCharacterList();
}

function closeCharacterList() {
  document.getElementById('charListDialog').classList.remove('remove');
  document.getElementById('charListDialog').classList.remove('open');
}

// ─── Stats Window ────────────────────────────────────────────────────────
function loadWindowStats(winId) {
  fetch('/api/stats').then(r=>r.json()).then(d=>{
    let html = '<div style="padding:4px;">';
    html += '<table style="margin-bottom:8px;"><tr><th>Veri</th><th>Kayıt Sayısı</th></tr>';
    const items = [
      ['İngilizce → Türkçe Sözlük', d.trk.total],
      ['Türkçe Leb Demeden', d.tur.total],
      ['Türkçe → İngilizce', d.rev.total],
      ['Eş Anlamlı Sözcükler', d.syn.total],
      ['Adam Asma', d.quiz.total],
    ];
    items.forEach(i => {
      html += `<tr><td>${i[0]}</td><td><b>${i[1].toLocaleString()}</b></td></tr>`;
    });
    html += '</table>';
    
    html += '<div class="group-box" style="margin-top:8px;"><legend>Konulara Göre Dağılım</legend>';
    html += '<table><tr><th>Konu</th><th>Kelime</th></tr>';
    d.topics.forEach(t => {
      html += `<tr><td>${t.name}</td><td>${t.count}</td></tr>`;
    });
    html += '</table></div></div>';
    document.getElementById(winId+'-body').innerHTML = html;
  });
}

// ─── Find Dialog ──────────────────────────────────────────────────────────
function showFindDialog() {
  closeAllMenus();
  document.getElementById('findDialog').classList.add('open');
  document.getElementById('findInput').value = '';
  document.getElementById('findResults').innerHTML = '';
  setTimeout(() => document.getElementById('findInput').focus(), 100);
}

function showReplaceDialog() {
  showFindDialog();
}

function doFind() {
  const q = document.getElementById('findInput').value;
  if (!q) { document.getElementById('findResults').innerHTML = '<div style="color:#800;">Kelime giriniz.</div>'; return; }
  
  const radios = document.getElementsByName('findType');
  let type = 'all';
  for (let r of radios) { if (r.checked) type = r.value || 'all'; }
  
  document.getElementById('findResults').innerHTML = '<div class="loading">Aranıyor...</div>';
  
  const promises = [];
  const labels = [];
  
  if (type === 'all' || type === 'trk') {
    promises.push(fetch('/api/trk/search?q='+encodeURIComponent(q)).then(r=>r.json()));
    labels.push('İngilizce → Türkçe');
  }
  if (type === 'all' || type === 'tur') {
    promises.push(fetch('/api/tur/search?q='+encodeURIComponent(q)).then(r=>r.json()));
    labels.push('Türkçe Leb Demeden');
  }
  if (type === 'all' || type === 'quiz') {
    promises.push(fetch('/api/quiz/search?q='+encodeURIComponent(q)).then(r=>r.json()));
      labels.push('Adam Asma');
    }
    
    if (type !== 'all' && type !== 'trk' && type !== 'tur' && type !== 'quiz') {
    // default to all
    Promise.all([
      fetch('/api/trk/search?q='+encodeURIComponent(q)).then(r=>r.json()),
      fetch('/api/tur/search?q='+encodeURIComponent(q)).then(r=>r.json()),
      fetch('/api/quiz/search?q='+encodeURIComponent(q)).then(r=>r.json()),
    ]).then(([trk, tur, quiz]) => {
      let html = '';
      let total = 0;
      if (trk.total > 0) {
        total += trk.total;
        html += '<div style="margin-top:4px;"><b>İngilizce → Türkçe</b></div>';
        trk.data.slice(0,20).forEach(e => { html += `<div style="padding:1px 4px;">${e.en} → ${e.tr}</div>`; });
      }
      if (tur.total > 0) {
        total += tur.total;
        html += '<div style="margin-top:4px;"><b>Türkçe Leb Demeden</b></div>';
        tur.data.slice(0,20).forEach(e => { html += `<div style="padding:1px 4px;">${e.word}</div>`; });
      }
      if (quiz.total > 0) {
        total += quiz.total;
        html += '<div style="margin-top:4px;"><b>Kelime Oyunu</b></div>';
        quiz.data.slice(0,20).forEach(e => { html += `<div style="padding:1px 4px;">[${e.topic}] ${e.en}</div>`; });
      }
      if (total === 0) html = '<div style="color:#666;">Sonuç bulunamadı.</div>';
      else html = `<div style="color:#444;margin-bottom:4px;">${total} sonuç</div>` + html;
      document.getElementById('findResults').innerHTML = html;
    });
    return;
  }
  
  Promise.all(promises).then(results => {
    let html = '';
    let total = 0;
    results.forEach((r, idx) => {
      if (r.total > 0) {
        total += r.total;
        html += `<div style="margin-top:4px;"><b>${labels[idx]}</b> (${r.total})</div>`;
        r.data.slice(0,20).forEach(e => {
          const text = e.en || e.word || '';
          const def = e.tr || e.def || e.synonyms || '';
          html += `<div style="padding:1px 4px;">${text} ${def ? '→ '+def : ''}</div>`;
        });
      }
    });
    if (total === 0) html = '<div style="color:#666;">Sonuç bulunamadı.</div>';
    else html = `<div style="color:#444;margin-bottom:4px;">${total} sonuç</div>` + html;
    document.getElementById('findResults').innerHTML = html;
  });
}

function closeDialog(id) {
  document.getElementById(id).classList.remove('open');
}

// ─── Check Options Dialog ─────────────────────────────────────────────────
function openSpellCheck() {
  closeAllMenus();
  closeAllWindows();
  const id = 'win-chk-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');
  let html = `<div class="win-window" id="${id}" style="width:500px;height:400px;overflow:hidden;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Yazım Denetimi</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:6px;flex:1;display:flex;flex-direction:column;min-height:0;">`;
  html += `<label style="font-size:13px;font-weight:600;margin-bottom:4px;">Metin:</label>`;
  html += `<textarea id="${id}-text" style="flex:1;resize:none;font-size:14px;padding:6px;font-family:'Segoe UI',sans-serif;" placeholder="Denetlenecek metni yazın…"></textarea>`;
  html += `<div style="margin:4px 0;display:flex;gap:6px;align-items:center;">`;
  html += `<button class="win-btn primary" onclick="runSpellCheck('${id}')">Denetle</button>`;
  html += `<span id="${id}-status" style="font-size:12px;color:#666;"></span>`;
  html += `</div>`;
  html += `<div id="${id}-results" style="flex:0 0 auto;max-height:150px;overflow-y:auto;font-size:13px;"></div>`;
  html += `</div></div>`;
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'spellcheck', id: id };
}

function runSpellCheck(winId) {
  const textEl = document.getElementById(winId + '-text');
  const resultsEl = document.getElementById(winId + '-results');
  const statusEl = document.getElementById(winId + '-status');
  const text = textEl.value.trim();
  if (!text) { statusEl.textContent = 'Lütfen metin girin.'; return; }

  statusEl.textContent = 'Denetleniyor…';
  resultsEl.innerHTML = '';

  const words = text.match(/[a-zA-ZçÇğĞışİöÖşŞüÜâîû]+/g) || [];
  if (words.length === 0) {
    statusEl.textContent = 'Denetlenecek kelime bulunamadı.';
    return;
  }

  let checked = 0;
  let errors = [];

  words.forEach((w, idx) => {
    fetch(`/api/check?q=${encodeURIComponent(w)}`)
      .then(r => r.json())
      .then(data => {
        checked++;
        statusEl.textContent = `${checked}/${words.length} denetlendi`;
        if (!data.valid) {
          let sug = '';
          if (data.suggestions && data.suggestions.length > 0) {
            sug = ' → ' + data.suggestions.slice(0, 5).map(s => s.word).join(', ');
          }
          errors.push({ word: data.word, suggestions: data.suggestions });
          const div = document.createElement('div');
          div.style.cssText = 'padding:2px 0;color:#c33;';
          div.textContent = data.word + sug;
          resultsEl.appendChild(div);
        }
        if (checked === words.length) {
          statusEl.textContent = errors.length > 0
            ? `${errors.length} hatalı kelime bulundu.`
            : '✓ Hiçbir hata bulunamadı.';
        }
      })
      .catch(() => {
        checked++;
        if (checked === words.length) {
          statusEl.textContent = errors.length > 0
            ? `${errors.length} hatalı kelime bulundu.`
            : '✓ Hiçbir hata bulunamadı.';
        }
      });
  });
}

function showCheckOptions() {
  closeAllWindows();
  const id = 'win-chk-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');
  
  let html = `<div class="win-window" id="${id}" style="width:360px;height:280px;overflow:hidden;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Denetim Opsiyonlar</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:6px;flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden;">`;
  html += `<div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin:0 0 6px 0;"><legend>Denetim Seçenekleri</legend>`;
  html += `<div style="flex:1;overflow-y:auto;min-height:0;padding-top:4px;">`;
  const opts = [
    'Paragraf başı kontrol',
    'Bileşik isim denetimi',
    'Özel isim yumuşama denetimi',
    'Cins isim apostrof denetimi',
    'Öneri getirme',
    'Yazarken denetim',
    'Şapka denetimi',
  ];
  opts.forEach(o => {
    html += `<label style="display:block;margin:2px 0;font-size:13px;font-weight:600;"><input type="checkbox" checked> ${o}</label>`;
  });
  html += `</div></div>`;
  html += `<div style="text-align:right;flex-shrink:0;"><button class="win-btn primary" onclick="closeWindow('${id}')">Tamam</button></div>`;
  html += `</div></div>`;
  
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'options', id: id };
}

// ─── Open Stats ───────────────────────────────────────────────────────────
function openStatsWindow() {
  closeAllMenus();
  openWindow('stats');
}

// ─── Open Quiz (Adam Asma) ──────────────────────────────────────────────
function openQuizWindow() {
  openWindow('quiz');
}

// ─── Turkish Spell Check Text Editor Module ──────────────────────────────────
function openTextEditor() {
  closeAllMenus();
  closeAllWindows();
  const id = 'win-edt';
  if (document.getElementById(id)) return;
  
  let html = `<div class="win-window" id="${id}" style="width:580px;height:450px;overflow:hidden;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text" id="${id}-title">MoonStar Türkçe Denetim Editörü - [isimsiz]</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  
  html += `<div class="win-body" style="padding:0;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;position:relative;">`;
  
  // Editor local Menu Bar
  html += `  <div class="menu-bar" style="border-bottom:1px solid #808080;padding:1px 2px;background:#c0c0c0;flex-shrink:0;user-select:none;display:flex;gap:4px;">`;
  html += `    <div class="menu-item" onclick="toggleEditorMenu('${id}-file-menu', event)" style="padding:2px 6px;cursor:pointer;">Dosya</div>`;
  html += `    <div class="menu-item" onclick="toggleEditorMenu('${id}-edit-menu', event)" style="padding:2px 6px;cursor:pointer;">Edit</div>`;
  html += `    <div class="menu-item" onclick="toggleEditorMenu('${id}-find-menu', event)" style="padding:2px 6px;cursor:pointer;">Bul</div>`;
  html += `    <div class="menu-item" onclick="toggleEditorMenu('${id}-text-menu', event)" style="padding:2px 6px;cursor:pointer;">Metin</div>`;
  html += `    <div class="menu-item" onclick="toggleEditorMenu('${id}-opts-menu', event)" style="padding:2px 6px;cursor:pointer;">Opsiyonlar</div>`;
  html += `    <div class="menu-item" onclick="toggleEditorMenu('${id}-help-menu', event)" style="padding:2px 6px;cursor:pointer;">Yardım</div>`;
  html += `  </div>`;
  
  // Editor absolute dropdown menus (contained inside the editor win-body)
  html += `  <div class="dropdown editor-dropdown" id="${id}-file-menu" style="display:none;position:absolute;left:2px;top:21px;z-index:100;background:#c0c0c0;border:2px solid;border-color:#fff #555 #555 #fff;min-width:140px;box-shadow:2px 2px 5px rgba(0,0,0,0.2);">`;
  html += `    <div class="dropdown-item" onclick="editorNew('${id}')" style="padding:4px 8px;cursor:pointer;">Yeni</div>`;
  html += `    <div class="dropdown-item" onclick="editorOpenDemo('${id}')" style="padding:4px 8px;cursor:pointer;">Dosya Açma (TEST)</div>`;
  html += `    <div class="dropdown-sep" style="border-top:1px solid #808080;border-bottom:1px solid #fff;margin:2px 0;"></div>`;
  html += `    <div class="dropdown-item" onclick="editorSave('${id}')" style="padding:4px 8px;cursor:pointer;">Kaydet</div>`;
  html += `    <div class="dropdown-item" onclick="closeWindow('${id}')" style="padding:4px 8px;cursor:pointer;">Kapat</div>`;
  html += `  </div>`;
  
  html += `  <div class="dropdown editor-dropdown" id="${id}-edit-menu" style="display:none;position:absolute;left:48px;top:21px;z-index:100;background:#c0c0c0;border:2px solid;border-color:#fff #555 #555 #fff;min-width:100px;box-shadow:2px 2px 5px rgba(0,0,0,0.2);">`;
  html += `    <div class="dropdown-item" onclick="editorUndo('${id}')" style="padding:4px 8px;cursor:pointer;">Geri Al</div>`;
  html += `    <div class="dropdown-sep" style="border-top:1px solid #808080;border-bottom:1px solid #fff;margin:2px 0;"></div>`;
  html += `    <div class="dropdown-item" onclick="editorCut('${id}')" style="padding:4px 8px;cursor:pointer;">Kes</div>`;
  html += `    <div class="dropdown-item" onclick="editorCopy('${id}')" style="padding:4px 8px;cursor:pointer;">Kopyala</div>`;
  html += `    <div class="dropdown-item" onclick="editorPaste('${id}')" style="padding:4px 8px;cursor:pointer;">Yapıştır</div>`;
  html += `    <div class="dropdown-item" onclick="editorClear('${id}')" style="padding:4px 8px;cursor:pointer;">Temizle</div>`;
  html += `  </div>`;
  
  html += `  <div class="dropdown editor-dropdown" id="${id}-find-menu" style="display:none;position:absolute;left:82px;top:21px;z-index:100;background:#c0c0c0;border:2px solid;border-color:#fff #555 #555 #fff;min-width:120px;box-shadow:2px 2px 5px rgba(0,0,0,0.2);">`;
  html += `    <div class="dropdown-item" onclick="editorShowFind('${id}')" style="padding:4px 8px;cursor:pointer;">Bul...</div>`;
  html += `    <div class="dropdown-item" onclick="editorShowReplace('${id}')" style="padding:4px 8px;cursor:pointer;">Değiştir...</div>`;
  html += `  </div>`;
  
  html += `  <div class="dropdown editor-dropdown" id="${id}-text-menu" style="display:none;position:absolute;left:112px;top:21px;z-index:100;background:#c0c0c0;border:2px solid;border-color:#fff #555 #555 #fff;min-width:160px;box-shadow:2px 2px 5px rgba(0,0,0,0.2);">`;
  html += `    <div class="dropdown-item" onclick="editorSpellCheck('${id}')" style="padding:4px 8px;cursor:pointer;">Yazım Denetimi (F2)</div>`;
  html += `  </div>`;
  
  html += `  <div class="dropdown editor-dropdown" id="${id}-opts-menu" style="display:none;position:absolute;left:150px;top:21px;z-index:100;background:#c0c0c0;border:2px solid;border-color:#fff #555 #555 #fff;min-width:160px;box-shadow:2px 2px 5px rgba(0,0,0,0.2);">`;
  html += `    <div class="dropdown-item" onclick="showCheckOptions()" style="padding:4px 8px;cursor:pointer;">Denetim Opsiyonları...</div>`;
  html += `  </div>`;
  
  html += `  <div class="dropdown editor-dropdown" id="${id}-help-menu" style="display:none;position:absolute;left:205px;top:21px;z-index:100;background:#c0c0c0;border:2px solid;border-color:#fff #555 #555 #fff;min-width:140px;box-shadow:2px 2px 5px rgba(0,0,0,0.2);">`;
  html += `    <div class="dropdown-item" onclick="showAbout()" style="padding:4px 8px;cursor:pointer;">MoonStar Hakkında</div>`;
  html += `  </div>`;
  
  // Monospace text editor field
  html += `  <div style="flex:1;min-height:0;position:relative;background:#fff;border-top:1px solid #808080;">`;
  html += `    <textarea id="${id}-textarea" style="width:100%;height:100%;border:none;outline:none;resize:none;font-family:'Courier New', monospace;font-size:14px;padding:8px;box-sizing:border-box;background:#fff;color:#000;line-height:1.4;white-space:pre-wrap;overflow-y:scroll;" onfocus="closeAllEditorMenus()"></textarea>`;
  html += `  </div>`;
  
  // Status Bar
  html += `  <div class="win-status" id="${id}-status" style="flex-shrink:0;padding:2px 4px;border-top:1px solid #808080;font-size:11px;background:#c0c0c0;user-select:none;">Editör Hazır.</div>`;
  
  html += `</div></div>`;
  
  const workArea = document.getElementById('workArea');
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'editor', id: id };
  
  // Attach keydown listener for F2 shortcut
  const textarea = document.getElementById(id + '-textarea');
  textarea.addEventListener('keydown', function(event) {
    if (event.key === 'F2') {
      event.preventDefault();
      editorSpellCheck(id);
    }
  });
  
  // Global click handler to close editor dropdowns
  document.addEventListener('click', closeAllEditorMenus);
}

function toggleEditorMenu(menuId, event) {
  event.stopPropagation();
  const dropdown = document.getElementById(menuId);
  const wasOpen = dropdown.style.display === 'block';
  closeAllEditorMenus();
  if (!wasOpen) {
    dropdown.style.display = 'block';
  }
}

function closeAllEditorMenus() {
  document.querySelectorAll('.editor-dropdown').forEach(d => d.style.display = 'none');
}

function editorNew(winId) {
  closeAllEditorMenus();
  const textarea = document.getElementById(winId + '-textarea');
  textarea.value = '';
  document.getElementById(winId + '-title').textContent = 'MoonStar Türkçe Denetim Editörü - [isimsiz]';
  document.getElementById(winId + '-status').textContent = 'Yeni belge oluşturuldu.';
}

function editorOpenDemo(winId) {
  closeAllEditorMenus();
  const status = document.getElementById(winId + '-status');
  status.textContent = 'Demo belgesi yükleniyor...';
  
  fetch('/api/editor/demo')
    .then(r => r.json())
    .then(data => {
      if (data.content) {
        document.getElementById(winId + '-textarea').value = data.content;
        document.getElementById(winId + '-title').textContent = `MoonStar Türkçe Denetim Editörü - [${data.filename}]`;
        status.textContent = 'Demo belgesi yüklendi.';
      } else {
        status.textContent = 'Hata: Demo belgesi yüklenemedi.';
      }
    })
    .catch(() => {
      status.textContent = 'Hata: Sunucu bağlantısı başarısız.';
    });
}

function editorSave(winId) {
  closeAllEditorMenus();
  alert('Dosya kaydedildi (Tarayıcı hafızasına simüle edildi).');
  document.getElementById(winId + '-status').textContent = 'Dosya başarıyla kaydedildi.';
}

function editorClear(winId) {
  closeAllEditorMenus();
  document.getElementById(winId + '-textarea').value = '';
}

function editorUndo(winId) {
  closeAllEditorMenus();
  // Browser native undo simulation
  document.getElementById(winId + '-textarea').focus();
  document.execCommand('undo');
}

function editorCut(winId) {
  closeAllEditorMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const selStart = t.selectionStart;
  const selEnd = t.selectionEnd;
  if (selStart !== selEnd) {
    const text = t.value;
    navigator.clipboard.writeText(text.substring(selStart, selEnd));
    t.value = text.substring(0, selStart) + text.substring(selEnd);
    t.setSelectionRange(selStart, selStart);
  }
}

function editorCopy(winId) {
  closeAllEditorMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const selStart = t.selectionStart;
  const selEnd = t.selectionEnd;
  if (selStart !== selEnd) {
    navigator.clipboard.writeText(t.value.substring(selStart, selEnd));
  }
}

function editorPaste(winId) {
  closeAllEditorMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  navigator.clipboard.readText().then(clipText => {
    const start = t.selectionStart;
    const end = t.selectionEnd;
    const val = t.value;
    t.value = val.substring(0, start) + clipText + val.substring(end);
    const newPos = start + clipText.length;
    t.setSelectionRange(newPos, newPos);
  });
}

function editorShowFind(winId) {
  closeAllEditorMenus();
  const query = prompt('Bulunacak metin:');
  if (!query) return;
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  const idx = text.indexOf(query, t.selectionStart);
  if (idx !== -1) {
    t.focus();
    t.setSelectionRange(idx, idx + query.length);
  } else {
    // Wrap around
    const idx2 = text.indexOf(query);
    if (idx2 !== -1) {
      t.focus();
      t.setSelectionRange(idx2, idx2 + query.length);
    } else {
      alert('Metin bulunamadı.');
    }
  }
}

function editorShowReplace(winId) {
  closeAllEditorMenus();
  const query = prompt('Değiştirilecek metin:');
  if (!query) return;
  const rep = prompt('Yeni metin:');
  if (rep === null) return;
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  if (text.includes(query)) {
    t.value = text.replaceAll(query, rep);
    alert('Metinler değiştirildi.');
  } else {
    alert('Metin bulunamadı.');
  }
}

// ─── Interactive Spell Checker Logic ─────────────────────────────────────────
let spellCheckState = {
  winId: null,
  words: [],
  currentIdx: 0,
  errors: [],
  errorIdx: 0
};

function editorSpellCheck(winId) {
  closeAllEditorMenus();
  const status = document.getElementById(winId + '-status');
  status.textContent = 'Yazım denetimi başlatılıyor...';
  
  const textarea = document.getElementById(winId + '-textarea');
  const text = textarea.value;
  if (!text.trim()) {
    alert('Denetlenecek metin yok.');
    status.textContent = 'Yazım denetimi iptal edildi (metin boş).';
    return;
  }
  
  // Extract words with offsets
  const regex = /[a-zA-ZçÇğĞıİöÖşŞüÜâîû]+/g;
  let match;
  const words = [];
  const uniqueWords = new Set();
  
  while ((match = regex.exec(text)) !== null) {
    words.push({
      word: match[0],
      start: match.index,
      end: regex.lastIndex
    });
    uniqueWords.add(match[0].toLowerCase());
  }
  
  if (words.length === 0) {
    alert('Denetlenecek kelime bulunamadı.');
    return;
  }
  
  // Perform bulk check
  const wordsList = Array.from(uniqueWords).join(',');
  status.textContent = 'Kelimeler sorgulanıyor...';
  
  fetch('/api/check/bulk?q=' + encodeURIComponent(wordsList))
    .then(r => r.json())
    .then(results => {
      // Filter out misspelled word occurrences
      const errors = [];
      words.forEach((w, idx) => {
        const check = results[w.word] || results[w.word.toLowerCase()];
        if (check && !check.valid) {
          errors.push(idx);
        }
      });
      
      if (errors.length === 0) {
        alert('✓ Hiçbir yazım hatası bulunamadı.');
        status.textContent = '✓ Yazım denetimi tamamlandı: Hata bulunamadı.';
        return;
      }
      
      // Initialize spell check loop state
      spellCheckState = {
        winId: winId,
        words: words,
        errors: errors,
        errorIdx: 0,
        results: results
      };
      
      // Open dialog
      document.getElementById('spellCheckDialog').classList.add('open');
      spellCheckNext();
    })
    .catch(() => {
      status.textContent = 'Hata: Sunucu bağlantısı başarısız.';
    });
}

function spellCheckNext() {
  const state = spellCheckState;
  const textarea = document.getElementById(state.winId + '-textarea');
  const status = document.getElementById(state.winId + '-status');
  
  if (state.errorIdx >= state.errors.length) {
    // Completed!
    closeSpellCheck();
    alert('Yazım denetimi tamamlandı.');
    status.textContent = '✓ Yazım denetimi tamamlandı.';
    textarea.focus();
    return;
  }
  
  const errWordIdx = state.errors[state.errorIdx];
  const errWordOccur = state.words[errWordIdx];
  
  // Highlight in textarea
  textarea.focus();
  textarea.setSelectionRange(errWordOccur.start, errWordOccur.end);
  
  // Scroll word into view if needed (textarea selection behavior)
  const lineNum = textarea.value.substr(0, errWordOccur.start).split("\n").length;
  const lineHeight = 19; // approx line height
  textarea.scrollTop = (lineNum - 4) * lineHeight;
  
  // Update fields
  document.getElementById('spell-err-word').value = errWordOccur.word;
  
  // Suggestions
  const check = state.results[errWordOccur.word] || state.results[errWordOccur.word.toLowerCase()];
  const suggestions = (check && check.suggestions) || [];
  const sugInput = document.getElementById('spell-sug-word');
  const sugList = document.getElementById('spell-suggestions');
  
  sugList.innerHTML = '';
  if (suggestions.length > 0) {
    sugInput.value = suggestions[0].word;
    sugList.innerHTML = suggestions.map((s, idx) => 
      `<div class="dict-word${idx===0?' dict-sel':''}" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectSpellSuggestion(this, '${s.word}')">${s.word}</div>`
    ).join('');
  } else {
    sugInput.value = errWordOccur.word; // fall back to original
    sugList.innerHTML = '<div style="color:#888;padding:6px;font-style:italic;">Öneri bulunamadı.</div>';
  }
  
  status.textContent = `Hata ${state.errorIdx + 1} / ${state.errors.length}: "${errWordOccur.word}"`;
}

function selectSpellSuggestion(el, word) {
  document.getElementById('spell-sug-word').value = word;
  const sugList = document.getElementById('spell-suggestions');
  sugList.querySelectorAll('.dict-word').forEach(e => e.classList.remove('dict-sel'));
  el.classList.add('dict-sel');
}

function spellCheckIgnore() {
  spellCheckState.errorIdx++;
  spellCheckNext();
}

function spellCheckAdd() {
  const word = spellCheckState.words[spellCheckState.errors[spellCheckState.errorIdx]].word;
  // In a real app this adds to user dictionary. Here we simulate.
  console.log('Added to user dictionary: ' + word);
  spellCheckState.errorIdx++;
  spellCheckNext();
}

function spellCheckReplace() {
  const state = spellCheckState;
  const textarea = document.getElementById(state.winId + '-textarea');
  const errWordIdx = state.errors[state.errorIdx];
  const errWordOccur = state.words[errWordIdx];
  
  const repWord = document.getElementById('spell-sug-word').value;
  if (!repWord) return;
  
  const text = textarea.value;
  textarea.value = text.substring(0, errWordOccur.start) + repWord + text.substring(errWordOccur.end);
  
  // Recalculate offsets for all subsequent occurrences
  const diff = repWord.length - errWordOccur.word.length;
  for (let i = errWordIdx + 1; i < state.words.length; i++) {
    state.words[i].start += diff;
    state.words[i].end += diff;
  }
  
  // Step
  state.errorIdx++;
  spellCheckNext();
}

function closeSpellCheck() {
  document.getElementById('spellCheckDialog').classList.remove('open');
  if (spellCheckState.winId) {
    document.getElementById(spellCheckState.winId + '-textarea').focus();
  }
}

// ─── Show About ───────────────────────────────────────────────────────────
function showAbout() {
  closeAllMenus();
  document.getElementById('aboutDialog').classList.add('open');
}

// ─── Init ─────────────────────────────────────────────────────────────────
showWelcomeWindow();
</script>
</body>
</html>
"""


# ─── Auto‑reload helper ─────────────────────────────────────────────────────

def start_with_reload():
    import subprocess
    script_path = os.path.abspath(__file__)
    proc = None
    try:
        while True:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except:
                    proc.kill()
                    proc.wait()
                time.sleep(0.5)
            proc = subprocess.Popen(
                [sys.executable, script_path],
                cwd=SCRIPT_DIR
            )
            mtime = os.stat(script_path).st_mtime
            print(f"  🔄 --reload aktif: PID={proc.pid}")
            while True:
                time.sleep(0.8)
                new_mtime = os.stat(script_path).st_mtime
                if new_mtime != mtime:
                    print("\n  🔄 Değişiklik algılandı, yeniden başlatılıyor…")
                    break
    except KeyboardInterrupt:
        if proc:
            proc.terminate()
            proc.wait()
        print("\nSunucu durduruldu.")


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    import subprocess
    pid = subprocess.run(['lsof', '-ti', f":{PORT}"], capture_output=True, text=True).stdout.strip()
    if pid:
        # If multiple PIDs are returned, split and kill each
        pids = pid.split()
        print(f"  ⚠ Port {PORT} kullanımda (PID:{', '.join(pids)}), eski process sonlandırılıyor…")
        for p in pids:
            subprocess.run(['kill', '-9', p], capture_output=True)
        time.sleep(0.3)

    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("0.0.0.0", PORT), MoonStarHandler)

    def shutdown(signum=None, frame=None):
        print("\nSunucu durduruldu.")
        server.shutdown()
        server.server_close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)

    print(f"\n🌙 MoonStar Veri Gezgini çalışıyor:")
    print(f"   http://localhost:{PORT}")
    print(f"\n   Sözlükler: İng→Tr ({len(TRK_DATA)}), Tr→Tr ({len(TUR_DATA)}), EşAnlam ({len(SYN_DATA)})")
    print(f"   Kelime Oyunu: {len(QUIZ_DATA)} kelime, {len([t for t in TOPIC_NAMES if len(t) > 1])} konu")
    print(f"\n   Çıkmak için Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    if "--reload" in sys.argv:
        start_with_reload()
    else:
        main()
