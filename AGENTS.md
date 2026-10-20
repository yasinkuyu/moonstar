## Application Overview

**Program**: MoonStar Türkçe Denetim Editörü (Turkish Spell Check Editor) — Borland C++ Win16 NE executable
- **Original Author**: Alper Özer (@aozer8080)
- **Data Source (Confirmed by Author)**: Digitized directly from **Fono Yayınları** (multi-volume English-Turkish and Turkish Synonyms dictionaries) entered via a custom in-house binary utility tool.
- **Features**: Turkish spell checker, grammar checker, word game ("Kelime Oyunu"), text statistics, multiple dictionary views
- **EXE format**: Win16 NE (New Executable) at file offset 0x250, 6 segments, 512B alignment
- **Entry**: CS=1 IP=0, Auto data seg=6, Stack SS=6 SP=0
- **Encoding**: CP857 for DOS strings (high bytes 0x80-0x9F), ISO-8859-9 for UI strings (0xA0-0xFF)
- **Goal**: every decoder must produce exactly what MTU.EXE produces. Rules come from the decompiled EXE, not from Turkish grammar guesses — no hand-written phonetics, no per-word patches.
- **Engine Architecture**: `src/engine/` — `tur_lexicon.py` (MTU.TUR words, suffixes, word recognizer), `binary_parser.py` (MTU.TES record decoder), `thesaurus.py` (thesaurus API), `ing.py` (MTU.ING Turkish→English dictionary), `speller.py` (spell checker + `*.SOZ` user dictionaries).
- **Ground Truth**: live Win16 RAM dump `data/ntvdm.exe.dmp` (thesaurus buffer at `0x60348`) and the screenshot word lists in `assets/GROUND_TRUTH_DATA.md` (`öz`, `kitap`, `elma`, `ekmek`, `gelmek`, `yüz`, `göz`, `akıl`, `güzel`, `test`, `mali`, `hafif`, `dolu`, `ağır`, `boş`, `adalet`, `cesaret`, `hürriyet`, `barış`, `zengin`, `ölüm`, `giriş`, `çıkış`). Screenshots show only the visible part of long lists, so extra words that sort after the last visible one are expected.

## Reverse-Engineering Workflow

REA (`rea`) cannot open Win16 NE files. Use Ghidra 12.1.4 headless directly (it has an NE loader). The analysed project, scripts and saved decompiled output live in `re/` (git-ignored; see `re/README.md`):

```bash
/opt/homebrew/Cellar/ghidra/12.1.4/libexec/support/analyzeHeadless <proj_dir> mtu \
    -import data/MTU.EXE -scriptPath <scripts> -postScript <Script>.java <args>
```

- The live DGROUP in `data/ntvdm.exe.dmp` is at `0x5999E` (runtime tables such as `ds:0x09CA` are only valid there).
- Ghidra maps segments as `Code1`=`1000:0000`, `Code2`=`1008:0000`, `Code3`=`1010:0000`, `Code4`=`1018:0000`, `Code5`=`1020:0000`, `Data6`(DGROUP)=`1028:0000`.
- File offset of `1010:xxxx` = `0xA200 + xxxx`; DGROUP offset `ds:xxxx` = file `0x19E00 + xxxx`.
- Some DGROUP tables are filled at runtime (e.g. the character table at `ds:0x09CA` is garbage in the file); static tables such as `ds:0x1588` and `ds:0x15AD` are valid in the file.

### Ground truth by emulation (`re/tools/`)
The decisive check is running the EXE's own code. `re/tools/mtu_emu.py` loads MTU.EXE into a 16-bit Unicorn emulator (`re/pylib`, git-ignored):
- Segments are placed at real-mode paragraphs and NE relocations applied (`KERNEL.113 __AHSHIFT = 12` for huge blocks).
- The KERNEL file/memory calls are stubbed (**349 = `_hread`**, 350 = `_hwrite`).
- The runtime tables `ds:0x09CA` / `0x0A8B` are copied from the live DGROUP in the RAM dump.
- The EXE's own loader `FUN_1010_0000` reads MTU.TUR, MTU.SOZ, MTU.TES, MTU.ING.
- Before calling `0842`/`0ba3`, the harness calls `FUN_1010_0691` to lock the dictionary blocks, as the document loop does.

| Script | Compares | Result |
|--------|----------|--------|
| `verify_thesaurus.py` | `engine.thesaurus` vs `FUN_1010_256c`, every headword | 13,829 / 13,829 identical |
| `verify_ing.py` | `engine.ing` vs `FUN_1010_3114`, every TUR word | 26,452 / 26,452 identical; `ahfat` hangs the EXE |
| `verify_speller.py [n] [seed]` | `engine.speller` check + suggestions vs `0842` + `0ba3`, at sentence start and mid-sentence | 9,670 / 9,670 identical (seed 2026, 4,835 words) |

```bash
PYTHONPATH=re/pylib python3 re/tools/verify_thesaurus.py [word …]
```

