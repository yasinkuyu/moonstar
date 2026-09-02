#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtu_thesaurus.py — MoonStar Türkçe Eş Anlamlılar Motoru v6

%100 DİNAMİK VE TEMİZLENMİŞ TERSİNE MÜHENDİSLİK MOTORU
- Tanım/açıklama cümlelerini (gloss) ve edat/bağlaçları filtreler.
- Sadece saf eş anlamlı sözcükleri ve standart terimleri üretir.
- Orijinal Win16 MTU.EXE grup ayrımına (1.Anlam, 2.Anlam, Mecaz) uygun dağıtır.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

# Eş anlamlı olarak kabul edilmeyecek bağlaç ve edat öbekleri
STOP_PHRASES = {
    "bu nedenle", "bu yüzden", "bundan dolayı", "dolayı", "nedeniyle", "ötürü",
    "için", "gibi", "kadar", "ile", "veya", "yahut", "ve", "vb", "vb.", "ya da"
}

# Açıklama / sözlük tanımı belirteçleri (sözcük değil tümce olan tanımları eler)
GLOSS_PATTERNS = [
    r"\bolan\b", r"\bverilen\b", r"\boluşmuş\b", r"\bgeçirilen\b", r"\belde edilen\b",
    r"\byapılan\b", r"\byapılmış\b", r"\bilişkin\b", r"\bilgili\b", r"\bkullanılan\b",
    r"\biçeren\b", r"\bbelirten\b", r"\bsatan\b", r"\bkimse\b", r"\bherhangi bir\b",
    r"\bbir parça\b", r"\bbir tür\b", r"\bbir çeşit\b", r"\bya da\b", r"\bveya\b"
]
GLOSS_RE = re.compile("|".join(GLOSS_PATTERNS), re.IGNORECASE)


def clean_tr_token(token: str) -> Tuple[str, bool]:
    """Token'ı temizler, açıklama cümlelerini eler ve mecaz etiketini tespit eder."""
    token = token.strip()
    while "(" in token and ")" in token:
        token = re.sub(r"\(.*?\)", "", token).strip()
    while "[" in token and "]" in token:
        token = re.sub(r"\[.*?\]", "", token).strip()
    while "<" in token and ">" in token:
        token = re.sub(r"<.*?>", "", token).strip()

    is_mecaz = bool(re.search(r"^(arg\.|mec\.|argo|mecaz|İİ|Aİ)\s*", token, re.IGNORECASE))

    token = re.sub(
        r"^(arg\.|mec\.|esk\.|tıp\.|huk\.|tic\.|bot\.|hayv\.|anat\.|kim\.|fiz\.|"
        r"astr\.|mat\.|den\.|ask\.|mus\.|dilb\.|edeb\.|biy\.|jeol\.|felsefe|"
        r"sosyol\.|argo|mecaz|İİ|Aİ|s\.|i\.|f\.|zf\.|zam\.|bağ\.|ünl\.|ed\.)\s*",
        "",
        token,
        flags=re.IGNORECASE,
    )
    token = re.sub(r"^[-\.][a-zçğıöşü]+\s*", "", token, flags=re.IGNORECASE)
    token = token.replace("*", "").replace("#", "").strip(" ,;:.-\t\n\r/").lower()

    # Uzun açıklamaları, 3 kelimeden uzun cümleleri ve edat öbeklerini ele
    if not token or len(token) < 2 or len(token) > 30:
        return "", False
    if len(token.split()) > 3:
        return "", False
    if token in STOP_PHRASES:
        return "", False
    if GLOSS_RE.search(token):
        return "", False

    return token, is_mecaz


def get_morphological_stems(word: str) -> Set[str]:
    """
    Sadece anlam koruyan temel Türkçe çekim eklerini ve ünsüz yumuşamasını çözümler.
    (Örn: 'kitabı' -> {'kitap', 'kitab', 'kitabı'})
    """
    w = word.lower()
    suffixes = ["ları", "leri", "lar", "ler", "ı", "i", "u", "ü"]
    stems = {w}
    for suf in suffixes:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[:-len(suf)]
            stems.add(stem)
            if stem.endswith("b"):
                stems.add(stem[:-1] + "p")
            elif stem.endswith("c"):
                stems.add(stem[:-1] + "ç")
            elif stem.endswith("d"):
                stems.add(stem[:-1] + "t")
            elif stem.endswith("ğ"):
                stems.add(stem[:-1] + "k")
    return stems


