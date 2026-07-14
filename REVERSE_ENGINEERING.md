# Reverse Engineering Notes

This document contains detailed technical information about the MoonStar dictionary file formats.

## File Structure

The MoonStar dictionary consists of several binary files:

- **MTU.TRK**: English-Turkish dictionary (17,988 entries) - ✅ Complete
- **MTU.TUR**: Turkish-English dictionary, Turkish synonyms, and Türkçe Leb Demeden feature
  - Türkçe Leb Demeden (26,775 entries) - ✅ Complete
  - Turkish-English dictionary (Section 3) - ⚠️ Decoder found, still garbled
  - Turkish synonyms (Section 3) - ⚠️ Decoder found, still garbled
- **MTU.ING**: İngilizce Leb Demeden feature - ⚠️ In progress
- **MTU.TES**: Test/quiz data for İngilizce Leb Demeden - ⚠️ In progress
- **MTU.SOZ**: Additional dictionary data - ⚠️ Needs analysis
- **MTU.EXE**: Suffix list for MTU.TRK (extracted from offset 1B8B8h-1BC45h) - ✅ Complete

## MTU.TRK Format

MTU.TRK consists of four parts:
1. Empty header (3 bytes)
2. Offset map for 2-letter prefixes (2028 bytes = 676 prefixes × 3 bytes)
3. List of English words (127,519 bytes) - uses morpheme expansion
4. List of Turkish definitions (702,248 bytes) - uses middle-endian offsets

Text encoding: CP 857 (Code Page 857 - Turkish)

### Morpheme Expansion

In MTU.TRK, commonly used suffixes are replaced with bytecode instructions and stored in MTU.EXE (1B8B8h-1BC45h) instead. These suffixes are then attached back by executing the instructions at runtime.

Instruction bytecodes:
- `0x00` or `0x12`: No operation
- `0x20`: Capitalize word
- `0x40-0x4F`: Combine first n characters of previous morpheme with current one
- `0x60-0x6F`: Same as above, capitalized
- `0x80`: Attach suffix (followed by suffix index)
- `0xA0`: Attach suffix, capitalized (followed by suffix index)
- `0xC0-0xCF`: Combine previous morpheme + current + suffix
- `0xE0-0xEF`: Same as above, capitalized

Turkish entry offsets use middle-endian byte ordering: `data[pos+1] | (data[pos+2] << 8) | (data[pos] << 16)`

## MTU.TUR Format

MTU.TUR consists of seven sections:
1. Header (12 bytes) - 4 × 16-bit values
2. Section 1 (66 bytes) - lookup table for letters (32 letters + 1)
3. Section 2 (2,050 bytes) - lookup table for two-letter prefixes (32×32 + 1)
4. Section 3 (45,052 bytes) - Turkish-English dictionary and synonyms data
5. Section 4 (107,100 bytes) - instructions for Türkçe Leb Demeden entries
6. Section 5 (62,800 bytes) - suffix data
7. Section 6 (3,640 bytes) - modification instructions

Text encoding: Custom alphabet where 0x00='a', 0x01='b', 0x02='c', 0x03='ç', etc.

Custom alphabet: `"abcçdefgğhıijklmnoöpqrsştuüvwxyzâ..........î..............û"`

### Section 3 Format

Section 3 entries are 14 bytes each:
- Byte 0: Unknown flag
- Bytes 1-2: Value (little-endian 16-bit) - references Section 4
- Bytes 3-13: Unknown data (11 bytes) - possibly contains English translation references

Disrupting this section causes entries in Turkish-English and Türkçe Eş Anlamlılar dictionaries to lose their suffixes (e.g. "abayı yakmak" -> "aba yak"). Doesn't seem to affect Leb Demeden.

### Suffix Length Calculation

Suffix length is determined by the second byte of Section 4 entries:
- `0x00-0x08`: length 0
- `0x08-0x10`: length 1
- `0x10-0x18`: length 2
- ... (continues by 8)
- `0xb0-0xb8`: length 22
- `0xb8-0xd0`: length 3
- `0xd0-0xe8`: length 4
- `0xe8-0x100`: length 5

## MTU.ING Format (Corrected)

MTU.ING is a 654,684-byte file that stores English vocabulary data for the İngilizce Leb Demeden feature. It uses a frequency-based custom alphabet and a suffix-based compression scheme.

### Structure Overview

1. **Table size** (bytes 0-2): 96,000 = 32,000 × 3 bytes
2. **Offset table** (bytes 3-96,002): 32,000 × 3-byte little-endian offsets
   - Offsets are absolute file positions pointing into the data area
   - Only ~14,464 of 32,000 slots are non-empty
3. **Data area** (bytes 96,003 onwards): ~558,681 bytes

### Slot Structure

Each slot (when non-empty) has:
- **2-byte header**: `[0x00, (slot_index + 1) % 256]`
- **Body**: variable-length byte sequence ending with an instruction byte (≥0x80)

