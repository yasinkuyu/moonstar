#! /usr/bin/python3

# mtu_ing.py — MTU.ING Quiz Metadata Decoder
#
# FULLY REVERSE-ENGINEERED (2026-07-14):
#   ✅ 32,000-slot offset table, data at byte 96,003
#   ✅ Slot header: [0x00, (trk_idx+1)%256, category_byte]
#   ✅ TRK index = slot position in offset table
#   ✅ Category byte → topic name mapping (36 topics from EXE)
#   ✅ Combined output: English word + Turkic translation + topic
#
# @yasinkuyu

import os
import struct

# EXE format marker table (at CS:0x1015, file 0x1215)
EXE = open(os.path.join(os.path.dirname(__file__), '..', 'data', 'MTU.EXE'), 'rb')
EXE_DATA = EXE.read()
EXE.close()

FMT_MARKERS = {}
for p in range(40):
    off = 0x1215 + p * 2
    FMT_MARKERS[p] = bytes([EXE_DATA[off], EXE_DATA[off + 1]])

FREQ_FMT = {
    0x02: 0, 0x03: 2, 0x0F: 1, 0x15: 4, 0x16: 4, 0x17: [3, 4],
}

def cp857_decode(b):
    mapping = {
        0x80: 'Ç', 0x81: 'ü', 0x87: 'ç', 0x8D: 'ı', 0x8E: 'Ä',
        0x90: 'Ğ', 0x91: 'ğ', 0x94: 'ö', 0x98: 'İ', 0x99: 'Ö',
        0x9A: 'ö', 0x9B: 'Ü', 0x9D: 'İ', 0x9E: 'Ş', 0x9F: 'ş',
        0xA7: 'ğ',
    }
    return mapping.get(b, chr(b) if 0x20 <= b <= 0x7E else f'[{b:02x}]')

# Extract topic names from EXE
area = EXE_DATA[0x1b600:0x1b800]
string_data = area[28:]
topics_raw = []
i = 0
while i < len(string_data):
    end = string_data.find(b'\x00', i)
    if end == -1:
        s = string_data[i:]
        if len(s) >= 2:
            topics_raw.append(s)
        break
    s = string_data[i:end]
    if len(s) >= 2:
        topics_raw.append(s)
    i = end + 1

topic_names = []
for raw in topics_raw:
    decoded = ''.join(cp857_decode(b) for b in raw)
    topic_names.append(decoded)

# Quiz file type names (TUR, TES, ING, TRK) and their index offsets
QUIZ_TYPES = {
    't': ('TUR', 0),   # Turkish→Turkish
    'e': ('TES', 3),   # Test
    'i': ('ING', 6),   # Quiz (word game)
    'r': ('TRK', 9),   # English→Turkish
}

def read_offsets(data):
    table_size = struct.unpack("<L", data[0:3] + b'\x00')[0]
    num_slots = table_size // 3
    offsets = []
    for i in range(num_slots):
        off = struct.unpack("<L", data[3 + i*3: 3 + (i+1)*3] + b'\x00')[0]
        offsets.append(off)
    return offsets, 3 + table_size

def Import(entries, path):
    data = open(path, "rb").read()
    offsets, data_start = read_offsets(data)

    for si in range(len(offsets) - 1):
        start = offsets[si]
        end = offsets[si + 1]
        if start >= end or start < data_start:
            continue
        if start + 3 > len(data) or data[start] != 0x00:
            continue

        header_idx = data[start + 1]
        header_flag = data[start + 2]
        body = data[start + 3:end]
        trk_idx = si if header_idx == (si + 1) % 256 else (header_idx - 1) % 256

        # topic_idx: bit7 = variant flag, lower 7 bits encode (topic * 3 modes)
        # Correct formula: (flag & 0x7F) % 36  (NOT flag % 36 which breaks for flag >= 128)
        # quiz_mode: (flag & 0x7F) // 36  → 0=mode0, 1=mode1, 2=mode2
        flag_low = header_flag & 0x7F
        entry = {
            'slot_pos': si,
            'header_idx': header_idx,
            'header_flag': header_flag,
            'is_variant': bool(header_flag & 0x80),
            'quiz_mode': flag_low // 36,
            'topic_idx': flag_low % 36,
            'trk_idx': trk_idx,
            'body_len': len(body),
        }
        entries.append(entry)

