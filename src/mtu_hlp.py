#! /usr/bin/python3
# -*- coding: utf-8 -*-

# mtu_hlp.py
#
# Exports MTU.HLP, the Windows Help file opened by the "Yardım" menu (F1).
#
# MTU.HLP is a WinHelp 3.0 file (HC30, |SYSTEM minor version 15). The parser
# below reads the format directly, using only the standard library:
#
#   HFS         file header "?_\x03\x00", B+ tree directory of internal files
#   |SYSTEM     version, date, help title (empty in MTU.HLP)
#   |Phrases    HC30 phrase table: count, 0x0100, offsets, phrase text
#   |TOPIC      2,048-byte blocks (12-byte header, no LZ77 in HC30) holding
#               TOPICLINK records: 2 = topic header (title), 1 = display text.
#               LinkData1 = paragraph info + formatting commands,
#               LinkData2 = text, phrase-compressed when DataLen2 is larger
#               than the stored size; every NUL in the text is the place of
#               the next formatting command.
#   |TOMAP      topic number -> topic position (jumps 0xE0/0xE1 use numbers)
#   |TTLBTREE   topic position -> title
#   |CTXOMAP    WinHelp context numbers ([MAP]) -> topic number
#   |FONT       face names and font descriptors (bold / italic / underline)
#
# HC30 files have no |CONTEXT (context strings are not stored) and MTU.HLP
# has no |KWBTREE / |KWDATA, so the keyword index is empty.
#
# Text is Windows-1254 (Turkish). The help compiler also wrote some letters
# with an older Turkish layout in the 0x9A-0x9F range (|Phrases, "A.\x9c.");
# those are mapped through LEGACY_TURKISH before decoding.
#
# Output:
#     output/MTU.HLP.TXT   every topic with its title and paragraphs,
#                          jumps marked as [[link text|target topic title]]
#     output/MTU.HLP.json  {"title", "index_topic", "contexts", "topics": [
#                          {"number", "title", "context", "paragraphs":
#                          [[{"text", "link", "bold", "italic"}...]...]}],
#                          "keywords": {}}
#
# @yasinkuyu

import json
import os
import struct
import sys

HFS_MAGIC = 0x00035F3F
BTREE_MAGIC = 0x293B
SYSTEM_MAGIC = 0x036C
TOPIC_BLOCK = 2048          # HC30 topic block size
TOPIC_BLOCK_HEADER = 12     # LastTopicLink, FirstTopicLink, LastTopicHeader
TOPICLINK_SIZE = 21         # BlockSize, DataLen2, PrevBlock, NextBlock, DataLen1, RecordType
TL_DISPLAY30 = 0x01
TL_TOPICHDR = 0x02

# Letters stored outside Windows-1254 (0x9C = Ş from "A.Ş.", the others from |Phrases)
LEGACY_TURKISH = {0x9A: "İ", 0x9B: "ı", 0x9C: "Ş", 0x9D: "ş", 0x9F: "ğ"}


def decode_text(raw):
    out = []
    for b in raw:
        if b in LEGACY_TURKISH:
            out.append(LEGACY_TURKISH[b])
        else:
            out.append(bytes([b]).decode("cp1254", errors="replace"))
    return "".join(out)


def read_cstring(data, pos):
    end = data.index(b"\0", pos)
    return data[pos:end], end + 1


# ---------------------------------------------------------------- HFS / B+ tree

def read_internal(data, offset):
    """Internal file: u32 reserved space, u32 used space, u8 flags, content."""
    _, used, _ = struct.unpack_from("<IIB", data, offset)
    return data[offset + 9:offset + 9 + used]


def btree_leaves(blob, parse_entry):
    """Yields (key, value) of every leaf entry of a WinHelp B+ tree."""
    magic, _, page_size = struct.unpack_from("<HHH", blob, 0)
    if magic != BTREE_MAGIC:
        raise ValueError("not a B+ tree")
    _, _, root, _, _, levels, _ = struct.unpack_from("<HHHhHHI", blob, 22)
    pages = 38
    page = root
    for _ in range(levels - 1):                  # leftmost child down to the leaves
        page = struct.unpack_from("<h", blob, pages + page * page_size + 4)[0]
    while page != -1:
        base = pages + page * page_size
        _, count, _, next_page = struct.unpack_from("<HHhh", blob, base)
        pos = base + 8
        for _ in range(count):
            key, value, pos = parse_entry(blob, pos)
            yield key, value
        page = next_page


def read_directory(data):
    magic, directory, _, size = struct.unpack_from("<IiiI", data, 0)
    if magic != HFS_MAGIC:
        raise ValueError("not a WinHelp file")
    if size != len(data):
        raise ValueError("file size %d, header says %d" % (len(data), size))

    def entry(blob, pos):
        name, pos = read_cstring(blob, pos)
        return name.decode("latin-1"), struct.unpack_from("<I", blob, pos)[0], pos + 4

    return dict(btree_leaves(read_internal(data, directory), entry))