### Frequency-Based Alphabet

Instead of a sequential a=0 mapping (as used by MTU.TUR), MTU.ING uses a frequency-ordered alphabet where each byte value 0x00-0x19 maps to an English letter based on its frequency in the data:

| Byte | Count | Letter | English Freq Rank |
|------|-------|--------|-------------------|
| 0x00 | 24,806 | e | 1st |
| 0x03 | 21,725 | t | 2nd |
| 0x0b | 20,525 | a | 3rd |
| 0x02 | 17,598 | o | 4th |
| 0x11 | 17,555 | i | 5th |
| 0x05 | 17,110 | n | 6th |
| 0x16 | 15,818 | s | 7th |
| 0x04 | 15,026 | h | 8th |
| 0x15 | 14,981 | r | 9th |
| 0x19 | 12,237 | d | 10th |
| 0x10 | 10,997 | l | 11th |
| 0x13 | 8,386 | c | 12th |
| 0x18 | 8,184 | u | 13th |
| 0x0e | 7,721 | m | 14th |
| 0x07 | 8,800 | w | 15th |
| 0x09 | 7,726 | f | 16th |
| 0x0f | 7,706 | g | 17th |
| 0x01 | 6,934 | y | 18th |
| 0x06 | 6,436 | p | 19th |
| 0x0d | 3,730 | b | 20th |
| 0x17 | 1,107 | v | 21st |
| 0x14 | 2,264 | k | 22nd |
| 0x0c | 1,073 | j | 23rd |
| 0x12 | 1,038 | x | 24th |
| 0x08 | 773 | q | 25th |
| 0x0a | 331 | z | 26th |

**Validation**: This mapping correctly decodes "the" (0x03 0x04 0x00), "an" (0x0b 0x05), "and" (0x0b 0x05 0x19), "for" (0x09 0x02 0x15), "are" (0x0b 0x15 0x00). 185 letter sequences between control bytes match words in the MTU.TRK English dictionary.

ASCII characters (0x20-0x7E) are used directly for punctuation, digits, and uppercase letters.

### Instruction Bytes (≥ 0x80)

Bytes 0x80-0xFF are instruction/control bytes that correspond to the suffix table stored in MTU.EXE (offset 0x1B8B8-0x1BC45, 195 entries). The suffix index = instruction_byte - 0x80.

| Byte | Index | Suffix | Frequency |
|------|-------|--------|-----------|
| 0x81 | 1 | ibility | 15,494 |
| 0x8a | 10 | lessly | 8,680 |
| 0x85 | 5 | ousness | 8,166 |
| 0x87 | 7 | edness | 7,063 |
| 0xc1 | 65 | ible | 5,890 |
| 0xc5 | 69 | ious | 5,454 |
| 0xca | 74 | like | 4,658 |
| 0x84 | 4 | fulness | 4,618 |
| 0x98 | 24 | fully | 3,523 |
| 0x9e | 30 | istic | 3,259 |

**Important**: The last byte of every non-empty slot is always an instruction byte (≥0x80).

### Entry Format (Partial Understanding)

The body of each slot consists of alternating letter sequences and instruction bytes:
```
[letter_bytes] [instruction] [letter_bytes] [instruction] ... [instruction]
```

Each instruction byte likely:
1. Terminates the preceding letter fragment
2. Specifies how to process/combine it (add suffix, modify, etc.)
3. The exact combination semantics are still under investigation

### Status

- ✅ Slot structure (32K slots, 3B offsets, freq alphabet) - Complete
- ✅ Frequency-based alphabet (0x00='e', 0x03='t', ...) - Verified against TRK dictionary
- ✅ Instruction bytes = suffix table indices from MTU.EXE - Confirmed
- ✅ Every slot ends with an instruction byte - Confirmed
- ⚠️ Instruction combination semantics - Unknown
- ⚠️ Multi-entry slots - Structure understood but content unreadable
- ❌ Complete working decoder - Not yet implemented

## MTU.SOZ Format

MTU.SOZ has the same magic number as MTU.TUR (`MG2\x1a`) and similar structure:
1. Magic number: `MG2\x1a`
2. Header (12 bytes) - 4 × 16-bit values
3. Section 1 (66 bytes) - lookup table for letters (32 letters + 1)
4. Section 2 (2,050 bytes) - lookup table for two-letter prefixes (32×32 + 1)
5. Section 3 (199,178 bytes) - 14,227 entries × 14 bytes each
   - Format: `[byte0] [bytes1-2: Section4 ref] [bytes3-13: MTU.ING offset (11 bytes)]`
   - The 11-byte block (bytes 3-13) is believed to contain MTU.ING offsets
   - This acts as a "bridge" between MG2 format (Turkish) and Morpheme format (English)
