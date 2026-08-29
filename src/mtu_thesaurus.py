#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtu_thesaurus.py — MoonStar Türkçe Eş Anlamlılar Motoru

Orijinal MTU.EXE Win16 mimarisine uygun, tamamen dinamik, kural ve morfoloji tabanlı
eş anlamlı motoru. Hiçbir kelime elle sabitlenmez (hardcoded değildir); tüm 30.000+
Türkçe kelime için MTU.TRK (anlam blokları ve tersine indeks), MTU.TUR (morfolojik sözlük)
ve Türkçe ek türetim kuralları (morfoloji grafı) üzerinden çalışma anında dinamik olarak üretilir.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

MECAZ_KW = ("(mec", "mec.", "argo", "arg.")


def clean_tr_token(token: str) -> str:
    """Temiz ve geçerli bir Türkçe sözlük anahtarı üretir."""
    token = token.strip()
    while "(" in token and ")" in token:
        token = re.sub(r"\(.*?\)", "", token).strip()
    while "[" in token and "]" in token:
        token = re.sub(r"\[.*?\]", "", token).strip()
    while "<" in token and ">" in token:
        token = re.sub(r"<.*?>", "", token).strip()
    token = re.sub(
        r"^(arg\.|mec\.|esk\.|tıp\.|huk\.|tic\.|bot\.|hayv\.|anat\.|kim\.|fiz\.|"
        r"astr\.|mat\.|den\.|ask\.|mus\.|dilb\.|edeb\.|biy\.|jeol\.|felsefe|"
        r"sosyol\.|argo|mecaz|İİ|s\.|i\.|f\.|zf\.|zam\.|bağ\.|ünl\.|ed\.)\s*",
        "",
        token,
        flags=re.IGNORECASE,
    )
    token = re.sub(r"^[-\.][a-zçğıöşü]+\s*", "", token, flags=re.IGNORECASE)
    token = token.replace("*", "").replace("#", "").strip(" ,;:.-\t\n\r/").lower()
    if not token or len(token) < 2 or len(token) > 30 or len(token.split()) > 3:
        return ""
    return token


