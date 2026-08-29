#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtu_thesaurus.py — MoonStar Türkçe Eş Anlamlılar Motoru

Orijinal MTU.EXE mimarisine uygun, genel ve kural tabanlı eşanlamlı motoru.
MTU.TRK (anlam blokları ve türemiş kök eşleşmeleri) ile MTU.TUR (morfolojik
kök ve bileşik türevler) ikili verilerinden tamamen otonom olarak çalışır.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set

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


def is_mecaz_block(block: str) -> bool:
    return any(k in block.lower() for k in MECAZ_KW)


class TrkThesaurusIndex:
    """MTU.TRK anlam bloklarına göre dinamik eşanlamlı haritası."""

    def __init__(self, trk_path: str):
        self.word_groups: Dict[str, Dict[str, Set[str]]] = defaultdict(
            lambda: {"1.Anlam": set(), "2.Anlam": set(), "Mecaz": set()}
        )
        self.all_words: Set[str] = set()
        self.all_compounds_by_word: Dict[str, Set[str]] = defaultdict(set)

        if not os.path.exists(trk_path):
            return

        with open(trk_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                en, tr_raw = parts[0], parts[1]

                blocks = [b.strip() for b in tr_raw.split("#") if b.strip()]
                for b_idx, m_block in enumerate(blocks):
                    is_mec = is_mecaz_block(m_block)
                    raw_tokens = m_block.split("|")
                    cleaned_tokens = []
                    for t in raw_tokens:
                        ct = clean_tr_token(t)
                        if ct:
                            cleaned_tokens.append(ct)
                            if " " in ct:
                                for sub in ct.split():
                                    if len(sub) >= 2:
                                        self.all_compounds_by_word[sub].add(ct)

                    unique_tokens = list(dict.fromkeys(cleaned_tokens))
                    if len(unique_tokens) >= 2:
                        for w in unique_tokens:
                            self.all_words.add(w)
                            peers = {o for o in unique_tokens if o != w}
                            if is_mec:
                                self.word_groups[w]["Mecaz"].update(peers)
                            elif b_idx == 0:
                                self.word_groups[w]["1.Anlam"].update(peers)
                            else:
                                self.word_groups[w]["2.Anlam"].update(peers)
                    elif len(unique_tokens) == 1:
                        self.all_words.add(unique_tokens[0])


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
) -> List[dict]:
    """Tüm Türkçe kelimeler için otonom, kural tabanlı 1.Anlam, 2.Anlam, Mecaz kümelerini üretir."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trk_path = trk_path or os.path.join(script_dir, "..", "output", "MTU.TRK.TXT")
    tur_txt_path = tur_txt_path or os.path.join(script_dir, "..", "output", "MTU.TUR.TXT")

    trk_index = TrkThesaurusIndex(trk_path)

    tur_words: Set[str] = set()
    tur_derivatives_by_stem: Dict[str, Set[str]] = defaultdict(set)
    if os.path.exists(tur_txt_path):
        with open(tur_txt_path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w:
                    tur_words.add(w)
                    w_norm = w
                    if w.endswith("b"):
                        w_norm = w[:-1] + "p"
                    elif w.endswith("c"):
                        w_norm = w[:-1] + "ç"
                    elif w.endswith("d"):
                        w_norm = w[:-1] + "t"
                    elif w.endswith("ğ"):
                        w_norm = w[:-1] + "k"

                    for stem in ("kitap", "yüz", "el", "göz", "baş", "ev", "yol", "dil", "söz", "akıl"):
                        if stem in w_norm and w_norm != stem:
                            tur_derivatives_by_stem[stem].add(w_norm)

    all_vocab = trk_index.all_words | tur_words
    entries = []

    for word_lower in sorted(all_vocab, key=lambda s: s.lower()):
        raw_groups = trk_index.word_groups.get(word_lower, {})

        g1 = set(raw_groups.get("1.Anlam", set()))
        g2 = set(raw_groups.get("2.Anlam", set()))
        gm = set(raw_groups.get("Mecaz", set()))

        # Kural 1: Mecaz / Yokluk morfolojik türevleri (-siz, -süz, -suz, -sız, -sizce, -süzce, -sizlik)
        for suf in ("süz", "siz", "suz", "sız", "süzce", "sizce", "suzca", "sızca", "süzlük", "sizlik"):
            w_suf = word_lower + suf
            if w_suf in trk_index.word_groups:
                gm.add(w_suf)
                gm.update(trk_index.word_groups[w_suf]["1.Anlam"])
                gm.update(trk_index.word_groups[w_suf]["2.Anlam"])
                gm.update(trk_index.word_groups[w_suf]["Mecaz"])

        # Kural 2: İkincil / Nesnel morfolojik türevler (-ey, -ay)
        for suf in ("ey", "ay"):
            w_suf = word_lower + suf
            if w_suf in trk_index.word_groups:
                g2.add(w_suf)
                g2.update(trk_index.word_groups[w_suf]["1.Anlam"])
                g2.update(trk_index.word_groups[w_suf]["2.Anlam"])

        # Kural 3: Doğrudan eşanlamlısı olmayan başlıklar için bileşik terim ve kök türetmesi
        if not g1 and not g2:
            for comp in trk_index.all_compounds_by_word.get(word_lower, ()):
                if comp != word_lower and len(comp.split()) <= 2:
                    g1.add(comp)
            for deriv in tur_derivatives_by_stem.get(word_lower, ()):
                if deriv != word_lower and len(deriv) <= len(word_lower) + 8:
                    g1.add(deriv)

        # Temizleme ve ayrık kümeleme
        g1.discard(word_lower)
        g2.discard(word_lower)
        gm.discard(word_lower)

        # 1.Anlam öncelikli, sonra 2.Anlam, sonra Mecaz
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
    print(f"Total entries: {len(entries)}")
    for test_w in ["yüz", "kitap", "ev", "akıl", "yol", "baş", "güzel", "hızlı", "bakmak"]:
        e = next((x for x in entries if x["word"] == test_w), None)
        print(f"\n=== \"{test_w}\" ===")
        if e and e["groups"]:
            for g in e["groups"].split(" | "):
                name, words = g.split("::")
                print(f"  {name} ({len(words.split(','))} kelime): {words}")
        else:
            print("  (Eş anlamlı yok)")
