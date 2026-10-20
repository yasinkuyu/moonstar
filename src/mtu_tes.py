#! /usr/bin/python3

# mtu_tes.py
#
# Exports MTU.TES, the Turkish thesaurus database used by the
# "Türkçe Eş Anlamlı Sözcükler" window (TES = Türkçe Eş Anlamlı Sözcükler).
#
# MTU.TES is a 32,000-slot offset table (32,000 * 3-byte pointers) whose slots
# map 1-to-1 to the MTU.TUR word list. All binary decoding is done by
# engine.thesaurus.ThesaurusEngine; this script is only a thin exporter.
#
# Output format (output/MTU.TES.TXT), one headword per line:
#     word<TAB>group::syn1,syn2,... | group::syn1,...
#
# @yasinkuyu

import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from engine.thesaurus import load_all_synonyms

def Export(entries, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for entry in entries:
            file.write(entry["word"])
            file.write('\t')
            file.write(entry["groups"])
            file.write('\n')

def main():
    output_path = os.path.join(script_dir, "..", "output", "MTU.TES.TXT")
    entries = load_all_synonyms()  # already in the EXE's sort order (FUN_1010_2e13)
    Export(entries, output_path)
    print("Exported", len(entries), "thesaurus entries from MTU.TES.")

if __name__ == "__main__":
    main()
