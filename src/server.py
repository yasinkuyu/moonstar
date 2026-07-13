#! /usr/bin/python3

# MoonStar Data Explorer — Web UI Server
# Serves all decoded MoonStar data through a browser interface
#
# @yasinkuyu

import os
import sys
import json
import struct
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
        elif path == "/api/rev":
            self.json_response(self.paginate(REV_DATA, params))
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
        results = [e for e in TRK_DATA if q in e["en"].lower() or q in e["tr"].lower()]
        return {"data": results[:100], "total": len(results)}

    def search_tur(self, params):
        q = params.get("q", [""])[0].lower()
        if not q:
            return {"data": [], "total": 0}
        results = [e for e in TUR_DATA if q in e["word"].lower()]
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
            result.append({
                "idx": idx,
                "name": q["topic"] if q["topic"] else f"Topic_{idx}",
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
<title>MoonStar Veri Gezgini</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #222; }
.header { background: #1a237e; color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
.header h1 { font-size: 20px; font-weight: 600; }
.header span { font-size: 13px; opacity: .8; }
.nav { background: #283593; display: flex; padding: 0 24px; gap: 4px; }
.nav a { color: #c5cae9; text-decoration: none; padding: 10px 16px; font-size: 14px; cursor: pointer; border-bottom: 2px solid transparent; }
.nav a:hover { color: #fff; background: rgba(255,255,255,0.1); }
.nav a.active { color: #fff; border-bottom-color: #ffeb3b; }
.content { max-width: 1200px; margin: 0 auto; padding: 24px; }
.tab { display: none; }
.tab.active { display: block; }
.card { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1); padding: 20px; margin-bottom: 20px; }
.card h2 { font-size: 18px; margin-bottom: 12px; color: #1a237e; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { background: #e8eaf6; text-align: left; padding: 8px 12px; font-weight: 600; color: #283593; border-bottom: 2px solid #c5cae9; }
td { padding: 6px 12px; border-bottom: 1px solid #eee; }
tr:hover td { background: #f5f5ff; }
.search-box { display: flex; gap: 8px; margin-bottom: 16px; }
.search-box input { flex: 1; padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.search-box button { padding: 8px 20px; background: #283593; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
.search-box button:hover { background: #1a237e; }
.pagination { display: flex; gap: 8px; align-items: center; justify-content: center; margin-top: 16px; }
.pagination button { padding: 6px 12px; border: 1px solid #ccc; background: #fff; border-radius: 4px; cursor: pointer; font-size: 13px; }
.pagination button:hover { background: #e8eaf6; }
.pagination button:disabled { opacity: .4; cursor: default; }
.pagination span { font-size: 13px; color: #666; }
.flag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.flag-normal { background: #e8f5e9; color: #2e7d32; }
.flag-variant { background: #fff3e0; color: #e65100; }
.topics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.topic-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; cursor: pointer; transition: all .2s; }
.topic-card:hover { border-color: #283593; box-shadow: 0 2px 8px rgba(26,35,126,.15); }
.topic-card h3 { font-size: 15px; color: #283593; }
.topic-card .count { font-size: 13px; color: #666; margin-top: 4px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.stat-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; text-align: center; }
.stat-card .num { font-size: 28px; font-weight: 700; color: #1a237e; }
.stat-card .label { font-size: 13px; color: #666; margin-top: 4px; }
.back-link { display: inline-block; margin-bottom: 12px; color: #283593; cursor: pointer; text-decoration: underline; font-size: 13px; }
.loading { text-align: center; padding: 40px; color: #999; font-size: 14px; }
.error { color: #c62828; padding: 12px; background: #ffebee; border-radius: 4px; }
</style>
</head>
<body>

<div class="header">
  <h1>🌙 MoonStar</h1>
  <span>Türkçe Denetim Editörü — Veri Gezgini</span>
</div>

<div class="nav" id="nav">
  <a class="active" onclick="switchTab('dictionary')">Sözlükler</a>
  <a onclick="switchTab('quiz')">Kelime Oyunu</a>
  <a onclick="switchTab('search')">Arama</a>
  <a onclick="switchTab('stats')">İstatistik</a>
</div>

<div class="content">

<!-- Dictionary Tab -->
<div id="tab-dictionary" class="tab active">
  <div class="card">
    <div style="display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap;">
      <button class="dict-btn active" onclick="switchDict('trk')" style="padding:6px 14px;border:1px solid #ccc;border-radius:4px;cursor:pointer;background:#283593;color:#fff;">İngilizce → Türkçe</button>
      <button class="dict-btn" onclick="switchDict('tur')" style="padding:6px 14px;border:1px solid #ccc;border-radius:4px;cursor:pointer;">Türkçe → Türkçe (Leb Demeden)</button>
      <button class="dict-btn" onclick="switchDict('rev')" style="padding:6px 14px;border:1px solid #ccc;border-radius:4px;cursor:pointer;">Türkçe → İngilizce</button>
      <button class="dict-btn" onclick="switchDict('syn')" style="padding:6px 14px;border:1px solid #ccc;border-radius:4px;cursor:pointer;">Eş Anlamlılar</button>
    </div>
    <div id="dict-content"><div class="loading">Yükleniyor...</div></div>
  </div>
</div>

<!-- Quiz Tab -->
<div id="tab-quiz" class="tab">
  <div id="quiz-topics-view">
    <div class="card">
      <h2>Kelime Oyunu — Konular</h2>
      <p style="color:#666;font-size:13px;margin-bottom:16px;">Her konudaki İngilizce→Türkçe kelime çiftlerini görüntülemek için tıklayın.</p>
      <div id="quiz-topics" class="topics-grid"><div class="loading">Yükleniyor...</div></div>
    </div>
  </div>
  <div id="quiz-detail-view" style="display:none;">
    <div class="card">
      <a class="back-link" onclick="showQuizTopics()">← Konulara Dön</a>
      <h2 id="quiz-topic-title"></h2>
      <div class="search-box">
        <input type="text" id="quiz-search-input" placeholder="Kelime ara..." onkeyup="if(event.key==='Enter')searchQuiz()">
        <button onclick="searchQuiz()">Ara</button>
      </div>
      <div id="quiz-content"><div class="loading">Yükleniyor...</div></div>
    </div>
  </div>
</div>

<!-- Search Tab -->
<div id="tab-search" class="tab">
  <div class="card">
    <h2>Tüm Sözlüklerde Ara</h2>
    <div class="search-box">
      <input type="text" id="global-search-input" placeholder="Kelime girin..." onkeyup="if(event.key==='Enter')globalSearch()">
      <button onclick="globalSearch()">Ara</button>
    </div>
    <div id="search-results"></div>
  </div>
</div>

<!-- Stats Tab -->
<div id="tab-stats" class="tab">
  <div class="card">
    <h2>Veri İstatistikleri</h2>
    <div id="stats-content"><div class="loading">Yükleniyor...</div></div>
  </div>
</div>

</div>

<script>
// ─── State ────────────────────────────────────────────────────────────────
let state = {
  dictType: 'trk',
  dictPage: 1,
  quizTopic: null,
  quizPage: 1,
  allTopics: [],
  topicNames: [],
};

// ─── Navigation ────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector(`.nav a:nth-child(${['dictionary','quiz','search','stats'].indexOf(name)+1})`).classList.add('active');
  if (name === 'dictionary') loadDict();
  if (name === 'quiz') showQuizTopics();
  if (name === 'stats') loadStats();
}

// ─── Dictionary ────────────────────────────────────────────────────────────
function switchDict(type) {
  state.dictType = type;
  state.dictPage = 1;
  document.querySelectorAll('.dict-btn').forEach(b => {b.style.background='#fff';b.style.color='#222';});
  event.target.style.background='#283593';
  event.target.style.color='#fff';
  loadDict();
}

function loadDict() {
  const map = {trk:'/api/trk', tur:'/api/tur', rev:'/api/rev', syn:'/api/syn'};
    const headers = {
    trk: ['İngilizce', 'Türkçe Karşılık'],
    tur: ['Kelime'],
    rev: ['Türkçe', 'İngilizce Karşılık'],
    syn: ['Kelime', 'Eş Anlamlılar'],
  };
  const keys = {
    trk: ['en','tr'],
    tur: ['word'],
    rev: ['tr','en'],
    syn: ['word','synonyms'],
  };

  fetch(map[state.dictType]+`?page=${state.dictPage}&per_page=50`)
    .then(r=>r.json())
    .then(d=>{
      let cols = headers[state.dictType].length;
      let html = `<table><tr>${headers[state.dictType].map(h=>`<th>${h}</th>`).join('')}</tr>`;
      d.data.forEach(e => {
        let vals = keys[state.dictType].map(k => `<td>${k === 'word' || k === 'en' ? '<b>'+e[k]+'</b>' : e[k]}</td>`).join('');
        html += `<tr>${vals}</tr>`;
      });
      html += '</table>';
      html += `<div class="pagination">`;
      html += `<button ${d.page<=1?'disabled':''} onclick="state.dictPage=1;loadDict()">«</button>`;
      html += `<button ${d.page<=1?'disabled':''} onclick="state.dictPage--;loadDict()">‹</button>`;
      html += `<span>Sayfa ${d.page}/${d.total_pages} (${d.total} kayıt)</span>`;
      html += `<button ${d.page>=d.total_pages?'disabled':''} onclick="state.dictPage++;loadDict()">›</button>`;
      html += `<button ${d.page>=d.total_pages?'disabled':''} onclick="state.dictPage=${d.total_pages};loadDict()">»</button>`;
      html += '</div>';
      document.getElementById('dict-content').innerHTML = html;
    });
}

// ─── Quiz ──────────────────────────────────────────────────────────────────
function showQuizTopics() {
  document.getElementById('quiz-topics-view').style.display = 'block';
  document.getElementById('quiz-detail-view').style.display = 'none';
  fetch('/api/quiz/topics').then(r=>r.json()).then(d=>{
    state.allTopics = d.topics;
    let html = '';
    d.topics.forEach(t => {
      html += `<div class="topic-card" onclick="showQuizTopic(${t.idx})">
        <h3>${t.name}</h3>
        <div class="count">${t.count} kelime</div>
      </div>`;
    });
    document.getElementById('quiz-topics').innerHTML = html;
  });
}

function showQuizTopic(idx) {
  state.quizTopic = idx;
  state.quizPage = 1;
  document.getElementById('quiz-topics-view').style.display = 'none';
  document.getElementById('quiz-detail-view').style.display = 'block';
  const topic = state.allTopics.find(t => t.idx === idx);
  document.getElementById('quiz-topic-title').textContent = topic ? topic.name : 'Konu ' + idx;
  loadQuizEntries();
}

function loadQuizEntries() {
  fetch(`/api/quiz?topic=${state.quizTopic}&page=${state.quizPage}&per_page=50`)
    .then(r=>r.json()).then(d=>{
      let html = `<table><tr><th>#</th><th>İngilizce</th><th>Türkçe</th><th>Tip</th></tr>`;
      d.data.forEach(e => {
        const flag = e.variant ? '<span class="flag flag-variant">Varyant</span>' : '<span class="flag flag-normal">Normal</span>';
        html += `<tr><td>${e.slot}</td><td><b>${e.en}</b></td><td>${e.tr||'-'}</td><td>${flag}</td></tr>`;
      });
      html += '</table>';
      html += `<div class="pagination">`;
      html += `<button ${d.page<=1?'disabled':''} onclick="state.quizPage=1;loadQuizEntries()">«</button>`;
      html += `<button ${d.page<=1?'disabled':''} onclick="state.quizPage--;loadQuizEntries()">‹</button>`;
      html += `<span>Sayfa ${d.page}/${d.total_pages} (${d.total} kayıt)</span>`;
      html += `<button ${d.page>=d.total_pages?'disabled':''} onclick="state.quizPage++;loadQuizEntries()">›</button>`;
      html += `<button ${d.page>=d.total_pages?'disabled':''} onclick="state.quizPage=${d.total_pages};loadQuizEntries()">»</button>`;
      html += '</div>';
      document.getElementById('quiz-content').innerHTML = html;
    });
}

function searchQuiz() {
  const q = document.getElementById('quiz-search-input').value;
  if (!q) { loadQuizEntries(); return; }
  fetch('/api/quiz/search?q='+encodeURIComponent(q))
    .then(r=>r.json()).then(d=>{
      let html = `<p style="margin-bottom:8px;color:#666;">"${q}" için ${d.total} sonuç</p><table><tr><th>Konu</th><th>İngilizce</th><th>Türkçe</th></tr>`;
      d.data.forEach(e => {
        html += `<tr><td>${e.topic}</td><td><b>${e.en}</b></td><td>${e.tr||'-'}</td></tr>`;
      });
      html += '</table>';
      document.getElementById('quiz-content').innerHTML = html;
    });
}

// ─── Global Search ────────────────────────────────────────────────────────
function globalSearch() {
  const q = document.getElementById('global-search-input').value;
  if (!q) { document.getElementById('search-results').innerHTML = ''; return; }
  document.getElementById('search-results').innerHTML = '<div class="loading">Aranıyor...</div>';

  Promise.all([
    fetch('/api/trk/search?q='+encodeURIComponent(q)).then(r=>r.json()),
    fetch('/api/tur/search?q='+encodeURIComponent(q)).then(r=>r.json()),
    fetch('/api/quiz/search?q='+encodeURIComponent(q)).then(r=>r.json()),
  ]).then(([trk, tur, quiz]) => {
    let html = `<p style="margin-bottom:12px;color:#666;">"${q}" için toplam ${trk.total + tur.total + quiz.total} sonuç</p>`;

    if (trk.total > 0) {
      html += `<h3 style="margin:12px 0 8px;">İngilizce → Türkçe (${trk.total})</h3><table><tr><th>İngilizce</th><th>Türkçe</th></tr>`;
      trk.data.forEach(e => html += `<tr><td><b>${e.en}</b></td><td>${e.tr}</td></tr>`);
      html += '</table>';
    }

    if (tur.total > 0) {
      html += `<h3 style="margin:12px 0 8px;">Türkçe → Türkçe (${tur.total})</h3><table><tr><th>Kelime</th><th>Anlam</th></tr>`;
      tur.data.forEach(e => html += `<tr><td><b>${e.word}</b></td><td>${e.def}</td></tr>`);
      html += '</table>';
    }

    if (quiz.total > 0) {
      html += `<h3 style="margin:12px 0 8px;">Kelime Oyunu (${quiz.total})</h3><table><tr><th>Konu</th><th>İngilizce</th><th>Türkçe</th></tr>`;
      quiz.data.forEach(e => html += `<tr><td>${e.topic}</td><td><b>${e.en}</b></td><td>${e.tr||'-'}</td></tr>`);
      html += '</table>';
    }

    if (trk.total + tur.total + quiz.total === 0) {
      html += '<div class="error">Sonuç bulunamadı.</div>';
    }

    document.getElementById('search-results').innerHTML = html;
  });
}

// ─── Stats ────────────────────────────────────────────────────────────────
function loadStats() {
  fetch('/api/stats').then(r=>r.json()).then(d=>{
    let html = '<div class="stats-grid">';
    const items = [
      {num: d.trk.total, label: 'İng→Tr Sözlük'},
      {num: d.tur.total, label: 'Tr→Tr Leb Demeden'},
      {num: d.syn.total, label: 'Eş Anlamlılar'},
      {num: d.rev.total, label: 'Tr→İng Sözlük'},
      {num: d.quiz.total, label: 'Quiz (Kelime Oyunu)'},
    ];
    items.forEach(i => {
      html += `<div class="stat-card"><div class="num">${i.num.toLocaleString()}</div><div class="label">${i.label}</div></div>`;
    });
    html += '</div>';

    html += '<h3 style="margin:24px 0 12px;color:#1a237e;">Konulara Göre Quiz Dağılımı</h3>';
    html += '<table><tr><th>Konu</th><th>Kelime Sayısı</th></tr>';
    d.topics.forEach(t => {
      html += `<tr><td>${t.name}</td><td>${t.count}</td></tr>`;
    });
    html += '</table>';

    document.getElementById('stats-content').innerHTML = html;
  });
}

// ─── Init ──────────────────────────────────────────────────────────────────
loadDict();
</script>
</body>
</html>
"""


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
    main()