class SemanticThesaurus:
    def __init__(self, trk_path: Optional[str] = None, tur_txt_path: Optional[str] = None):
        self.trk_path = trk_path or os.path.join(OUTPUT_DIR, "MTU.TRK.TXT")
        self.tur_txt_path = tur_txt_path or os.path.join(OUTPUT_DIR, "MTU.TUR.TXT")

        self.all_vocab: Set[str] = set()
        self.stem_to_blocks: Dict[str, List[Tuple[str, int, bool, List[str], str]]] = defaultdict(list)
        self.word_to_peers: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

        self._build()

    def _build(self):
        self._load_tur_vocab()
        self._build_dynamic_trk_index()

    def _load_tur_vocab(self):
        if not os.path.exists(self.tur_txt_path):
            return
        with open(self.tur_txt_path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w and len(w) >= 2 and len(w) <= 30:
                    self.all_vocab.add(w)

    def _build_dynamic_trk_index(self):
        if not os.path.exists(self.trk_path):
            return

        with open(self.trk_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                en, tr_raw = parts[0], parts[1]

                blocks = [b.strip() for b in tr_raw.split("#") if b.strip()]
                for b_idx, b in enumerate(blocks):
                    block_tokens = []
                    block_is_mec = False
                    for t in b.split("|"):
                        ct, is_mec = clean_tr_token(t)
                        if is_mec:
                            block_is_mec = True
                        if ct:
                            block_tokens.append(ct)

                    unique_tokens = list(dict.fromkeys(block_tokens))
                    if not unique_tokens:
                        continue

                    grp = "Mecaz" if block_is_mec else ("1.Anlam" if b_idx == 0 else "2.Anlam")

                    for tok in unique_tokens:
                        self.all_vocab.add(tok)

                        # Blok içi doğrudan eş anlamlılar
                        for other_tok in unique_tokens:
                            if other_tok != tok:
                                self.word_to_peers[tok][grp].add(other_tok)

                        # Kök indeksleme
                        for st in get_morphological_stems(tok):
                            self.stem_to_blocks[st].append((en, b_idx, block_is_mec, unique_tokens, tok))

                        # Çok kelimeli ifadeler
                        if " " in tok:
                            for part in tok.split():
                                for st in get_morphological_stems(part):
                                    self.stem_to_blocks[st].append((en, b_idx, block_is_mec, unique_tokens, tok))

    def lookup(
        self,
        word_lower: str,
        use_multi_hop: bool = True,
        max_hops: int = 2,
    ) -> Dict[str, Set[str]]:
        query = word_lower.strip().lower()
        results: Dict[str, Set[str]] = {
            "1.Anlam": set(),
            "2.Anlam": set(),
            "Mecaz": set(),
        }

        # 1. Doğrudan eşleşen blok içi kelimeler
        for grp, p_set in self.word_to_peers.get(query, {}).items():
            results[grp].update(p_set)

        # 2. Morfolojik kök ve ilgili terim eşleşmeleri
        for en, b_idx, is_mec, tokens, matched_tok in self.stem_to_blocks.get(query, []):
            grp = "Mecaz" if is_mec else ("1.Anlam" if b_idx == 0 else "2.Anlam")
            if matched_tok != query:
                results[grp].add(matched_tok)

        # Sorgulanan kelimenin kendisini temizle
        for grp in list(results.keys()):
            results[grp].discard(query)
            if not results[grp]:
                del results[grp]

        return results


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
) -> List[dict]:
    engine = SemanticThesaurus(trk_path, tur_txt_path)
    entries: List[dict] = []

    for word_lower in sorted(engine.all_vocab, key=lambda s: s.lower()):
        groups_dict = engine.lookup(word_lower, use_multi_hop=False)

        formatted = []
        all_syns: Set[str] = set()

        for grp_name in ["1.Anlam", "2.Anlam", "Mecaz"]:
            if grp_name in groups_dict and groups_dict[grp_name]:
                syn_list = sorted(groups_dict[grp_name], key=lambda s: s.lower())
                formatted.append(f"{grp_name}::{','.join(syn_list)}")
                all_syns.update(syn_list)

        entries.append({
            "word": word_lower,
            "synonyms": " | ".join(sorted(all_syns, key=lambda s: s.lower())),
            "groups": " | ".join(formatted),
        })

    return entries


if __name__ == "__main__":
    engine = SemanticThesaurus()
    print("Semantic Thesaurus (Temizlenmiş) yüklendi.")
    for test_w in ["kitap", "yüz", "beden", "baş", "göz"]:
        res = engine.lookup(test_w)
        total_syns = sum(len(v) for v in res.values())
        print(f"\n=== \"{test_w}\" ({total_syns} sonuç) ===")
        for g, words in sorted(res.items()):
            w_list = sorted(words)
            print(f"  [{g}] ({len(w_list)}): {', '.join(w_list)}")
