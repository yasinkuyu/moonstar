#! /usr/bin/python3

# MoonStar Data Explorer — Web UI Server
# Serves all decoded MoonStar data through a browser interface
#
# @yasinkuyu

import os
import sys
import json
import time
import signal
import http.server
import urllib.parse

try:
    from spell_check import TurkishSpellChecker, text_check_response
    from core.constants import TOPIC_NAMES as QUIZ_TOPIC_NAMES
    from core.text import tr_lower, turkish_sort_key
except ImportError:
    from src.spell_check import TurkishSpellChecker, text_check_response
    from src.core.constants import TOPIC_NAMES as QUIZ_TOPIC_NAMES
    from src.core.text import tr_lower, turkish_sort_key

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")

def normalize_tr(s):
    """Normalize Turkish characters to ASCII for search matching."""
    tr_to_ascii = str.maketrans('ışçöüğîâû', 'iscougiau')
    return tr_lower(s).translate(tr_to_ascii)


PORT = int(os.environ.get("MOONSTAR_PORT", "8080"))
# Bind to loopback by default; set MOONSTAR_HOST=0.0.0.0 to expose on the network
HOST = os.environ.get("MOONSTAR_HOST", "127.0.0.1")


# ─── Data Loaders ───────────────────────────────────────────────────────────

def load_trk():
    """
    İngilizce Türkçe Sözlük from MTU.TRK (engine.trk, port of FUN_1010_397b), in the EXE's
    order. `key` is the lowercase text the window matches, `lines` the "Türkçe Karşılıklar" list.
    """
    try:
        from engine.trk import TrkDictionary
    except ImportError:
        from src.engine.trk import TrkDictionary
    entries = TrkDictionary().entries()
    for e in entries:
        e["tr"] = " ".join(line.strip() for line in e["lines"])
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


def load_synonyms():
    """
    Turkish thesaurus entries (Türkçe Eş Anlamlı Sözcükler) decoded from MTU.TES
    by engine.thesaurus, an exact port of the MTU.EXE thesaurus routines.
    """
    try:
        from engine.thesaurus import load_all_synonyms
    except ImportError:
        from src.engine.thesaurus import load_all_synonyms

    return load_all_synonyms()  # already in the EXE's sort order (FUN_1010_2e13)


def load_ing():
    """
    Türkçe İngilizce Sözlük and topic-tagged word game entries from MTU.ING,
    decoded by engine.ing (exact port of the MTU.EXE routine FUN_1010_3114).
    Meanings keep the EXE label text (" 1.eye", "   look") and are joined by newlines.
    """
    try:
        from engine.ing import IngDictionary, topic_index
    except ImportError:
        from src.engine.ing import IngDictionary, topic_index

    rev, quizzes = [], []
    for e in IngDictionary().all_entries():
        rev.append({"tr": e["tr"], "en": "\n".join(l["text"] for l in e["labels"])})
        for l in e["labels"]:
            topic_idx = topic_index(l["topic"])
            if topic_idx is not None:
                quizzes.append({
                    "en": l["text"].strip().lstrip("0123456789.").strip(),
                    "tr": e["tr"],
                    "topic": QUIZ_TOPIC_NAMES[topic_idx],
                    "topic_idx": topic_idx,
                })
    return rev, quizzes


# ─── Load all data ──────────────────────────────────────────────────────────

print("Loading data...")
TRK_DATA = load_trk()
TUR_DATA = load_tur()
SYN_DATA = load_synonyms()
REV_DATA, QUIZ_DATA = load_ing()

CHECKER = TurkishSpellChecker()


def load_help():
    """MTU.HLP (WinHelp 3.0) decoded by mtu_hlp."""
    try:
        from mtu_hlp import help_json, parse_hlp
    except ImportError:
        from src.mtu_hlp import help_json, parse_hlp
    path = os.path.join(DATA_DIR, "MTU.HLP")
    return help_json(parse_hlp(path)) if os.path.exists(path) else {"topics": [], "index_topic": None}


HELP_DATA = load_help()


def load_game_words():
    """Kelime Oyunu word pools: "Ana Sözlükten" (MTU.TUR) and "Kullanıcı Sözlükten" (MTU.SOZ)."""
    try:
        from engine.game import MAIN, USER, game_words
    except ImportError:
        from src.engine.game import MAIN, USER, game_words
    lexicon = CHECKER.lexicon
    return {"main": game_words(lexicon, source=MAIN),
            "user": game_words(lexicon, CHECKER.speller.user, USER)}


GAME_WORDS = load_game_words()

print(f"  TRK: {len(TRK_DATA)} entries")
print(f"  TUR: {len(TUR_DATA)} entries")
print(f"  SYN: {len(SYN_DATA)} entries")
print(f"  REV: {len(REV_DATA)} entries")
print(f"  QUIZ: {len(QUIZ_DATA)} entries")
print(f"  Topics: {len(QUIZ_TOPIC_NAMES)}")


# POST endpoints answered by spell_check.text_check_response
CHECK_PATHS = ("/api/check/text", "/api/check/next", "/api/check/control", "/api/check/start", "/api/check/complete")


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
            elif path == "/api/help":
                self.json_response(HELP_DATA)
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
        relative = urllib.parse.unquote(path[len("/assets/"):])
        assets_root = os.path.realpath(self.ASSETS_DIR)
        filepath = os.path.realpath(os.path.join(assets_root, relative))
        try:
            inside = os.path.commonpath([assets_root, filepath]) == assets_root
        except ValueError:
            inside = False
        if not inside:
            self.send_error(403)
            return
        if not os.path.isfile(filepath):
            self.send_error(404)
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
        except OSError:
            self.send_error(404)

    def serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in CHECK_PATHS:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 4 * 1024 * 1024:
            self.send_error(413 if length else 400)
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        if not isinstance(body, dict):
            body = {}
        self.json_response(text_check_response(CHECKER, parsed.path, body))

    def json_response(self, data):
        try:
            json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(json_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            # Use connection.sendall for reliable delivery
            self.connection.sendall(json_bytes)
        except Exception as e:
            import sys
            print(f"json_response error: {e}", file=sys.stderr)
            try:
                self.send_error(500, f"JSON response error: {e}")
            except:
                pass

    @staticmethod
    def int_param(params, name, default, lo=None, hi=None):
        try:
            value = int(params.get(name, [default])[0])
        except (TypeError, ValueError):
            value = default
        if lo is not None and value < lo:
            value = lo
        if hi is not None and value > hi:
            value = hi
        return value

    def paginate(self, data, params):
        page = self.int_param(params, "page", 1, lo=1)
        per_page = self.int_param(params, "per_page", 50, lo=1, hi=100000)
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
            "total": CHECKER.lexicon.word_count,
            "suffix_count": CHECKER.lexicon.suffix_count,
        }
        return result

    def get_stats(self):
        # Topic distribution
        topic_stats = [{"name": t["name"], "count": t["count"]} for t in self.get_quiz_topics()["topics"]]

        return {
            "trk": {"total": len(TRK_DATA)},
            "tur": {"total": len(TUR_DATA)},
            "syn": {"total": len(SYN_DATA)},
            "rev": {"total": len(REV_DATA)},
            "quiz": {"total": len(QUIZ_DATA)},
            "topics": topic_stats,
            "topic_names": QUIZ_TOPIC_NAMES,
        }

    def get_quiz_topics(self):
        topic_counts = {}
        for q in QUIZ_DATA:
            topic_counts[q["topic_idx"]] = topic_counts.get(q["topic_idx"], 0) + 1
        return {"topics": [
            {"idx": idx, "name": QUIZ_TOPIC_NAMES[idx], "count": topic_counts[idx]}
            for idx in sorted(topic_counts)
        ]}

    def get_quiz_entries(self, params):
        topic = self.int_param(params, "topic", 0)
        return self.paginate([q for q in QUIZ_DATA if q["topic_idx"] == topic], params)

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
        # MTU.EXE FUN_1010_4b79: a random playable word of the chosen dictionary, no hint
        import random
        source = params.get("source", ["main"])[0]
        pool = GAME_WORDS.get(source, GAME_WORDS["main"])
        if not pool:
            return {"error": "Kelime bulunamadı"}
        return {"word": random.choice(pool)}


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
.win-input, .win-window input[type="text"], .win-window textarea {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  padding: 5px 6px;
  font-size: 14px;
  font-family: inherit;
  font-weight: bold;
  outline: none;
  background: #fff;
}

/* Win16 listbox */
.win-list {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  background: #fff;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
  min-width: 0;
  box-sizing: border-box;
}

