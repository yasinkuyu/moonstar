# Moonstar

This project intends to revive one of the most popular Turkish software ever written, namely "MoonStar Türkçe Dil Kılavuzu", otherwise known as "MTU Sözlük".

MoonStar was an easy-to-use application that included Turkish-English, English-Turkish and Turkish synonyms dictionaries, a spell checker, and a Hangman game. However, being a 16-bit application programmed in 1994, it's not possible to run it under a 64-bit OS without using some kind of emulation.

Driven by curiosity, this project sets out to provide a free, open source, multi-platform interface to MoonStar.

## Status

- **MTU.TRK**: English-Turkish dictionary (17,988 entries) - ✅ Complete
- **MTU.TUR**: Turkish-English dictionary and Türkçe Leb Demeden (26,775 words) - ✅ Leb Demeden complete, dictionary in progress
- **MTU.ING**: İngilizce Leb Demeden - ⚠️ In progress
- **MTU.TES**: Test/quiz data - ⚠️ In progress
- **MTU.SOZ**: Additional dictionary data - ⚠️ Needs analysis

## Usage

Run the extractors from the `src/` directory:

```bash
cd src
python3 mtu_trk.py    # Extract English-Turkish dictionary
python3 mtu_tur.py    # Extract Turkish-English dictionary and Leb Demeden
python3 mtu_ing.py    # Extract İngilizce Leb Demeden words
python3 mtu_tes.py    # Extract test/quiz data
```

Output files are written to the `output/` directory.

## Roadmap

- [x] Reverse engineer MTU.TRK format
- [x] Reverse engineer MTU.TUR Leb Demeden format
- [ ] Complete MTU.TUR Turkish-English dictionary extraction
- [ ] Complete MTU.TUR Turkish synonyms extraction
- [ ] Verify and fix MTU.ING format
- [ ] Verify and fix MTU.TES format
- [ ] Analyze MTU.SOZ format
- [ ] Build a GUI that emulates the original application

## Notes

- MTU.TRK uses CP 857 encoding with morpheme expansion and suffix attachment via bytecode instructions.
- MTU.TUR uses a custom alphabet encoding where 0x00='a', 0x01='b', etc.
- Some entries in MTU.TRK are corrupted even in the original application (14 entries total).
- Suffixes are stored in MTU.EXE and referenced via bytecode instructions to reduce file size.

For detailed reverse engineering notes, see [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).

## License

This project is a reverse engineering effort to revive the MoonStar dictionary. The original software was released in 1994 with free license
