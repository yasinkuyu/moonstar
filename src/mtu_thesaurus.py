#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtu_thesaurus.py — Geriye dönük uyumluluk sarmalayıcısı (engine.thesaurus modülünü çağırır)
"""

from __future__ import annotations

import os
from typing import List, Optional, Set

from engine.thesaurus import ThesaurusEngine, clean_tr_token

# Geriye dönük uyumluluk için alias
SemanticThesaurus = ThesaurusEngine


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

        entries.append({
            "word": word_lower,
            "synonyms": " | ".join(sorted(all_syns, key=lambda s: s.lower())),
            "groups": " | ".join(formatted),
        })

    return entries


if __name__ == "__main__":
    engine = ThesaurusEngine()
    print("Thesaurus Engine yüklendi.")
    for test_w in ["öz", "kitap", "elma", "ekmek", "gelmek", "yüz", "göz", "akıl", "güzel"]:
        res = engine.lookup(test_w)
        total_syns = sum(len(v) for v in res.values())
        print(f"\n=== \"{test_w}\" ({total_syns} sonuç) ===")
        for g, words in sorted(res.items()):
            w_list = sorted(words)
            print(f"  [{g}] ({len(w_list)}): {', '.join(w_list[:10])}{'...' if len(w_list) > 10 else ''}")
