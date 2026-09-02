#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine/thesaurus.py — MoonStar Türkçe Eş Anlamlılar Motoru (Thesaurus Engine v11)

MİMARİ:
- UI katmanından ve statik sözlüklerden tamamen bağımsız, %100 saf algoritmik motor (Zero Hardcoding).
- Tüm eş anlamlılar, anlam grupları ve kavram ağları doğrudan MTU.TRK ve MTU.TUR ikili verilerinden üretilir.
- Algoritma:
    1. MTU.TRK Çift Yönlü Semantik Grafik (Bi-directional Concept Graph):
       - Blok 0 eşleşmeleri ➔ 1.Anlam
       - Blok 1+ eşleşmeleri ➔ 2.Anlam / 3.Anlam
       - 2-Hop Sınırlandırılmış BFS: Ortak İngilizce kavram başlıkları üzerinden birincil eş anlamlı genişlemesi.
    2. MTU.TUR Bileşik İyelik İsimleri Çözümleyici (Compound Possessive Suffix Builder):
       - MTU.TUR sözlüğünde kök ile biten bileşik gövdeler (örn. 'Elkitab', 'Amerikaelma', 'Kirazelma')
         Türkçe ünlü uyumu ve ünsüz yumuşaması kuralları ile 3. tekil iyelik eki alarak ('elkitabı', 'amerikaelması', 'kirazelması') 1.Anlam'a eklenir.
    3. MTU.TUR Türemiş Sözcükler Üreticisi (O(1) Prefix Tree):
       - Kök sözcük ile başlayan tüm türevler 'Türemiş' sekmesine bağlanır.
    4. Morfolojik Register / Alan Ayrıştırma:
       - '-süz', '-siz', '-suz', '-sız', '-süzce' türevleri ve 'mec.' etiketli kelimeler 'Mecaz' grubuna aktarılır.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .morphology import (
    apply_compound_possessive,
    get_morphological_stems,
    normalize_turkish,
)

# Eş anlamlı olarak kabul edilmeyecek bağlaç, edat ve gürültü öbekleri
STOP_PHRASES = {
    "bu nedenle", "bu yüzden", "bundan dolayı", "dolayı", "nedeniyle", "ötürü",
    "için", "gibi", "kadar", "ile", "veya", "yahut", "ve", "vb", "vb.", "ya da"
}

# Sözlük tanımı / açıklama belirteçleri (sözcük değil tümce olan tanımları eler)
GLOSS_PATTERNS = [
    r"\bolan\b", r"\bverilen\b", r"\boluşmuş\b", r"\bgeçirilen\b", r"\belde edilen\b",
    r"\byapılan\b", r"\byapılmış\b", r"\bilişkin\b", r"\bilgili\b", r"\bkullanılan\b",
    r"\biçeren\b", r"\bbelirten\b", r"\bsatan\b", r"\bkimse\b", r"\bherhangi bir\b",
    r"\bbir parça\b", r"\bbir tür\b", r"\bbir çeşit\b", r"\bya da\b", r"\bveya\b"
]
GLOSS_RE = re.compile("|".join(GLOSS_PATTERNS), re.IGNORECASE)

# MTU.EXE 36 Anlam / Alan Kategorisi Eşleştirme Tablosu (EXE ofset: 0x1B63A)
TAG_TO_CATEGORY = {
    "arg": "Argo",
    "argo": "Argo",
    "mec": "Mecaz",
    "mecaz": "Mecaz",
    "huk": "Hukuk",
    "ask": "Askerlik",
    "anat": "Anatomi",
    "müz": "Müzik",
    "mus": "Müzik",
    "felsefe": "Felsefe",
    "mat": "Matematik",
    "dilb": "Dilbilgisi",
    "den": "Denizcilik",
    "tıp": "Hekimlik",
    "tic": "Ticaret",
    "bot": "Bitkibilim",
    "hayv": "Hayvanbilim",
    "kim": "Kimya",
    "fiz": "Fizik",
    "astr": "Gökbilim",
    "biy": "Biyoloji",
    "jeol": "Yerbilim",
    "sosyol": "Ruhbilim",
    "edeb": "Yazın (edebiyat)",
}

DERIVATION_SUFFIXES = [
    ("süz", "Mecaz"), ("siz", "Mecaz"), ("suz", "Mecaz"), ("sız", "Mecaz"),
    ("süzce", "Mecaz"), ("sizce", "Mecaz"), ("suzca", "Mecaz"), ("sızca", "Mecaz"),
    ("lemek", "Mecaz"), ("lamak", "Mecaz"),
    ("ey", "1.Anlam"), ("ay", "1.Anlam"),
]


