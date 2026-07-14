#! /usr/bin/python3

# MoonStar Data Explorer — Web UI Server
# Serves all decoded MoonStar data through a browser interface
#
# @yasinkuyu

import os
import sys
import json
import struct
import time
import http.server
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")

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
    return entries


def load_synonyms():
    """Load Turkish synonyms."""
    entries = []
    path = os.path.join(OUTPUT_DIR, "MTU.TUR_ES_ANLAM.TXT")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        entries.append({"word": parts[0], "synonyms": parts[1]})
    return entries


def load_trk_reverse():
    """Load Turkish→English (reverse of TRK)."""
    entries = []
    path = os.path.join(OUTPUT_DIR, "MTU.TUR_TR_EN.TXT")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        entries.append({"tr": parts[0], "en": parts[1]})
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
        else:
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
        q = params.get("q", [""])[0].lower()
        if not q:
            return {"data": [], "total": 0}
        results = [e for e in TRK_DATA if e["en"].lower().startswith(q)]
        return {"data": results[:100], "total": len(results)}

    def search_tur(self, params):
        q = params.get("q", [""])[0].lower()
        if not q:
            return {"data": [], "total": 0}
        results = [e for e in TUR_DATA if e["word"].lower().startswith(q)]
        return {"data": results[:100], "total": len(results)}

    def search_rev(self, params):
        q = params.get("q", [""])[0].lower()
        if not q:
            return {"data": [], "total": 0}
        results = [e for e in REV_DATA if e["tr"].lower().startswith(q)]
        return {"data": results[:100], "total": len(results)}

    def search_syn(self, params):
        q = params.get("q", [""])[0].lower()
        if not q:
            return {"data": [], "total": 0}
        results = [e for e in SYN_DATA if e["word"].lower().startswith(q)]
        return {"data": results[:100], "total": len(results)}

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
        for q in QUIZ_DATA:
            t = q["topic_idx"]
            topic_counts[t] = topic_counts.get(t, 0) + 1
        result = []
        for idx in sorted(topic_counts.keys()):
            name = q["topic"] if q["topic"] else ""
            if idx < len(TOPIC_NAMES) and len(TOPIC_NAMES[idx]) > 1:
                name = TOPIC_NAMES[idx]
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


# ─── HTML Page ──────────────────────────────────────────────────────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MoonStar Türkçe Denetim Editörü</title>
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
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
  box-sizing: border-box;
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
}
.main-win > .win-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0 !important;
}