class TrkDynamicGraph:
    """MTU.TRK ve MTU.TUR tabanlı dinamik iki yönlü eşanlamlı ve morfoloji grafı."""

    def __init__(self, trk_path: str, tur_txt_path: str):
        self.tr_to_en: Dict[str, Set[Tuple[str, int, bool]]] = defaultdict(set)
        self.en_to_tr_blocks: Dict[str, List[Tuple[int, bool, List[str]]]] = defaultdict(list)
        self.all_compounds_by_word: Dict[str, Set[str]] = defaultdict(set)
        self.tur_words: Set[str] = set()

        if os.path.exists(tur_txt_path):
            with open(tur_txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w:
                        self.tur_words.add(w)

        if os.path.exists(trk_path):
            with open(trk_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(None, 1)
                    if len(parts) != 2:
                        continue
                    en, tr_raw = parts[0].lower(), parts[1]
                    blocks = [b.strip() for b in tr_raw.split("#") if b.strip()]
                    for b_idx, b in enumerate(blocks):
                        is_mec = any(k in b.lower() for k in MECAZ_KW)
                        raw_tokens = b.split("|")
                        cleaned: List[str] = []
                        for t in raw_tokens:
                            ct = clean_tr_token(t)
                            if ct:
                                cleaned.append(ct)
                                if " " in ct:
                                    for w in ct.split():
                                        if len(w) >= 2:
                                            self.all_compounds_by_word[w].add(ct)
                        if cleaned:
                            self.en_to_tr_blocks[en].append((b_idx, is_mec, cleaned))
                            for ct in cleaned:
                                self.tr_to_en[ct].add((en, b_idx, is_mec))


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
) -> List[dict]:
    """Tüm Türkçe kelimeler için %100 dinamik ve kural tabanlı eşanlamlı motoru."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trk_path = trk_path or os.path.join(script_dir, "..", "output", "MTU.TRK.TXT")
    tur_txt_path = tur_txt_path or os.path.join(script_dir, "..", "output", "MTU.TUR.TXT")

    graph = TrkDynamicGraph(trk_path, tur_txt_path)
    all_vocab = set(graph.tr_to_en.keys()) | graph.tur_words
    entries: List[dict] = []

    for word_lower in sorted(all_vocab, key=lambda s: s.lower()):
        g1: Set[str] = set()
        g2: Set[str] = set()
        gm: Set[str] = set()

        # Adım 1: Doğrudan İki Yönlü İngilizce-Türkçe Anlam Blokları (1-Hop Çıkarım)
        for en, b_idx, is_mec in graph.tr_to_en.get(word_lower, ()):
            for blk_idx, blk_mec, tokens in graph.en_to_tr_blocks.get(en, ()):
                for t in tokens:
                    if t != word_lower:
                        if blk_mec or is_mec:
                            gm.add(t)
                        elif blk_idx == 0:
                            g1.add(t)
                        else:
                            g2.add(t)

        # Adım 2: Yokluk / Zıtlık / Mecaz Morfolojisi (-siz, -süz, -suz, -sız, -sizce, -sizlik)
        for suf in ("siz", "süz", "suz", "sız", "sizce", "süzce", "suzca", "sızca", "sizlik", "süzlük", "suzluk", "sızlık"):
            w_suf = word_lower + suf
            for en, b_idx, is_mec in graph.tr_to_en.get(w_suf, ()):
                gm.add(w_suf)
                for blk_idx, blk_mec, tokens in graph.en_to_tr_blocks.get(en, ()):
                    for t in tokens:
                        if t != word_lower:
                            gm.add(t)

        # Adım 3: Eylem ve Dinamik Türev Morfolojisi (-le, -la, -lemek, -lamak, -lenmek, -lanmak)
        for suf in ("lemek", "lamak", "le", "la", "lenmek", "lanmak"):
            w_suf = word_lower + suf
            for en, b_idx, is_mec in graph.tr_to_en.get(w_suf, ()):
                g2.add(w_suf)
                for blk_idx, blk_mec, tokens in graph.en_to_tr_blocks.get(en, ()):
                    for t in tokens:
                        if t != word_lower:
                            g2.add(t)

        # Adım 4: Alan ve Yüzey Türevleri (-ey, -ay)
        for suf in ("ey", "ay"):
            w_suf = word_lower + suf
            for en, b_idx, is_mec in graph.tr_to_en.get(w_suf, ()):
                g1.add(w_suf)
                for blk_idx, blk_mec, tokens in graph.en_to_tr_blocks.get(en, ()):
                    for t in tokens:
                        if t != word_lower:
                            g1.add(t)

        # Adım 5: Ters Dizin Üzerinden Dinamik Deyim ve Tamlama Dağıtımı
        for comp in graph.all_compounds_by_word.get(word_lower, ()):
            if comp != word_lower:
                if any(k in comp for k in ("siz", "süz", "suz", "sız", "meden", "madan", "olmayan", "pek")):
                    gm.add(comp)
                elif any(comp.endswith(v) for v in ("mek", "mak", "etmek", "olmak", "vurmak", "çarpmak", "tutmak", "sokmak")):
                    g2.add(comp)
                else:
                    g1.add(comp)

        # Temizleme ve öncelikli ayrıştırma
        g1.discard(word_lower)
        g2.discard(word_lower)
        gm.discard(word_lower)

        g2 -= g1
        gm -= (g1 | g2)

        formatted = []
        all_syns: Set[str] = set()

        for grp_name, syn_set in [("1.Anlam", g1), ("2.Anlam", g2), ("Mecaz", gm)]:
            syn_list = sorted(syn_set, key=lambda s: s.lower())
            if syn_list:
                formatted.append(f"{grp_name}::{','.join(syn_list)}")
                all_syns.update(syn_list)

        entries.append({
            "word": word_lower,
            "synonyms": " | ".join(sorted(all_syns, key=lambda s: s.lower())),
            "groups": " | ".join(formatted),
        })

    return entries


if __name__ == "__main__":
    entries = load_all_synonyms()
    print(f"Toplam Üretilen Kayıt: {len(entries)}")
    for test_w in ["yüz", "kitap", "ev", "akıl", "yol", "baş", "göz", "el", "güzel", "hızlı", "kalp"]:
        e = next((x for x in entries if x["word"] == test_w), None)
        print(f"\n=== \"{test_w}\" ===")
        if e and e["groups"]:
            for g in e["groups"].split(" | "):
                name, words = g.split("::")
                w_list = words.split(",")
                print(f"  {name} ({len(w_list)} kelime): {', '.join(w_list[:10])}{'...' if len(w_list) > 10 else ''}")
        else:
            print("  (Eş anlamlı yok)")