# ---------------------------------------------------------------- small files

def parse_system(blob):
    magic, minor, major, gen_date, flags = struct.unpack_from("<HHHIH", blob, 0)
    if magic != SYSTEM_MAGIC:
        raise ValueError("bad |SYSTEM magic")
    title = b""
    if minor <= 16:                              # HC30: the title follows the header
        title, _ = read_cstring(blob, 12)
    return {"minor": minor, "major": major, "date": gen_date, "flags": flags,
            "title": decode_text(title)}


def parse_phrases(blob):
    if not blob:
        return []
    count, one_hundred = struct.unpack_from("<HH", blob, 0)
    if one_hundred != 0x0100:
        raise ValueError("unsupported |Phrases layout")
    offsets = struct.unpack_from("<%dH" % (count + 1), blob, 4)
    return [blob[4 + offsets[i]:4 + offsets[i + 1]] for i in range(count)]


def parse_tomap(blob):
    """Topic number -> position. Entry 0 is the index (contents) topic."""
    return list(struct.unpack_from("<%di" % (len(blob) // 4), blob))


def parse_ctxomap(blob):
    count = struct.unpack_from("<H", blob, 0)[0]
    return [struct.unpack_from("<iI", blob, 2 + i * 8) for i in range(count)]


def parse_titles(blob):
    def entry(b, pos):
        key = struct.unpack_from("<i", b, pos)[0]
        title, pos = read_cstring(b, pos + 4)
        return key, decode_text(title), pos
    return dict(btree_leaves(blob, entry))


def parse_fonts(blob):
    """Font descriptor list: {"face", "half_points", "bold", "italic", "underline"}."""
    _, count, face_off, desc_off = struct.unpack_from("<4H", blob, 0)
    fonts = []
    for i in range(count):
        attr, half_points, _family, face = struct.unpack_from("<BBBH", blob, desc_off + i * 11)
        name = blob[face_off + face * 20:face_off + face * 20 + 20].split(b"\0")[0]
        fonts.append({"face": name.decode("latin-1"), "half_points": half_points,
                      "bold": bool(attr & 1), "italic": bool(attr & 2),
                      "underline": bool(attr & 4)})
    return fonts


# ---------------------------------------------------------------- |TOPIC

def topic_links(topic):
    """Walks the TOPICLINK chain. Positions are offsets in |TOPIC (block headers
    included); a link never starts in the last 21 bytes of a block."""
    def to_linear(pos):
        return pos - TOPIC_BLOCK_HEADER * (pos // TOPIC_BLOCK + 1)

    def to_pos(linear):
        step = TOPIC_BLOCK - TOPIC_BLOCK_HEADER
        return (linear // step) * TOPIC_BLOCK + linear % step + TOPIC_BLOCK_HEADER

    stream = b"".join(topic[i + TOPIC_BLOCK_HEADER:i + TOPIC_BLOCK]
                      for i in range(0, len(topic), TOPIC_BLOCK))
    pos = struct.unpack_from("<i", topic, 4)[0]  # FirstTopicLink of block 0
    while True:
        if TOPIC_BLOCK - pos % TOPIC_BLOCK < TOPICLINK_SIZE:
            pos = (pos // TOPIC_BLOCK + 1) * TOPIC_BLOCK + TOPIC_BLOCK_HEADER
        if pos >= len(topic):
            return
        lin = to_linear(pos)
        size, len2, _, _, len1, rtype = struct.unpack_from("<iiiiiB", stream, lin)
        if size <= 0:
            raise ValueError("bad TOPICLINK at 0x%X" % pos)
        yield pos, rtype, stream[lin + TOPICLINK_SIZE:lin + len1], stream[lin + len1:lin + size], len2
        pos = to_pos(lin + size)


def expand_phrases(raw, size, phrases):
    """HC30 phrase compression: byte 1..15 + next byte = phrase number n,
    phrase n // 2, followed by a space when n is odd."""
    if size <= len(raw):
        return raw
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if 0 < c < 16:
            n = 256 * (c - 1) + raw[i + 1]
            out += phrases[n // 2]
            if n & 1:
                out += b" "
            i += 2
        else:
            out.append(c)
            i += 1
    if len(out) != size:
        raise ValueError("phrase expansion gave %d bytes, expected %d" % (len(out), size))
    return bytes(out)


def scan_word(b, i):
    """Compressed unsigned short: 1 byte (value*2) or 2 bytes (value*2+1)."""
    if b[i] & 1:
        return struct.unpack_from("<H", b, i)[0] >> 1, i + 2
    return b[i] >> 1, i + 1


def scan_long(b, i):
    """Compressed signed long: 2 bytes biased by 0x4000 or 4 bytes by 0x40000000."""
    w = struct.unpack_from("<H", b, i)[0]
    if w & 1:
        return (struct.unpack_from("<I", b, i)[0] >> 1) - 0x40000000, i + 4
    return (w >> 1) - 0x4000, i + 2


def scan_short(b, i):
    """Compressed signed short: biased by 0x40 / 0x4000."""
    v, j = scan_word(b, i)
    return v - (0x4000 if j - i == 2 else 0x40), j


def format_commands(ld1):
    """Paragraph info + formatting commands of a display record (HC30)."""
    _, i = scan_long(ld1, 0)                     # size of the rest of LinkData1
    i += 4                                       # unknown byte, biased byte, id
    bits = struct.unpack_from("<H", ld1, i)[0]
    i += 2
    if bits & 0x0001:
        _, i = scan_long(ld1, i)
    for bit in (0x0002, 0x0004, 0x0008, 0x0010, 0x0020, 0x0040):
        if bits & bit:                           # spacing above/below/lines, indents
            _, i = scan_short(ld1, i)
    if bits & 0x0100:                            # border: flags + width
        i += 3
    if bits & 0x0200:                            # tab stops
        n, i = scan_short(ld1, i)
        for _ in range(n):
            stop, i = scan_word(ld1, i)
            if stop & 0x4000:
                _, i = scan_word(ld1, i)
    cmds = []
    while i < len(ld1):
        c = ld1[i]
        i += 1
        if c == 0xFF:
            cmds.append(("end", None))
            break
        if c == 0x80:                            # font change
            cmds.append(("font", struct.unpack_from("<h", ld1, i)[0]))
            i += 2
        elif c == 0x81:
            cmds.append(("line", None))
        elif c == 0x82:
            cmds.append(("par", None))
        elif c == 0x83:
            cmds.append(("tab", None))
        elif c in (0x8B, 0x8C):                  # non-breaking space / hyphen
            cmds.append(("char", " " if c == 0x8B else "-"))
        elif c in (0xE0, 0xE1):                  # HC30 popup / jump to topic number
            cmds.append(("popup" if c == 0xE0 else "jump", struct.unpack_from("<i", ld1, i)[0]))
            i += 4
        elif c == 0x89:
            cmds.append(("endlink", None))
        elif c == 0x20:
            cmds.append(("vfld", None))
            i += 4
        elif c == 0x21:
            cmds.append(("dtype", None))
            i += 2
        elif c in (0x86, 0x87, 0x88):            # embedded picture
            i += 1
            w = struct.unpack_from("<H", ld1, i)[0]
            size = (struct.unpack_from("<I", ld1, i)[0] if w & 1 else w) >> 1
            i += 4 if w & 1 else 2
            cmds.append(("picture", size))
            i += size
        elif c in (0xC8, 0xCC):                  # macro
            n = struct.unpack_from("<h", ld1, i)[0]
            cmds.append(("macro", ld1[i + 2:i + 2 + n]))
            i += 2 + n
        else:
            raise ValueError("unknown formatting command 0x%02X" % c)
    return cmds


def display_paragraphs(ld1, text, fonts, font_state):
    """Splits a display record into paragraphs of runs. Text segment k (up to
    the k-th NUL) is followed by formatting command k."""
    cmds = format_commands(ld1)
    segments = text.split(b"\0")
    if len(segments) != len(cmds) + 1 or segments[-1]:
        raise ValueError("text/command mismatch")
    paragraphs, runs = [], []
    link = None
    for seg, (cmd, arg) in zip(segments, cmds + [("eof", None)]):
        if seg:
            add_run(runs, decode_text(seg), link, fonts, font_state[0])
        if cmd == "font":
            font_state[0] = arg
        elif cmd == "par":
            paragraphs.append(runs)
            runs = []
        elif cmd == "line":
            add_run(runs, "\n", link, fonts, font_state[0])
        elif cmd == "tab":
            add_run(runs, "\t", link, fonts, font_state[0])
        elif cmd == "char":
            add_run(runs, arg, link, fonts, font_state[0])
        elif cmd in ("jump", "popup"):
            link = (cmd, arg)
        elif cmd == "endlink":
            link = None
        elif cmd in ("vfld", "dtype", "picture", "macro"):
            raise ValueError("unhandled command %s" % cmd)
    if runs:
        paragraphs.append(runs)
    return paragraphs


def add_run(runs, text, link, fonts, font):
    style = fonts[font] if 0 <= font < len(fonts) else {}
    run = {"text": text, "link": link,
           "bold": style.get("bold", False), "italic": style.get("italic", False)}
    last = runs[-1] if runs else None
    if last and all(last[k] == run[k] for k in ("link", "bold", "italic")):
        last["text"] += text
    else:
        runs.append(run)


# ---------------------------------------------------------------- whole file

def parse_hlp(path):
    with open(path, "rb") as f:
        data = f.read()
    files = read_directory(data)
    blob = lambda name: read_internal(data, files[name]) if name in files else b""

    system = parse_system(blob("|SYSTEM"))
    if system["minor"] > 16:
        raise ValueError("only WinHelp 3.0 (HC30) files are supported")
    phrases = parse_phrases(blob("|Phrases"))
    fonts = parse_fonts(blob("|FONT"))
    tomap = parse_tomap(blob("|TOMAP"))
    titles = parse_titles(blob("|TTLBTREE"))
    number_of = {pos: n for n, pos in enumerate(tomap) if n and pos}

    topics = []
    font_state = [0]
    for pos, rtype, ld1, ld2, len2 in topic_links(blob("|TOPIC")):
        text = expand_phrases(ld2, len2, phrases)
        if rtype == TL_TOPICHDR:
            if pos not in number_of:
                raise ValueError("topic at 0x%X missing from |TOMAP" % pos)
            title = titles.get(pos, decode_text(text.split(b"\0")[0]))
            topics.append({"number": number_of[pos], "position": pos, "title": title,
                           "context": None, "paragraphs": []})
            font_state = [0]
        elif rtype == TL_DISPLAY30:
            topics[-1]["paragraphs"] += display_paragraphs(ld1, text, fonts, font_state)
        else:
            raise ValueError("unknown TOPICLINK type %d" % rtype)

    by_number = {t["number"]: t for t in topics}
    by_position = {t["position"]: t for t in topics}
    index_topic = by_position.get(tomap[0]) if tomap else None
    contexts = {}
    for map_id, number in parse_ctxomap(blob("|CTXOMAP")):
        target = by_number.get(number) or (index_topic if number == 0 else None)
        contexts[map_id] = target["title"] if target else None
        if target:
            target["context"] = (target["context"] or []) + [map_id]

    unresolved = []
    for t in topics:
        for para in t["paragraphs"]:
            for run in para:
                if run["link"]:
                    kind, number = run["link"]
                    target = by_number.get(number)
                    if target is None:
                        unresolved.append((t["title"], number))
                        run["link"] = None
                    else:
                        run["link"] = target["title"]
                        if kind == "popup":
                            run["popup"] = True
        while t["paragraphs"] and not t["paragraphs"][-1]:
            t["paragraphs"].pop()

    return {"title": system["title"], "version": "%d.%d" % (system["major"], system["minor"]),
            "index_topic": index_topic["title"] if index_topic else None,
            "contexts": contexts, "topics": topics, "keywords": {},
            "unresolved_links": unresolved, "internal_files": sorted(files)}


# ---------------------------------------------------------------- export

def paragraph_text(para):
    parts = []
    for run in para:
        if run["link"]:
            parts.append("[[%s|%s]]" % (run["text"], run["link"]))
        else:
            parts.append(run["text"])
    return "".join(parts).rstrip()


def export_txt(hlp, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("MTU.HLP  (WinHelp 3.0, |SYSTEM version %s, %d topics)\n" % (hlp["version"], len(hlp["topics"])))
        f.write("Index topic: %s\n" % hlp["index_topic"])
        for t in hlp["topics"]:
            f.write("\n%s\n# %d  %s\n%s\n" % ("=" * 72, t["number"], t["title"], "=" * 72))
            if t["context"]:
                f.write("Context: %s\n" % ", ".join(str(c) for c in t["context"]))
            for para in t["paragraphs"]:
                f.write(paragraph_text(para) + "\n")


def help_json(hlp):
    """The help file as the web UI and MTU.HLP.json use it."""
    return {
        "title": hlp["title"],
        "index_topic": hlp["index_topic"],
        "contexts": {str(k): v for k, v in hlp["contexts"].items()},
        "topics": [{"number": t["number"], "title": t["title"], "context": t["context"],
                    "paragraphs": t["paragraphs"]} for t in hlp["topics"]],
        "keywords": hlp["keywords"],
    }


def export_json(hlp, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(help_json(hlp), f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(base_dir, "data", "MTU.HLP")
    if not os.path.exists(src):
        print("File not found:", src)
        return 1
    hlp = parse_hlp(src)
    out_dir = os.path.join(base_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    export_txt(hlp, os.path.join(out_dir, "MTU.HLP.TXT"))
    export_json(hlp, os.path.join(out_dir, "MTU.HLP.json"))
    links = sum(1 for t in hlp["topics"] for p in t["paragraphs"] for r in p if r["link"])
    print("Exported %d topics, %d jumps (%d unresolved) from MTU.HLP"
          % (len(hlp["topics"]), links, len(hlp["unresolved_links"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