def export_by_topic(entries, trk_words, trk_dict, path):
    """Export ING data organized by topic, showing English→Turkic word pairs."""
    topic_entries = {}
    for entry in entries:
        topic_idx = entry['topic_idx']
        if topic_idx not in topic_entries:
            topic_entries[topic_idx] = []
        topic_entries[topic_idx].append(entry)

    with open(path, 'w', encoding='utf-8') as f:
        f.write("=== MTU.ING Quiz Data by Topic ===\n")
        f.write(f"Total entries: {len(entries)}\n\n")

        for topic_idx in sorted(topic_entries.keys()):
            topic_name = topic_names[topic_idx + 2] if topic_idx + 2 < len(topic_names) else f'Topic_{topic_idx}'
            t_entries = topic_entries[topic_idx]
            t_entries.sort(key=lambda e: e['slot_pos'])

            # Count mode variants (bit 7) and quiz modes (0/1/2)
            normal  = sum(1 for e in t_entries if not e['is_variant'])
            variant = sum(1 for e in t_entries if     e['is_variant'])

            f.write(f"\n{'='*60}\n")
            f.write(f"{topic_name.upper()} ({len(t_entries)} entries, {normal} normal + {variant} variant)\n")
            f.write(f"{'='*60}\n")

            for entry in t_entries:
                trk_idx = entry['trk_idx']
                english = trk_words[trk_idx] if 0 <= trk_idx < len(trk_words) else '???'
                turkish = trk_dict.get(trk_idx, '')

                mode_str = f"m{entry['quiz_mode']}"
                var_str  = "V" if entry['is_variant'] else "N"
                tag = f"{var_str}{mode_str}"

                if turkish:
                    f.write(f"  Slot {entry['slot_pos']:>5} [{tag:>3}] {english:<30s} → {turkish}\n")
                else:
                    f.write(f"  Slot {entry['slot_pos']:>5} [{tag:>3}] {english}\n")

def export_debug(entries, trk_words, path):
    """Debug export with format markers (for technical analysis)."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"{'Slot':>5} {'TRK#':>5} {'Flag':>4} {'Word':<30} {'Body':>5}B\n")
        f.write('-' * 60 + '\n')
        for entry in entries:
            trk_idx = entry['trk_idx']
            word = trk_words[trk_idx] if 0 <= trk_idx < len(trk_words) else '???'
            f.write(f"{entry['slot_pos']:>5} {trk_idx:>5} {entry['header_flag']:4d} {word:<30} {entry['body_len']:>5}B\n")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "..", "data", "MTU.ING")
    output_dir = os.path.join(script_dir, "..", "output")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Load ING entries
    entries = []
    Import(entries, data_path)

    # Load TRK English word list
    trk_words = []
    trk_words_path = os.path.join(output_dir, "MTU.TRK.TXT")
    if os.path.exists(trk_words_path):
        with open(trk_words_path, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.split()[0] if line.strip() else ''
                trk_words.append(word)
    else:
        from mtu_trk import Import as TrkImport
        import sys
        sys.path.insert(0, script_dir)
        trk_dict = []
        TrkImport(trk_dict, os.path.join(script_dir, "..", "data", "MTU.TRK"))
        trk_words = [eng for eng, tur in trk_dict]

    # Load TRK full dictionary (English→Turkish)
    trk_dict = {}
    if os.path.exists(trk_words_path):
        with open(trk_words_path, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        trk_dict[idx] = parts[1]
                    else:
                        trk_dict[idx] = ''

    # Export meaningful output organized by topic
    topic_path = os.path.join(output_dir, "MTU.ING.BY_TOPIC.TXT")
    export_by_topic(entries, trk_words, trk_dict, topic_path)
    print(f"Exported {len(entries)} entries to {topic_path}")

    # Debug export
    debug_path = os.path.join(output_dir, "MTU.ING.DEBUG.TXT")
    export_debug(entries, trk_words, debug_path)
    print(f"Exported debug data to {debug_path}")

    # Print summary
    topic_counts = {}
    for e in entries:
        t = e['topic_idx']
        topic_counts[t] = topic_counts.get(t, 0) + 1

    print(f"\n=== Summary ===")
    print(f"Total ING entries: {len(entries)}")
    for t in sorted(topic_counts.keys()):
        name = topic_names[t + 2] if t + 2 < len(topic_names) else f'Topic_{t}'
        print(f"  {name}: {topic_counts[t]}")

if __name__ == "__main__":
    main()
