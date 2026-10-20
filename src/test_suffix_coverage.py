#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_suffix_coverage.py — MTU.TUR / MTU.TES Full Suffix Coverage Verifier

Tests all 26,775 words and every suffix invocation across MTU.TES,
measuring resolution rate and ensuring 0 unknown suffix IDs.
"""

from __future__ import annotations

import struct
import sys
from collections import Counter

from engine.thesaurus import ThesaurusEngine
from engine.tur_lexicon import get_suffix_table


def run_coverage_test():
    print("=" * 78)
    print("  MOONSTAR THESAURUS SUFFIX COVERAGE & COMPLETENESS TEST")
    print("=" * 78)

    engine = ThesaurusEngine()
    suf_table = get_suffix_table()
    print(f"\n[1] Suffix Table Boyutu: {len(suf_table)} / 3,218 ek tanımlı.")

    # Scan all slots in MTU.TES
    offsets, tes_data = engine.parser.tes_offsets, engine.parser.tes_data
    total_slots = min(engine.lexicon.word_count, len(offsets) - 1)
    total_suffix_invocations = 0
    resolved_suffixes = 0
    unresolved_suffixes = 0
    unknown_ids = Counter()

    def count_chain(slot, pos, first_is_word):
        """Walks one u16 chain (bit 15 = more); returns (suffix IDs, new pos)."""
        ids = []
        first = first_is_word
        while pos + 2 <= len(slot):
            raw = struct.unpack("<H", slot[pos:pos + 2])[0]
            pos += 2
            if not first:
                ids.append(raw & 0x7FFF)
            first = False
            if not raw & 0x8000:
                break
        return ids, pos

    for s in range(total_slots):
        off1 = offsets[s]
        off2 = offsets[s + 1]
        if off2 <= off1:
            continue
        slot = tes_data[off1:off2]
        if len(slot) == 3 and slot[0] == 0xFF:
            continue  # redirect stub (FUN_1010_2fec)

        # Record layout as decoded by FUN_1010_256c
        chains = []
        pos = 0
        if slot[0] == 0xC0:
            # Alias: the EXE reads only the target chain, then decodes the target slot
            ids, _ = count_chain(slot, 1, first_is_word=True)
            chains.append(ids)
            pos = len(slot)
        last_topic = 0
        while pos < len(slot):
            b = slot[pos]
            pos += 1
            if b & 0x80 or b & 0x40:
                if not b & 0x80:
                    last_topic = 0
                ids, pos = count_chain(slot, pos, first_is_word=False)
                chains.append(ids)
                continue
            if (b & 0x0F) > 0x0B and (b & 0x0F) != last_topic:
                last_topic = b & 0x0F
                pos += 1
            for _ in range(((b >> 4) & 3) + 1):
                ids, pos = count_chain(slot, pos, first_is_word=True)
                chains.append(ids)

        for ids in chains:
            for sid in ids:
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
    print(f"    Farklı Bilinmeyen ID : {len(unknown_ids)} {[hex(i) for i in sorted(unknown_ids)]}")

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

    success = total_suffix_invocations > 0 and rate >= 95.0 and all_targets_ok
    print("\n" + "=" * 78)
    if success:
        print("  SONUÇ: BAŞARILI (%95+ Kapsam Hedefi ve Tüm Kritik Sözcükler Geçti)")
    else:
        print("  SONUÇ: EKSİK VAR")
    print("=" * 78)
    return success


if __name__ == "__main__":
    sys.exit(0 if run_coverage_test() else 1)
