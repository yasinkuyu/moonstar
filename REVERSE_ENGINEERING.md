# Reverse Engineering Notes

This document contains detailed technical information about the MoonStar dictionary file formats.

## File Structure

The MoonStar dictionary consists of several binary files:

- **MTU.TRK**: English-Turkish dictionary (17,988 entries) - ✅ Complete
- **MTU.TUR**: Turkish-English dictionary, Turkish synonyms, and Türkçe Leb Demeden feature
  - Türkçe Leb Demeden (26,775 entries) - ✅ Complete
  - Turkish-English dictionary (Section 3) - ⚠️ In progress
  - Turkish synonyms (Section 3) - ⚠️ In progress
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

## MTU.ING / MTU.TES Format

MTU.ING and MTU.TES have the same structure:
1. Base offset (3 bytes) - first offset value
2. Offset map for 2-letter prefixes (2,028 bytes = 676 prefixes × 3 bytes)
3. List of entries (variable length)

Format appears similar to MTU.TRK but entries contain only English words (no Turkish translations). Uses CP 857 encoding with morpheme expansion.

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

- Some entries in MTU.TRK are corrupted even in the original application (14 entries total): aeze, auction, believe in, beneficial, blackmail, correlation, encore, Hebrew, hurricane, jut, march, orient, performance, rubbishy
- Middle-endian byte ordering is used for Turkish entry offsets in MTU.TRK
- Suffixes are stored in MTU.EXE and referenced via bytecode instructions to reduce file size
- MTU.TUR uses a custom alphabet encoding that differs from CP 857

