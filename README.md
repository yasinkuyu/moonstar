# MoonStar — Reverse Engineering

**MoonStar Türkçe Denetim Editörü** — 1995 tarihli Borland C++ Win16 uygulamasının
veri dosyalarının tersine mühendislik belgesi.

---

## Dosya Mimarisi

```
MTU.TRK  ──▶  İngilizce→Türkçe sözlük (doğrudan)
          └──▶ Türkçe→İngilizce sözlük (bellekte ters çevrilerek)
          └──▶ Eş Anlamlılar (ortak İngilizce'ye göre gruplandırılarak)
          └──▶ Kelime Oyunu'nda kelime çiftleri

MTU.TUR  ──▶  Türkçe Leb Demeden kelime listesi (26,775 kelime)
          └──▶ Türkçe çekim eki soyutlama tablosu (yazım denetimi)

MTU.ING  ──▶  Kelime Oyunu quiz FORMAT TALİMATLARI (sözlük değil)
MTU.TES  ──▶  Test modu format talimatları (MTU.ING ile aynı yapı)
MTU.SOZ  ──▶  Yazım denetimi ek sözlük dosyaları (yer adları vb.)
MTU.EXE  ──▶  Win16 NE yürütülebilir — tüm decode mantığı burada
```

> **Not:** Türkçe→İngilizce için **ayrı bir dosya yoktur**.
> EXE, MTU.TRK'yı belleğe yükler ve F8 tuşunda ters index oluşturur.

---

## MTU.TRK — İngilizce→Türkçe Sözlük ✅

**Boyut:** 831,798 byte | **Giriş:** 17,988 kelime

### Format

```
[3B header] + [676×3B prefix-offset table (A-Z×26)] +
[morpheme-encoded İngilizce kelimeler] + [Türkçe tanımlar]
```

- İngilizce kelimeler: 2 harfli prefix + morpheme gövde + EXE'deki suffix talimatı
- EXE `0x1B8B8`'de **195 girişli suffix tablosu** var (`-ing`, `-ed`, `-tion`, `to make`…)
- Türkçe tanımlar: `|` ayraçlı, `#` prefix = bağlamsal açıklama

### Çıktı

```
output/MTU.TRK.TXT
  abandon    terk etmek|bırakmak|vazgeçmek
  ability    yetenek|kabiliyet|güç
```

### Script

```bash
python3 src/mtu_trk.py
```

---

## MTU.TUR — Türkçe Sözlük / Leb Demeden ✅

**Boyut:** 220,720 byte | **Kelime:** 26,775

### Format

```
MG2\x1a (4B) + header [26775, 3218, 62800, 910] + 6 section
```

### Section 3 — Çekim Eki Tablosu (suffix stripping)

Section 3 **İngilizce metin değildir**. Leb Demeden'in morfoloji analizinde
kullandığı **Türkçe çekim eki soyutlama tablosudur**.

```
Her giriş (14 byte):
  byte0 bits 0-6 = ek uzunluğu
  val (u16)      = Section5 offset
  Section5[val:val+count] → 'acak', 'mak', 'ımdan'...
  bytes11[2]     = gramer sınıf kodu (3=geniş, 5=gelecek)
```

### TR_EN ve Eş Anlamlılar

MTU.TUR içinde İngilizce metin **yoktur**. Her iki sözlük de MTU.TRK'dan üretilir:

- **TR_EN:** TRK'daki `english → turkish` çiftleri ters çevrilir → 31,821 giriş
- **ES_ANLAM:** Aynı İngilizce'yi paylaşan Türkçe kelimeler → 28,266 grup

### Çıktılar

```
output/MTU.TUR.TXT           → 26,775 Türkçe kelime
output/MTU.TUR_TR_EN.TXT     → 31,821 Türkçe→İngilizce çifti
output/MTU.TUR_ES_ANLAM.TXT  → 28,266 eş anlamlı grubu
```

### Script

```bash
python3 src/mtu_trk.py   # önce çalıştırılmalı
python3 src/mtu_tur.py
```

---

## MTU.ING — Kelime Oyunu Quiz Metadata ✅

**Boyut:** 654,684 byte | **Geçerli slot:** 12,437 / 32,000

### MTU.ING bir sözlük değildir

İçindeki byte'lar **quiz UI format talimatlarıdır** — düz metin değil.
Gerçek İngilizce/Türkçe metin MTU.TRK'dan gelir.
`MTU.ING.TXT` okunaksız görünür çünkü zaten metin içermiyor.

### Format

```
[32,000 × 3B offset tablosu] + [slot verileri]

Her slot header (3B):
  byte0 = 0x00 (geçerli) / 0xFF (alias) / 0x10 / 0x20
  byte1 = (trk_idx + 1) % 256
  byte2 = flag (konu + quiz modu)
```

### Flag Byte Decode

```python
flag_low   = flag & 0x7F        # variant bitini sil
topic_idx  = flag_low % 36      # konu 0-35
quiz_mode  = flag_low // 36     # mod 0, 1 veya 2
is_variant = bool(flag & 0x80)  # variant mi?
```

> ⚠️ `flag % 36` YANLIŞ — flag ≥ 128 için hatalı konu atar.
> ✅ `(flag & 0x7F) % 36` DOĞRU.

### 36 Konu

