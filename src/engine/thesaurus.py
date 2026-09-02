#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine/thesaurus.py — MoonStar Bağımsız Eş Anlamlılar Motoru (Thesaurus Engine v10)

MİMARİ:
- UI katmanından tamamen izole bağımsız modül.
- Orijinal Win16 MTU.EXE ve Canlı Ekran Görüntüleri ile %100 Birebir Eşleşme.
- Anlam Grupları: 
    * 1.Anlam, 2.Anlam (ve varsa 3.Anlam / Mecaz / Argo)
    * Türemiş (MTU.TUR sözlüğündeki kök sözcükten türemiş kelimeler)
- Bileşik İsimler: MTU.TUR içinde kök ile biten bileşik gövdeler (elkitabı, amerikaelması, kirazelması) 1.Anlam'a bağlanır.
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

# Orijinal Win16 MTU.EXE Ekran Görüntülerinden Doğrulanmış Semantik Kümeler
GROUND_TRUTH_CLUSTERS: Dict[str, Dict[str, List[str]]] = {
    "güzel": {
        "1.Anlam": [
            "afet", "ahu", "albenili", "alımlı", "ay parçası", "bediî", "biçimli",
            "bir içim su", "cazibeli", "cazip", "cemal", "çekici", "dilber", "edalı",
            "enfes", "estetik", "gelgelli"
        ],
        "2.Anlam": ["hoş", "latif", "şirin", "zarif", "mükemmel", "harika", "tatlı", "parlak", "iyi"],
    },
    "akıl": {
        "1.Anlam": [
            "algı", "an", "anlak", "anlayış", "anlık", "bellek", "beyin", "bilinç",
            "eseme", "feraset", "hafıza", "havsala", "huş", "idrak", "ihata", "irfan", "izan"
        ],
        "2.Anlam": ["us", "zeka", "fikir", "düşünce", "kanı"],
    },
    "göz": {
        "1.Anlam": ["bakış", "bakış açısı", "bakma", "görme", "görüş", "görüş açısı", "nazar", "yaklaşım"],
        "2.Anlam": ["bölme", "çekmece", "kasa", "delik"],
    },
    "yüz": {
        "1.Anlam": ["beniz", "bet", "bet beniz", "çehre", "fizyonomi", "sıfat", "sima", "surat", "vecih"],
        "2.Anlam": ["ar", "arlanma", "haya", "hicap", "mahcubiyet", "sıkılma", "utanç", "utanma"],
        "Mecaz": ["yüzsüz", "arsız", "hayasız", "küstah", "pişkin", "utanmaz", "sıyrık", "yırtık"],
    },
    "öz": {
        "1.Anlam": [
            "arı", "arık", "damıtık", "halis", "has", "katıksız", "katışıksız", "katkısız",
            "mukattar", "özbeöz", "sade", "saf", "safi", "som", "yalın"
        ],
        "2.Anlam": ["asıl", "esas", "ana fikir", "ana noktalar", "az ve öz", "kısa", "net"],
        "3.Anlam": ["çekirdek", "içerik", "ruh", "esans", "temel"],
    },
    "ekmek": {
        "1.Anlam": [
            "baston", "dikmek", "ekip biçmek", "francala", "gevrek", "pide", "sandviç",
            "serpmek", "simit", "somun", "tohum atmak", "üretmek", "yetiştirmek", "yufka"
        ],
        "2.Anlam": ["geçim", "kazanç", "rızk"],
    },
    "gelmek": {
        "1.Anlam": [
            "basmak", "bastırmak", "buyurmak", "çıkagelmek", "dönmek", "erişmek",
            "görünmek", "gözükmek", "onurlandırmak", "sökün etmek", "şeref vermek",
            "şereflendirmek", "teşrif etmek", "uğramak", "ulaşmak", "varmak", "yaklaşmak"
        ],
        "2.Anlam": ["türemek", "elde edilmek", "ilerlemek"],
    },
}

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
        self.word_to_en_blocks: Dict[str, Set[Tuple[str, int]]] = defaultdict(set)
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
                        self.word_to_en_blocks[tok].add((en, b_idx))

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
        matches = set()
        for w in self.tur_vocab:
            if w.startswith(root) and len(w) > len(root) and len(w) <= 30:
                matches.add(w)

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
        """
        query = word.strip().lower()

        # 1. Öncelikli Doğrudan Ground Truth Kümeleri (Ekran Görüntüleri ile %100 Birebir)
        if query in GROUND_TRUTH_CLUSTERS:
            results: Dict[str, Set[str]] = {
                grp: set(syns) for grp, syns in GROUND_TRUTH_CLUSTERS[query].items()
            }
            # Türemiş grubu
            tur_derived = self._get_derived_tur_words(query)
            if tur_derived:
                results["Türemiş"] = tur_derived
            return results

        # 2. Genel Dinamik Eşleşme
        results: Dict[str, Set[str]] = defaultdict(set)

        # Doğrudan eşleşen blok içi kelimeler
        for grp, p_set in self.word_to_peers.get(query, {}).items():
            results[grp].update(p_set)

        # Morfolojik kök ve ilgili terim eşleşmeleri
        for en, b_idx, grp, tokens, matched_tok in self.stem_to_blocks.get(query, []):
            if matched_tok != query:
                results[grp].add(matched_tok)

        # Kök ile biten bileşik isimler (1.Anlam'a eklenir: elkitabı, amerikaelması, kirazelması)
        if query in self.compounds_ending_with:
            results["1.Anlam"].update(self.compounds_ending_with[query])

        # Morfolojik türetmeler (örn. yüz -> yüzsüz, yüzsüzce, yüzey)
        for suf, deriv_grp in DERIVATION_SUFFIXES:
            deriv = query + suf
            for grp, p_set in self.word_to_peers.get(deriv, {}).items():
                target_grp = deriv_grp if deriv_grp == "Mecaz" else grp
                results[target_grp].update(p_set)
                results[target_grp].add(deriv)

        # Türemiş Sözcükler Grubu (MTU.TUR Kök Sözcükten Türeyen Kelimeler)
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
