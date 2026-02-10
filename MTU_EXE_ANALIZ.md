# MTU.EXE Analiz Raporu

## Bulgular

### Dosya Formatları Karşılaştırması

1. **MTU.TRK** (831,798 bytes)
   - Format: 3 boş byte + offset table (2028 bytes) + entries
   - Encoding: CP 857
   - Yapı: [instruction] [suffix?] [morpheme] [0xFF] [tr_offset_3byte]

2. **MTU.TUR** (220,720 bytes)
   - Format: MG2\x1a magic + header (4x16-bit) + 7 section
   - Encoding: Custom alphabet
   - Header: [26775, 3218, 62800, 910]

3. **MTU.ING** (654,684 bytes)
   - Format: 3 byte base offset (96000) + offset table + entries
   - Encoding: CP 857 (muhtemelen)
   - Base offset: 96000
   - Prefix "aa" entry data: 3 bytes (0xFF 0x0E 0x00) - entry count marker?

4. **MTU.TES** (640,866 bytes)
   - Format: 3 byte base offset (96000) + offset table + entries
   - Encoding: CP 857 (muhtemelen)
   - Base offset: 96000
   - Prefix "aa" entry data: 3 bytes (0xFF 0x0E 0x00) - entry count marker?

5. **MTU.SOZ** (23,007 bytes)
   - Format: MG2\x1a magic + header (4x16-bit) + sections
   - Encoding: Custom alphabet (muhtemelen)
   - Header: [2193, 14227, 6415, 6166]
   - Section 3: 14227 entries (14 bytes each)

### MTU.EXE'deki Bulgular

- Suffix listesi: 0x1B8B8 - 0x1BC45
- String referansları: ".SOZ", "MG2", "TUR" bulundu
- Entry size (14) referansları bulundu
- Section count (4, 7) referansları bulundu

### Önemli Gözlemler

1. **MTU.ING ve MTU.TES** aynı base offset'i (96000) kullanıyor ve aynı yapıya sahip görünüyor
2. **MTU.SOZ Section 3** formatı hala belirsiz - offset'ler direkt MTU.ING'e işaret etmiyor
3. **MTU.ING/TES** entry formatı MTU.TRK'den farklı - prefix başına sadece 3 byte (0xFF + count + ?)
4. Her dosyanın formatı gerçekten farklı, ortak bir pattern yok

### Format Analizi Sonuçları

**MTU.ING Entry Formatı (Kısmi):**
- Prefix başına format: `[instruction] [entry_count] [entries...]`
- Örnek: `0x00 0x03` = instruction 0x00, 3 entry var
- Entry formatı muhtemelen MTU.TRK'ye benzer ama encoding/decode sorunları var
- Bazı prefix'ler sadece 3 byte: `0xFF [count] 0x00` (entry count marker?)

**MTU.TES Entry Formatı:**
- MTU.ING ile aynı yapıya sahip görünüyor
- Aynı base offset (96000) kullanıyor

**MTU.SOZ Section 3:**
- 14227 entry (14 bytes each)
- Format: `[byte0] [bytes1-2] [bytes3-13]`
- Offset'ler direkt MTU.ING'e işaret etmiyor
- Belki MTU.TUR Section 3'e işaret ediyor?

### Sonraki Adımlar

1. MTU.ING ve MTU.TES'in entry formatını çözmek için byte-level analiz devam ediyor
2. MTU.SOZ Section 3'ün gerçek formatını anlamak gerekiyor - belki offset'ler relative veya farklı base kullanıyor
3. MTU.EXE'deki dosya okuma fonksiyonlarını disassemble etmek faydalı olabilir
4. Her dosyanın formatı gerçekten farklı - ortak bir pattern bulmak zor