/* Dictionary split pane */
.dict-word {
  padding: 2px 4px;
  cursor: pointer;
  border-bottom: none;
  font-size: 14px;
  font-weight: bold;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  display: block;
}
.dict-word:hover { background: #e8e8ff; }

.dict-sel { background: #000080; color: #fff; }
.exe-dlg { padding: 6px 14px 10px; background: #c0c0c0; color: #000; font-family: 'MS Sans Serif', Tahoma, Arial, sans-serif; font-size: 12px; display: flex; flex-direction: column; gap: 8px; }
.exe-rect3d { position: relative; border: 1px solid #808080; box-shadow: 1px 1px 0 #fff, inset 1px 1px 0 #fff; padding: 9px 8px; }
.exe-group { padding-top: 14px; }
.exe-group-label { position: absolute; top: -8px; left: 8px; background: #c0c0c0; padding: 0 3px; }
.exe-static { min-height: 16px; font-weight: bold; white-space: pre; overflow: hidden; text-overflow: ellipsis; }
.exe-btn-row { display: flex; justify-content: space-around; }
.exe-bmp-btn { width: 63px; height: 39px; border: 0; padding: 0; cursor: pointer; background: var(--up) center / 63px 39px no-repeat; image-rendering: pixelated; }
.exe-bmp-btn:active { background-image: var(--down); }
.help-topic { flex: 1; overflow-y: auto; background: #fff; border: 1px solid #808080; padding: 6px 10px; font-family: Arial, Helvetica, sans-serif; font-size: 13px; color: #000; }
.help-topic p { margin: 0; min-height: 1em; white-space: pre-wrap; tab-size: 4; }
.help-link { color: #008000; text-decoration: underline; cursor: pointer; }
.dict-sel:hover { background: #000080; }
.dict-meaning {
  padding: 2px 4px;
  border-bottom: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  align-items: baseline;
  gap: 5px;
  color: #000;
  user-select: none;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}
.dict-meaning:hover { background: #e8e8ff; }
.dict-meaning .row-num { flex-shrink: 0; min-width: auto; color: inherit; font-weight: inherit; }
.dict-meaning .meaning-content {
  flex: 1;
  min-width: 0;
  color: inherit;
  font-weight: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meaning-sel { background: #000080; color: #fff; }
.meaning-sel .row-num { color: #fff; }
.meaning-sel .meaning-content { color: #fff; }
.meaning-sel:hover { background: #000080; }

/* 3D group box */
.group-box {
  border: 2px solid;
  border-color: #808080 #fff #fff #808080;
  padding: 16px 6px 6px;
  margin-top: 8px;
  position: relative;
  box-sizing: border-box;
  overflow: visible;
}
.group-box legend {
  position: absolute;
  top: -10px;
  left: 8px;
  background: #c0c0c0;
  padding: 0 4px;
  font-size: 14px;
  font-weight: bold;
  font-family: 'MS Sans Serif', Tahoma, Arial, sans-serif;
  color: #000;
  text-shadow: 0.5px 0.5px #fff;
  white-space: nowrap;
  z-index: 5;
  line-height: 1;
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

/* ─── Main Menu Mini Mode ────────────────────────────────────────────────── */
.welcome-mini {
  width: auto !important;
  min-width: 334px !important;
  max-width: 340px !important;
  height: auto !important;
  box-sizing: border-box !important;
}
.welcome-mini .welcome-body {
  padding: 4px !important;
  background: #c0c0c0 !important;
  display: block !important;
}
.welcome-mini .welcome-panel {
  border: none !important;
  background: transparent !important;
  padding: 0 !important;
  margin: 0 !important;
  display: block !important;
  box-sizing: border-box !important;
}
.welcome-mini .welcome-grid {
  display: flex !important;
  flex-direction: row !important;
  gap: 4px !important;
  justify-content: center !important;
  align-items: center !important;
  grid-template-columns: none !important;
  grid-template-rows: none !important;
  width: auto !important;
}
.welcome-mini .btn-sprite-btn_denetim,
.welcome-mini .btn-sprite-btn_klavye,
.welcome-mini .btn-sprite-btn_adam_asma,
.welcome-mini .welcome-sep,
.welcome-mini .welcome-banner {
  display: none !important;
}
.welcome-mini .btn-sprite-btn_en_tr {
  display: inline-block !important;
  order: 1 !important;
}
.welcome-mini .btn-sprite-btn_tr_en {
  display: inline-block !important;
  order: 2 !important;
}
.welcome-mini .btn-sprite-btn_esanlam {
  display: inline-block !important;
  order: 3 !important;
}

/* ─── CSS Sprites System ─────────────────────────────────────────────────── */
.sprite-btn {
  background-image: url('/assets/buttons_sprite.png?v=1');
  background-repeat: no-repeat;
  image-rendering: pixelated;
  display: inline-block;
  cursor: pointer;
  box-sizing: border-box;
  user-select: none;
  border: none;
  outline: none;
  padding: 0;
  margin: 0;
}

/* Toolbar Buttons (104x50) */
.btn-sprite-toolbar { width: 104px; height: 50px; }
.btn-sprite-btn_denetim { background-position: 0px 0px; }
.btn-sprite-btn_denetim:active { background-position: 0px -50px; }

.btn-sprite-btn_tr_en { background-position: -104px 0px; }
.btn-sprite-btn_tr_en:active { background-position: -104px -50px; }

.btn-sprite-btn_esanlam { background-position: -208px 0px; }
.btn-sprite-btn_esanlam:active { background-position: -208px -50px; }

.btn-sprite-btn_klavye { background-position: -312px 0px; }
.btn-sprite-btn_klavye:active { background-position: -312px -50px; }

.btn-sprite-btn_en_tr { background-position: -416px 0px; }
.btn-sprite-btn_en_tr:active { background-position: -416px -50px; }

.btn-sprite-btn_adam_asma { background-position: -520px 0px; }
.btn-sprite-btn_adam_asma:active { background-position: -520px -50px; }

/* Dialog Buttons (63x39) */
.btn-sprite-dialog { width: 63px; height: 39px; flex-shrink: 0; }
.btn-sprite-tamam { background-position: 0px -100px; }
.btn-sprite-tamam:active { background-position: 0px -139px; }

.btn-sprite-iptal { background-position: -63px -100px; }
.btn-sprite-iptal:active { background-position: -63px -139px; }

.btn-sprite-edit { background-position: -126px -100px; }
.btn-sprite-edit:active { background-position: -126px -139px; }

.btn-sprite-sozluk { background-position: -189px -100px; }
.btn-sprite-sozluk:active { filter: brightness(0.92); }

.btn-sprite-basla { background-position: -252px -100px; }
.btn-sprite-basla:active { filter: brightness(0.92); }

.btn-sprite-degistir-d { background-position: -315px -100px; cursor: not-allowed !important; opacity: 0.6; pointer-events: none; }

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
  width: 326px; padding: 4px 6px; gap: 6px;
  background: #c0c0c0; box-sizing: border-box;
  margin: 0 auto; user-select: none;
}
.hm-upper {
  display: flex; flex-direction: row; gap: 8px;
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
.hm-key-sprite {
  width: 25px; height: 25px;
  background-image: url('/assets/keys_sprite.png?v=1');
  background-repeat: no-repeat;
  image-rendering: pixelated;
  display: block;
  cursor: pointer;
  box-sizing: border-box;
}
.hm-key-sprite.used {
  cursor: default;
  opacity: 0.65;
  filter: contrast(0.85);
  outline: 1px dotted #808080;
  outline-offset: -2px;
}
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
.hm-gallows-sprite {
  width: 52px; height: 76px;
  background-image: url('/assets/gallows_sprite.png?v=1');
  background-repeat: no-repeat;
  image-rendering: pixelated;
  display: block;
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
  color: #000;
  font-family: 'MS Sans Serif', 'Microsoft Sans Serif', Tahoma, 'Arial Black', sans-serif;
  display: flex; align-items: center; justify-content: center;
  white-space: nowrap; overflow: hidden;
  margin-top: auto;
  flex-shrink: 0;
}
.hm-word-text {
  display: inline-block;
  white-space: nowrap;
  font-weight: 800;
  text-transform: uppercase;
}
.hm-btns {
  display: flex; flex-direction: row; gap: 8px;
  line-height: 0; flex-shrink: 0;
  justify-content: center;
  width: 250px;
  margin-top: 8px;
  margin-bottom: 0;
}
.sprite-btn.disabled {
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
  background: transparent;
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
      <!-- Menu Bar (Minimal Desktop MDI: Yardım & Zoom) -->
      <div class="menu-bar" id="menuBar">
        <div class="menu-items-group">
          <div class="menu-item" onclick="toggleMenu('mainHelpMenu', event)" onmouseenter="onMenuItemHover('mainHelpMenu', event)">Yardım</div>
        </div>
        <div class="retro-zoom-controls">
          <span class="retro-zoom-label">🔍 Ölçek:</span>
          <button class="retro-zoom-btn active" onclick="setUiScale(1.0)" id="zoomBtn-1_0" title="%100 Orijinal">1x</button>
          <button class="retro-zoom-btn" onclick="setUiScale(1.25)" id="zoomBtn-1_25" title="%125 Orta">1.25x</button>
          <button class="retro-zoom-btn" onclick="setUiScale(1.5)" id="zoomBtn-1_5" title="%150 Geniş">1.5x</button>
          <button class="retro-zoom-btn" onclick="setUiScale(2.0)" id="zoomBtn-2_0" title="%200 Büyük">2x</button>
        </div>
      </div>

      <!-- Main Desktop Dropdown Menus -->
      <div class="dropdown" id="mainHelpMenu">
        <div class="dropdown-item" onclick="openHelp()">İçerik (F1)</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="showChangelog()">Change Log</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="showAbout()">MoonStar Hakkında</div>
      </div>

      <!-- Editor Child Window Dropdown Menus (Exact 0x5C200 MTU.EXE Resources) -->
      <div class="dropdown" id="edtFileMenu">
        <div class="dropdown-item" onclick="editorNew('win-edt')">Yeni Dosya</div>
        <div class="dropdown-item" onclick="editorOpenDemo('win-edt')">Dosya Açma (TEST)</div>
        <div class="dropdown-item" onclick="editorUploadFile('win-edt')">Dosya Aç...</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorSave('win-edt')">Dosya Kaydetme <span style="float:right;color:#666;font-size:11px;margin-left:12px;">Alt+F8</span></div>
        <div class="dropdown-item" onclick="editorSaveAs('win-edt')">Başka İsimle Kaydet...</div>
        <div class="dropdown-item" onclick="editorMergeFile('win-edt')">Dosya Birleştirme...</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="closeWindow('win-edt')">Editör Çıkışı</div>
      </div>
      <div class="dropdown" id="edtEditMenu">
        <div class="dropdown-item" onclick="editorUndo('win-edt')">İptal et <span style="float:right;color:#666;font-size:11px;margin-left:12px;">^Z</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorCut('win-edt')">Kes <span style="float:right;color:#666;font-size:11px;margin-left:12px;">^X</span></div>
        <div class="dropdown-item" onclick="editorCopy('win-edt')">Kopyala <span style="float:right;color:#666;font-size:11px;margin-left:12px;">^C</span></div>
        <div class="dropdown-item" onclick="editorPaste('win-edt')">Yapıştır <span style="float:right;color:#666;font-size:11px;margin-left:12px;">^V</span></div>
        <div class="dropdown-item" onclick="editorSave('win-edt')">Diske kaydet</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorUppercase('win-edt')">Büyük harf <span style="float:right;color:#666;font-size:11px;margin-left:12px;">^Q</span></div>
        <div class="dropdown-item" onclick="editorLowercase('win-edt')">Küçük harf <span style="float:right;color:#666;font-size:11px;margin-left:12px;">^W</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorSingleParagraph('win-edt')">Tek paragraf yap</div>
        <div class="dropdown-item" onclick="editorSortParagraphs('win-edt')">Paragraf sıralama</div>
      </div>
      <div class="dropdown" id="edtFindMenu">
        <div class="dropdown-item" onclick="showFindDialog()">Al ve bul <span style="float:right;color:#666;font-size:11px;margin-left:12px;">Alt+F3</span></div>
        <div class="dropdown-item" onclick="editorShowFind('win-edt')">Bul <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F3</span></div>
        <div class="dropdown-item" onclick="editorShowReplace('win-edt')">Değiştir <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F4</span></div>
      </div>
      <div class="dropdown" id="edtTextMenu">
        <div class="dropdown-item" onclick="editorSpellCheck('win-edt')">Denetle <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F5</span></div>
        <div class="dropdown-item" onclick="editorDictCheck('win-edt')">Sözlük kontrol <span style="float:right;color:#666;font-size:11px;margin-left:12px;">Shift+F5</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="showCheckOptions()">Denetim Opsiyonlar...</div>
        <div class="dropdown-item" onclick="editorShowUserDict('win-edt')">Kullanıcı sözlük...</div>
        <div class="dropdown-item" onclick="winAlert('Kontrol sözlüğü (KONTROL.SOZ) hazır.')">Kontrol sözlük...</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorLookupTur('win-edt')">Leb demeden (Türkçe) <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F6</span></div>
        <div class="dropdown-item" onclick="editorLookupEld('win-edt')">Leb demeden (İngilizce) <span style="float:right;color:#666;font-size:11px;margin-left:12px;">Shift+F6</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorLookupSyn('win-edt')">Eş Anlamlı kelimeler <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F7</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorLookupRev('win-edt')">Türkçe -> İngilizce <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F8</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorLookupTrk('win-edt')">İngilizce -> Türkçe <span style="float:right;color:#666;font-size:11px;margin-left:12px;">Shift+F8</span></div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="editorShowStats('win-edt')">Metin İstatistik <span style="float:right;color:#666;font-size:11px;margin-left:12px;">F9</span></div>
      </div>
      <div class="dropdown" id="edtOptsMenu">
        <div class="dropdown-item" onclick="openCharacterList('win-kbd-select')">Karakter Listesi...</div>
        <div class="dropdown-item" onclick="showKeyboardModule()">Klavye Seçimi...</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="winAlert('MoonStar Türkçe Dil Denetim ve Editör Sistemi v4.0')">Genel tanımlar...</div>
      </div>
      <div class="dropdown" id="edtHelpMenu">
        <div class="dropdown-item" onclick="openHelp()">İçerik (F1)</div>
        <div class="dropdown-sep"></div>
        <div class="dropdown-item" onclick="showChangelog()">Change Log</div>
        <div class="dropdown-sep"></div>
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
      <span id="statusText"></span>
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
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="closeDialog('aboutDialog')" title="Tamam"></div>
      </div>
    </div>
  </div>
</div>

<!-- Changelog Dialog -->
<div class="dialog-overlay" id="changelogDialog">
  <div class="win-window" style="width:480px;height:430px;display:flex;flex-direction:column;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar - Change Log</span>
      <div class="win-title-btns"><button onclick="closeDialog('changelogDialog')">✕</button></div>
    </div>
    <div class="win-body" style="padding:10px;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;gap:8px;box-sizing:border-box;">
      <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;padding:12px 6px 6px;margin:0;"><legend>Sürüm Notları</legend>
        <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;padding:10px 12px;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;font-size:12px;line-height:1.6;color:#000;">
          <div style="font-size:13px;font-weight:bold;color:#000080;border-bottom:1px solid #000080;padding-bottom:2px;margin-bottom:6px;">
            v4.0 (Modern Web Sürümü)
          </div>
          <ul style="margin:0 0 12px 0;padding-left:18px;">
            <li><strong>Kelime Oyunu:</strong> MTU.ING konu etiketli kelimeleri (32 konu), retro ses efektleri ve 10 aşamalı darağacı.</li>
            <li><strong>Türkçe Q & F Sanal Klavye:</strong> Özel karakter seçimi, CP1254 karakter tablosu ve editöre aktarma desteği.</li>
            <li><strong>Sözlük Motoru:</strong>
              <div style="margin-left:8px;font-size:11px;color:#333;">
                • İngilizce ➔ Türkçe (17.988 kelime)<br>
                • Türkçe ➔ İngilizce (24.042 madde)<br>
                • Türkçe Eş Anlamlılar (13.657 kelime)<br>
                • Türkçe Leb Demeden (26.775 kelime)
              </div>
            </li>
            <li><strong>Türkçe Denetim Editörü:</strong> Canlı imla denetimi, sözlük kontrol raporu, kullanıcı sözlüğü yönetimi ve metin istatistikleri.</li>
            <li><strong>Windows 3.1 UX:</strong> Çoklu pencere sürükleme, derinlik odak yönetimi ve orijinal Win16 menü yapısı.</li>
          </ul>

          <div style="font-size:13px;font-weight:bold;color:#800000;border-bottom:1px solid #800000;padding-bottom:2px;margin-bottom:6px;">
            v3.1 (Orijinal Win16 Sürümü - 1994)
          </div>
          <ul style="margin:0 0 12px 0;padding-left:18px;">
            <li>Orijinal Windows 3.1 16-bit sürümü (Borland C++).</li>
            <li>Türkçe Denetim Editörü, morfolojik analiz ve heceleme motoru.</li>
            <li>İHLAS Bilgi İşlem ve Ticaret A.Ş. dağıtımı.</li>
          </ul>

          <div style="font-size:13px;font-weight:bold;color:#008000;border-bottom:1px solid #008000;padding-bottom:2px;margin-bottom:6px;">
            Credits
          </div>
          <ul style="margin:0 0 8px 0;padding-left:18px;">
            <li><a href="https://github.com/erengy" target="_blank" style="color:#000080;text-decoration:underline;">https://github.com/erengy</a></li>
            <li><a href="https://github.com/yasinkuyu" target="_blank" style="color:#000080;text-decoration:underline;">https://github.com/yasinkuyu</a></li>
          </ul>

          <div style="font-style:italic;color:#333;margin-top:6px;padding-top:6px;border-top:1px dashed #808080;">
            Müjdat Özalp anısına.
          </div>
        </div>
      </div>
      <div style="display:flex;justify-content:center;margin-top:2px;">
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="closeDialog('changelogDialog')" title="Tamam"></div>
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
        <label><input type="radio" name="findType" value="all" checked onclick="document.getElementById('findInput').placeholder='Kelime girin...'"> Tüm sözlükler</label><br>
        <label><input type="radio" name="findType" value="trk" onclick="document.getElementById('findInput').placeholder='İngilizce kelime girin...'"> İngilizce → Türkçe</label><br>
        <label><input type="radio" name="findType" value="tur" onclick="document.getElementById('findInput').placeholder='Türkçe kelime girin...'"> Türkçe → Türkçe</label><br>
        <label><input type="radio" name="findType" value="quiz" onclick="document.getElementById('findInput').placeholder='Konu veya kelime...'"> Adam Asma</label>
      </div>
      <div style="margin-top:8px;text-align:right;">
        <button class="win-btn primary" onclick="doFind()">Bul</button>
        <button class="win-btn" onclick="closeDialog('findDialog')">İptal</button>
      </div>
      <div id="findResults" style="margin-top:8px;max-height:200px;overflow-y:auto;font-size:13px;"></div>
    </div>
  </div>
</div>

<!-- Hidden File Inputs for Editor -->
<input type="file" id="editorFileInput" style="display:none;" accept=".txt,.doc,.bak,.soz,text/*" onchange="editorHandleFileOpen(event)">
<input type="file" id="editorMergeInput" style="display:none;" accept=".txt,.doc,.bak,.soz,text/*" onchange="editorHandleFileMerge(event)">

<!-- Spell check dialogs: MTU.EXE dialog resources 2217 and 2218, buttons are the EXE's own bitmaps -->
<div class="dialog-overlay" id="spellCheckDialog">
  <div class="win-window" style="width:368px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Hatalı veya Bilinmeyen Sözcük</span>
      <div class="win-title-btns"><button onclick="spellCheckStop()">✕</button></div>
    </div>
    <div class="win-body exe-dlg">
      <div class="exe-rect3d"><div id="spell-err-word" class="exe-static"></div></div>
      <div class="exe-rect3d exe-group"><span class="exe-group-label">Öneriler</span>
        <div class="win-list" id="spell-suggestions" style="height:128px;overflow-y:auto;background:#fff;"></div>
      </div>
      <div class="exe-btn-row">
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_sozluk.png');--down:url('/assets/exe/btn_sozluk_down.png')" onclick="spellCheckAddWord()" title="Sözlük"></button>
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_degistir.png');--down:url('/assets/exe/btn_degistir_down.png')" onclick="spellCheckReplace()" title="Değiştir"></button>
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_devam.png');--down:url('/assets/exe/btn_devam_down.png')" onclick="spellCheckContinue()" title="Devam"></button>
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_dur.png');--down:url('/assets/exe/btn_dur_down.png')" onclick="spellCheckStop()" title="Dur"></button>
      </div>
    </div>
  </div>
</div>

<div class="dialog-overlay" id="punctCheckDialog">
  <div class="win-window" style="width:284px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Noktalama Hatası</span>
      <div class="win-title-btns"><button onclick="spellCheckStop()">✕</button></div>
    </div>
    <div class="win-body exe-dlg">
      <div class="exe-rect3d"><div id="punct-err-word" class="exe-static"></div></div>
      <div class="exe-rect3d"><div id="punct-replacement" class="exe-static"></div></div>
      <div class="exe-btn-row">
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_degistir.png');--down:url('/assets/exe/btn_degistir_down.png')" onclick="spellCheckReplace()" title="Değiştir"></button>
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_devam.png');--down:url('/assets/exe/btn_devam_down.png')" onclick="spellCheckContinue()" title="Devam"></button>
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_dur.png');--down:url('/assets/exe/btn_dur_down.png')" onclick="spellCheckStop()" title="Dur"></button>
      </div>
    </div>
  </div>
</div>

<!-- Text Stats Dialog (MTU.EXE offset 0x5F853) -->
<div class="dialog-overlay" id="textStatsDialog">
  <div class="win-window" style="width:340px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Metin İstatistik</span>
      <div class="win-title-btns"><button onclick="closeDialog('textStatsDialog')">✕</button></div>
    </div>
    <div class="win-body" style="padding:12px;background:#c0c0c0;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;font-size:12px;">
      <div class="group-box" style="padding:8px 12px;margin-bottom:12px;">
        <legend>İstatistik Değerleri</legend>
        <table style="width:100%;font-size:12px;border-collapse:collapse;font-weight:bold;line-height:1.8;">
          <tr><td style="padding:2px 0;">Toplam Sözcük:</td><td style="text-align:right;" id="stat-total-words">0</td></tr>
          <tr><td style="padding:2px 0;">Farklı Sözcük:</td><td style="text-align:right;" id="stat-unique-words">0</td></tr>
          <tr><td style="padding:2px 0;">Toplam Karakter:</td><td style="text-align:right;" id="stat-total-chars">0</td></tr>
          <tr><td style="padding:2px 0;">Boşluksuz Karakter:</td><td style="text-align:right;" id="stat-nospace-chars">0</td></tr>
          <tr><td style="padding:2px 0;">Toplam Paragraf:</td><td style="text-align:right;" id="stat-total-paragraphs">0</td></tr>
          <tr><td style="padding:2px 0;">Toplam Satır:</td><td style="text-align:right;" id="stat-total-lines">0</td></tr>
        </table>
      </div>
      <div style="display:flex;justify-content:center;">
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="closeDialog('textStatsDialog')" title="Tamam"></div>
      </div>
    </div>
  </div>
</div>

<!-- Help viewer: MTU.HLP (WinHelp 3.0) topics -->
<div class="dialog-overlay" id="helpDialog">
  <div class="win-window" style="width:560px;height:440px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Yardım - MTU.HLP</span>
      <div class="win-title-btns"><button onclick="closeDialog('helpDialog')">✕</button></div>
    </div>
    <div class="win-body" style="padding:4px;display:flex;flex-direction:column;gap:4px;height:100%;box-sizing:border-box;background:#c0c0c0;">
      <div style="display:flex;gap:4px;">
        <button class="win-btn" style="height:23px;font-size:11px;" onclick="helpShow(helpState.data.index_topic)">İçerik</button>
        <button class="win-btn" id="help-back" style="height:23px;font-size:11px;" onclick="helpBack()">Geri</button>
      </div>
      <div id="help-topic" class="help-topic"></div>
    </div>
  </div>
</div>

<!-- User Dictionary Dialog -->
<div class="dialog-overlay" id="userDictDialog">
  <div class="win-window" style="width:360px;height:340px;">
    <div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">Kullanıcı Sözlüğü</span>
      <div class="win-title-btns"><button onclick="closeDialog('userDictDialog')">✕</button></div>
    </div>
    <div class="win-body" style="padding:10px;display:flex;flex-direction:column;gap:8px;height:100%;box-sizing:border-box;">
      <div style="font-weight:bold;font-size:12px;">Özel Eklenen Sözcükler:</div>
      <div class="win-list" id="user-dict-list" style="flex:1;overflow-y:auto;background:#fff;font-size:12px;"></div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <button class="win-btn" onclick="clearUserDict()">Sözlüğü Temizle</button>
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="closeDialog('userDictDialog')" title="Tamam"></div>
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
        
        <!-- Tamam Button using sprite -->
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" id="char-btn-tamam" onclick="confirmCharacterSelection()" title="Tamam"></div>
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
          <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="confirmQuizTopic()" title="Tamam"></div>
          <div class="sprite-btn btn-sprite-dialog btn-sprite-iptal" onclick="closeQuizTopicDialog()" title="İptal"></div>
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
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="confirmOyunKelimeleri()" title="Tamam"></div>
        <div class="sprite-btn btn-sprite-dialog btn-sprite-iptal" onclick="closeOyunKelimeleriDialog()" title="İptal"></div>
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
  closeAllMenus();
  const id = 'alert-' + Date.now();
  const ov = document.createElement('div');
  ov.className = 'dialog-overlay open';
  ov.id = id;
  ov.innerHTML = `<div class="win-window" style="min-width:300px;max-width:400px;">
    <div class="win-title inactive"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar</span>
      <div class="win-title-btns"><button onclick="document.getElementById('${id}').remove()">✕</button></div>
    </div>
    <div class="win-body" style="padding:20px;text-align:center;">
      <div style="font-size:14px;margin-bottom:16px;white-space:pre-line;">${escHtml(msg)}</div>
      <button class="win-btn" onclick="document.getElementById('${id}').remove()">Tamam</button>
    </div>
  </div>`;
  document.body.appendChild(ov);
}

// ─── Menu System ──────────────────────────────────────────────────────────
let menuOpen = false;

function closeAllMenus() {
  menuOpen = false;
  document.querySelectorAll('.dropdown').forEach(m => m.classList.remove('open'));
  document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('open'));
}

function closeAllChildWindows() {
  closeAllMenus();
  Object.keys(state.windows).forEach(id => {
    if (id !== 'win-welcome') {
      closeWindow(id);
    }
  });
}

function positionDropdown(menu, targetEl) {
  const scale = state.uiScale || 1.0;
  const rect = targetEl.getBoundingClientRect();
  menu.style.left = (rect.left / scale) + 'px';
  menu.style.top = ((rect.bottom + 1) / scale) + 'px';
}

function toggleMenu(id, event) {
  event.stopPropagation();
  const menu = document.getElementById(id);
  if (!menu) return;
  const isOpen = menu.classList.contains('open');
  closeAllMenus();
  if (!isOpen) {
    menuOpen = true;
    menu.classList.add('open');
    event.target.classList.add('open');
    positionDropdown(menu, event.target);
  } else {
    menuOpen = false;
  }
}

function onMenuItemHover(id, event) {
  if (menuOpen) {
    const menu = document.getElementById(id);
    if (!menu) return;
    closeAllMenus();
    menuOpen = true;
    menu.classList.add('open');
    event.target.classList.add('open');
    positionDropdown(menu, event.target);
  }
}

// Ensure clicking any menu item or clicking outside immediately closes all dropdowns
document.addEventListener('click', function(e) {
  if (e.target.closest('.dropdown-item')) {
    closeAllMenus();
    return;
  }
  if (!e.target.closest('.menu-item') && !e.target.closest('.dropdown')) {
    closeAllMenus();
  }
}, true);

// ─── Windows Management System ───────────────────────────────────────────
function bringToFront(winId) {
  const win = document.getElementById(winId);
  if (!win) return;
  state.topZ = (state.topZ || 10) + 1;
  win.style.zIndex = state.topZ;
  
  // Update title bar colors: active window is blue, inactive windows are gray
  document.querySelectorAll('.win-window').forEach(w => {
    const title = w.querySelector('.win-title');
    if (title) {
      if (w.id === winId) {
        title.classList.remove('inactive');
      } else {
        title.classList.add('inactive');
      }
    }
  });

  // Auto-focus primary input in the active window
  setTimeout(() => {
    const searchInput = document.getElementById(winId + '-search') || (win && win.querySelector('input[type="text"]:not([readonly])'));
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }, 50);
}

function makeDraggable(winEl, handleEl) {
  if (!winEl || !handleEl) return;
  handleEl.style.cursor = 'move';
  handleEl.style.userSelect = 'none';
  handleEl.style.webkitUserSelect = 'none';

  handleEl.addEventListener('mousedown', function(e) {
    if (e.button !== 0) return;
    if (e.target.tagName === 'BUTTON' || e.target.closest('.win-title-btns') || e.target.closest('button')) return;
    
    e.preventDefault();
    bringToFront(winEl.id);
    
    const scale = (typeof state !== 'undefined' && state.uiScale) ? state.uiScale : 1.0;
    const rect = winEl.getBoundingClientRect();
    const workArea = document.getElementById('workArea') || document.body;
    const workRect = workArea.getBoundingClientRect();
    
    // Compute current position relative to workArea in CSS pixels
    const initialLeft = (rect.left - workRect.left) / scale;
    const initialTop = (rect.top - workRect.top) / scale;
    
    // Explicitly convert from CSS centering transforms to absolute positioning
    winEl.style.position = 'absolute';
    winEl.style.transform = 'none';
    winEl.style.margin = '0';
    winEl.style.left = initialLeft + 'px';
    winEl.style.top = initialTop + 'px';
    
    const startX = e.clientX;
    const startY = e.clientY;
    
    function onMouseMove(moveEvent) {
      const dx = (moveEvent.clientX - startX) / scale;
      const dy = (moveEvent.clientY - startY) / scale;
      winEl.style.left = (initialLeft + dx) + 'px';
      winEl.style.top = (initialTop + dy) + 'px';
    }
    
    function onMouseUp() {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    }
    
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}

function closeAllWindows() {
  closeQuizTopicDialog();
  Object.keys(state.windows).forEach(k => {
    const el = document.getElementById(k);
    if (el) el.remove();
    delete state.windows[k];
  });
}

function closeDialog(id) {
  closeAllMenus();
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

function openWindow(type, opts) {
  opts = opts || {};
  closeAllMenus();
  if (type === 'quiz') {
    openHangman();
    return;
  }
  
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
      config = { title: 'Türkçe Leb Demeden ...', type: 'tur', w: 300, h: 360 };
      break;
    case 'en-ld':
      config = { title: 'İngilizce Leb Demeden ...', type: 'eld', w: 300, h: 360 };
      break;
    case 'stats':
      config = { title: 'Metin İstatistik', type: 'stats', w: 480, h: 340 };
      break;
    default:
      config = { title: 'Pencere', type: 'trk', w: 400, h: 300 };
  }

  // If a window of this type is already open, focus it
  const existingWinId = Object.keys(state.windows).find(k => state.windows[k].type === config.type);
  if (existingWinId) {
    bringToFront(existingWinId);
    return;
  }
  
  // Remove welcome window if active
  const welcomeWin = document.getElementById('win-welcome');
  if (welcomeWin) {
    welcomeWin.remove();
    delete state.windows['win-welcome'];
  }

  const id = 'win-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');

  // Input remembering: retrieve last searched query independently per window type
  state.lastDictQuery = state.lastDictQuery || {};
  const rememberedQuery = (opts && opts.query) || state.lastDictQuery[config.type] || '';

  let html = `<div class="win-window" id="${id}" style="width:${config.w}px;height:${config.h}px;${opts.keep ? 'top:36px;left:48px;transform:none;' : ''}">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">${config.title}</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  
  if (config.type === 'trk' || config.type === 'rev') {
    html += `<div class="win-body" style="padding:10px;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:8px;">
      
      <!-- Top Search row: Sözcük label, input field and Tamam button -->
      <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-shrink:0;gap:8px;">
        <div style="flex:1;display:flex;flex-direction:column;gap:4px;">
          <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">Sözcük</div>
          <input class="win-input" type="text" style="width:100%;background:#c0c0c0;" id="${id}-search" value="${escHtml(rememberedQuery)}" oninput="dictSearchDebounced('${id}')" onkeydown="if(event.key==='Enter'){event.preventDefault();}">
        </div>
        <!-- EXE (DICTDLG): Tamam (id 501) ends the dialog like Esc; Enter (IDOK) is ignored, search is live -->
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="clearTimeout(_searchTimer['${id}']);closeWindow('${id}')" title="Tamam"></div>
      </div>

      <!-- Mid lists row: left listbox and right listbox -->
      <div style="display:flex;gap:12px;flex:1;min-height:0;min-width:0;">
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px;min-height:0;">
          <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">${config.type==='trk'?'İngilizce Sözcükler':'Türkçe Sözcükler'}</div>
          <div class="win-list" style="flex:1;overflow-y:auto;" id="${id}-list"></div>
        </div>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px;min-height:0;">
          <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">${config.type==='trk'?'Türkçe Karşılıklar':'İngilizce Karşılıklar'}</div>
          <div class="win-list" style="flex:1;overflow-y:auto;" id="${id}-defn"></div>
        </div>
      </div>
      
      <!-- Bottom detail row: label and read-only text field -->
      <div style="flex-shrink:0;display:flex;flex-direction:column;gap:4px;">
        <div style="font-size:13px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">${config.type==='trk'?'Türkçe Karşılık':'İngilizce Karşılık'}</div>
        <input class="win-input" type="text" readonly style="width:100%;background:#c0c0c0;color:#000;" id="${id}-detail">
      </div>
    </div>`;
  } else if (config.type === 'syn') {
    html += `<div class="win-body" style="padding:10px;flex:1;display:flex;flex-direction:column;min-height:0;min-width:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:8px;box-sizing:border-box;">
      
      <div style="display:flex;gap:12px;flex:1;min-height:0;min-width:0;">
        <!-- Left Column -->
        <div style="width:230px;display:flex;flex-direction:column;gap:8px;flex-shrink:0;min-height:0;">
          <!-- Sözcük Row -->
          <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0;">
            <div style="font-size:14px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">Sözcük</div>
            <input class="win-input" type="text" style="width:100%;background:#c0c0c0;font-weight:bold;font-family:inherit;" id="${id}-search" value="${escHtml(rememberedQuery)}" oninput="synTriggerSearch('${id}')" onkeydown="if(event.key==='Enter'){event.preventDefault();synTriggerSearch('${id}');}">
          </div>
          
          <!-- Kök Sözcük Row -->
          <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0;">
            <div style="font-size:14px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;">Kök Sözcük</div>
            <input class="win-input" type="text" readonly style="width:100%;background:#c0c0c0;color:#000;font-weight:bold;font-family:inherit;" id="${id}-stem">
          </div>
          
          <!-- Anlam Grupları Group Box -->
          <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin-top:10px;"><legend style="font-size:14px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;padding:0 4px;">Anlam Grupları</legend>
            <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-groups"></div>
          </div>
          
          <!-- Bottom Buttons Row (Centered under Left Column) -->
          <div style="display:flex;gap:20px;flex-shrink:0;margin-top:2px;margin-bottom:2px;justify-content:center;align-items:center;width:100%;">
            <!-- Tamam Button using sprite - closes window -->
            <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" id="${id}-btn-tamam" onclick="closeWindow('${id}')" title="Tamam"></div>
                 
            <!-- Değiştir Button using sprite - permanently disabled -->
            <div class="sprite-btn btn-sprite-dialog btn-sprite-degistir-d" id="${id}-btn-degistir" title="Değiştir"></div>
          </div>
        </div>
        
        <!-- Right Column (Eş Anlamları Group Box) -->
        <div class="group-box" style="flex:1;min-width:0;display:flex;flex-direction:column;margin-top:10px;"><legend style="font-size:14px;font-weight:bold;color:#000;text-shadow:0.5px 0.5px #fff;padding:0 4px;">Eş Anlamları</legend>
          <div class="win-list" style="flex:1;min-width:0;overflow-y:auto;overflow-x:hidden;background:#fff;" id="${id}-defn"></div>
        </div>
      </div>
    </div>`;
  } else if (config.type === 'tur' || config.type === 'eld') {
    // MTU.EXE dialogs 2207 / 2208: Sözcük, word list, Tamam (501) and Değiştir (516)
    html += `<div class="win-body exe-dlg" style="flex:1;min-height:0;">
      <div class="exe-rect3d exe-group"><span class="exe-group-label">Sözcük</span>
        <input class="win-input" type="text" style="width:100%;" id="${id}-search" value="${escHtml(rememberedQuery)}" oninput="dictSearchDebounced('${id}')" onkeydown="if(event.key==='Enter'){event.preventDefault();}">
      </div>
      <div class="exe-rect3d exe-group" style="flex:1;display:flex;flex-direction:column;min-height:0;"><span class="exe-group-label">${config.type === 'tur' ? 'Türkçe Sözcükler' : 'İngilizce Sözcükler'}</span>
        <div class="win-list" style="flex:1;overflow-y:auto;" id="${id}-list"></div>
      </div>
      <div style="display:flex;justify-content:space-around;">
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" onclick="closeWindow('${id}')" title="Tamam"></div>
        <button class="exe-bmp-btn" style="--up:url('/assets/exe/btn_degistir.png');--down:url('/assets/exe/btn_degistir_down.png')" onclick="lebReplace('${id}')" title="Değiştir"></button>
      </div>
    </div>`;
  } else if (config.type === 'stats') {
    html += `<div class="win-body" id="${id}-body" style="padding:4px;flex:1;display:flex;flex-direction:column;min-height:0;overflow:auto;"><div class="loading">Yükleniyor...</div></div>`;
  }
  
  html += `</div>`;
  
  // Insert at beginning of work area
  workArea.insertAdjacentHTML('afterbegin', html);
  
  const winEl = document.getElementById(id);
  const titleEl = winEl.querySelector('.win-title');
  winEl.addEventListener('mousedown', () => bringToFront(id));
  if (titleEl) makeDraggable(winEl, titleEl);
  bringToFront(id);
  
  // Load data
  state.windows[id] = { type: config.type, id: id };
  
  switch(config.type) {
    case 'trk': loadWindowDict(id, 'trk', '/api/trk'); break;
    case 'rev': loadWindowDict(id, 'rev', '/api/rev'); break;
    case 'syn': loadWindowDict(id, 'syn', '/api/syn'); break;
    case 'tur': lebSearch(id); break;
    case 'eld': loadWindowDict(id, 'trk', '/api/trk'); break;
    case 'stats': loadWindowStats(id); break;
  }
}

function closeWindow(id) {
  const win = document.getElementById(id);
  if (win) win.remove();
  delete state.windows[id];
  if (state.activeHangmanId === id) state.activeHangmanId = null;
  
  const remainingKeys = Object.keys(state.windows);
  if (remainingKeys.length === 0) {
    showWelcomeWindow();
  } else {
    bringToFront(remainingKeys[remainingKeys.length - 1]);
  }
}

// ─── Turkish Stemming Helper ──────────────────────────────────────────────
function getTurkishStem(word) {
  word = trLower(word.trim().replace(/^#/, ''));
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

// ─── Türkçe Eş Anlamlı Sözcükler Logic ────────────────────────────────────
function synTriggerSearch(winId) {
  const input = document.getElementById(winId + '-search');
  const q = input ? input.value.trim() : '';
  if (!q) {
    const stemEl = document.getElementById(winId + '-stem');
    if (stemEl) stemEl.value = '';
    const grp = document.getElementById(winId + '-groups');
    if (grp) grp.innerHTML = '';
    const defn = document.getElementById(winId + '-defn');
    if (defn) defn.innerHTML = '';
    return;
  }

  state.lastSearchQuery = q;
  state.lastDictQuery = state.lastDictQuery || {};
  state.lastDictQuery['syn'] = q;
  
  const fullData = state.windowData && state.windowData[winId];
  if (!fullData || !fullData.length) return;
  
  const qLower = trLower(q);
  // 1. Exact Turkish match (e.g. 'açık' -> 'açık', avoids collision with 'acık')
  let match = fullData.find(e => trLower(e.word) === qLower);

  // 2. Exact match with circumflex normalization (e.g. 'mali' -> 'malî')
  if (!match) {
    const qCirc = qLower.replace(/î/g,'i').replace(/â/g,'a').replace(/û/g,'u');
    match = fullData.find(e => {
      const wCirc = trLower(e.word).replace(/î/g,'i').replace(/â/g,'a').replace(/û/g,'u');
      return wCirc === qCirc;
    });
  }

  // 3. Fallback to ASCII folding (e.g. english keyboard 'acik' -> 'açık')
  if (!match) {
    const qnNorm = normalizeSearch(q);
    match = fullData.find(e => normalizeSearch(e.word) === qnNorm);
  }

  // 4. Suffix-stripped stem match (e.g. 'yüzünde' -> 'yüz')
  if (!match && q.length >= 3) {
    const stemNorm = normalizeSearch(getTurkishStem(q));
    if (stemNorm && stemNorm !== normalizeSearch(q)) {
      match = fullData.find(e => normalizeSearch(e.word) === stemNorm);
    }
  }
  
  if (match) {
    document.getElementById(winId + '-stem').value = match.word;
    
    const grp = document.getElementById(winId + '-groups');
    const groups = match.groups || '';
    let clusters = [];

    if (groups) {
      const parts = groups.split(' | ').filter(Boolean);
      clusters = parts.map((p) => {
        const segs = p.split('::');
        if (segs.length < 2) return null;
        const label = segs[0].trim();
        const trWords = segs[1].split(',').map(s => s.trim()).filter(Boolean);
        return { label: label, tr: trWords };
      }).filter(Boolean);
    }

    state.synClusters = state.synClusters || {};
    state.synClusters[winId] = clusters;
    
    if (clusters.length === 0) {
      grp.innerHTML = '<div style="color:#888;padding:8px;">Grup yok</div>';
      document.getElementById(winId + '-defn').innerHTML = '<div style="color:#888;padding:8px;">Eş anlamlı yok</div>';
      synSetReplaceEnabled(winId, false);
    } else {
      grp.innerHTML = clusters.map((c, ci) => {
        return `<div class="dict-meaning${ci===0?' meaning-sel':''}" style="cursor:pointer; border-bottom:none; font-weight:bold; font-family:inherit; padding:2px 4px;"
          onclick="synFilterGroup('${winId}', ${ci}, this)">${escHtml(c.label)}</div>`;
      }).join('');
      synFilterGroup(winId, 0, grp.querySelector('.dict-meaning'));
    }
  } else {
    document.getElementById(winId + '-stem').value = '';
    document.getElementById(winId + '-groups').innerHTML = '<div style="color:#888;padding:8px;">Sonuç bulunamadı</div>';
    document.getElementById(winId + '-defn').innerHTML = '<div style="color:#888;padding:8px;">Sonuç bulunamadı</div>';
    synSetReplaceEnabled(winId, false);
  }
}

function synFilterGroup(winId, clusterIdx, el) {
  const clusters = state.synClusters && state.synClusters[winId];
  if (!clusters || !clusters[clusterIdx]) return;

  const grp = document.getElementById(winId + '-groups');
  if (grp) {
    grp.querySelectorAll('.dict-meaning').forEach(e => e.classList.remove('meaning-sel'));
    if (el) el.classList.add('meaning-sel');
  }

  const df = document.getElementById(winId + '-defn');
  if (!df) return;
  const trWords = clusters[clusterIdx].tr;
  if (!trWords || !trWords.length) {
    df.innerHTML = '<div style="color:#888;padding:8px;">Eş anlamlı yok</div>';
    synSetReplaceEnabled(winId, false);
    return;
  }
  
  const currentWord = (document.getElementById(winId + '-search').value || '').trim();
  const synList = trWords.filter(w => trLower(w) !== trLower(currentWord));
  const displayWords = (synList.length > 0 ? synList : trWords).slice().sort((a, b) => a.localeCompare(b, 'tr'));

  state.synDisplayWords = state.synDisplayWords || {};
  state.synDisplayWords[winId] = displayWords;
  df.innerHTML = displayWords.map((m, i) => {
    return `<div class="dict-word${i===0?' dict-sel':''}" style="border-bottom:none; font-weight:bold; font-family:inherit; cursor:pointer; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; width:100%; box-sizing:border-box;" onclick="synonymSelect('${winId}',${i})" ondblclick="synonymDblClick('${winId}',${i})" title="${escHtml(m)}">${escHtml(m)}</div>`;
  }).join('');
  
  state.synSelectedWord = state.synSelectedWord || {};
  state.synSelectedWord[winId] = displayWords[0] || '';
  synSetReplaceEnabled(winId, false);
}

function synonymDblClick(winId, idx) {
  const words = (state.synDisplayWords && state.synDisplayWords[winId]) || [];
  const word = words[idx];
  if (word === undefined) return;
  const input = document.getElementById(winId + '-search');
  if (input) {
    input.value = word;
    synTriggerSearch(winId);
  }
}

function synonymSelect(winId, idx) {
  const words = (state.synDisplayWords && state.synDisplayWords[winId]) || [];
  const word = words[idx] || '';
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
  // Win16 editor replace placeholder
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

      // If search input has a remembered query, trigger search immediately
      const searchInput = document.getElementById(winId + '-search');
      if (searchInput && searchInput.value.trim()) {
        if (type === 'syn') {
          synTriggerSearch(winId);
        } else {
          dictSearch(winId);
        }
      }
    });
}

function renderLabelLines(winId, lines) {
  const df = document.getElementById(winId + '-defn');
  if (!df) return;
  const items = lines.filter(l => l.trim()).map(l => {
    const m = l.match(/^\s*(\d+)\.(.*)$/);
    return m ? { num: m[1] + '.', text: m[2].trim() } : { num: '', text: l.trim() };
  });
  _meaningWin = _meaningWin || {};
  _meaningWin[winId] = { parts: items.map(it => it.text), sel: 0 };
  df.innerHTML = items.map((it, i) =>
    `<div class="dict-meaning${i===0?' meaning-sel':''}" onclick="selectMeaning('${winId}',${i})">
      <span class="row-num">${escHtml(it.num)}</span>
      <div class="meaning-content"><div>${escHtml(it.text)}</div></div>
    </div>`).join('');
  const dt = document.getElementById(winId + '-detail');
  if (dt) dt.value = items.length ? items[0].text : '';
}

function renderMeanings(winId, meanings) {
  if (!meanings) {
    const df = document.getElementById(winId + '-defn');
    if (df) df.innerHTML = '<div style="color:#888;padding:8px;">Anlam yok</div>';
    const dt = document.getElementById(winId + '-detail');
    if (dt) dt.value = '';
    return;
  }

  // MTU.ING (Türkçe İngilizce): one EXE label per line, numbered only where the data numbers it
  if (meanings.includes('\n')) {
    renderLabelLines(winId, meanings.split('\n'));
    return;
  }

  // Meanings are separated by '#' in MTU.TRK
  let parts = [];
  if (meanings.includes('#')) {
    parts = meanings.split('#').map(p => {
      // Within each meaning block, synonyms are separated by '|'
      return p.split('|').map(s => s.trim()).filter(Boolean).join(', ');
    }).filter(Boolean);
  } else {
    // If no '#' (e.g. in TR->EN dictionary where translations are '|'-separated)
    parts = meanings.split('|').map(p => p.trim()).filter(Boolean);
  }

  const df = document.getElementById(winId + '-defn');
  if (!df) return;
  if (!parts.length) {
    df.innerHTML = '<div style="color:#888;padding:8px;">Anlam yok</div>';
    const dt = document.getElementById(winId + '-detail');
    if (dt) dt.value = '';
    return;
  }
  _meaningWin = _meaningWin || {};
  _meaningWin[winId] = { parts: parts, sel: 0 };
  df.innerHTML = parts.map((m, i) => {
    // Always assign sequential numbers to every item (like Win16 original)
    const numText = (i + 1) + '.';
    const content = m.replace(/^\d+\.\s*/, '').trim();
    
    return `<div class="dict-meaning${i===0?' meaning-sel':''}" onclick="selectMeaning('${winId}',${i})">
      <span class="row-num">${numText}</span>
      <div class="meaning-content"><div>${escHtml(content)}</div></div>
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
    if (!isSyn) {
      renderMeanings(winId, val);
    }
  }
  // Anlam Grupları
  const grp = document.getElementById(winId + '-groups');
  if (grp && wd && wd[idx]) {
    const groups = wd[idx]['groups'] || '';
    if (groups && isSyn) {
      const parts = groups.split(' | ').filter(Boolean);
      const clusters = parts.map((p, ci) => {
        const segs = p.split('::');
        if (segs.length < 2) return null;
        let label = segs[0].trim();
        if (!label.includes('.Anlam') && label !== 'Mecaz' && label !== 'Argo') {
          label = (ci + 1) + '.Anlam';
        }
        const trWords = segs[1].split(',').map(s => s.trim()).filter(Boolean);
        return { label: label, tr: trWords };
      }).filter(Boolean);

      state.synClusters = state.synClusters || {};
      state.synClusters[winId] = clusters;

      if (clusters.length === 0) {
        grp.innerHTML = '<div style="color:#888;padding:8px;">Grup yok</div>';
      } else {
        grp.innerHTML = clusters.map((c, ci) =>
          `<div class="dict-meaning${ci===0?' meaning-sel':''}" style="cursor:pointer; border-bottom:none; font-weight:bold; font-family:inherit; padding:3px 6px;"
            onclick="synFilterGroup('${winId}', ${ci}, this)">${escHtml(c.label)}</div>`
        ).join('');
        synFilterGroup(winId, 0, grp.querySelector('.dict-meaning'));
      }
    } else if (grp) {
      grp.innerHTML = '';
    }
  }
}

function trLower(s) {
  return String(s).replace(/İ/g, 'i').replace(/I/g, 'ı').toLowerCase().replace(/\u0307/g, '');
}

function normalizeSearch(s) {
  return trLower(s)
    .replace(/î/g,'i').replace(/â/g,'a').replace(/û/g,'u')
    .replace(/ı/g,'i').replace(/ş/g,'s').replace(/ç/g,'c').replace(/ö/g,'o').replace(/ü/g,'u').replace(/ğ/g,'g');
}
// İngilizce Türkçe Sözlük (MTU.EXE FUN_1010_397b): only words starting with the typed text
// are listed, in the EXE's order, after at least two letters a–z; only A–Z are case folded.
function trkSearch(winId, raw) {
  const fullData = state.windowData && state.windowData[winId];
  if (!fullData) return;
  const key = raw.replace(/[A-Z]/g, c => c.toLowerCase());
  const found = /^[a-z]{2}/.test(key) ? fullData.filter(e => e.key.startsWith(key)) : [];
  state.activeData = state.activeData || {};
  state.activeData[winId] = found;
  const listEl = document.getElementById(winId + '-list');
  listEl.innerHTML = found.map((e, i) =>
    `<div class="dict-word${i === 0 ? ' dict-sel' : ''}" onclick="trkSelect('${winId}',${i})">${escHtml(e.en)}</div>`).join('');
  listEl.scrollTop = 0;
  trkSelect(winId, 0);
}

// Türkçe Leb Demeden (MTU.EXE FUN_1010_3648): words starting with the typed text
function lebSearch(winId) {
  const input = document.getElementById(winId + '-search');
  const text = input ? input.value : '';
  postJson('/api/check/complete', { text: text }).then(r => {
    const listEl = document.getElementById(winId + '-list');
    if (!listEl) return;
    state.activeData = state.activeData || {};
    state.activeData[winId] = r.words.map(w => ({ en: w }));
    listEl.innerHTML = r.words.map((w, i) =>
      `<div class="dict-word${i === 0 ? ' dict-sel' : ''}" onclick="trkSelect('${winId}',${i})">${escHtml(w)}</div>`).join('');
    listEl.scrollTop = 0;
  });
}

// "Değiştir" (516): the selected word replaces the word at the editor's cursor
function lebReplace(winId) {
  const sel = document.querySelector(`#${winId}-list .dict-sel`);
  const src = state.lebSource;
  if (sel && src) {
    const t = document.getElementById(src.winId + '-textarea');
    if (t) {
      t.value = t.value.slice(0, src.start) + sel.textContent + t.value.slice(src.end);
      t.focus();
      t.setSelectionRange(src.start + sel.textContent.length, src.start + sel.textContent.length);
    }
  }
  closeWindow(winId);
}

function trkFirstMeaning(line) {
  // "Türkçe Karşılık": the line without its "%2d." number, at most 60 characters
  const c = line.charAt(0);
  return (c === ' ' || (c >= '1' && c <= '8') ? line.slice(3) : line).slice(0, 60);
}

function trkSelect(winId, idx) {
  const items = document.querySelectorAll(`#${winId}-list .dict-word`);
  items.forEach((el, i) => el.classList.toggle('dict-sel', i === idx));
  const e = (state.activeData[winId] || [])[idx];
  const df = document.getElementById(winId + '-defn');
  const dt = document.getElementById(winId + '-detail');
  if (!df) return;
  if (!e) {
    df.innerHTML = '';
    if (dt) dt.value = '';
    return;
  }
  df.innerHTML = e.lines.map((l, i) =>
    `<div class="dict-meaning${i === 0 ? ' meaning-sel' : ''}" style="white-space:pre;" onclick="trkSelectLine('${winId}',${idx},${i})">${escHtml(l)}</div>`).join('');
  if (dt) dt.value = trkFirstMeaning(e.lines[0] || '');
}

function trkSelectLine(winId, idx, line) {
  const e = (state.activeData[winId] || [])[idx];
  if (!e) return;
  document.querySelectorAll(`#${winId}-defn .dict-meaning`).forEach((el, i) => el.classList.toggle('meaning-sel', i === line));
  const dt = document.getElementById(winId + '-detail');
  if (dt) dt.value = trkFirstMeaning(e.lines[line] || '');
}

function dictSearch(winId) {
  const input = document.getElementById(winId + '-search');
  const q = input ? input.value.trim() : '';
  const win = state.windows[winId];
  if (!win) return;
  if (win.type === 'trk' || win.type === 'eld') {
    if (q) {
      state.lastDictQuery = state.lastDictQuery || {};
      state.lastDictQuery[win.type] = q;
    }
    trkSearch(winId, input ? input.value : '');
    return;
  }
  if (win.type === 'tur') {
    lebSearch(winId);
    return;
  }

  if (q) {
    state.lastSearchQuery = q;
    state.lastDictQuery = state.lastDictQuery || {};
    state.lastDictQuery[win.type] = q;
  }

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
  const turkishLowercase = trLower;
  const qnStrict = turkishLowercase(q);

  // 1. Birebir prefix eşleşmesi (Türkçe küçük harf)
  let filtered = fullData.filter(e => turkishLowercase(e[key1] || '').startsWith(qnStrict));

  // 2. Sadece bulunamazsa: ş→s, ç→c, ö→o vb. normalize eşleşmesi
  if (filtered.length === 0) {
    const qnNorm = normalizeSearch(q);
    filtered = fullData.filter(e => normalizeSearch(e[key1] || '').startsWith(qnNorm));
  }

  filtered.sort((a, b) => {
    const va = (a[key1] || '').trim();
    const vb = (b[key1] || '').trim();
    const vaLow = trLower(va);
    const vbLow = trLower(vb);
    
    if (vaLow === qnStrict && vbLow !== qnStrict) return -1;
    if (vbLow === qnStrict && vaLow !== qnStrict) return 1;
    
    if (win.type === 'trk') {
      return vaLow.localeCompare(vbLow, 'en');
    } else {
      return vaLow.localeCompare(vbLow, 'tr');
    }
  });

  state.activeData[winId] = filtered.slice(0, 100);

  const listEl = document.getElementById(winId + '-list');
  if (filtered.length === 0) {
    if (listEl) listEl.innerHTML = '<div style="color:#888;padding:8px;">Sonuç bulunamadı</div>';
    const defnEl = document.getElementById(winId + '-defn');
    if (defnEl) defnEl.innerHTML = '';
    const dt = document.getElementById(winId + '-detail');
    if (dt) dt.value = '';
    return;
  }

  const listHtml = state.activeData[winId].map((e, i) => {
    const label = e[key1] || '';
    return `<div class="dict-word${i===0?' dict-sel':''}" onclick="dictSelect('${winId}','${key2||''}',${i})">${escHtml(label)}</div>`;
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
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
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
      // Classic Win3.1 / DOS triumphant arpeggio fanfare (C5 -> E5 -> G5 -> C6 -> E6)
      playTone(523.25, 'triangle', 0.10, 0.20, 0.00); // C5
      playTone(659.25, 'triangle', 0.10, 0.20, 0.08); // E5
      playTone(783.99, 'triangle', 0.10, 0.22, 0.16); // G5
      playTone(1046.50, 'triangle', 0.28, 0.26, 0.24); // C6
      playTone(1318.51, 'triangle', 0.38, 0.28, 0.36); // E6
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
  closeAllMenus();
  closeQuizTopicDialog();
  
  const existingId = Object.keys(state.windows).find(k => state.windows[k].type === 'hangman');
  if (existingId) {
    bringToFront(existingId);
    return;
  }
  
  const welcomeWin = document.getElementById('win-welcome');
  if (welcomeWin) {
    welcomeWin.remove();
    delete state.windows['win-welcome'];
  }

  const id = 'win-hm-' + (state.nextWindowId++);
  const workArea = document.getElementById('workArea');

  let html = `<div class="win-window" id="${id}" style="width:342px;height:auto;">`;
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
  
  const winEl = document.getElementById(id);
  const titleEl = winEl.querySelector('.win-title');
  winEl.addEventListener('mousedown', () => bringToFront(id));
  if (titleEl) makeDraggable(winEl, titleEl);
  bringToFront(id);
  
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
  const found = Object.keys(state.windows).find(k => state.windows[k].type === 'hangman');
  return found || null;
}

function isWindowTopmost(winId) {
  const el = document.getElementById(winId);
  if (!el) return false;
  // A modal dialog (alert, topic list, …) takes keyboard input instead
  if (document.querySelector('.dialog-overlay.open')) return false;
  let topId = null;
  let topZ = -Infinity;
  document.querySelectorAll('#workArea .win-window').forEach(w => {
    const z = parseInt(w.style.zIndex, 10) || 0;
    if (z >= topZ) { topZ = z; topId = w.id; }
  });
  return topId === winId;
}

window.addEventListener('keydown', function(ev) {
  const id = activeHangmanId();
  if (!id || !isWindowTopmost(id)) return;
  const isEditing = ev.target && (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA');
  if (isEditing) return;
  if (ev.key === ' ') {
    ev.preventDefault();
    const info = state.windows[id] && state.windows[id].hangman;
    if (!info || !info.started || info.done) {
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
        // keep board playable — reopen empty state, then show the error on top
        if (win.hangman) {
          win.hangman.started = false;
          win.hangman.word = '';
          renderHangman(id);
        }
        const game = document.getElementById(id + '-game');
        if (game) {
          game.insertAdjacentHTML('afterbegin',
            '<p style="color:#800;padding:8px;">' + escHtml(d.error) + '</p>');
        }
        return;
      }
      const word = toTrUpper(d.word || '');
      initHangmanGame(id, word, '', topicIdx);
      SoundFX.playStart();
    });
}

function initHangmanGame(id, word, hint, topicIdx) {
  const wordUpper = toTrUpper(word);
  const info = {
    word: wordUpper, hint: hint, topicIdx: topicIdx,
    guessed: [], wrong: 0, maxWrong: 9, done: false, id: id,
    score: HM_START_SCORE,  // "Başla" sets the score to 10000 (ds:0x240C)
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
  if (won || lost) {
    info.done = true;
    if (lost) {
      info.score = 0;
      setTimeout(() => SoundFX.playLose(), 160);
    } else if (won) {
      setTimeout(() => SoundFX.playWin(), 160);
    }
  }

  const wordLen = started ? (info.word ? info.word.length : 0) : 0;
  let hmLetterSpacing = 6;
  let hmFontSize = 18;
  if (wordLen <= 4) {
    hmLetterSpacing = 10;
  } else if (wordLen <= 6) {
    hmLetterSpacing = 8;
  } else if (wordLen <= 8) {
    hmLetterSpacing = 6;
  } else if (wordLen <= 10) {
    hmLetterSpacing = 5;
  } else if (wordLen <= 12) {
    hmLetterSpacing = 3.5;
  } else if (wordLen <= 14) {
    hmLetterSpacing = 2;
    hmFontSize = 17;
  } else if (wordLen > 14) {
    hmLetterSpacing = 1;
    hmFontSize = 15;
  }

  const displayChars = started
    ? (info.done
        ? info.word.split('')
        : info.word.split('').map(c => info.guessed.includes(c) ? c : '_'))
    : [];
  const displayWord = displayChars.join('');

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
      const cls = disabled ? ' used' : '';
      const onClick = disabled ? '' : `onclick="guessLetter('${id}','${letter}')"`;
      const xPos = -(idx * 25);
      const yPos = disabled ? -25 : 0;

      html += `<div class="hm-key-sprite${cls}" style="background-position:${xPos}px ${yPos}px;" ` +
        `title="${letter}" ${onClick}></div>`;
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
  html += `<div class="hm-gallows"><div class="hm-gallows-sprite" style="background-position:${-(stage * 52)}px 0px;"></div></div>`;
  html += `<div class="hm-scorecol">`;
  html += `<div class="hm-scorelabel">Puan</div>`;
  html += `<div class="hm-scorebox" id="${id}-score">${info.score}</div>`;
  html += `</div></div>`;
  html += `<div class="hm-ad"><img width="98" height="98" src="/assets/logo_acer.png?v=1" alt="Acer"></div>`;
  html += `</div>`;
  
  const wordStyle = started && wordLen > 0
    ? `style="letter-spacing:${hmLetterSpacing}px; font-size:${hmFontSize}px; margin-right:-${hmLetterSpacing}px;"`
    : '';
  html += `<div class="hm-wordbox"><span class="hm-word-text" ${wordStyle}>${displayWord}</span></div>`;
  
  const isPlaying = started && !info.done;
  const sozlukCls = isPlaying ? 'disabled' : '';
  const sozlukClick = isPlaying ? '' : `onclick="hangmanSozluk('${id}')"`;
  const baslaCls = isPlaying ? 'disabled' : '';
  const baslaClick = isPlaying ? '' : `onclick="hangmanBasla('${id}')"`;

  html += `<div class="hm-btns">`;
  html += `<div class="sprite-btn btn-sprite-dialog btn-sprite-sozluk ${sozlukCls}" title="Sözlük" ${sozlukClick}></div>`;
  html += `<div class="sprite-btn btn-sprite-dialog btn-sprite-basla ${baslaCls}" title="Başla" ${baslaClick}></div>`;
  html += `<div class="sprite-btn btn-sprite-dialog btn-sprite-iptal" title="İptal" onclick="SoundFX.playClick();closeWindow('${id}')"></div>`;
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
    // EXE: the "?" button opens the first hidden letter and halves the score; it is not a
    // wrong guess, and like every letter button it is disabled once pressed
    info.guessed.push('?');
    for (const c of info.word) {
      if (!info.guessed.includes(c)) {
        info.guessed.push(c);
        break;
      }
    }
    info.score = Math.floor(info.score / 2);
    SoundFX.playHint();
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
  renderHangman(id);
}

function openRawWindow(id, title, w, h, bodyHtml) {
  closeAllMenus();
  const welcomeWin = document.getElementById('win-welcome');
  if (welcomeWin) {
    welcomeWin.remove();
    delete state.windows['win-welcome'];
  }
  
  if (document.getElementById(id)) {
    bringToFront(id);
    return;
  }

  const workArea = document.getElementById('workArea');
  let html = `<div class="win-window" id="${id}" style="width:${w}px;height:${h}px;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">${title}</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body" style="padding:4px;flex:1;display:flex;flex-direction:column;min-height:0;overflow:auto;">`;
  html += bodyHtml;
  html += `</div></div>`;
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'raw', id: id };
  
  const winEl = document.getElementById(id);
  const titleEl = winEl.querySelector('.win-title');
  winEl.addEventListener('mousedown', () => bringToFront(id));
  if (titleEl) makeDraggable(winEl, titleEl);
  bringToFront(id);
}

// ─── Welcome Screen ───────────────────────────────────────────────────────
function welcomeBtnPress(img, pressed) {
  if (!img) return;
  img.src = pressed ? img.dataset.p : img.dataset.n;
}

function toggleWelcomeMiniMode() {
  const win = document.getElementById('win-welcome');
  if (!win) return;
  win.classList.toggle('welcome-mini');
  state.welcomeMiniMode = win.classList.contains('welcome-mini');
}

function showWelcomeWindow() {
  const id = 'win-welcome';
  if (document.getElementById(id)) return;
  const workArea = document.getElementById('workArea');
  state.windows[id] = { type: 'welcome', id: id };

  const isMini = state.welcomeMiniMode || false;
  const v = '3';
  const modules = [
    { label: 'Türkçe Denetim', base: 'btn_denetim', action: 'openTextEditor()' },
    { label: 'Türkçe / İngilizce', base: 'btn_tr_en', action: "openWindow('tr-ing')" },
    { label: 'Türkçe Eş Anlamlılar', base: 'btn_esanlam', action: "openWindow('synonyms')" },
    { label: 'Klavye', base: 'btn_klavye', action: 'showKeyboardModule()' },
    { label: 'İngilizce / Türkçe', base: 'btn_en_tr', action: "openWindow('ing-tr')" },
    { label: 'Adam Asma', base: 'btn_adam_asma', action: "openHangman()" },
  ];

  let html = `<div class="win-window${isMini ? ' welcome-mini' : ''}" id="${id}" style="${isMini ? 'width:auto;' : 'width:372px;'}height:auto;" ondblclick="toggleWelcomeMiniMode()">`;
  html += `<div class="win-title" ondblclick="toggleWelcomeMiniMode()"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text">MoonStar Türkçe Dil Kılavuzu</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  html += `<div class="win-body welcome-body" style="padding:6px;">`;
  html += `<div class="welcome-panel">`;
  html += `<div class="welcome-grid">`;
  modules.forEach(m => {
    html += `<div class="sprite-btn btn-sprite-toolbar btn-sprite-${m.base}" title="${m.label}" onclick="${m.action}"></div>`;
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
  
  const winEl = document.getElementById(id);
  const titleEl = winEl.querySelector('.win-title');
  winEl.addEventListener('mousedown', () => bringToFront(id));
  if (titleEl) makeDraggable(winEl, titleEl);
  bringToFront(id);
}

function showKeyboardModule() {
  closeAllMenus();
  const id = 'win-kbd-select';
  if (document.getElementById(id)) return;
  
  openRawWindow(id, 'Klavye Seçimi', 340, 335, `
    <div style="padding:4px 6px;flex:1;display:flex;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:10px;box-sizing:border-box;height:100%;">
      <!-- Left Column -->
      <div style="flex:1;display:flex;flex-direction:column;gap:8px;min-height:0;height:100%;">
        <!-- 1.Klavye Group Box -->
        <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin:0;padding:12px 4px 4px;"><legend>1.Klavye</legend>
          <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-kbd1">
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 1, 'F', this)">Türkçe F-Klavye</div>
            <div class="dict-word dict-sel" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 1, 'Q', this)">Türkçe Q-Klavye</div>
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 1, 'EN', this)">İngilizce Q-Klavye</div>
          </div>
        </div>
        
        <!-- 2.Klavye Group Box -->
        <div class="group-box" style="flex:1;display:flex;flex-direction:column;min-height:0;margin:0;padding:12px 4px 4px;"><legend>2.Klavye</legend>
          <div class="win-list" style="flex:1;overflow-y:auto;background:#fff;" id="${id}-kbd2">
            <div class="dict-word dict-sel" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 2, 'F', this)">Türkçe F-Klavye</div>
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 2, 'Q', this)">Türkçe Q-Klavye</div>
            <div class="dict-word" style="border-bottom:none; font-weight:bold; font-family:inherit;" onclick="selectKbdLayout('${id}', 2, 'EN', this)">İngilizce Q-Klavye</div>
          </div>
        </div>
        
        <!-- Dikkat Group Box -->
        <div class="group-box" style="flex-shrink:0;padding:12px 6px 6px;margin:0;text-align:center;font-size:11px;line-height:1.4;font-weight:bold;"><legend>Dikkat</legend>
          <div>Klavyeler arasında geçiş</div>
          <div>CTRL+F1 tuşu ile yapılır</div>
        </div>
      </div>
      
      <!-- Right Column -->
      <div style="width:75px;display:flex;flex-direction:column;gap:8px;flex-shrink:0;justify-content:flex-start;align-items:center;padding-top:4px;">
        <!-- Edit Button using sprite -->
        <div class="sprite-btn btn-sprite-dialog btn-sprite-edit" id="${id}-btn-edit" onclick="showVirtualKeyboard('${id}')" title="Edit"></div>
             
        <!-- Tamam Button using sprite -->
        <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" id="${id}-btn-tamam" onclick="closeWindow('${id}')" title="Tamam"></div>
             
        <!-- İptal Button using sprite -->
        <div class="sprite-btn btn-sprite-dialog btn-sprite-iptal" id="${id}-btn-iptal" onclick="closeWindow('${id}')" title="İptal"></div>
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
    bringToFront(id);
    return;
  }
  
  let titleName = "Türkçe Q-Klavye";
  const selEl = document.querySelector('#win-kbd-select-kbd1 .dict-sel');
  if (selEl) {
    titleName = selEl.textContent.trim();
  }
  openRawWindow(id, titleName, 435, 265, `
    <div style="padding:4px 6px;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;gap:6px;box-sizing:border-box;height:100%;">
      
      <!-- Keyboard Keys Grid in Recessed Border Frame -->
      <div style="border:2px solid;border-color:#808080 #fff #fff #808080;padding:6px 4px;background:#c0c0c0;flex-shrink:0;box-sizing:border-box;">
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
          <!-- Tamam Button using sprite -->
          <div class="sprite-btn btn-sprite-dialog btn-sprite-tamam" id="${id}-btn-tamam" onclick="closeWindow('${id}')" title="Tamam"></div>
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
        `style="width:25px;height:25px;border:2px solid;${keyStyle}display:flex;justify-content:center;align-items:center;text-align:center;line-height:1;font-size:12px;font-weight:bold;cursor:pointer;user-select:none;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;box-sizing:border-box;padding:0;margin:0;">` +
        `<span style="display:inline-flex;align-items:center;justify-content:center;width:100%;height:100%;line-height:1;text-align:center;">${ch}</span>` +
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
  closeAllMenus();
  charListState.kbdWinId = kbdWinId || null;
  
  // Save current editor selection / cursor
  const textarea = document.getElementById('win-edt-textarea');
  if (textarea) {
    charListState.cursorStart = textarea.selectionStart;
    charListState.cursorEnd = textarea.selectionEnd;
  }
  
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
  const ch = cp1254Chars[code] || '';
  const winId = charListState.kbdWinId;
  
  // 1. Insert into Text Editor if it exists
  const textarea = document.getElementById('win-edt-textarea');
  if (textarea && ch) {
    const start = (charListState.cursorStart !== undefined && charListState.cursorStart !== null) 
      ? charListState.cursorStart 
      : (textarea.selectionStart || 0);
    const end = (charListState.cursorEnd !== undefined && charListState.cursorEnd !== null) 
      ? charListState.cursorEnd 
      : (textarea.selectionEnd || 0);
    const val = textarea.value;
    textarea.value = val.substring(0, start) + ch + val.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + ch.length;
    textarea.focus();
    if (typeof updateEditorStatus === 'function') {
      updateEditorStatus('Karakter eklendi: ' + ch);
    }
  }
  
  // 2. If called from Virtual Keyboard, update key definition
  const vkState = virtualKeyboardState;
  const idx = vkState.selectedKeyIdx;
  if (idx !== null && idx >= 0 && idx < vkState.keys.length) {
    const key = vkState.keys[idx];
    if (vkState.layers.alt) {
      key.alt = ch;
    } else if (vkState.layers.shift) {
      key.shift = ch;
    } else {
      key.normal = ch;
    }
    console.log(`Updated key ${idx} to ${ch}`);
    if (winId) drawVirtualKeyboardKeys(winId);
  }
  
  closeCharacterList();
}

function closeCharacterList() {
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
        trk.data.slice(0,20).forEach(e => { html += `<div style="padding:1px 4px;">${escHtml(e.en)} → ${escHtml(e.tr)}</div>`; });
      }
      if (tur.total > 0) {
        total += tur.total;
        html += '<div style="margin-top:4px;"><b>Türkçe Leb Demeden</b></div>';
        tur.data.slice(0,20).forEach(e => { html += `<div style="padding:1px 4px;">${escHtml(e.word)}</div>`; });
      }
      if (quiz.total > 0) {
        total += quiz.total;
        html += '<div style="margin-top:4px;"><b>Kelime Oyunu</b></div>';
        quiz.data.slice(0,20).forEach(e => { html += `<div style="padding:1px 4px;">[${escHtml(e.topic)}] ${escHtml(e.en)}</div>`; });
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
          html += `<div style="padding:1px 4px;">${escHtml(text)} ${def ? '→ '+escHtml(def) : ''}</div>`;
        });
      }
    });
    if (total === 0) html = '<div style="color:#666;">Sonuç bulunamadı.</div>';
    else html = `<div style="color:#444;margin-bottom:4px;">${total} sonuç</div>` + html;
    document.getElementById('findResults').innerHTML = html;
  });
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
  // The EXE's check loop over the whole text, every error answered with "Devam"
  fetchTextCheck(text).then(res => {
    if (res.words.length === 0) {
      statusEl.textContent = 'Denetlenecek kelime bulunamadı.';
      return;
    }
    res.errors.forEach(err => {
      const div = document.createElement('div');
      div.style.cssText = 'padding:2px 0;color:#c33;';
      if (err.kind === 'punct') {
        div.textContent = err.word + ' → ' + err.replacement + ' (noktalama)';
      } else {
        const sug = err.suggestions.slice(0, 5).map(s => s.word).join(', ');
        div.textContent = err.word + (sug ? ' → ' + sug : '');
      }
      resultsEl.appendChild(div);
    });
    statusEl.textContent = res.errors.length > 0
      ? `${res.errors.length} hata bulundu (${res.words.length} sözcük).`
      : '✓ Hiçbir hata bulunamadı.';
  }).catch(() => {
    statusEl.textContent = 'Hata: Sunucu bağlantısı başarısız.';
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
let currentEditorWinId = null;
if (!state.userDictionary) state.userDictionary = new Set();

function openTextEditor() {
  closeAllMenus();
  const id = 'win-edt';
  if (document.getElementById(id)) {
    bringToFront(id);
    return;
  }
  
  const welcomeWin = document.getElementById('win-welcome');
  if (welcomeWin) {
    welcomeWin.remove();
    delete state.windows['win-welcome'];
  }
  
  let html = `<div class="win-window" id="${id}" style="width:620px;height:480px;overflow:hidden;">`;
  html += `<div class="win-title"><img class="win-title-icon" src="/assets/moonstar_icon.png?v=2"><span class="win-title-text" id="${id}-title">MoonStar Türkçe Denetim Editörü - [isimsiz]</span>`;
  html += `<div class="win-title-btns"><button onclick="closeWindow('${id}')">✕</button></div></div>`;
  
  html += `<div class="win-body" style="padding:0;flex:1;display:flex;flex-direction:column;min-height:0;background:#c0c0c0;color:#000;font-family:'MS Sans Serif', Tahoma, Arial, sans-serif;position:relative;">`;
  
  // Editor local Menu Bar
  html += `  <div class="menu-bar" style="justify-content:flex-start;gap:0;padding:1px 2px;border-bottom:1px solid #808080;background:#c0c0c0;flex-shrink:0;user-select:none;">`;
  html += `    <div class="menu-items-group" style="display:flex;align-items:center;gap:0;">`;
  html += `      <div class="menu-item" onclick="toggleMenu('edtFileMenu', event)" onmouseenter="onMenuItemHover('edtFileMenu', event)" style="padding:3px 8px;cursor:pointer;">Dosya</div>`;
  html += `      <div class="menu-item" onclick="toggleMenu('edtEditMenu', event)" onmouseenter="onMenuItemHover('edtEditMenu', event)" style="padding:3px 8px;cursor:pointer;">Edit</div>`;
  html += `      <div class="menu-item" onclick="toggleMenu('edtFindMenu', event)" onmouseenter="onMenuItemHover('edtFindMenu', event)" style="padding:3px 8px;cursor:pointer;">Bul</div>`;
  html += `      <div class="menu-item" onclick="toggleMenu('edtTextMenu', event)" onmouseenter="onMenuItemHover('edtTextMenu', event)" style="padding:3px 8px;cursor:pointer;">Metin</div>`;
  html += `      <div class="menu-item" onclick="toggleMenu('edtOptsMenu', event)" onmouseenter="onMenuItemHover('edtOptsMenu', event)" style="padding:3px 8px;cursor:pointer;">Opsiyonlar</div>`;
  html += `      <div class="menu-item" onclick="toggleMenu('edtHelpMenu', event)" onmouseenter="onMenuItemHover('edtHelpMenu', event)" style="padding:3px 8px;cursor:pointer;">Yardım</div>`;
  html += `    </div>`;
  html += `  </div>`;
  
  // Monospace text editor field
  html += `  <div style="flex:1;min-height:0;position:relative;background:#fff;border-top:1px solid #808080;">`;
  html += `    <textarea id="${id}-textarea" spellcheck="false" style="width:100%;height:100%;border:none;outline:none;resize:none;font-family:'Courier New', monospace;font-size:14px;padding:8px;box-sizing:border-box;background:#fff;color:#000;line-height:1.4;white-space:pre-wrap;overflow-y:scroll;" onfocus="closeAllMenus()"></textarea>`;
  html += `  </div>`;
  
  // Status Bar
  html += `  <div class="win-status" id="${id}-status" style="flex-shrink:0;padding:2px 6px;border-top:1px solid #808080;font-size:11px;background:#c0c0c0;user-select:none;">Editör Hazır. Denetim için F5'e basınız.</div>`;
  
  html += `</div></div>`;
  
  const workArea = document.getElementById('workArea');
  workArea.insertAdjacentHTML('afterbegin', html);
  state.windows[id] = { type: 'editor', id: id };
  
  const winEl = document.getElementById(id);
  const titleEl = winEl.querySelector('.win-title');
  winEl.addEventListener('mousedown', () => bringToFront(id));
  if (titleEl) makeDraggable(winEl, titleEl);
  bringToFront(id);
  
  // Attach keydown listener for all authentic shortcuts
  const textarea = document.getElementById(id + '-textarea');
  textarea.addEventListener('keydown', function(event) {
    if (event.key === 'F1') {
      event.preventDefault();
      openHelp();
    } else if (event.key === 'F2' || (event.key === 'F5' && !event.shiftKey)) {
      event.preventDefault();
      editorSpellCheck(id);
    } else if (event.key === 'F5' && event.shiftKey) {
      event.preventDefault();
      editorDictCheck(id);
    } else if (event.key === 'F3' && event.altKey) {
      event.preventDefault();
      showFindDialog();
    } else if (event.key === 'F3') {
      event.preventDefault();
      editorShowFind(id);
    } else if (event.key === 'F4') {
      event.preventDefault();
      editorShowReplace(id);
    } else if (event.key === 'F6' && !event.shiftKey) {
      event.preventDefault();
      editorLookupTur(id);
    } else if (event.key === 'F6' && event.shiftKey) {
      event.preventDefault();
      editorLookupEld(id);
    } else if (event.key === 'F7') {
      event.preventDefault();
      editorLookupSyn(id);
    } else if (event.altKey && event.key === 'F8') {
      event.preventDefault();
      editorSave(id);
    } else if (event.key === 'F8' && !event.shiftKey) {
      event.preventDefault();
      editorLookupRev(id);
    } else if (event.key === 'F8' && event.shiftKey) {
      event.preventDefault();
      editorLookupTrk(id);
    } else if (event.key === 'F9') {
      event.preventDefault();
      editorShowStats(id);
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'q') {
      event.preventDefault();
      editorUppercase(id);
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'w') {
      event.preventDefault();
      editorLowercase(id);
    }
  });
}

function editorNew(winId) {
  closeAllMenus();
  const textarea = document.getElementById(winId + '-textarea');
  textarea.value = '';
  document.getElementById(winId + '-title').textContent = 'MoonStar Türkçe Denetim Editörü - [isimsiz]';
  document.getElementById(winId + '-status').textContent = 'Yeni belge oluşturuldu.';
  textarea.focus();
}

function editorOpenDemo(winId) {
  closeAllMenus();
  const status = document.getElementById(winId + '-status');
  status.textContent = 'TEST demo belgesi yükleniyor...';
  
  fetch('/api/editor/demo')
    .then(r => r.json())
    .then(data => {
      if (data.content) {
        document.getElementById(winId + '-textarea').value = data.content;
        document.getElementById(winId + '-title').textContent = `MoonStar Türkçe Denetim Editörü - [${data.filename}]`;
        status.textContent = `Demo belgesi (${data.filename}) başarıyla yüklendi.`;
      } else {
        status.textContent = 'Hata: Demo belgesi yüklenemedi.';
      }
    })
    .catch(() => {
      status.textContent = 'Hata: Sunucu bağlantısı başarısız.';
    });
}

function editorUploadFile(winId) {
  closeAllMenus();
  currentEditorWinId = winId;
  document.getElementById('editorFileInput').click();
}

function editorHandleFileOpen(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    if (currentEditorWinId) {
      document.getElementById(currentEditorWinId + '-textarea').value = e.target.result;
      document.getElementById(currentEditorWinId + '-title').textContent = `MoonStar Türkçe Denetim Editörü - [${file.name}]`;
      document.getElementById(currentEditorWinId + '-status').textContent = `"${file.name}" yüklendi.`;
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

function editorMergeFile(winId) {
  closeAllMenus();
  currentEditorWinId = winId;
  document.getElementById('editorMergeInput').click();
}

function editorHandleFileMerge(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    if (currentEditorWinId) {
      const t = document.getElementById(currentEditorWinId + '-textarea');
      t.value = (t.value ? t.value + '\n\n' : '') + e.target.result;
      document.getElementById(currentEditorWinId + '-status').textContent = `"${file.name}" içeriği birleştirildi.`;
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

function downloadFile(filename, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

function editorSave(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  const titleEl = document.getElementById(winId + '-title');
  let filename = 'belge.txt';
  if (titleEl && titleEl.textContent.includes('[') && !titleEl.textContent.includes('[isimsiz]')) {
    filename = titleEl.textContent.split('[')[1].replace(']', '').trim();
  }
  downloadFile(filename, text);
  document.getElementById(winId + '-status').textContent = `"${filename}" dosyası kaydedildi.`;
}

function editorSaveAs(winId) {
  closeAllMenus();
  const filename = prompt('Kaydedilecek dosya adı:', 'belge.txt');
  if (!filename) return;
  const t = document.getElementById(winId + '-textarea');
  downloadFile(filename, t.value);
  document.getElementById(winId + '-title').textContent = `MoonStar Türkçe Denetim Editörü - [${filename}]`;
  document.getElementById(winId + '-status').textContent = `"${filename}" dosyası kaydedildi.`;
}

function editorClear(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const start = t.selectionStart;
  const end = t.selectionEnd;
  if (start !== end) {
    const val = t.value;
    t.value = val.substring(0, start) + val.substring(end);
    t.setSelectionRange(start, start);
  } else {
    t.value = '';
  }
}

function editorUndo(winId) {
  closeAllMenus();
  document.getElementById(winId + '-textarea').focus();
  document.execCommand('undo');
}

function editorCut(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const start = t.selectionStart;
  const end = t.selectionEnd;
  if (start !== end) {
    const text = t.value;
    navigator.clipboard.writeText(text.substring(start, end));
    t.value = text.substring(0, start) + text.substring(end);
    t.setSelectionRange(start, start);
  }
}

function editorCopy(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const start = t.selectionStart;
  const end = t.selectionEnd;
  if (start !== end) {
    navigator.clipboard.writeText(t.value.substring(start, end));
  }
}

function editorPaste(winId) {
  closeAllMenus();
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

function trToUpper(str) {
  return str.replace(/i/g, 'İ').replace(/ı/g, 'I').toUpperCase();
}

function trToLower(str) {
  return str.replace(/İ/g, 'i').replace(/I/g, 'ı').toLowerCase();
}

function editorUppercase(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const start = t.selectionStart;
  const end = t.selectionEnd;
  const val = t.value;
  if (start !== end) {
    const sel = val.substring(start, end);
    t.value = val.substring(0, start) + trToUpper(sel) + val.substring(end);
    t.setSelectionRange(start, end);
  } else {
    t.value = trToUpper(val);
  }
  document.getElementById(winId + '-status').textContent = 'Büyük harfe dönüştürüldü.';
}

function editorLowercase(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  t.focus();
  const start = t.selectionStart;
  const end = t.selectionEnd;
  const val = t.value;
  if (start !== end) {
    const sel = val.substring(start, end);
    t.value = val.substring(0, start) + trToLower(sel) + val.substring(end);
    t.setSelectionRange(start, end);
  } else {
    t.value = trToLower(val);
  }
  document.getElementById(winId + '-status').textContent = 'Küçük harfe dönüştürüldü.';
}

function editorSingleParagraph(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  if (!text.trim()) return;
  const paragraphs = text.split(/\n\s*\n/);
  const processed = paragraphs.map(p => p.replace(/\r?\n/g, ' ').replace(/\s+/g, ' ').trim()).join('\n\n');
  t.value = processed;
  document.getElementById(winId + '-status').textContent = 'Tek paragraf düzeni uygulandı.';
}

function editorSortParagraphs(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  if (!text.trim()) return;
  const paragraphs = text.split(/\n+/).map(p => p.trim()).filter(p => p.length > 0);
  paragraphs.sort((a, b) => a.localeCompare(b, 'tr'));
  t.value = paragraphs.join('\n\n');
  document.getElementById(winId + '-status').textContent = 'Paragraflar alfabetik olarak sıralandı.';
}

function editorShowFind(winId) {
  closeAllMenus();
  const query = prompt('Bulunacak metin (F3):');
  if (!query) return;
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  const idx = text.toLocaleLowerCase('tr').indexOf(query.toLocaleLowerCase('tr'), t.selectionStart);
  if (idx !== -1) {
    t.focus();
    t.setSelectionRange(idx, idx + query.length);
    document.getElementById(winId + '-status').textContent = `"${query}" bulundu.`;
  } else {
    const idx2 = text.toLocaleLowerCase('tr').indexOf(query.toLocaleLowerCase('tr'));
    if (idx2 !== -1) {
      t.focus();
      t.setSelectionRange(idx2, idx2 + query.length);
      document.getElementById(winId + '-status').textContent = `"${query}" baştan bulundu.`;
    } else {
      winAlert(`"${query}" metni bulunamadı.`);
    }
  }
}

function editorShowReplace(winId) {
  closeAllMenus();
  const query = prompt('Değiştirilecek metin (F4):');
  if (!query) return;
  const rep = prompt('Yeni metin:');
  if (rep === null) return;
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  if (text.includes(query)) {
    t.value = text.replaceAll(query, rep);
    document.getElementById(winId + '-status').textContent = `"${query}" -> "${rep}" olarak değiştirildi.`;
  } else {
    winAlert(`"${query}" metni bulunamadı.`);
  }
}

function editorShowStats(winId) {
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  const text = t.value;
  const totalChars = text.length;
  const noSpaceChars = text.replace(/\s/g, '').length;
  const lines = text.split('\n').length;
  const paragraphs = text.split(/\n\s*\n/).filter(p => p.trim().length > 0).length;
  const words = text.match(/[a-zA-ZçÇğĞıİöÖşŞüÜâîû]+/g) || [];
  const totalWords = words.length;
  const uniqueWords = new Set(words.map(w => w.toLocaleLowerCase('tr'))).size;
  
  document.getElementById('stat-total-words').textContent = totalWords.toLocaleString('tr-TR');
  document.getElementById('stat-unique-words').textContent = uniqueWords.toLocaleString('tr-TR');
  document.getElementById('stat-total-chars').textContent = totalChars.toLocaleString('tr-TR');
  document.getElementById('stat-nospace-chars').textContent = noSpaceChars.toLocaleString('tr-TR');
  document.getElementById('stat-total-paragraphs').textContent = (paragraphs || (text.trim() ? 1 : 0)).toLocaleString('tr-TR');
  document.getElementById('stat-total-lines').textContent = lines.toLocaleString('tr-TR');
  
  document.getElementById('textStatsDialog').classList.add('open');
}

function postJson(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });
}

// Whole text as the EXE checks it when every error gets "Devam": {errors, words}
function fetchTextCheck(text) {
  return postJson('/api/check/text', { text: text });
}

function editorDictCheck(winId) {
  // MTU.EXE "Sözlük kontrol" (FUN_1018_10c4): from the cursor, stop at the first word that is
  // a form of a control dictionary (KONTROL.SOZ) entry and select it; nothing is shown otherwise.
  closeAllMenus();
  const t = document.getElementById(winId + '-textarea');
  const status = document.getElementById(winId + '-status');
  postJson('/api/check/control', { text: t.value, pos: t.selectionEnd })
    .then(r => {
      t.focus();
      if (r.match) {
        t.setSelectionRange(r.match.start, r.match.end);
        status.textContent = `Kontrol sözlüğünde bulunan sözcük: "${r.match.word}"`;
      } else {
        status.textContent = 'Sözlük kontrol tamamlandı.';
      }
    })
    .catch(() => {
      status.textContent = 'Hata: Sunucu bağlantısı başarısız.';
    });
}

function getEditorSelectedOrWord(winId) {
  const t = document.getElementById(winId + '-textarea');
  const start = t.selectionStart;
  const end = t.selectionEnd;
  const val = t.value;
  if (start !== end) {
    return val.substring(start, end).trim();
  }
  const left = val.slice(0, start).search(/[a-zA-ZçÇğĞıİöÖşŞüÜâîû]+$/);
  const right = val.slice(start).search(/[^a-zA-ZçÇğĞıİöÖşŞüÜâîû]/);
  if (left !== -1) {
    const wStart = left;
    const wEnd = right === -1 ? val.length : start + right;
    return val.substring(wStart, wEnd).trim();
  }
  return '';
}

function editorWordRange(winId) {
  const t = document.getElementById(winId + '-textarea');
  const val = t.value;
  let start = t.selectionStart, end = t.selectionEnd;
  if (start === end) {
    while (start > 0 && /[^\s.,;:!?"()]/.test(val[start - 1])) start--;
    while (end < val.length && /[^\s.,;:!?"()]/.test(val[end])) end++;
  }
  return { winId: winId, start: start, end: end, word: val.slice(start, end) };
}

function editorLookupTur(winId) {
  closeAllMenus();
  state.lebSource = editorWordRange(winId);
  openWindow('tr-tr', { query: state.lebSource.word });
}

function editorLookupEld(winId) {
  closeAllMenus();
  state.lebSource = editorWordRange(winId);
  openWindow('en-ld', { query: state.lebSource.word });
}

function editorLookupTrk(winId) {
  closeAllMenus();
  const w = getEditorSelectedOrWord(winId);
  openWindow('ing-tr', { query: w });
}

function editorLookupSyn(winId) {
  closeAllMenus();
  const w = getEditorSelectedOrWord(winId);
  openWindow('synonyms', { query: w });
}

function editorLookupRev(winId) {
  closeAllMenus();
  const w = getEditorSelectedOrWord(winId);
  openWindow('tr-ing', { query: w });
}

function editorShowUserDict(winId) {
  closeAllMenus();
  renderUserDictList();
  document.getElementById('userDictDialog').classList.add('open');
}

function renderUserDictList() {
  const listEl = document.getElementById('user-dict-list');
  if (!state.userDictionary || state.userDictionary.size === 0) {
    listEl.innerHTML = '<div style="color:#888;padding:8px;font-style:italic;">Kullanıcı sözlüğünde henüz sözcük yok.</div>';
    return;
  }
  listEl.innerHTML = Array.from(state.userDictionary).sort().map(w => 
    `<div style="padding:3px 6px;border-bottom:1px solid #eee;font-weight:bold;">${escHtml(w)}</div>`
  ).join('');
}

function clearUserDict() {
  if (confirm('Kullanıcı sözlüğünü temizlemek istediğinizden emin misiniz?')) {
    state.userDictionary.clear();
    renderUserDictList();
  }
}

// ─── Interactive Spell Checker (MTU.EXE FUN_1018_11e0) ──────────────────────
// The server runs the EXE's check loop up to the next error; the buttons do what the
// EXE's do: Sözlük adds the word and checks it again, Değiştir replaces it, Devam skips
// it and every later occurrence, Dur ends the check.
let spellCheckState = { winId: null };

function editorSpellCheck(winId) {
  closeAllMenus();
  const status = document.getElementById(winId + '-status');
  const textarea = document.getElementById(winId + '-textarea');
  if (!textarea.value.trim()) {
    winAlert('Denetlenecek metin yok.');
    status.textContent = 'Yazım denetimi iptal edildi (metin boş).';
    return;
  }
  // FUN_1018_11e0 starts at the cursor; the word before it sets the sentence state
  const pos = textarea.selectionStart;
  spellCheckState = { winId: winId, pos: pos, state: 0x80, ignore: [], punct: null, err: null, sel: 0 };
  status.textContent = 'Yazım denetimi yapılıyor...';
  postJson('/api/check/start', { text: textarea.value, pos: pos }).then(r => {
    spellCheckState.state = r.state;
    spellCheckStep();
  }).catch(() => {
    status.textContent = 'Hata: Sunucu bağlantısı başarısız.';
  });
}

function spellCheckStep() {
  const s = spellCheckState;
  const textarea = document.getElementById(s.winId + '-textarea');
  const status = document.getElementById(s.winId + '-status');
  postJson('/api/check/next', {
    text: textarea.value, pos: s.pos, state: s.state, ignore: s.ignore,
    user_words: Array.from(state.userDictionary || []), punct_continue: s.punct,
  }).then(r => {
    const err = r.error;
    s.err = err;
    document.getElementById('spellCheckDialog').classList.remove('open');
    document.getElementById('punctCheckDialog').classList.remove('open');
    if (!err) {
      status.textContent = '✓ Yazım denetimi tamamlandı.';
      winAlert('Yazım denetimi tamamlandı.');
      textarea.focus();
      return;
    }
    textarea.focus();
    textarea.setSelectionRange(err.start, err.end);
    const lineNum = textarea.value.substr(0, err.start).split("\n").length;
    textarea.scrollTop = (lineNum - 4) * 19;
    if (err.kind === 'punct') {
      document.getElementById('punct-err-word').textContent = err.word;
      document.getElementById('punct-replacement').textContent = err.replacement;
      document.getElementById('punctCheckDialog').classList.add('open');
      status.textContent = `Noktalama hatası: "${err.word}"`;
      return;
    }
    document.getElementById('spell-err-word').textContent = err.word;
    const list = document.getElementById('spell-suggestions');
    s.sel = Number.isInteger(err.best) ? err.best : 0;
    list.innerHTML = err.suggestions.map((sug, idx) =>
      `<div class="dict-word${idx === s.sel ? ' dict-sel' : ''}" style="border-bottom:none;font-family:inherit;padding:1px 4px;cursor:default;" onclick="selectSpellSuggestion(this, ${idx})" ondblclick="selectSpellSuggestion(this, ${idx});spellCheckReplace()">${escHtml(sug.word)}</div>`
    ).join('');
    document.getElementById('spellCheckDialog').classList.add('open');
    status.textContent = `Hatalı veya bilinmeyen sözcük: "${err.word}"`;
  }).catch(() => {
    status.textContent = 'Hata: Sunucu bağlantısı başarısız.';
  });
}

function selectSpellSuggestion(el, idx) {
  spellCheckState.sel = idx;
  const list = document.getElementById('spell-suggestions');
  list.querySelectorAll('.dict-word').forEach(e => e.classList.remove('dict-sel'));
  el.classList.add('dict-sel');
}

function spellCheckReplace() {
  const s = spellCheckState;
  const err = s.err;
  if (!err) return;
  const textarea = document.getElementById(s.winId + '-textarea');
  const text = textarea.value;
  if (err.kind === 'punct') {
    // "kitap,defter" → "kitap, defter"; the loop checks the word again from its start
    textarea.value = text.substring(0, err.start) + err.replacement + text.substring(err.end);
    s.pos = err.start;
    s.state = err.state;
    s.punct = null;
  } else {
    const sug = err.suggestions[s.sel];
    if (!sug) return;
    textarea.value = text.substring(0, err.start) + sug.word + text.substring(err.start + sug.replace_len);
    s.pos = err.start + sug.word.length;
    s.state = sug.state;
    s.punct = null;
  }
  spellCheckStep();
}

function spellCheckContinue() {
  const s = spellCheckState;
  const err = s.err;
  if (!err) return;
  if (err.kind === 'punct') {
    // the word before the punctuation is checked on its own
    s.pos = err.start;
    s.state = err.state;
    s.punct = err.start;
  } else {
    s.ignore.push(err.word);
    s.pos = err.continue.pos;
    s.state = err.continue.state;
    s.punct = null;
  }
  spellCheckStep();
}

function spellCheckAddWord() {
  const s = spellCheckState;
  const err = s.err;
  if (!err || err.kind !== 'word') return;
  if (!state.userDictionary) state.userDictionary = new Set();
  state.userDictionary.add(err.word.replace(/\.$/, '').toLocaleLowerCase('tr'));
  s.pos = err.start;
  s.state = err.state;
  s.punct = null;
  spellCheckStep();
}

function spellCheckStop() {
  document.getElementById('spellCheckDialog').classList.remove('open');
  document.getElementById('punctCheckDialog').classList.remove('open');
  if (spellCheckState.winId) {
    const ta = document.getElementById(spellCheckState.winId + '-textarea');
    if (ta) ta.focus();
    const st = document.getElementById(spellCheckState.winId + '-status');
    if (st) st.textContent = 'Yazım denetimi durduruldu.';
  }
  spellCheckState.err = null;
}

// ─── Help (MTU.HLP) ─────────────────────────────────────────────────────────
// Every help request of the EXE opens the index topic (all |CTXOMAP contexts map to it).
const helpState = { data: null, history: [] };

function openHelp() {
  closeAllMenus();
  const show = () => {
    helpState.history = [];
    helpState.current = null;
    helpShow(helpState.data.index_topic);
    document.getElementById('helpDialog').classList.add('open');
  };
  if (helpState.data) { show(); return; }
  fetch('/api/help').then(r => r.json()).then(d => { helpState.data = d; show(); })
    .catch(() => winAlert('Yardım dosyası yüklenemedi.'));
}

function helpShow(title, fromBack) {
  const topic = helpState.data.topics.find(t => t.title === title);
  if (!topic) return;
  if (!fromBack && helpState.current && helpState.current !== title) helpState.history.push(helpState.current);
  helpState.current = title;
  const el = document.getElementById('help-topic');
  el.innerHTML = topic.paragraphs.map(para => '<p>' + para.map(run => {
    let html = escHtml(run.text);
    if (run.bold) html = '<b>' + html + '</b>';
    if (run.italic) html = '<i>' + html + '</i>';
    if (run.link) html = `<span class="help-link" data-topic="${escHtml(run.link)}">${html}</span>`;
    return html;
  }).join('') + '</p>').join('');
  el.querySelectorAll('.help-link').forEach(a => a.onclick = () => helpShow(a.dataset.topic));
  el.scrollTop = 0;
  document.getElementById('help-back').disabled = helpState.history.length === 0;
}

function helpBack() {
  const prev = helpState.history.pop();
  if (prev) helpShow(prev, true);
}

// ─── Show About & Changelog ──────────────────────────────────────────────
function showAbout() {
  closeAllMenus();
  document.getElementById('aboutDialog').classList.add('open');
}

function showChangelog() {
  closeAllMenus();
  document.getElementById('changelogDialog').classList.add('open');
}

// ─── Init ─────────────────────────────────────────────────────────────────
showWelcomeWindow();

fetch('/api/stats').then(r => r.json()).then(st => {
  const el = document.getElementById('statusText');
  const n = v => v.toLocaleString('tr-TR');
  if (el) el.textContent = `TRK: ${n(st.trk.total)} | TUR: ${n(st.tur.total)} | SYN: ${n(st.syn.total)} | REV: ${n(st.rev.total)} | KELİME OYUNU: ${n(st.quiz.total)}`;
}).catch(() => {});
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
    my_pid = str(os.getpid())
    try:
        pid = subprocess.run(['lsof', '-ti', f"tcp:{PORT}", '-sTCP:LISTEN'], capture_output=True, text=True).stdout.strip()
        if pid:
            pids = []
            for p in pid.split():
                if p == my_pid:
                    continue
                cmdline = subprocess.run(['ps', '-o', 'command=', '-p', p], capture_output=True, text=True).stdout
                # Only stop stale instances of this server, never unrelated processes
                if 'ui.py' in cmdline:
                    pids.append(p)
            if pids:
                print(f"  ⚠ Port {PORT} kullanımda (PID:{', '.join(pids)}), eski process sonlandırılıyor…")
                for p in pids:
                    subprocess.run(['kill', '-9', p], capture_output=True)
                time.sleep(0.4)
    except Exception:
        pass

    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer((HOST, PORT), MoonStarHandler)

    def shutdown(signum=None, frame=None):
        # server.shutdown() blocks until serve_forever() returns; calling it from
        # the signal handler (same thread) would deadlock, so run it separately.
        import threading
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)

    print(f"\n🌙 MoonStar Veri Gezgini çalışıyor:")
    print(f"   http://{'localhost' if HOST in ('127.0.0.1', '0.0.0.0') else HOST}:{PORT}")
    print(f"\n   Sözlükler: İng→Tr ({len(TRK_DATA)}), Tr→Tr ({len(TUR_DATA)}), EşAnlam ({len(SYN_DATA)})")
    print(f"   Kelime Oyunu: {len(QUIZ_DATA)} kelime, {len(QUIZ_TOPIC_NAMES)} konu")
    print(f"\n   Çıkmak için Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nSunucu durduruldu.")
    sys.exit(0)


if __name__ == "__main__":
    if "--reload" in sys.argv:
        start_with_reload()
    else:
        main()