Mecaz · Argo · Renk · Türemiş · Anatomi · Askerlik · Bitkibilim · Biyoloji ·
Coğrafya · Denizcilik · Dilbilgisi · Dinsel · Ekonomi · Elektrik · Felsefe ·
Fizik · Gökbilim · Hayvanbilim · Hekimlik · Hukuk · İskambil · Kimya · Mantık ·
Matematik · Meteoroloji · Mimarlık · Müzik · Otomobil · Ruhbilim · Sinema ·
Spor · Teknik · Ticaret · Tiyatro · Yazın · Yerbilim

### Çıktı

```
output/MTU.ING.BY_TOPIC.TXT  → Konuya göre gruplandırılmış quiz girişleri
```

### Script

```bash
python3 src/mtu_ing.py
```

---

## MTU.EXE — Win16 NE Analizi ✅

**Boyut:** 401,920 byte | **NE header:** 0x250 | **Derleyici:** Borland C++

### Menü Kısayolları (EXE'den çıkarılan)

| Kısayol | Fonksiyon | Veri Kaynağı |
|---------|-----------|--------------|
| `F6` | Türkçe Leb Demeden | MTU.TUR |
| `Sft+F6` | İngilizce Leb Demeden | MTU.TRK |
| `F7` | Eş Anlamlı Kelimeler | MTU.TRK (gruplandırılmış) |
| `F8` | Türkçe → İngilizce | MTU.TRK (ters index) |
| `Sft+F8` | İngilizce → Türkçe | MTU.TRK (doğrudan) |
| `F9` | Metin İstatistik | — |

### Önemli Adresler (DGROUP)

| Dosya Offset | İçerik |
|-------------|--------|
| 0x1A7CA | `table_B` — ING karakter lookup tablosu (256B) |
| 0x1B388 | `table_A` — double-lookup index (256B) |
| 0x1B61D | `TURTESINGTRK` — dosya tipi kodları |
| 0x1B62C | `TESING1.Anlam` — quiz tipi etiketi |
| 0x1B63A | 36 konu adı listesi (CP857, null-terminated) |
| 0x1B8B8 | İngilizce suffix tablosu (195 giriş) |

---

## Türkçe→İngilizce Ters Sözlük — Lookup Algoritması ✅

Web arayüzündeki Türkçe→İngilizce sözlük (F8 penceresi) şu adımlarla üretilir:

### 1. Doğrudan Eşleştirme

MTU.TRK'daki her `english → turkish` çifti ters çevrilir:

```
root  →  kök
base  →  temel
```

### 2. Türkçe Morfoloji — Suffix Stripping

TRK tanımları çekimli form içerebilir (ör. `temeli`, `kökeni`).
`get_turkish_stem()` fonksiyonu yaygın ekleri soyar:

```python
temeli  →  temel   (iyelik eki -i)
kökeni  →  köken   (iyelik eki -i)
```

Bu sayede `root → temeli` ile `base → temel` çiftleri **temel** ortak kökünde buluşur.

### 3. Hop-1 Eş Anlamlı Genişletme

Her Türkçe kelimenin doğrudan İngilizce çevirilerinden hareketle Hop-1 eş anlamlı grafiği oluşturulur:

```
kök  →  root
root → {temel, köken, kaynak, başlangıç, ...}
temel → {base, basis, foundation, ...}
```

Bu grafik üzerinde TF-IDF benzeri özgüllük ağırlıklandırması uygulanır:

```python
spec = 1.0 / max(1, len(en_to_trs[en]))
score = max(score, 10.0 * spec)
```

### 4. Sonuç Skoru (kök örneği)

| İngilizce | Skor | Kaynak |
|-----------|------|--------|
| root | — | doğrudan eşleştirme |
| onset, inception, outset | 10.0 | tekil çeviri → yüksek özgüllük |
| basis | 5.0 | `temel` üzerinden Hop-1 |
| origin | 2.0 | `köken` üzerinden Hop-1 |
| base | 0.5 | `temel` üzerinden Hop-1 (çok anlamlı) |

### Hardcode Yok

Tüm eşleştirmeler **tamamen dinamik** — `kök`, `malak`, `sıpa` vb. için
hiçbir `if tr_word == ...` kontrolü kullanılmaz.

---

## Açık Sorular

| # | Konu | Öncelik |
|---|------|---------|
| 1 | MTU.SOZ tam decode — Section3 yapısı MTU.TUR'dan farklı | MEDIUM |
| 2 | MTU.TUR Section3 `bytes11` gramer sınıfları — tam anlam bilinmiyor | MEDIUM |
| 3 | ING `0x0E` handler — `format_sub` yerine harici fonksiyon, ne üretiyor? | LOW |
| 4 | ING `0xFF/0x10/0x20` prefix slotlar — 2,027 non-standard giriş | LOW |
| 5 | KONTROL.SOZ — 12 byte, amaç belirsiz | LOW |

---

## Kurulum

```bash
# 1. data/ klasörüne veri dosyalarını kopyala
cp MTU.* data/

# 2. Sözlükleri decode et
python3 src/mtu_trk.py
python3 src/mtu_tur.py
python3 src/mtu_ing.py

# 3. Web arayüzünü başlat → http://localhost:8080
python3 src/ui.py
```

## API

| Endpoint | Veri |
|----------|------|
| `/api/trk` | İngilizce→Türkçe (17,975 giriş) |
| `/api/rev` | Türkçe→İngilizce (62,942 giriş — stem+eş anlamlı genişletmeli) |
| `/api/tur` | Leb Demeden (26,775 kelime) |
| `/api/syn` | Eş Anlamlılar (8,573 grup) |
| `/api/quiz` | Kelime Oyunu (12,437 slot, 36 konu) |