### EXE EXTRACTED RESOURCES
All UI strings found in data segment (0x19E00-0x24800) and post-segment area (0x24800-0x62200):
- **Dialog/menu labels**: "Kelime Oyunu", "İngilizce Türkçe Sözlük", "Türkçe Eş Anlamlı Sözcükler", etc.
- **Spell check options**: Paragraf başı kontrol, Bileşik isim denetimi, Özel isim yumuşama denetimi, etc.
- **File type identifiers**: `TESING` at `ds:0x182C` (file `0x1B62C`) — `FUN_1010_2fec(n)` replaces the extension of `MTU.EXE` with `"TESING"[n*3:n*3+3]`, so `n=0` opens **MTU.TES** and `n=1` opens **MTU.ING**.

### Data File Usage — EXE-Verified Offsets

| File | EXE Evidence | Used By |
|------|-------------|---------|
| MTU.TRK | `TRK` in `TURTESINGTRK` roster (`0x1B61D`); 195-entry English suffix table at `0x1B8B8-0x1BC45` | `İngilizce Türkçe Sözlük` (`0x1BC6C`), Kelime Oyunu |
| MTU.TUR | `TUR` in file-open filter `".SOZ\0MG2\x1a\0.SOZ\0TUR"` (`0x1BC54`) and roster | Word list for every Turkish feature, Leb Demeden suffix analyzer, spell check |
| MTU.TES | `FUN_1010_2fec(0)`, decoded by `FUN_1010_256c` | `Türkçe Eş Anlamlı Sözcükler` |
| MTU.ING | `FUN_1010_2fec(1)`, decoded by `FUN_1010_3114` | `Türkçe İngilizce Sözlük` |
| MTU.SOZ | `FUN_1010_0391(4)` loads `<name>.SOZ` (name `MTU` at `ds:0x00A4`), checks `MG2\x1a` (`ds:0x1E4A`); saved by `FUN_1010_04b9` | User dictionary 0 — searched by the spell checker after MTU.TUR |
| MTU.HLP | `HLP` in class registration (`0x1B23B`) | `Yardım` (F1) |
| MTU.INI / MTU1.INI | `INI` in class registration (`0x1B23B`) | `Seçenekler`, `Klavye Seçimi` (`0x5DE0F`), window state |
| KONTROL.SOZ | Same format | One-word user dictionary (`denir`) |
| TEST | — | CP857 Turkish text with `<BL>`/`<IT>` markup; `Dosya Açma` demo document |

## MTU.TUR (Turkish word list + suffix table) ✅ EXE-exact

**Code**: `src/engine/tur_lexicon.py` (`TurLexicon`), exported by `src/mtu_tur.py` → `output/MTU.TUR.TXT` (26,775 words).

### File layout
```
"MG2\x1a"
header: u16 word_count (26775), suffix_count (3218), sec5_len (62800), sec6_count (910)
Section 1: 33 × u16   per-letter index into Section 3
Section 2: 1025 × u16 two-letter prefix table (32×32 + 1): first word index of each prefix (ds:0x8B99)
Section 3: 3218 × 14B suffix records (ds:0x93DD)
Section 4: 26775 × 4B word records (ds:0x93E9)
Section 5: 62800B     letter codes for word bodies and long suffixes (ds:0x93E5)
Section 6: 910 × 4B   morphological class records (ds:0x8B97)
```
All text uses the 32-letter alphabet `abcçdefgğhıijklmnoöpqrsştuüvwxyz`; code `| 0x20` is the circumflex variant (â = 0x20, î = 0x2B, û = 0x3A).

### Word text — `FUN_1010_2e73` + `FUN_1010_1bc4`
- **Prefix**: the 2-letter prefix `k` with `Section2[k] <= idx < Section2[k+1]` (codes `k >> 5`, `k & 31`).
- **Section 4 record** `[b0, b1, b2, b3]`, `flags = b0 | b1 << 8`:
  - `flags & 0x3FF` = **Section 6 index (10 bits)**.
  - `flags >> 11` = body code: `0` no body; `1` → `[b2]`; `2` → `[b2, b3]`; `3..22` → that many codes at `Section5[b2|b3<<8]`; `23+` → `n = (code-23)//3 + 3` codes at the offset, rotated by `(code-23)%3`: 0 = last letter first, 1 = first letter last, 2 = reversed.
  - `flags & 0x400` (b1 bit 2) with body code 3..22 → the last body letter is replaced through the **mutation table `ds:0x1588`** (file `0x1B388`). This is how hardened forms (`ahmağ → ahmak`, `ahbab → ahbap`) and other final-letter alternations (`abonmaz → abonman`) are stored.
- **Section 6 flags** `f = s6[0] | s6[1] << 8`:
  - `f & 0x40` → prefix letters a/i/u (codes 0x00/0x0B/0x1A) get the circumflex (`âcil`, `âdil`, `âdet`).
  - `f & 0x100` → capitalize the first letter (1,379 words; proper nouns).

