#! /usr/bin/python3

# mtu_ing.py — MTU.ING Turkish→English Dictionary exporter (Türkçe İngilizce Sözlük)
#
# MTU.ING is decoded by engine.ing, an exact port of the MTU.EXE routine
# FUN_1010_3114. Outputs:
#   output/MTU.ING.TXT          Turkish entry<TAB>English meanings (as the EXE shows them, ' | '-separated)
#   output/MTU.ING.BY_TOPIC.TXT entries whose meanings carry a topic byte, grouped by topic
#
# @yasinkuyu

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.constants import TOPIC_NAMES
from engine.ing import IngDictionary, topic_name


def GetOutputPath(filename):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output', filename)


def Export(entries, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(e["tr"] + "\t" + " | ".join(l["text"].strip() for l in e["labels"]) + "\n")


def ExportByTopic(entries, path):
    by_topic = defaultdict(list)
    for e in entries:
        for l in e["labels"]:
            name = topic_name(l["topic"])
            if name:
                by_topic[name].append((e["tr"], l["text"].strip()))
    with open(path, "w", encoding="utf-8") as f:
        for name in TOPIC_NAMES:
            if name not in by_topic:
                continue
            f.write(f"=== {name} ({len(by_topic[name])}) ===\n")
            for tr, en in by_topic[name]:
                f.write(f"{tr}\t{en}\n")
            f.write("\n")
    return by_topic


def main():
    entries = IngDictionary().all_entries()
    Export(entries, GetOutputPath("MTU.ING.TXT"))
    by_topic = ExportByTopic(entries, GetOutputPath("MTU.ING.BY_TOPIC.TXT"))
    labels = sum(len(e["labels"]) for e in entries)
    print(f"Exported {len(entries)} Türkçe→İngilizce entries ({labels} meanings).")
    print(f"Exported {sum(len(v) for v in by_topic.values())} topic-tagged meanings in {len(by_topic)} topics.")


if __name__ == "__main__":
    main()
