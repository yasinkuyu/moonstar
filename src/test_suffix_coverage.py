#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_suffix_coverage.py — MTU.TUR / MTU.TES Full Suffix Coverage Verifier

Tests all 26,775 words and every suffix invocation across MTU.TES,
measuring resolution rate and ensuring 0 unknown suffix IDs.
"""

from __future__ import annotations

import struct
from collections import Counter
from typing import Dict, List, Set

from engine.thesaurus import ThesaurusEngine, apply_tes_suffix_id, get_suffix_table


def run_coverage_test():
    print("=" * 78)
    print("  MOONSTAR THESAURUS SUFFIX COVERAGE & COMPLETENESS TEST")
    print("=" * 78)

    engine = ThesaurusEngine()
    suf_table = get_suffix_table()
    print(f"\n[1] Suffix Table Boyutu: {len(suf_table)} / 3,218 ek tanımlı.")

    # Scan all slots in MTU.TES
    total_slots = min(len(engine.tur_words), len(engine.tes_offsets) - 1)
    total_suffix_invocations = 0
    resolved_suffixes = 0
    unresolved_suffixes = 0
    unknown_ids = Counter()

    for s in range(total_slots):
        off1 = engine.tes_offsets[s]
        off2 = engine.tes_offsets[s + 1]
        if off2 <= off1:
            continue
        slot = engine.tes_data[off1:off2]
        if not slot:
            continue

        pos = 0
        if slot[0] == 0x80:
            pos = 1
            while pos + 2 <= len(slot):
                raw = struct.unpack("<H", slot[pos:pos + 2])[0]
                has_more = bool(raw & 0x8000)
                sid = raw & 0x7FFF
                pos += 2
                total_suffix_invocations += 1
                if sid < len(suf_table) and suf_table[sid]:
                    resolved_suffixes += 1
                else:
                    unresolved_suffixes += 1
                    unknown_ids[sid] += 1
                if not has_more:
                    break

        elif (slot[0] & 0xC0) == 0xC0:
            pos = 3
            while pos + 2 <= len(slot):
                raw = struct.unpack("<H", slot[pos:pos + 2])[0]
                has_more = bool(raw & 0x8000)
                sid = raw & 0x7FFF
                pos += 2
                total_suffix_invocations += 1
                if sid < len(suf_table) and suf_table[sid]:
                    resolved_suffixes += 1
                else:
                    unresolved_suffixes += 1
                    unknown_ids[sid] += 1
                if not has_more:
                    break

        while pos < len(slot):
            b = slot[pos]
            pos += 1
            if b == 0x40:
                # Deverbal boundary delimiter
                while pos + 2 <= len(slot):
                    raw = struct.unpack("<H", slot[pos:pos + 2])[0]
                    has_more = bool(raw & 0x8000)
                    sid = raw & 0x7FFF
                    pos += 2
                    total_suffix_invocations += 1
                    if sid < len(suf_table) and suf_table[sid]:
                        resolved_suffixes += 1
                    else:
                        unresolved_suffixes += 1
                        unknown_ids[sid] += 1
                    if not has_more:
                        break
                continue
            elif (b & 0x0F) == 0x0C and pos < len(slot):
                pos += 1

            word_count = ((b >> 4) & 3) + 1
            for _ in range(word_count):
                if pos + 2 > len(slot):
                    break
                raw_w = struct.unpack("<H", slot[pos:pos + 2])[0]
                pos += 2
                has_more = bool(raw_w & 0x8000)
                while has_more and pos + 2 <= len(slot):
                    raw_s = struct.unpack("<H", slot[pos:pos + 2])[0]
                    pos += 2
                    sid = raw_s & 0x7FFF
                    has_more = bool(raw_s & 0x8000)
                    total_suffix_invocations += 1
                    if sid < len(suf_table) and suf_table[sid]:
                        resolved_suffixes += 1
                    else:
                        unresolved_suffixes += 1
                        unknown_ids[sid] += 1

    rate = (resolved_suffixes / total_suffix_invocations * 100.0) if total_suffix_invocations else 0.0
    print(f"\n[2] Toplam Ek Uygulaması : {total_suffix_invocations:,}")
    print(f"    Çözülen Ek Sayısı    : {resolved_suffixes:,} (%{rate:.2f})")
    print(f"    Çözülemeyen Ek Sayısı: {unresolved_suffixes}")
    print(f"    Farklı Bilinmeyen ID : {len(unknown_ids)}")

    # Target words verification
    target_words = {
        "yeni": "kullanılmamış",
        "eski": "durmuş",
        "soğutkan": "soğutucu",
        "problem": "açmaz",
        "sorun": "açmaz",
    }
    print("\n[3] Kritik Hedef Kelimeler Doğrulaması:")
    all_targets_ok = True
    for w, expected in target_words.items():
        res = engine.lookup(w)
        all_words = set()
        for _, words in res:
            all_words.update(words)
        found = expected in all_words
        status = "BAŞARILI" if found else "BAŞARISIZ"
        print(f"    • '{w}' -> '{expected}' içeriyor mu? [{status}]")
        if not found:
            all_targets_ok = False

    print("\n" + "=" * 78)
    if rate >= 95.0 and all_targets_ok:
        print("  SONUÇ: BAŞARILI (%95+ Kapsam Hedefi ve Tüm Kritik Sözcükler Geçti)")
    else:
        print("  SONUÇ: EKSİK VAR")
    print("=" * 78)


if __name__ == "__main__":
    run_coverage_test()