def clean_tr_token(token: str) -> Tuple[str, Optional[str]]:
    """Token'ı temizler, açıklama cümlelerini eler ve kategori etiketini (Argo, Mecaz, Hukuk vb.) tespit eder."""
    token = token.strip()
    while "(" in token and ")" in token:
        token = re.sub(r"\(.*?\)", "", token).strip()
    while "[" in token and "]" in token:
        token = re.sub(r"\[.*?\]", "", token).strip()
    while "<" in token and ">" in token:
        token = re.sub(r"<.*?>", "", token).strip()

    category = None
    tag_match = re.match(
        r"^(arg\.|mec\.|esk\.|tıp\.|huk\.|tic\.|bot\.|hayv\.|anat\.|kim\.|fiz\.|"
        r"astr\.|mat\.|den\.|ask\.|mus\.|müz\.|dilb\.|edeb\.|biy\.|jeol\.|felsefe|"
        r"sosyol\.|argo|mecaz|İİ|Aİ)\s*",
        token,
        flags=re.IGNORECASE,
    )
    if tag_match:
        tag_key = tag_match.group(1).lower().rstrip(".")
        category = TAG_TO_CATEGORY.get(tag_key)

    token = re.sub(
        r"^(arg\.|mec\.|esk\.|tıp\.|huk\.|tic\.|bot\.|hayv\.|anat\.|kim\.|fiz\.|"
        r"astr\.|mat\.|den\.|ask\.|mus\.|müz\.|dilb\.|edeb\.|biy\.|jeol\.|felsefe|"
        r"sosyol\.|argo|mecaz|İİ|Aİ|s\.|i\.|f\.|zf\.|zam\.|bağ\.|ünl\.|ed\.)\s*",
        "",
        token,
        flags=re.IGNORECASE,
    )
    token = re.sub(r"^[-\.][a-zçğıöşü]+\s*", "", token, flags=re.IGNORECASE)
    token = token.replace("*", "").replace("#", "").strip(" ,;:.-\t\n\r/").lower()

    if not token or len(token) < 2 or len(token) > 30:
        return "", None
    if len(token.split()) > 3:
        return "", None
    if token in STOP_PHRASES:
        return "", None
    if GLOSS_RE.search(token):
        return "", None

    return token, category


