# Moonstar

This project intends to revive one of the most popular Turkish software ever written, namely "MoonStar Türkçe Dil Kılavuzu", otherwise known as "MTU Sözlük".

MoonStar was an easy-to-use application that included Turkish-English, English-Turkish and Turkish synonyms dictionaries, a spell checker, and a Hangman game. However, being a 16-bit application programmed in 1994, it's not possible to run it under a 64-bit OS without using some kind of emulation.

Driven by curiosity, this project sets out to provide a free, open source, multi-platform interface to MoonStar.

## Status

- **MTU.TRK**: English-Turkish dictionary (17,988 entries) - ✅ Complete
- **MTU.TUR**:
  - Türkçe Leb Demeden (26,775 words) - ✅ Complete
  - Turkish-English dictionary (2,571 entries) - ⚠️ English text encoding needs further analysis
  - Turkish synonyms (1,339 entries) - ⚠️ Needs format verification
- **MTU.ING**: İngilizce Leb Demeden (329 words extracted) - ⚠️ Format differs from MTU.TRK; uses vocabulary index structure
- **MTU.TES**: Test/quiz data (417 entries extracted) - ⚠️ Same format as MTU.ING
- **MTU.SOZ**: Additional dictionary data (12,891 entries) - ✅ Complete

## Usage

Run the extractors from the project root or `src/` directory:

```bash
python3 src/mtu_trk.py    # Extract English-Turkish dictionary
python3 src/mtu_tur.py    # Extract Turkish-English dictionary and Leb Demeden
python3 src/mtu_ing.py    # Extract İngilizce Leb Demeden words
python3 src/mtu_tes.py    # Extract test/quiz data
python3 src/mtu_soz.py    # Extract additional dictionary data
python3 src/mtu_exe_suffixes.py  # Extract suffix list from MTU.EXE
```

Output files are written to the `output/` directory.

## Output Files

| File | Description | Entries |
|------|-------------|---------|
| `MTU.TRK.TXT` | English-Turkish dictionary | 17,988 |
| `MTU.TUR.TXT` | Türkçe Leb Demeden (idioms) | 26,775 |
| `MTU.TUR_TR_EN.TXT` | Turkish-English dictionary | 2,571 |
| `MTU.TUR_ES_ANLAM.TXT` | Turkish synonyms | 1,339 |
| `MTU.ING.TXT` | İngilizce Leb Demeden | 329 |
| `MTU.SOZ.TXT` | Additional dictionary data | 12,891 |
| `MTU.TES.TXT` | Test/quiz word data | 417 |
| `MTU.EXE.SUFFIXES.TXT` | Suffix list from MTU.EXE | 195 |

## File Formats

### MTU.TRK (Complete)
Simple format: 3-byte header + 676×3 byte offset table + word data. Uses CP 857 encoding with morpheme expansion and suffix attachment via bytecode. Suffixes stored in MTU.EXE.

### MTU.TUR (Partial)
MG2 format with 7 sections. Custom alphabet encoding (0x00='a'..0x1f='z'). Section 4 contains word formation instructions (26,775 entries). Section 3 contains dictionary/synonym data (3,218 entries) with English text encoded in an 11-byte block that needs further analysis.

### MTU.ING / MTU.TES (In Progress)
These files have a different structure than MTU.TRK. The offset table starts at byte 0, and the data uses a vocabulary index + prefix data structure. The morpheme expansion format differs from MTU.TRK, requiring further reverse engineering.

### MTU.SOZ (Complete)
MG2 format similar to MTU.TUR. Contains 12,891 entries using custom alphabet encoding.

## Roadmap

- [x] Reverse engineer MTU.TRK format
- [x] Reverse engineer MTU.TUR Leb Demeden format
- [x] Reverse engineer MTU.SOZ format
- [ ] Complete MTU.TUR Turkish-English dictionary English text decoding
- [ ] Complete MTU.TUR Turkish synonyms verification
- [ ] Reverse engineer MTU.ING format (vocabulary index structure)
- [ ] Reverse engineer MTU.TES format
- [ ] Build a GUI that emulates the original application

## Notes

- MTU.TRK uses CP 857 encoding with morpheme expansion and suffix attachment via bytecode instructions.
- MTU.TUR uses a custom alphabet encoding where 0x00='a', 0x01='b', etc.
- Some entries in MTU.TRK are corrupted even in the original application (14 entries total).
- Suffixes are stored in MTU.EXE and referenced via bytecode instructions to reduce file size.

For detailed reverse engineering notes, see [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).

## License

This project is a reverse engineering effort to revive the MoonStar dictionary. The original software was released in 1994 with free license