### Suffix text — `FUN_1010_2f55`
Section 3 record `e` (14 bytes): `n = e[0] & 0x7F` letters; `n < 3` → `e[1:1+n]`, else `Section5[e[1]|e[2]<<8 :+n]`; if `e[0] & 0x80` the last letter goes through `ds:0x1588`. The EXE **appends suffix text verbatim** — each suffix ID is one fixed allomorph (`0x07DC` = `sız`, `0x07EF` = `siz`, `0x04BB` = `lüksüz`); there is no vowel harmony or consonant softening at runtime. `data/suffixes.json` is generated from this (`src/suffix_extractor.py`).

Bytes 3–13 of a suffix record are the morphological class data used by the analyzer below (`e[3]`, `e[4]`, `e[5..6]`, `e[7..8]`, `e[9]`, `e[10]`, `e[11]`, `e[12]`, `e[13]`).

### Word recognition (Leb Demeden analyzer) — `FUN_1010_18f3`, `FUN_1010_0a0e`
Ported in `TurLexicon.find_index()`:
1. Typed text → letter codes, case and circumflex folded; apostrophe = 0x60; `.` ends the word (`18f3`).
2. Try stems from the longest down to the 2-letter prefix (`0a0e`). For each stem, find the first word with that exact body (`1a3c`/`1b3e`), then walk same-spelled homonyms, accepting the first one where the remainder validates (`1d8b`).
3. Empty remainder (`1f1e`/`1f9c`): rejected if Section 6 `s6[2] & 0x80` (word cannot stand alone, e.g. `dolu` #6100) — or for `da` when `s6[2] & 0x40`.
4. Non-empty remainder: rejected if `s6[1] & 0x04`; proper nouns (`s6[1] & 0x80`) need an apostrophe; then `20de` splits the remainder into Section 3 suffixes (longest first, recursive), each checked by `234d` against the current class state and updating it from `e[9]`, `e[11]`, `e[12]`, `e[13]`; finally the class byte must not have bit 7.
5. The thesaurus window masks the option flags (`ds:0x7A1B &= 0xC3`), which fixes several branches; spell-check mode uses the unmasked options and is **not** ported yet.

Examples: `giriş → gir`, `kitaplar → kitap`, `evlerimizden → ev`, `Ankara'dan → Ankara`, `dolu → #6101`.

## MTU.TES (Türkçe Eş Anlamlı Sözcükler) ✅ EXE-exact

`TES` = **T**ürkçe **E**ş Anlamlı **S**özcükler (Fono Turkish Thesaurus). Earlier notes calling it "test/quiz metadata" were wrong.

**Code**: `src/engine/binary_parser.py` (`TesBinaryParser`), API `src/engine/thesaurus.py` (`ThesaurusEngine.lookup` / `lookup_ordered`), export `src/mtu_tes.py` → `output/MTU.TES.TXT` (13,657 headwords).

### Slot loading — `FUN_1010_2fec`
- 32,000 × 3-byte little-endian offsets at `i*3`; slot `i` = `data[off[i]:off[i+1]]`, indexed by **MTU.TUR word index**.
- A 3-byte slot `FF lo hi` is a **redirect**: the EXE follows it to word `lo | hi << 8`; if that slot is empty it moves to the next index.
- `FUN_1010_256c` also moves to the next same-spelled homonym while the slot is empty.

### Record stream — `FUN_1010_256c`
Every word is a u16 chain: first value `& 0x7FFF` = MTU.TUR word index (`2e73`), following values = Section 3 suffix IDs (`2f55`), bit 15 = "more follows". Texts are concatenated verbatim.

| First byte | Meaning |
|-----------|---------|
| slot starts `0xC0` | **Alias**: one chain (target word + suffixes) names the target; the target slot is decoded instead; entries equal to the headword are dropped. 5,534 slots. |
| `b & 0x80` | Suffix chain appended to the current string. At slot start (`0x80`, 1,727 slots) it turns the headword into a derived headword (`gir` + `iş` = `giriş`, `sev` + `mek` = `sevmek`). |
| `b & 0x40` (bit 7 clear) | **Sub-record title**: headword + suffix chain (`yüz` → `yüzlemek`, `yüzsüzce`, `yüzsüz`). `b & 0x0F` = number of leading letters the typed text must match to select it (0 = whole title). Resets the topic state. |
| otherwise | **Synonym entry**: `((b >> 4) & 3) + 1` words joined by spaces; group code `b & 0x0F`. |

- **Topic groups**: code `0x0C–0x0F` reads one topic byte `t` **only when the code differs from the previous topic code**; following records with the same code reuse it. Group code becomes `t + 0x10`, label `TOPIC_NAMES[t + 4]`.
- **Group labels** (`ds:0x15CD` / `ds:0x15B7`): codes 0–4 → `N.Anlam` (N counts these groups in display order, it is not the code); 5–6 → Mecaz; 7–8 → Argo; 9 → Renk; 0x0A → Türemiş; `≥ 0x10` → topic names. Consecutive entries with the same code form one group, so two Mecaz groups can appear (`el`).
- **Selection**: without a matching sub-record title, the groups before the first title are shown; otherwise the groups after the matched title, up to the next title. Words in a group are sorted by `FUN_1010_2e13` (alphabet order, non-letters as space).
- The buffer this produces for `yüz` is identical, in order, to the 61 strings at RAM dump `0x60348`.
- One slot (`güvenoy`, #9205) starts with `0x90` and makes the EXE read suffix IDs past the table — a defect in the original data.

## MTU.TRK (English→Turkish Dictionary) ✅
- **Format**: 3B header + 676×3B prefix-offset table (A-Z×26) + morpheme-encoded English words (127,519B) + Turkish definitions (702,248B)
- **Output**: 17,988 entries, `english` padded to a fixed 30-column field + `türkçe`. Headwords may contain spaces (`believe in`, `upside down`): readers must split at column 30, not at the first space.
- **Script**: `src/mtu_trk.py`
- **Key insight**: English words stored as prefix (2 letters from table) + morpheme text + suffix instruction (195-entry suffix table at EXE 0x1B8B8-0x1BC45)

## MTU.ING (Türkçe İngilizce Sözlük) ✅ EXE-exact

MTU.ING is the **Turkish→English dictionary**, not quiz metadata. Earlier notes ("32,000-slot table, data at 96,003, slot header `[0x00, (trk_idx+1)%256, category]`", `decode_letter`/`format_sub` jump tables) misread it: the offset table was read 3 bytes off and the slots were keyed to MTU.TRK.

**Code**: `src/engine/ing.py` (`IngDictionary`, port of `FUN_1010_3114`), export `src/mtu_ing.py` → `output/MTU.ING.TXT` (24,042 Turkish entries, 50,789 English meanings) and `output/MTU.ING.BY_TOPIC.TXT`.

- **Slots**: same layout and loader as MTU.TES (`FUN_1010_2fec(1)`): 32,000 × 3-byte offsets at `i*3`, indexed by MTU.TUR word index, `FF lo hi` redirects, homonym fallback. The typed word is recognised with the same analyzer as the thesaurus.
- **Turkish entry** (bit 7 clear): `((b >> 4) & 3) + 1` words, each a u16 chain (TUR word + Section 3 suffixes). Example: `göz`, `göz atmak`, `gözlük`.
- **English label** (bit 7 set), belonging to the preceding entry:
  - `b & 0x0F` = part of speech. Names are inferred from the data, the EXE shows no text for them: 1 noun, 3 conjunction, 4 adverb, 5 verb, 6 postposition, 7 adjective, 8 interjection, 0xA idiom.
  - `b & 0x10` → one usage byte. Inferred: 7 British English (crisps), 8 vulgar, 9 slang, 10 figurative…
  - `b & 0x20` → one topic byte `t` = `TOPIC_NAMES[t + 3]` (1 Anatomi … 32 Yerbilim).
  - `b & 0x40` → numbered meaning: prefix `"%2d."` (`ds:0x1E5A`). Otherwise `"   "` (`ds:0x1E5F`) after a numbered one.
  - Text: bytes until bit 7. `c & 0x40` → English morpheme `ds:0x1617[c & 0x3F]` ("to make ", "tion", "somebody", …). Otherwise 6-bit letter code. The Turkish-only letter codes are punctuation (jump table `CS:0x361C`: 03 space, 08 `,`, 0A `?`, 12 `/`, 17 `(`, 23 `.`, 28 `'`, 2B `!`, 32 `-`, 37 `)`, 3A = byte 0x82 = CP857 `é`). `c & 0x20` → uppercase.
- **Selection**: the first entry starting with the typed text, else the entry with the longest common prefix; its labels are listed as stored (`" 1.eye"`, `"   look"`, unnumbered `"book"`).
- **Data quirks**:
  - `ilkyardım`, `incehastalık`, `karatahta` have a duplicated entry header without labels; `intak` has no meanings.
  - `ahfat` and `itburun` redirect to an empty slot just before themselves. `2fec` then loops forever: typing `ahfat` hangs the original window. The port returns no result instead.
- **Word game**: the web UI's topic list and hangman use the 1,890 topic-tagged meanings. Which data the EXE's own "Kelime Oyunu" uses is not verified.

### Topic Names (EXE `0x1B63A`, DGROUP `0x183A`)
| Cat | Topic | Cat | Topic | Cat | Topic |
|-----|-------|-----|-------|-----|-------|
| 0 | Mecaz | 12 | Ekonomi | 24 | Meteoroloji |
| 1 | Argo | 13 | Elektrik, elektronik | 25 | Mimarlık |
| 2 | Renk | 14 | Felsefe | 26 | Müzik |
| 3 | Türemiş | 15 | Fizik | 27 | Otomobil, otomotiv |
| 4 | Anatomi | 16 | Gökbilim (astronomi) | 28 | Ruhbilim (psikoloji) |
| 5 | Askerlik | 17 | Hayvanbilim | 29 | Sinema |
| 6 | Bitkibilim | 18 | Hekimlik | 30 | Spor |
| 7 | Biyoloji | 19 | Hukuk | 31 | Teknik, teknoloji |
| 8 | Coğrafya | 20 | İskambil | 32 | Ticaret |
| 9 | Denizcilik | 21 | Kimya | 33 | Tiyatro |
| 10 | Dilbilgisi, dilbilim | 22 | Mantık | 34 | Yazın (edebiyat) |
| 11 | Dinsel | 23 | Matematik | 35 | Yerbilim (jeoloji) |

Thesaurus topic groups use entry `t + 4` of this list, MTU.ING label topics entry `t + 3`.

## MTU.SOZ (User dictionary) ✅ EXE-exact

`*.SOZ` is the EXE's **user dictionary** format (load `FUN_1010_0391`, save `FUN_1010_04b9`). Earlier notes ("two alphabet32 streams, 20 group blocks, substring search, word boundaries not stored") were wrong; the "verified" matches `ankara`, `marmara`, `edirne` were substring accidents. Ankara, Edirne and Marmara are in MTU.TUR itself.

```
"MG2\x1a"  u16 count (2193)  u16 text_len (14227)  text[text_len]  records[count × 4]     8 + 14227 + 8772 = 23007 bytes
```
- **Records**: Section 4 layout without the 2-letter prefix (`FUN_1010_1bc4` user branch, `ds:0x8B90 = 0`):
  - `flags & 0x3FF` = Section 6 index.
  - `flags >> 11` = length code (same rules as MTU.TUR, no final-letter mutation).
  - `flags & 0x400` selects the dictionary's own text area; otherwise MTU.TUR Section 5 is used.
- **Codes**: `| 0x80` = uppercase letter (abbreviations `ABD`, `CHP`, `Cad`).
- **Content**: MTU.SOZ = 2,193 proper names (places, people, abbreviations), records sorted for binary search. `KONTROL.SOZ` = one word (`denir`).
- **Code**: `engine.speller.UserDictionary`; export `src/mtu_soz.py` → `output/MTU.SOZ.TXT`, `output/KONTROL.SOZ.TXT`.

## Spell Checker (Türkçe Denetim) ✅ EXE-exact decisions and suggestions

**Code**: `src/engine/speller.py` (`Speller`), used by `src/spell_check.py` and the web UI (`POST /api/check/text`).

- **`FUN_1010_0842`**: checks one word.
  - Fewer than `ds:0x009F` (= 2) letters → accepted.
  - Otherwise `0a0e`: MTU.TUR stems as in the thesaurus; then user dictionary 0 (MTU.SOZ) for every prefix length; plus a special case for the pronoun `o` (Section 6 classes 0x373 / 0x28D).
  - If nothing is found → `07bf`: Roman numerals (letters c l m v x, plus `I` typed uppercase or `i` typed lowercase).
- **Spell mode differences from the thesaurus**: `ds:0x8B8C = 0`, and the option byte `ds:0x7A1B = ds:0x009E = 0x94` (MTU.INI offset 0x48) is not masked:
  - Proper nouns (`s6[1] & 1`) must be typed with a capital (`ankara` ✗, `Ankara'dan` ✓).
  - Proper nouns take suffixes only after an apostrophe (`s6[1] & 0x80`).
  - Words with `s6[1] & 4` take no suffix.
  - Option bits 0x30 = 1: a required prefix circumflex (`s6[0] & 0x40` without `0x20`) must be typed.
  - A typed circumflex must exist in the word.
- **Case** (`ds:0x8B8A` from `18f3`): mixed case (`kiTap`) or a backquote is an error. At a sentence start (`ds:0x8B8B = 0x80`) a lowercase word is an error.
- **Sentence state** (`ds:0x8B8B`):
  - After a word it holds the harmony class (`f93 & 3`) of its last suffix, or 0x80 when the word ends in `.`.
  - Enclitics (`s6[2] & 0x40`: `mı`, `de`, …) must match the previous word's class: `okudum mu` ✓, `okudum mı` ✗.
  - Vowel classes come from `ds:0x15AD`.
- **Suggestions** (`FUN_1010_0ba3`, only when option bit 0x80 "Öneri getirme" is set):
  - **Suggestion mode** (`ds:0x8B8C = 0x40`): the analysis accepts and repairs instead of rejecting. `1f9c` copies the stored spelling (circumflexes) into the candidate, and proper nouns get their capital.
  - **A known word that broke a rule** gets one suggestion: the repaired word. An enclitic gets the vowel from `ds:0x15A9` (ü u i ı) matching the previous word (`okudum mı` → `mu`).
  - **Otherwise, in this order:**
    - Deleting each letter, swapping each adjacent pair (score 8).
    - All 32 letters inserted or replaced at positions 0 and 1 (`10e4`).
    - One missing / one wrong letter against every MTU.TUR word with the same two-letter prefix and every user-dictionary word (`116c`).
    - For exact stems (`1396`): a word split `kitap okudum` (`144d`), an apostrophe for proper nouns `Ankara'da`, and one missing / wrong letter inside the suffix chain (`158a`, recursive over Section 3).
  - **Scores**: `|ds:0x1568[a] − ds:0x1568[b]|` (keyboard/sound position), 8 for deletions and insertions, 0 for splits and exact suffixes. The lowest score is preselected; ties keep the first. A duplicate re-selects the earlier entry (`0f93`).
  - **Formatting** (`0f93`): the typed word's case is applied. Abbreviations (`s6[1] & 0x84`) get a period (`Prof` → `Prof.`), and abbreviations typed with the period are valid.
  - **Reach**: only edits at the first two letters or within one letter of a stored word/suffix are found, so `yanlis` (two wrong letters) gets no suggestion — in the EXE too.
- **Not ported**: the document tokenizer (`FUN_1018_11e0`) is approximated:
  - Words keep apostrophe-attached suffixes; a period right after a word belongs to it (sentence end or abbreviation).
  - `!`, `?` and other periods end a sentence unless the period touches a digit.
- **Global state the port reproduces.** The EXE keeps these in globals that leak from one candidate to the next; the suggestions depend on it:
  - `0x8B8D` / `0x8B82`: proper-noun softening flag and position survive a failed analysis. `0ba3` then hardens `Muttalib` → `Muttalip` before editing.
  - `0x8B8C` bit 2: one rejected abbreviation record lets the next one pass (`hk`).
  - `0x8B10`: a rejected homonym can leave its circumflex in the candidate (`hak` at sentence start → `Hâk`).
  - `0x8B8E`: set by the last `1b3e` compare, e.g. the binary-search probe, not the candidate.
  - `0x8B80` / `0x8ADE`: the body length and body buffer used by `1f9c` can be stale (`halayığ` → `hâla yığ`).
  - `0x8B42`: comparisons past the end of the typed word read the NUL as letter "a" (`atac` gets no `ataca`).
  - `158a` recurses with the state `20de` left behind.
- **EXE bugs kept on purpose** (they are what the program shows):
  - After an abbreviation stem a split overwrites the space (`drpiş` → `Drşpiş`).
  - An empty prefix range looks at the next prefix's first word (`dçağı` → `dç ağı`).
- **Window lookups** (thesaurus and Türkçe İngilizce) use the same analyzer: `Speller.for_windows()` = suggestion mode, options `& 0xC3`, no user dictionary. A typed circumflex moves to the next same-body homonym (`dahi` / `dâhi`).
- **Demo document** `data/TEST` (2,392 words): 6 errors, all explainable — unknown names (Akat, Emsan, Ofas), one real typo (`Göceçlik`), `"…"dir` split by a quote, lowercase after `...`.

### Runtime tables (live DGROUP)
The live DGROUP is at **`0x5999E` in `data/ntvdm.exe.dmp`** (the copies at `0x4EB9E` and `0x4A577E` are the unrelocated file image).
- `ds:0x09CA`: letter code → CP857 character (`abcçdefgğhıijklmnoöpqrsştuüvwxyzâ…î…û`, `+0x80` uppercase, `0xC0–0xD6` = `ÄÅÁÀÂÉÊË…`).
- `ds:0x0A8B`: CP857 character → letter class (`0x60` apostrophe, `0xFC` `.`/`,`, `0xFD` digits, `0xFF` space/hyphen).
- `ds:0x7A1B = 0x94`, `ds:0x009F = 2`.

## Other Data Files

| File | Size | Format | Notes |
|------|------|--------|-------|
| MTU.HLP | 26KB | Windows HLP (`3F 5F 03 00`) | Turkish help text, unread |
| MTU.INI / MTU1.INI | 1.5KB | Binary + text | Window state, font (Times New Roman / System), keyboard layout table |
| TEST | 19KB | CP857 text with `<BL>`, `<IT>` | Demo document |

## MTU.EXE — NE Header (file offset 0x250)

| Field | Value |
|-------|-------|
| **Signature** | `NE` (0x454E) |
| **Linker** | Borland C++ v5.10 (0x0A05) |
| **Segments** | 6 |
| **Entry** | CS=1 IP=0 |
| **Auto DS** | seg 6 |
| **Stack** | SS=6 SP=0 |
| **Heap** | 16,384B |
| **Stack size** | 5,120B |
| **Alignment** | 2⁹ = 512B |
| **Segment table** | NE+0x40 (file 0x290) |
| **Target OS** | 2 (Windows) |
| **Windows ver** | 3.0 (0x0008) |

| Seg | Sector | File Offset | Length | Flags | Type |
|-----|--------|------------|--------|-------|------|
| 1 | 9 | 0x1200 | 9,051B | 0x1D50 | Code |
| 2 | 27 | 0x3600 | 20,985B | 0x1D50 | Code |
| 3 | 81 | 0xA200 | 19,697B | 0x1D50 | Code (Turkish lexicon, analyzer, TES/ING decoders) |
| 4 | 124 | 0xF800 | 12,311B | 0x1D50 | Code |
| 5 | 155 | 0x13600 | 24,347B | 0x1D50 | Code |
| 6 | 207 | 0x19E00 | 43,516B | 0x0D51 | Data (DGROUP) |

### Key routines (segment 3)
| Ghidra address | File offset | Function |
|---------------|-------------|----------|
| `1010:0391` | 0xA591 | Open data file by roster index; `.SOZ` user dictionaries |
| `1010:04b9` | 0xA6B9 | Save user dictionary |
| `1010:07bf` | 0xA9BF | Roman numerals (letter table at `CS:0x0826`) |
| `1010:0842` | 0xAA42 | **Spell check one word** |
| `1010:0a0e` | 0xAC0E | Stem search over MTU.TUR, then user dictionary 0 |
| `1010:0ba3` | 0xADA3 | **Suggestions** (`0f93` add, `10e4` letters, `116c` near words, `1396`/`144d`/`158a` stem repairs) |
| `1010:18f3` | 0xBAF3 | Typed text → letter codes |
| `1010:1bc4` | 0xBDC4 | Word body from Section 4 |
| `1010:1d8b` | 0xBF8B | Validate stem + remainder |
| `1010:20de` | 0xC2DE | Suffix chain analyzer (recursive) |
| `1010:234d` | 0xC54D | Suffix/class compatibility |
| `1010:256c` | 0xC76C | **MTU.TES record decoder** |
| `1010:2e13` | 0xD013 | Sort key for display |
| `1010:2e73` | 0xD073 | Headword text (prefix + body + Section 6) |
| `1010:2f55` | 0xD155 | Suffix text from Section 3 |
| `1010:2fec` | 0xD1EC | Slot loader for TES/ING |
| `1010:3114` | 0xD314 | **MTU.ING record decoder** — Türkçe İngilizce Sözlük (contains file `0xD5BD`, which older notes wrongly called the TES routine) |

### Important DGROUP addresses
| ds: | Meaning |
|-----|---------|
| `0x009E` / `0x009F` | Default option byte (0x94) / minimum word length (2) |
| `0x0A8B` | Character → letter class table (runtime) |
| `0x09CA` | Letter code → display character (runtime) |
| `0x1588` | Final-letter mutation table (static) |
| `0x15AD` | Vowel harmony class per letter (static) |
| `0x15A9` | High vowel per harmony class: ü u i ı (static) |
| `0x1568` | Keyboard/sound position per letter, suggestion scores (static) |
| `0x15B7` / `0x15CD` | Group label pointer tables |
| `0x182C` | `TESING` extension roster |
| `0x7A1B` | Option flags (copy of `0x009E`; the thesaurus masks it with 0xC3) |
| `0x93FB` / `0x9403` | User dictionary 0 / 1 headers (magic, count, text length) |
| `0x8B10` | Typed text as letter codes |
| `0x8B97`, `0x8B99` | Section 6 base, Section 2 prefix table |
| `0x93DD`, `0x93E5`, `0x93E9` | Section 3, Section 5, Section 4 bases |

## Win16 Search Behavior (dictionary windows)
- **Client-side only** — all data loaded once on window open.
- **Incremental scroll-to-match**: as the user types, the list scrolls to the first entry whose normalized prefix matches.
- **Normalization**: case-insensitive with Turkish İ/I, circumflex ignored; the web UI also folds `ı→i`, `ş→s`, `ç→c`, `ö→o`, `ü→u`, `ğ→g` so `birak` matches `bırakmak`.
- **Tamam button (control id 501) closes the window** (`EndDialog`, same code path as Esc / IDCANCEL) in all dictionary dialogs (resources 2200 İngilizce Türkçe, 2201 Türkçe İngilizce, 2202 Eş Anlamlı, 2207/2208 Leb Demeden; procs `DICTDLG`, `TRTHESDLG`). **Enter does nothing**: no button has `BS_DEFPUSHBUTTON`, so it sends IDOK (1), which the dialog procedures ignore. The second button (516) takes the selected list word and closes. Searching is live on every keystroke (EN_CHANGE on edit 1250).
- **Empty query**: scrolls to the first entry.

## Remaining Unknowns
| # | Unknown | Priority |
|---|---------|----------|
| 1 | **Kelime Oyunu data source** — which file and fields the EXE's word game uses (likely the MTU.ING topic/usage bytes). | MEDIUM |
| 2 | **Spell checker tokenizer** — port the document loop `FUN_1018_11e0` (punctuation, numbers, quotes); word decisions and suggestions are verified. | MEDIUM |
| 3 | **MTU.ING usage byte** (`b & 0x10`) — names of the 10 usage classes; the EXE shows no text for them. | LOW |
| 4 | **MTU.HLP** — standard Windows Help; not extracted. | LOW |

## Build & Run
```bash
python3 src/mtu_trk.py              # TRK dictionary → output/MTU.TRK.TXT
python3 src/mtu_tur.py              # TUR word list → output/MTU.TUR.TXT (+ TR_EN, ES_ANLAM from TRK)
python3 src/mtu_tes.py              # Thesaurus → output/MTU.TES.TXT
python3 src/mtu_ing.py              # Türkçe→İngilizce → output/MTU.ING.TXT, MTU.ING.BY_TOPIC.TXT
python3 src/mtu_soz.py              # User dictionaries → output/MTU.SOZ.TXT, KONTROL.SOZ.TXT
python3 src/suffix_extractor.py     # Section 3 suffixes → data/suffixes.json
python3 src/test_comparison.py      # Verification against EXE tables, RAM dump, screenshots and MTU.ING samples
(cd src && python3 test_suffix_coverage.py)  # Suffix ID coverage over all MTU.TES records
python3 src/ui.py                   # Web UI on 127.0.0.1:8080 (MOONSTAR_HOST / MOONSTAR_PORT)
```

## Change Log

### 2026-10-20 — Verified against the EXE running in an emulator
- `re/tools/mtu_emu.py` runs MTU.EXE routines in Unicorn.
- Thesaurus 13,829/13,829, Türkçe İngilizce 26,452/26,452 and spell checker 9,670/9,670 are identical.
- Fixes found this way:
  - `û` folds to `ü` (class 0x3A).
  - ING special code 0x3A is `é`.
  - The windows use the full analyzer (typed circumflex picks the next homonym).
  - The global-state effects listed under Spell Checker.
  - A redirect loop guard (`ahfat`).
- Confirmed EXE behaviour, not port errors: `sevmek` shows `sevmemek`'s synonyms; `ankarada` preselects `Ankara da`.

### 2026-10-20 — Spell checker suggestions
- Ported the suggestion engine (`0ba3`, `0f93`, `10e4`, `116c`, `1396`, `144d`, `158a`) into `engine/speller.py`; `spell_check.py` no longer has its own suggestion rules.
- The web UI preselects the EXE's best suggestion.
- Abbreviations typed with a period are valid (`Prof.`, `Dr.`, `vb.`); `data/TEST` errors dropped from 12 to 6.
- `code_char` uses the full runtime `ds:0x09CA` table (apostrophe 0x60, space 0x21).
- Ghidra project and all decompiled output are kept in `re/` (git-ignored, see `re/README.md`).

### 2026-10-20 — Spell checker and user dictionaries
- Ported the spell-check path (`0842`, `0a0e` with the user dictionary, spell-mode `1d8b`…`1f9c`, `07bf`) as `src/engine/speller.py`.
- `spell_check.py` takes its accept/reject decisions from it. The web UI checks whole texts through `POST /api/check/text`, so sentence state and apostrophe suffixes are handled.
- MTU.SOZ is the EXE user dictionary (2,193 proper names), not place-name streams. KONTROL.SOZ is a one-word user dictionary.
- Located the live DGROUP in the RAM dump (`0x5999E`) and read the runtime character and class tables from it.
- Data quirk: 3 words whose stored final `î` carries the mutation bit (`bigudî`, `tağaddî`, `yerberî`) display as `bigudÄ`… in the EXE as well.

### 2026-10-20 — MTU.ING is the Turkish→English dictionary
- Ported `FUN_1010_3114` as `src/engine/ing.py`: 24,042 Turkish entries with 50,789 English meanings, 0 decode errors.
- `mtu_ing.py` exports it. In the web UI, the Türkçe İngilizce window uses it instead of a reversed MTU.TRK list.
- The word game topics come from the label topic byte; the old "quiz category byte" interpretation is removed.

### 2026-10-20 — EXE-exact thesaurus and lexicon
- Decompiled the thesaurus path of MTU.EXE with Ghidra and ported it: `tur_lexicon.py` (`2e73`, `1bc4`, `2f55`, analyzer `0a0e`…`234d`) and `binary_parser.py` (`2fec`, `256c`).
- Removed guessed logic: hand-written vowel harmony (`engine/suffix.py`, `engine/phonetics.py`), per-word patches (`imtihal`, `hak`, `akıbes`…), the "word ends in ğ → k" rule, the `0x10 … 0x0A` collocation heuristic and byte-by-byte `0x40` scanning.
- Results:
  - RAM dump `0x60348`: 61/61 strings in order, 57/57 cluster words (previously 33/57).
  - All 22 screenshot words are consistent.
  - Words with corrupt output dropped from 64 to 0; unresolved suffix calls from 178 to 3 (the corrupt `güvenoy` slot).
  - 2,101 MTU.TUR words corrected (circumflex, hardening, 10-bit Section 6 index).
- Corrected earlier claims:
  - TES group codes: `0x10` is a word count, not Mecaz; 7–8 is Argo.
  - Redirect stubs are followed, not bypassed.
  - Section 6 index is 10 bits, and hardening comes from Section 4 bit 10.
  - `0xD5BD` belongs to the ING decoder.
- Fixed bugs:
  - `mtu_tur.py` capitalization leaked across a prefix group.
  - Turkish İ/I lowercasing.
  - Multi-word TRK headwords were split at the first space.
  - Short Section 3 suffixes were read from the wrong bytes.
  - `mtu_tes.py` read the file in the wrong format.
  - Web UI: escaping, input validation, SIGTERM handling, and others.
- Tests now fail when results diverge from the dump.
- Removed unused files: `src/disasm16.py`, `src/mtu_thesaurus.py`, `src/engine/suffix.py`, `src/engine/phonetics.py`.

### 2026-09-02
- Identified MTU.TES as the Turkish thesaurus.

### 2026-08-28
- MTU.SOZ analysed as "streams + substring search" (superseded: it is the user dictionary format, see 2026-10-20).

### 2026-08-27
- ING topic formula fixed to `(flag & 0x7F) % 36`.