/* Menu Bar */
.menu-bar {
  background: #c0c0c0;
  padding: 1px 2px;
  display: flex;
  gap: 0;
  flex-shrink: 0;
  flex-grow: 0;
  border-bottom: 1px solid #808080;
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

/* Main work area */
.work-area {
  flex: 1;
  padding: 2px;
  overflow: auto;
  position: relative;
  background: #808080;
}

/* Win16-style window frame */
.win-window {
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #404040 #404040 #fff;
  box-shadow: 2px 2px 0 rgba(0,0,0,0.4);
  margin-bottom: 4px;
  display: inline-block;
  min-width: 280px;
  vertical-align: top;
}
.win-title {
  background: #000080;
  color: #fff;
  padding: 3px 4px;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  cursor: default;
}
.win-title.inactive {
  background: #808080;
}
.win-title-text { flex: 1; }
.win-title-btns { display: flex; gap: 2px; margin-left: auto; }
.win-title-btns button {
  width: 13px; height: 12px;
  background: #c0c0c0;
  border: 1px solid;
  border-color: #fff #808080 #808080 #fff;
  font-size: 7px;
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
.win-input:focus {
  border-color: #000;
}

/* Win16 listbox */
.win-list {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  background: #fff;
  overflow-y: auto;
}

/* Dictionary split pane */
.dict-word {
  padding: 3px 6px;
  cursor: pointer;
  border-bottom: 1px dotted #ddd;
  font-size: 14px;
}
.dict-word:hover { background: #e8e8ff; }

.dict-sel { background: #000080; color: #fff; }
.dict-sel:hover { background: #000080; }
.dict-meaning {
  padding: 4px 6px;
  border-bottom: 1px solid #ccc;
  cursor: pointer;
  font-size: 14px;
}
.dict-meaning:hover { background: #e8e8ff; }
.dict-meaning .row-num { display: inline-block; min-width: 24px; color: #888; }
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
  background: #c0c0c0;
  border-top: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  padding: 0 4px;
  display: flex;
  font-size: 11px;
  flex-shrink: 0;
  flex-grow: 0;
  height: 18px;
  align-items: center;
}
.status-bar .status-sep {
  width: 2px;
  background: #808080;
  margin: 0 4px;
  border-left: 1px solid #fff;
}

/* Scrollbar-like areas */
.scroll-area {
  overflow-y: auto;
  max-height: 400px;
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

/* Topics grid */
.topics-grid { display: flex; flex-wrap: wrap; gap: 4px; }
.topic-tile {
  background: #c0c0c0;
  border: 2px solid;
  border-color: #fff #808080 #808080 #fff;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  display: inline-block;
}
.topic-tile:active {
  border-color: #808080 #fff #fff #808080;
}
.topic-tile .count { font-size: 12px; color: #666; }

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
  z-index: 500;
}
.dialog-overlay.open { display: flex; align-items: center; justify-content: center; }

/* Context help */
.help-text { font-size: 11px; color: #444; padding: 8px; }
</style>
</head>
<body>

<div class="desktop">
  <!-- Main Application Window -->
  <div class="win-window main-win" id="mainWin">
    <div class="win-title"><span class="win-title-text">MoonStar Türkçe Denetim Editörü</span>
      <div class="win-title-btns"><button>—</button><button>□</button><button>✕</button></div>
    </div>
    <div class="win-body" style="padding:0;">
      <!-- Menu Bar -->
      <div class="menu-bar" id="menuBar">
        <div class="menu-item" onclick="toggleMenu('fileMenu', event)">Dosya</div>
        <div class="menu-item" onclick="toggleMenu('editMenu', event)">Düzen</div>
        <div class="menu-item" onclick="toggleMenu('searchMenu', event)">Ara</div>
        <div class="menu-item" onclick="toggleMenu('checkMenu', event)">Denetim</div>
        <div class="menu-item" onclick="toggleMenu('dictMenu', event)">Sözlük</div>
        <div class="menu-item" onclick="toggleMenu('statsMenu', event)">İstatistik</div>
        <div class="menu-item" onclick="toggleMenu('optionsMenu', event)">Seçenekler</div>
        <div class="menu-item" onclick="toggleMenu('helpMenu', event)">Yardım</div>
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
        <div class="dropdown-item" onclick="showCheckOptions()">Denetim Opsiyonlar</div>
      </div>
      <div class="dropdown" id="dictMenu">
        <div class="dropdown-item" onclick="openWindow('ing-tr')">Leb demeden (İngilizce → Türkçe)</div>
        <div class="dropdown-item" onclick="openWindow('tr-ing')">Leb demeden (Türkçe → İngilizce)</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="openWindow('synonyms')">Eş Anlamlı kelimeler</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="openWindow('tr-tr')">Türkçe Leb Demeden</div>
      </div>
      <div class="dropdown" id="statsMenu">
        <div class="dropdown-item" onclick="openStatsWindow()">Metin İstatistik</div>
      </div>
      <div class="dropdown" id="optionsMenu">
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Karakter Listesi</div>
        <div class="dropdown-item" onclick="winAlert('Bu özellik sadece veri görüntüleme amaçlıdır.')">Genel tanımlar</div>
      </div>
      <div class="dropdown" id="helpMenu">
        <div class="dropdown-item" onclick="showAbout()">MoonStar Hakkında</div>
      </div>

      <!-- Client Area for Child Windows -->
      <div class="work-area" id="workArea">
        <!-- Windows will be added here dynamically -->
      </div>

      <!-- Status Bar -->
      <div class="status-bar">
        <span>MoonStar Veri Gezgini</span>
        <span class="status-sep"></span>
        <span id="statusText">TRK: 17.975 | TUR: 26.775 | QUIZ: 12.437</span>
      </div>
    </div>
  </div>
</div>

<!-- About Dialog -->
<div class="dialog-overlay" id="aboutDialog">
  <div class="win-window" style="min-width:350px;">
    <div class="win-title inactive"><span class="win-title-text">MoonStar Hakkında</span>
      <div class="win-title-btns"><button onclick="closeDialog('aboutDialog')">✕</button></div>
    </div>
    <div class="win-body" style="text-align:center;padding:20px;">
      <div style="font-size:36px;color:#000080;margin-bottom:8px;">★</div>
      <div style="font-size:16px;font-weight:bold;">MoonStar</div>
      <div style="font-size:14px;margin:4px 0;">Türkçe Denetim Editörü</div>
      <div style="font-size:13px;color:#666;margin:12px 0;">
        Veri Gezgini Sürümü<br>
        Tersine Mühendislik: yasinkuyu<br>
        2026
      </div>
      <div style="font-size:13px;color:#888;">
        TRK: 17.975 | TUR: 26.775 | QUIZ: 12.437
      </div>
      <div style="margin-top:16px;">
        <button class="win-btn" onclick="closeDialog('aboutDialog')">Tamam</button>
      </div>
    </div>
  </div>
</div>

<!-- Find Dialog -->
<div class="dialog-overlay" id="findDialog">
  <div class="win-window" style="min-width:350px;">
    <div class="win-title inactive"><span class="win-title-text">Al ve bul</span>
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
        <label><input type="radio" name="findType" onclick="document.getElementById('findInput').placeholder='Konu veya kelime...'"> Kelime Oyunu</label>
      </div>
      <div style="margin-top:8px;text-align:right;">
        <button class="win-btn primary" onclick="doFind()">Bul</button>
        <button class="win-btn" onclick="closeDialog('findDialog')">İptal</button>
      </div>
      <div id="findResults" style="margin-top:8px;max-height:200px;overflow-y:auto;font-size:13px;"></div>
    </div>
  </div>
</div>

<script>
// ─── State ────────────────────────────────────────────────────────────────
let state = {
  windows: {},
  nextWindowId: 0,
  pageCache: {},
};

// ─── Win16 Alert Dialog ──────────────────────────────────────────────────
function winAlert(msg) {
  const id = 'alert-' + Date.now();
  const ov = document.createElement('div');
  ov.className = 'dialog-overlay open';
  ov.id = id;
  ov.innerHTML = `<div class="win-window" style="min-width:300px;max-width:400px;">
    <div class="win-title inactive"><span class="win-title-text">MoonStar</span>
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
  Object.keys(state.windows).forEach(k => {
    const el = document.getElementById(k);
    if (el) el.remove();
    delete state.windows[k];
  });
}

function openWindow(type) {
  closeAllMenus();
  closeAllWindows();
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
      config = { title: 'Türkçe Eş Anlamlı Sözcükler', type: 'syn', w: 540, h: 380 };
      break;
    case 'tr-tr':
      config = { title: 'Türkçe Leb Demeden', type: 'tur', w: 480, h: 380 };
      break;
    case 'quiz':
      config = { title: 'Kelime Oyunu - Konular', type: 'quiz-topics', w: 520, h: 380 };
      break;
    case 'stats':
      config = { title: 'Metin İstatistik', type: 'stats', w: 480, h: 340 };
      break;
    default:
      config = { title: 'Pencere', type: 'trk', w: 400, h: 300 };
  }

  let html = `<div class="win-window" id="${id}" style="width:${config.w}px;position:relative;">`;
  html += `<div class="win-title"><span class="win-title-text">${config.title}</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  
  if (config.type === 'trk' || config.type === 'rev') {
    html += `<div class="win-body" style="padding:4px;">
      <div style="margin-bottom:4px;display:flex;gap:4px;">
        <input class="win-input" type="text" placeholder="Sözcük ara..." style="flex:1;" id="${id}-search" oninput="dictSearchDebounced('${id}')">
        <button class="win-btn small" onclick="dictSearch('${id}')">👌 Tamam</button>
      </div>
      <div style="display:flex;gap:4px;margin-bottom:4px;">
        <div class="group-box" style="flex:1;"><legend>${type==='trk'?'İngilizce Sözcükler':'Türkçe Sözcükler'}</legend>
          <div class="win-list" style="height:180px;overflow-y:auto;" id="${id}-list"></div>
        </div>
        <div class="group-box" style="flex:1;"><legend>${type==='trk'?'Türkçe Karşılıklar':'İngilizce Karşılıklar'}</legend>
          <div class="win-list" style="height:180px;overflow-y:auto;" id="${id}-defn"></div>
        </div>
      </div>
      <div>
        <label style="font-weight:700;font-size:14px;">${type==='trk'?'Türkçe Karşılık':'İngilizce Karşılık'}</label><br>
        <input class="win-input" type="text" readonly style="width:100%;background:#fff;color:#000;border:2px inset #c0c0c0;" id="${id}-detail">
      </div>
      <div class="win-status" id="${id}-status"></div>
    </div>`;
  } else if (config.type === 'syn') {
    html += `<div class="win-body" style="padding:4px;">
      <div style="margin-bottom:4px;">
        <input class="win-input" type="text" placeholder="Kök sözcük ara..." style="width:100%;" id="${id}-search" oninput="dictSearchDebounced('${id}')">
      </div>
      <div style="display:flex;gap:4px;">
        <div class="group-box" style="flex:1;"><legend>Kök Sözcük</legend>
          <div class="win-list" style="height:130px;overflow-y:auto;" id="${id}-list"></div>
        </div>
        <div class="group-box" style="flex:1;"><legend>Eş Anlamları</legend>
          <div class="win-list" style="height:130px;overflow-y:auto;" id="${id}-defn"></div>
        </div>
      </div>
      <div class="group-box"><legend>Anlam Grupları</legend>
        <div class="win-list" style="height:60px;overflow-y:auto;" id="${id}-groups"></div>
      </div>
      <div class="win-status" id="${id}-status"></div>
    </div>`;
  } else if (config.type === 'tur') {
    html += `<div class="win-body" style="padding:4px;">
      <div style="margin-bottom:4px;">
        <input class="win-input" type="text" placeholder="Sözcük ara..." style="width:100%;" id="${id}-search" oninput="dictSearchDebounced('${id}')">
      </div>
      <div class="group-box"><legend>Türkçe Sözcükler</legend>
        <div class="win-list" style="height:230px;overflow-y:auto;" id="${id}-list"></div>
      </div>
      <div class="win-status" id="${id}-status"></div>
    </div>`;
  } else if (config.type === 'quiz-topics') {
    html += `<div class="win-body">`;
    html += `<div id="${id}-body" style="padding:4px;"><div class="loading">Yükleniyor...</div></div></div>`;
  } else if (config.type === 'stats') {
    html += `<div class="win-body" id="${id}-body"><div class="loading">Yükleniyor...</div></div>`;
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
    case 'quiz-topics': loadQuizTopics(id); break;
    case 'stats': loadWindowStats(id); break;
  }
}

function closeWindow(id) {
  const win = document.getElementById(id);
  if (win) win.remove();
  delete state.windows[id];
}

// ─── Dictionary Window ───────────────────────────────────────────────────
function loadWindowDict(winId, type, apiUrl) {
  const key1 = { trk: 'en', rev: 'tr', syn: 'word', tur: 'word' }[type];
  const key2 = { trk: 'tr', rev: 'en', syn: 'synonyms' }[type];
  const label1 = { trk: 'İngilizce Sözcükler', rev: 'Türkçe Sözcükler', syn: 'Kök Sözcük', tur: 'Sözcükler' }[type];
  
  fetch(apiUrl + `?page=1&per_page=99999`)
    .then(r=>r.json())
    .then(d=>{
      let listHtml = d.data.map((e, i) => {
        let en = e[key1] || '';
        return `<div class="dict-word${i===0?' dict-sel':''}" onclick="dictSelect('${winId}','${key2||''}',${i})">${en}</div>`;
      }).join('');
      let firstDef = d.data.length > 0 ? (d.data[0][key2] || '') : '';
      
      document.getElementById(winId + '-list').innerHTML = listHtml;
      if (firstDef) renderMeanings(winId, firstDef);
      document.getElementById(winId + '-status').textContent = `${d.total.toLocaleString()} kayıt`;
      state.windowData = state.windowData || {};
      state.windowData[winId] = d.data;
      const listEl = document.getElementById(winId + '-list');
      const selEl = listEl && listEl.querySelector('.dict-sel');
      if (selEl) selEl.scrollIntoView({ block: 'nearest' });
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
  df.innerHTML = parts.map((m, i) =>
    `<div class="dict-meaning${i===0?' meaning-sel':''}" onclick="selectMeaning('${winId}',${i})">${i===0?'<span class="row-num">1.</span> ':'<span class="row-num"></span> '}${m}</div>`
  ).join('');
  const dt = document.getElementById(winId + '-detail');
  if (dt) dt.value = parts[0];
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
  if (dt) dt.value = mw.parts[idx];
}

function dictSelect(winId, key2, idx) {
  document.querySelectorAll(`#${winId}-list .dict-word`).forEach(el => el.classList.remove('dict-sel'));
  const items = document.querySelectorAll(`#${winId}-list .dict-word`);
  if (items[idx]) items[idx].classList.add('dict-sel');
  const wd = state.windowData && state.windowData[winId];
  if (wd && wd[idx]) {
    const val = wd[idx][key2] || '';
    renderMeanings(winId, val);
  }
}

function dictSearch(winId) {
  const input = document.getElementById(winId + '-search');
  const q = input ? input.value.trim() : '';
  const win = state.windows[winId];
  if (!win) return;
  
  const apis = { trk: '/api/trk/search?q=', rev: '/api/rev/search?q=', syn: '/api/syn/search?q=', tur: '/api/tur/search?q=' };
  const apiUrl = apis[win.type];
  if (!apiUrl) return;
  
  if (!q) { loadWindowDict(winId, win.type, '/api/' + win.type); return; }
  
  fetch(apiUrl + encodeURIComponent(q))
    .then(r=>r.json())
    .then(d=>{
      const key1 = { trk: 'en', rev: 'tr', syn: 'word', tur: 'word' }[win.type];
      const key2 = { trk: 'tr', rev: 'en', syn: 'synonyms' }[win.type];
      let listHtml = d.data.map((e, i) => {
        let val = e[key1] || '';
        return `<div class="dict-word${i===0?' dict-sel':''}" onclick="dictSelect('${winId}','${key2||''}',${i})">${val}</div>`;
      }).join('');
      let firstDef = d.data.length > 0 ? (d.data[0][key2] || '') : '';
      document.getElementById(winId + '-list').innerHTML = listHtml;
      if (firstDef) renderMeanings(winId, firstDef);
      document.getElementById(winId + '-status').textContent = `${d.total} sonuç`;
      state.windowData = state.windowData || {};
      state.windowData[winId] = d.data;
    });
}

let _searchTimer = {};
function dictSearchDebounced(winId) {
  clearTimeout(_searchTimer[winId]);
  _searchTimer[winId] = setTimeout(() => dictSearch(winId), 150);
}

// ─── Quiz Topics Window ──────────────────────────────────────────────────
function loadQuizTopics(winId) {
  fetch('/api/quiz/topics').then(r=>r.json()).then(d=>{
    let html = `<div style="padding:4px;"><p style="margin-bottom:8px;font-size:13px;color:#444;">Her konudaki İngilizce→Türkçe kelime çiftlerini görüntülemek için tıklayın.</p>`;
    html += `<div class="topics-grid">`;
    d.topics.forEach(t => {
      html += `<div class="topic-tile" onclick="openQuizDetail(${t.idx},'${t.name}')">
        <b>${t.name}</b><br><span class="count">${t.count} kelime</span>
      </div>`;
    });
    html += `</div></div>`;
    document.getElementById(winId + '-body').innerHTML = html;
  });
}

function openQuizDetail(topicIdx, topicName) {
  const id = 'win-quiz-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');
  
  let html = `<div class="win-window full" id="${id}">`;
  html += `<div class="win-title"><span class="win-title-text">Kelime Oyunu — ${topicName}</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:4px;">`;
  html += `<div style="margin-bottom:4px;display:flex;gap:4px;">`;
  html += `<input class="win-input" type="text" id="${id}-search" placeholder="Bu konuda ara..." style="flex:1;" onkeyup="if(event.key==='Enter') quizSearch('${id}',${topicIdx})">`;
  html += `<button class="win-btn small" onclick="quizSearch('${id}',${topicIdx})">Ara</button>`;
  html += `</div>`;
  html += `<div class="win-list scroll-area" style="border:2px inset #c0c0c0;max-height:350px;" id="${id}-body"><div class="loading">Yükleniyor...</div></div>`;
  html += `<div class="win-status" id="${id}-status"></div>`;
  html += `</div></div>`;
  
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'quiz-detail', page: 1, topicIdx: topicIdx, id: id };
  
  loadQuizDetail(id, topicIdx, 1);
}

function loadQuizDetail(winId, topicIdx, page) {
  fetch(`/api/quiz?topic=${topicIdx}&page=${page}&per_page=50`)
    .then(r=>r.json()).then(d=>{
      let html = `<table><tr><th>#</th><th>İngilizce</th><th>Türkçe</th></tr>`;
      d.data.forEach(e => {
        html += `<tr><td>${e.slot}</td><td><b>${e.en}</b></td><td>${e.tr||'-'}</td></tr>`;
      });
      html += `</table>`;
      html += `<div class="pagination">`;
      html += `<button ${d.page<=1?'disabled':''} onclick="loadQuizDetail('${winId}',${topicIdx},1)">|◀</button>`;
      html += `<button ${d.page<=1?'disabled':''} onclick="loadQuizDetail('${winId}',${topicIdx},${d.page-1})">◀</button>`;
      html += `<span>${d.page} / ${d.total_pages}</span>`;
      html += `<button ${d.page>=d.total_pages?'disabled':''} onclick="loadQuizDetail('${winId}',${topicIdx},${d.page+1})">▶</button>`;
      html += `<button ${d.page>=d.total_pages?'disabled':''} onclick="loadQuizDetail('${winId}',${topicIdx},${d.total_pages})">▶|</button>`;
      html += `<span style="margin-left:8px;color:#666;">${d.total.toLocaleString()} kayıt</span>`;
      html += `</div>`;
      document.getElementById(winId+'-body').innerHTML = html;
      document.getElementById(winId+'-status').textContent = `${d.total} kayıt - Sayfa ${d.page}/${d.total_pages}`;
    });
}

function quizSearch(winId, topicIdx) {
  const input = document.getElementById(winId+'-search');
  const q = input ? input.value : '';
  if (!q) { loadQuizDetail(winId, topicIdx, 1); return; }
  fetch('/api/quiz/search?q='+encodeURIComponent(q))
    .then(r=>r.json()).then(d=>{
      let html = `<p style="padding:4px;color:#666;">"${q}" için ${d.total} sonuç</p>`;
      html += `<table><tr><th>Konu</th><th>İngilizce</th><th>Türkçe</th></tr>`;
      d.data.forEach(e => {
        html += `<tr><td>${e.topic}</td><td><b>${e.en}</b></td><td>${e.tr||'-'}</td></tr>`;
      });
      html += `</table>`;
      document.getElementById(winId+'-body').innerHTML = html;
      document.getElementById(winId+'-status').textContent = `${d.total} sonuç`;
    });
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
      ['Kelime Oyunu (Quiz)', d.quiz.total],
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
    labels.push('Kelime Oyunu');
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
function showCheckOptions() {
  closeAllMenus();
  const id = 'win-chk-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');
  
  let html = `<div class="win-window" id="${id}" style="min-width:350px;">`;
  html += `<div class="win-title"><span class="win-title-text">Denetim Opsiyonlar</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body">`;
  html += `<div class="group-box"><legend>Denetim Seçenekleri</legend>`;
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
    html += `<label style="display:block;margin:2px 0;"><input type="checkbox" checked> ${o}</label>`;
  });
  html += `</div>`;
  html += `<div style="margin-top:8px;text-align:right;"><button class="win-btn primary" onclick="closeWindow('${id}')">Tamam</button></div>`;
  html += `</div></div>`;
  
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'options', id: id };
}

// ─── Open Stats ───────────────────────────────────────────────────────────
function openStatsWindow() {
  closeAllMenus();
  openWindow('stats');
}

// ─── Open Quiz (Kelime Oyunu) ─────────────────────────────────────────────
function openQuizWindow() {
  const id = 'win-quiz-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');
  
  let html = `<div class="win-window full" id="${id}">`;
  html += `<div class="win-title"><span class="win-title-text">Kelime Oyunu</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:4px;">`;
  html += `<div class="group-box"><legend>Oyun Kelimeleri</legend>`;
  html += `<label style="display:block;margin:4px 0;"><input type="radio" name="quizSrc" checked> Ana Sözlükten</label>`;
  html += `<label style="display:block;margin:4px 0;"><input type="radio" name="quizSrc"> Kullanıcı Sözlükten</label>`;
  html += `<div style="margin-top:8px;text-align:right;"><button class="win-btn primary" onclick="loadQuizTopics('${id}')">Konuları Göster</button></div>`;
  html += `</div>`;
  html += `<div id="${id}-body"></div>`;
  html += `</div></div>`;
  
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'quiz-topics', id: id };
}

// ─── Show About ───────────────────────────────────────────────────────────
function showAbout() {
  closeAllMenus();
  document.getElementById('aboutDialog').classList.add('open');
}

// ─── Init ─────────────────────────────────────────────────────────────────
openWindow('ing-tr');
</script>
</body>
</html>
"""


# ─── Auto‑reload helper ─────────────────────────────────────────────────────

def start_with_reload():
    import time
    mtime = os.stat(__file__).st_mtime
    pid = os.fork()
    if pid == 0:
        # child → run server
        main()
        sys.exit(0)
    # parent → watch file
    print(f"  🔄 --reload aktif: {__file__} izleniyor (PID={pid})")
    try:
        while True:
            time.sleep(0.8)
            new_mtime = os.stat(__file__).st_mtime
            if new_mtime != mtime:
                mtime = new_mtime
                print("\n  🔄 Değişiklik algılandı, yeniden başlatılıyor…")
                os.kill(pid, 15)  # SIGTERM
                import time as t2
                t2.sleep(0.5)
                pid2 = os.fork()
                if pid2 == 0:
                    main()
                    sys.exit(0)
                pid = pid2
    except KeyboardInterrupt:
        os.kill(pid, 15)
        print("\nSunucu durduruldu.")


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), MoonStarHandler)
    print(f"\n🌙 MoonStar Veri Gezgini çalışıyor:")
    print(f"   http://localhost:{PORT}")
    print(f"\n   Sözlükler: İng→Tr ({len(TRK_DATA)}), Tr→Tr ({len(TUR_DATA)}), EşAnlam ({len(SYN_DATA)})")
    print(f"   Kelime Oyunu: {len(QUIZ_DATA)} kelime, {len([t for t in TOPIC_NAMES if len(t) > 1])} konu")
    print(f"\n   Çıkmak için Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu durduruldu.")
        server.server_close()


if __name__ == "__main__":
    if "--reload" in sys.argv:
        start_with_reload()
    else:
        main()
