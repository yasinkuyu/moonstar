// MoonStar static build — answers the web UI's /api/* requests in the browser.
//
// Dictionary lists come from JSON files produced by src/build_static.py with the
// same loaders as src/ui.py. The spell checker runs the Python engine itself
// (src/engine, src/spell_check.py) in Pyodide, loaded on first use.
(function () {
  'use strict';

  const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js';
  const realFetch = window.fetch.bind(window);
  const cache = {};

  function loadJson(name) {
    if (!cache[name]) {
      cache[name] = realFetch('api/' + name + '.json').then(r => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
    }
    return cache[name];
  }

  // Same as normalize_tr() in src/ui.py
  const TR_ASCII = { 'ı': 'i', 'ş': 's', 'ç': 'c', 'ö': 'o', 'ü': 'u', 'ğ': 'g', 'î': 'i', 'â': 'a', 'û': 'u' };
  function normalizeTr(s) {
    return s.replace(/İ/g, 'i').replace(/I/g, 'ı').toLowerCase().replace(/̇/g, '')
      .replace(/[ışçöüğîâû]/g, c => TR_ASCII[c]);
  }

  function intParam(params, name, def, lo, hi) {
    let v = parseInt(params.get(name), 10);
    if (isNaN(v)) v = def;
    if (lo !== undefined && v < lo) v = lo;
    if (hi !== undefined && v > hi) v = hi;
    return v;
  }

  function paginate(data, params) {
    const page = intParam(params, 'page', 1, 1);
    const perPage = intParam(params, 'per_page', 50, 1, 100000);
    const start = (page - 1) * perPage;
    return {
      total: data.length, page: page, per_page: perPage,
      total_pages: Math.ceil(data.length / perPage),
      data: data.slice(start, start + perPage),
    };
  }

  function prefixSearch(name, key) {
    return params => {
      const q = params.get('q') || '';
      if (!q) return { data: [], total: 0 };
      const qn = normalizeTr(q);
      return loadJson(name).then(list => {
        const results = list.filter(e => normalizeTr(e[key]).startsWith(qn));
        return { data: results.slice(0, 100), total: results.length };
      });
    };
  }

  function quizTopics() {
    return Promise.all([loadJson('quiz'), loadJson('stats')]).then(([quiz, stats]) => {
      const counts = {};
      quiz.forEach(q => { counts[q.topic_idx] = (counts[q.topic_idx] || 0) + 1; });
      return {
        topics: Object.keys(counts).map(Number).sort((a, b) => a - b)
          .map(idx => ({ idx: idx, name: stats.topic_names[idx], count: counts[idx] })),
      };
    });
  }

  const HANGMAN_LETTERS = new Set('abcçdefgğhıijklmnoöprsştuüvyzâîû');

  function hangmanWord(params) {
    const t = params.get('topic');
    const topic = t !== null && t !== '' && t !== '-1' && !isNaN(parseInt(t, 10)) ? parseInt(t, 10) : null;
    return loadJson('quiz').then(quiz => {
      const pool = quiz.filter(q => (topic === null || q.topic_idx === topic) &&
        q.tr.length >= 3 && q.tr.length <= 14 && [...q.tr].every(ch => HANGMAN_LETTERS.has(ch)));
      if (!pool.length) return { error: 'Kelime bulunamadı' };
      const q = pool[Math.floor(Math.random() * pool.length)];
      return { word: q.tr, en: q.en, tr: q.tr, hint: q.en, topic: q.topic, topic_idx: q.topic_idx };
    });
  }

  // ─── Spell checker: the Python engine in Pyodide ─────────────────────────
  let checker = null;

  function showLoading(on) {
    let el = document.getElementById('pyodide-loading');
    if (on && !el) {
      el = document.createElement('div');
      el.id = 'pyodide-loading';
      el.textContent = 'Yazım denetimi yükleniyor…';
      el.style.cssText = 'position:fixed;right:8px;bottom:28px;z-index:99999;background:#ffffe1;' +
        'border:1px solid #000;padding:4px 8px;font:12px "MS Sans Serif",Arial,sans-serif;';
      document.body.appendChild(el);
    } else if (!on && el) {
      el.remove();
    }
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error('Pyodide yüklenemedi'));
      document.head.appendChild(s);
    });
  }

  function getChecker() {
    if (!checker) {
      showLoading(true);
      checker = (async () => {
        await loadScript(PYODIDE_URL);
        const py = await loadPyodide();
        const manifest = await realFetch('py/manifest.json').then(r => r.json());
        await Promise.all(manifest.map(async path => {
          const buf = new Uint8Array(await realFetch('py/' + path).then(r => r.arrayBuffer()));
          const dir = '/moonstar/' + path.split('/').slice(0, -1).join('/');
          py.FS.mkdirTree(dir);
          py.FS.writeFile('/moonstar/' + path, buf);
        }));
        await py.runPythonAsync(`
import os, sys, json
os.chdir("/moonstar/src")
sys.path.insert(0, "/moonstar/src")
from spell_check import TurkishSpellChecker
_checker = TurkishSpellChecker()

def _check(q):
    r = _checker.check(q)
    r["dictionary"] = {"total": _checker.lexicon.word_count, "suffix_count": _checker.lexicon.suffix_count}
    return json.dumps(r, ensure_ascii=False)

def _check_text(text):
    return json.dumps({"tokens": _checker.check_text(text)}, ensure_ascii=False)
`);
        return py;
      })();
      checker.then(() => showLoading(false), err => {
        showLoading(false);
        checker = null;
        console.error(err);
      });
    }
    return checker;
  }

  function checkWord(params) {
    const q = params.get('q') || '';
    if (!q) return { valid: false, word: '', suggestions: [] };
    return getChecker().then(py => JSON.parse(py.globals.get('_check')(q)));
  }

  function checkText(body) {
    let text = '';
    try {
      const b = JSON.parse(body || '{}');
      if (b && typeof b.text === 'string') text = b.text;
    } catch (e) { /* empty text */ }
    return getChecker().then(py => JSON.parse(py.globals.get('_check_text')(text)));
  }

  const GET_ROUTES = {
    '/api/stats': () => loadJson('stats'),
    '/api/trk': params => loadJson('trk').then(d => paginate(d, params)),
    '/api/trk/search': prefixSearch('trk', 'en'),
    '/api/tur': params => loadJson('tur').then(d => paginate(d, params)),
    '/api/tur/search': prefixSearch('tur', 'word'),
    '/api/syn': params => loadJson('syn').then(d => paginate(d, params)),
    '/api/syn/search': prefixSearch('syn', 'word'),
    '/api/rev': params => loadJson('rev').then(d => paginate(d, params)),
    '/api/rev/search': prefixSearch('rev', 'tr'),
    '/api/quiz/topics': quizTopics,
    '/api/quiz': params => loadJson('quiz').then(d =>
      paginate(d.filter(q => q.topic_idx === intParam(params, 'topic', 0)), params)),
    '/api/quiz/search': params => {
      const q = (params.get('q') || '').toLowerCase();
      if (!q) return { data: [], total: 0 };
      return loadJson('quiz').then(d => {
        const results = [];
        for (const e of d) {
          if (e.en.toLowerCase().includes(q) || e.tr.toLowerCase().includes(q)) {
            results.push(e);
            if (results.length >= 100) break;
          }
        }
        return { data: results, total: results.length };
      });
    },
    '/api/hangman/word': hangmanWord,
    '/api/check': checkWord,
    '/api/editor/demo': () => loadJson('demo'),
  };

  function jsonResponse(data, status) {
    return new Response(JSON.stringify(data), {
      status: status || 200,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }

  window.fetch = function (input, init) {
    const raw = typeof input === 'string' ? input : input.url;
    const url = new URL(raw, window.location.href);
    const apiAt = url.pathname.indexOf('/api/');
    if (apiAt < 0 || !raw.replace(/^\.?\//, '/').startsWith('/api/')) {
      return realFetch(input, init);
    }
    const path = url.pathname.slice(apiAt);
    const method = ((init && init.method) || 'GET').toUpperCase();
    let handler;
    if (method === 'POST' && path === '/api/check/text') {
      handler = () => checkText(init && init.body);
    } else if (method === 'GET' && GET_ROUTES[path]) {
      handler = () => GET_ROUTES[path](url.searchParams);
    }
    if (!handler) return Promise.resolve(jsonResponse({ error: 'not found' }, 404));
    return Promise.resolve().then(handler).then(
      data => jsonResponse(data),
      err => jsonResponse({ error: String(err && err.message || err) }, 500));
  };
})();