6. Section 4 (8,772 bytes) - instructions for Turkish word formation
7. Section 5 (6,415 bytes) - suffix data
8. Section 6 (24,664 bytes) - modification instructions

**Key Insight:** MTU.SOZ Section 3 serves as a lookup table connecting Turkish words (from Section 4) to English translations (in MTU.ING). The 11-byte block format is still under investigation.

## Notes

## MTU.TUR Section 3 — TR_EN & ES_ANLAM Decode Algorithm

### Section 3 Entry Structure (14 bytes each, 3,218 entries total)
```
[byte0:1] [val:2] [bytes11:11]
```
- **byte0** = type/control byte
- **val** = u16 index into Section 4 (Turkish word suffix instructions)
- **bytes11** = 11-byte data block

### byte0 Control Field
| Bits | Field | Description |
|------|-------|-------------|
| 0–6 | `count` | Number of bytes to decode (0–127) |
| 7 | `double_lookup` | If set, last byte uses double indirection via table_A → table_B |

### Data Source Selection
| count | Data source for decoding |
|-------|-------------------------|
| 0–2 | From the 11-byte block itself (`entry[3:3+count]`) |
| 3+ | From Section 4 at offset `val` (suffix instruction data) |

### Character Decode Algorithm
```
for each byte b in source:
    if (double_lookup && b is last_byte):
        idx = table_A[b]         # 1st lookup
        ch = table_B[idx]        # 2nd lookup
    else:
        ch = table_B[b]          # single lookup
```
Output byte `ch` should be decoded as CP857 for final text.

### Lookup Tables in EXE (DGROUP / data segment)
| Table | File offset | DGROUP offset | Size | Description |
|-------|-------------|---------------|------|-------------|
| table_A | `0x1B388` | `0x1588` | 256 bytes | Extra index for double-lookup |
| table_B | `0x1A7CA` | `0x09CA` | 256 bytes | Main character lookup table |

**table_A** (first 32 bytes):
`0x0a 0x13 0x03 0x03 0x18 0x0b 0x0f 0x0d 0x0d 0x05 0x18 0x05 0x07 0x0f 0x10 0x10 0x18 0x00 0x11 0x0f 0x14 0x10 0x18 0x10 0x10 0x00 0x00 0x18 0x1c 0x1d 0x15 0x10`

**table_B** decoded as CP857 (selected chars):
- mapping: `0x00→c 0x01→c 0x02→j 0x03→é 0x04→f 0x05→d 0x06→o 0x07→b 0x08→Ñ 0x09→i 0x0a→ä 0x0b→l 0x0c→h 0x0d→j 0x0e→e 0x0f→h`
- `0x10→l 0x11→n 0x12→Ø 0x13→u 0x14→s 0x15→s 0x16→z 0x17→Ü 0x18→v 0x19→t 0x1a→ê 0x1b→s 0x1c→u 0x1d→y 0x1e→p`
- Contains many control chars (0x01, 0x02, 0x05, 0x09) mixed with CP857 glyphs
- 113 unique byte values across 256 entries

### Current Status
- `DecodeEnglishText()` in `mtu_tur.py` was **WRONG** — used `alphabet[b]` instead of EXE's table_B → **FIXED** ✅
- Even with correct table_B (EXE 0x1A7CA) + table_A (0x1B388), output contains control chars (0x01, 0x02, 0x05, 0x09) — Section 3 data is **morphological format instructions**, not English text
- **Clean TR_EN + ES_ANLAM** now generated from TRK data instead:
  - TR_EN: 37,043 entries (reversed from TRK English→Turkish pairs) ✅
  - ES_ANLAM: 12,695 entries (Turkish words grouped by shared English translation) ✅
- The EXE's Section 3 decoder is documented in `mtu_tur.py` as `DecodeSection3Entry()` for reference
- `byte0` may still distinguish TR_EN from ES_ANLAM entries, but irrelevant since both are now generated from TRK

### EXE Code Locations
- Two decode functions found in **seg3** (file 0xA200):
  - Function 1: file offset `0xC460` (seg3+0x1C60)
  - Function 2: file offset `0xD158` (seg3+0x2F58)
- Section 3 base pointer at DGROUP `[0x93DD:0x93DF]` (file 0x1A9DD)
- Section 4 base pointer at DGROUP `[0x93E5:0x93E7]` (file 0x1A9E5)

## MTU.TRK Notes
- Some entries in MTU.TRK are corrupted even in the original application (14 entries total): aeze, auction, believe in, beneficial, blackmail, correlation, encore, Hebrew, hurricane, jut, march, orient, performance, rubbishy
- Middle-endian byte ordering is used for Turkish entry offsets in MTU.TRK
- Suffixes are stored in MTU.EXE and referenced via bytecode instructions to reduce file size
- MTU.TUR uses a custom alphabet encoding for Turkish words (Leb Demeden), but Section 3 uses EXE table_B for character mapping