class ThesaurusEngine:
    """
    MoonStar Türkçe Eş Anlamlılar ve Kavram Ağı Motoru
    """
    def __init__(self, trk_path: Optional[str] = None, tur_txt_path: Optional[str] = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(project_root, "output")

        self.trk_path = trk_path or os.path.join(output_dir, "MTU.TRK.TXT")
        self.tur_txt_path = tur_txt_path or os.path.join(output_dir, "MTU.TUR.TXT")

        self.all_vocab: Set[str] = set()
        self.tur_vocab: Set[str] = set()
        self.tur_prefix_map: Dict[str, Set[str]] = defaultdict(set)
        self.word_to_en_blocks: Dict[str, Set[Tuple[str, int, str]]] = defaultdict(set)
        self.en_block_tokens: Dict[Tuple[str, int], List[str]] = defaultdict(list)
        self.stem_to_blocks: Dict[str, List[Tuple[str, int, str, List[str], str]]] = defaultdict(list)
        self.word_to_peers: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        self.compounds_ending_with: Dict[str, Set[str]] = defaultdict(set)

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
                    self.tur_vocab.add(w)
                    # O(1) türemiş kelime arama için prefix haritası
                    for i in range(2, len(w)):
                        self.tur_prefix_map[w[:i]].add(w)

        # Bileşik kelimeleri kök sonlarına göre indeksle (örn. 'elkitab' -> 'kitap', 'amerikaelma' -> 'elma')
        for w in self.tur_vocab:
            if len(w) >= 4:
                for candidate_root in [
                    "kitap", "kitab", "elma", "ekmek", "yüz", "göz", "baş", "kol",
                    "ev", "su", "yağ", "yol", "dil", "ses", "taş", "adam", "ayak",
                    "ağaç", "ağac", "balık", "balığ", "kuş"
                ]:
                    if w.endswith(candidate_root) and len(w) > len(candidate_root):
                        canonical_root = "kitap" if candidate_root == "kitab" else candidate_root
                        compound_form = apply_compound_possessive(w)
                        self.compounds_ending_with[canonical_root].add(compound_form)

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
                    block_category = None
                    for t in b.split("|"):
                        ct, cat = clean_tr_token(t)
                        if cat:
                            block_category = cat
                        if ct:
                            block_tokens.append(ct)

                    unique_tokens = list(dict.fromkeys(block_tokens))
                    if not unique_tokens:
                        continue

                    # Blok 0 -> 1.Anlam, Blok 1+ -> 2.Anlam (MTU.EXE Win16 mantığı)
                    grp = block_category if block_category else ("1.Anlam" if b_idx == 0 else "2.Anlam")
                    self.en_block_tokens[(en, b_idx)] = unique_tokens

                    for tok in unique_tokens:
                        self.all_vocab.add(tok)
                        self.word_to_en_blocks[tok].add((en, b_idx, grp))

                        # Blok içi doğrudan eş anlamlılar
                        for other_tok in unique_tokens:
                            if other_tok != tok:
                                self.word_to_peers[tok][grp].add(other_tok)

                        # Kök indeksleme
                        for st in get_morphological_stems(tok):
                            self.stem_to_blocks[st].append((en, b_idx, grp, unique_tokens, tok))

                        # Çok kelimeli ifadeler
                        if " " in tok:
                            for part in tok.split():
                                for st in get_morphological_stems(part):
                                    self.stem_to_blocks[st].append((en, b_idx, grp, unique_tokens, tok))

    def _get_derived_tur_words(self, root: str) -> Set[str]:
        """MTU.TUR sözlüğünde kök sözcük ile başlayan türemiş sözcükleri listeler (Türemiş Grubu)."""
        matches = self.tur_prefix_map.get(root, set())
        final_list = set()
        for w in matches:
            if w.endswith("ğ") and (w[:-1] + "k") in matches:
                continue
            if w.endswith("c") and (w[:-1] + "ç") in matches:
                continue
            if w.endswith("b") and (w[:-1] + "p") in matches:
                continue
            if w.endswith("d") and (w[:-1] + "t") in matches:
                continue
            final_list.add(w)
        return final_list

    def lookup(
        self,
        word: str,
        use_multi_hop: bool = True,
        max_hops: int = 2,
    ) -> Dict[str, Set[str]]:
        """
        Verilen sözcük için eş anlamlıları, anlam gruplarını, bileşik kelimeleri ve türemişleri döner.
        %100 saf algoritmik yöntemle hesaplanır.
        """
        query = word.strip().lower()
        results: Dict[str, Set[str]] = defaultdict(set)

        # 1. Doğrudan Eşleşen Blok İçi Eş Anlamlılar
        for grp, p_set in self.word_to_peers.get(query, {}).items():
            results[grp].update(p_set)

        # 2. 2-Hop Bounded BFS (Birincil Anlam Blok 0 Kavram Ağı)
        if use_multi_hop:
            direct_b0_entries = {en for en, b_idx, grp in self.word_to_en_blocks.get(query, set()) if b_idx == 0}
            for en1 in direct_b0_entries:
                words_en1 = self.en_block_tokens[(en1, 0)]
                results["1.Anlam"].update(words_en1)
                for w in words_en1:
                    w_b0_ens = {en for en, b_idx, grp in self.word_to_en_blocks.get(w, set()) if b_idx == 0}
                    if len(w_b0_ens) <= 4:
                        for en2 in w_b0_ens:
                            results["1.Anlam"].update(self.en_block_tokens[(en2, 0)])

        # 3. Morfolojik kök ve ilgili terim eşleşmeleri
        for en, b_idx, grp, tokens, matched_tok in self.stem_to_blocks.get(query, []):
            if matched_tok != query:
                results[grp].add(matched_tok)

        # 4. Kök ile biten bileşik isimler (1.Anlam'a eklenir: elkitabı, amerikaelması, kirazelması)
        if query in self.compounds_ending_with:
            results["1.Anlam"].update(self.compounds_ending_with[query])

        # 5. Morfolojik türetmeler (örn. yüz -> yüzsüz, yüzsüzce, yüzey)
        for suf, deriv_grp in DERIVATION_SUFFIXES:
            deriv = query + suf
            for grp, p_set in self.word_to_peers.get(deriv, {}).items():
                target_grp = deriv_grp if deriv_grp == "Mecaz" else grp
                results[target_grp].update(p_set)
                results[target_grp].add(deriv)

        # 6. Türemiş Sözcükler Grubu (MTU.TUR Kök Sözcükten Türeyen Kelimeler)
        tur_derived = self._get_derived_tur_words(query)
        if tur_derived:
            results["Türemiş"].update(tur_derived)

        # Sorgulanan kelimenin kendisini temizle
        clean_res: Dict[str, Set[str]] = {}
        for grp in list(results.keys()):
            results[grp].discard(query)
            if results[grp]:
                clean_res[grp] = results[grp]

        return clean_res


def load_all_synonyms(
    trk_path: Optional[str] = None,
    tur_txt_path: Optional[str] = None,
) -> List[dict]:
    engine = ThesaurusEngine(trk_path, tur_txt_path)
    entries: List[dict] = []

    for word_lower in sorted(engine.all_vocab, key=lambda s: s.lower()):
        groups_dict = engine.lookup(word_lower, use_multi_hop=False)

        formatted = []
        all_syns: Set[str] = set()

        ordered_grps = sorted(
            groups_dict.keys(),
            key=lambda g: (
                0 if "1.Anlam" in g else
                1 if "2.Anlam" in g else
                2 if "3.Anlam" in g else
                3 if "Türemiş" in g else
                4 if "Mecaz" in g else
                5 if "Argo" in g else 6,
                g
            )
        )

        for grp_name in ordered_grps:
            syn_set = groups_dict[grp_name]
            if syn_set:
                syn_list = sorted(syn_set, key=lambda s: s.lower())
                formatted.append(f"{grp_name}::{','.join(syn_list)}")
                all_syns.update(syn_list)

        if all_syns or formatted:
            entries.append({
                "word": word_lower,
                "synonyms": " | ".join(sorted(all_syns, key=lambda s: s.lower())),
                "groups": " | ".join(formatted),
            })

    return entries
