# Thesaurus Ek (Suffix) Algoritmasını Mükemmelleştirme Planı

## Problem

Mevcut `thesaurus.py` motoru 1,022 farklı ek ID'den sadece ~80'ini `apply_tes_suffix_id()` fonksiyonunda hardcode olarak tanıyor. Sonuç:

| Metrik | Değer |
|--------|-------|
| **Toplam ek uygulaması** | 46,634 |
| **Doğru çözülen** | 34,503 (%74.1) |
| **Çözülenemeyen** | 12,131 (%25.9) |
| **Bilinmeyen farklı ek ID** | 883 |
| **Etkisi** | ~4,000+ kelimenin yanlış veya eksik çıktısı |

Bozuk çıktı örnekleri:
- `yeni` → `kullanıl` (doğrusu: `kullanılmamış`) — 0xC0 redirect suffix chain eksik
- `eski` → `dur` (doğrusu: `durgun` vb.) — bare root
- `soğutkan` → `soğu` (doğrusu: `soğutucu` vb.) — 0x082f (-t) unhandled

## Araştırma Bulguları

### Bulgular

1. **0xC0 Redirect Suffix Chain Bug (KRİTİK)**
   - 0xC0 redirect stub'ları 5 byte'tan FAZLA olabilir (7, 9, 11, 12 byte)
   - Byte 3+ bir suffix CHAIN'i kodlar (u16 çiftleri, bit-15 devam biti)
   - Mevcut kod sadece ilk 5 byte'ı okuyor → sonraki ekleri kaçırıyor
   - **160 slot** etkileniyor (155×7B, 3×9B, 1×11B, 1×12B)
   - Kanıt: `yeni` slotu `[0xC0, 0x39, 0xB8, 0x92, 0x82, 0xC6, 0x84, 0x43, 0x05]` = `kullan` + `-ıl` + `-ma` + `-mış` = `kullanılmamış` ✅

2. **Section 3 Raw Text ≠ Ek Metni**
   - Section 3'teki Section 5 ham metni doğrudan ek değildir
   - Örnek: `-li` (0x0494) → raw="uş", `-le` (0x0446) → raw="kt"
   - 3+ karakterli ekler bazen eşleşiyor (lık, lik, sel, mak) ama kısa olanlar eşleşmiyor
   - bytes11 (11-byte morfolojik veri) ek metnini üretmek için EXE algoritmasında kullanılıyor

3. **bytes11 Yapısı**
   - `b11[7]`: Ünsüz + ünlü kodlaması (0x87=lı/ş, 0x47=li/ş, 0x27=lu, 0x17=lü)
   - `b11[10]`: Ünlü uyumu grubu (0=ü, 1=u, 2=i, 3=ı, +4=ek ünsüz)
   - `b11[0]`: Morfolojik sınıf (0x20=türetme, 0x50=çekim, 0x60=fiil, 0x80=edilgen)
   - EXE'nin seg3 fonksiyonları (0xC460, 0xD158) bu byte'ları işliyor

4. **En Sık Bilinmeyen Ek ID'leri** (top 10):

| ID | Kullanım | Olası Ek |
|----|----------|----------|
| 0x0093 | 473 | Bileşik sözcük eki (sever, kâr, cı, cı, vb.) |
| 0x07E0 | 347 | -vî (sıfat eki) |
| 0x00A5 | 267 | -kâr, -men, -baz (Farsça/meslek) |
| 0x069E | 224 | Bileşik sözcük bağlantısı |
| 0x09C8 | 222 | Bileşik sözcük bağlantısı |
| 0x0918 | 212 | Bileşik sözcük bağlantısı |
| 0x02FA | 204 | Bileşik sözcük / fiil eki |
| 0x00DF | 198 | -çıl, -hane, dış kaynak |
| 0x069B | 176 | Bileşik sözcük bağlantısı |
| 0x0129 | 174 | -den, bağlantı eki |

## Önerilen Değişiklikler

### Faz 1: Kritik Bug Düzeltmeleri (Hemen)

#### [MODIFY] [thesaurus.py](file:///Users/yasinkuyu/DEV/moonstar-master/src/engine/thesaurus.py)

**1a. 0xC0 Redirect Suffix Chain Desteği**
- Mevcut 5-byte sabit okumayı kaldır
- Byte 3'ten itibaren bit-15 continuation protokolüyle suffix chain ayrıştır
- Her suffix ID'yi sırayla `apply_tes_suffix_id()` ile uygula
- Doğru derived word'ü üret (yeni→kullanılmamış, vb.)

**1b. 0xC0 Sub-Record Redirect + Chain Kombinasyonu**
- `sub_suf > 0` olduğunda ÖNCE sub-record lookup yap
- Eğer chain'de ek suffix varsa, onları da hedef slot'a uygula

---

### Faz 2: Otomatik Ek Tablosu Çıkarma (Büyük Kazanım)

#### [NEW] [suffix_extractor.py](file:///Users/yasinkuyu/DEV/moonstar-master/src/suffix_extractor.py)

**Strateji**: EXE'nin seg3 suffix decode fonksiyonunu (0xC460) mini x86 emülatörle çalıştırarak TÜM 3,218 suffix ID için doğru ek metnini otomatik üret.

**Alternatif Strateji** (daha basit): DOSBox-X otomasyon scripti ile 200-300 anahtar kelimeyi sorgulayıp çıktıları karşılaştır, eksik suffix ID'leri empirik olarak tespit et.

**En Pratik Strateji**: bytes11 yapısını kısmen çözerek suffix gruplarını otomatik map'le:

```
b11[7] & 0x07 → ünsüz ailesi:
  1=c/ç, 2=d/t, 3=g/k, 4=l, 5=m, 6=n, 7=s/ş/z
b11[7] >> 4 → ünlü tipi:
  0=ü, 1=u, 2=i, 3=ı, 4=e, 5=a, 8=yok (sadece ünsüz)
b11[10] & 3 → ünlü uyumu grubu
```

#### [MODIFY] [thesaurus.py](file:///Users/yasinkuyu/DEV/moonstar-master/src/engine/thesaurus.py)

**2a. Fallback Suffix Table**
- `suffix_extractor.py` ile üretilen JSON tablosunu yükle
- `apply_tes_suffix_id()` hardcoded rule bulamazsa tabloya başvur
- Root + suffix_text birleştirme + temel ünlü uyumu kuralları uygula

**2b. Bileşik Sözcük Eki Desteği**
- Birçok "suffix" aslında bileşik sözcük bağlantısıdır (0x0093, 0x069E, vb.)
- Bu ID'ler ikinci bir TUR word indeksi + birleştirme kuralı içerir
- Mevcut `_decode_tes_slot` mantığını bileşik sözcük desteğiyle genişlet

---

### Faz 3: Doğrulama ve Kalite Kontrol

#### [NEW] [test_suffix_coverage.py](file:///Users/yasinkuyu/DEV/moonstar-master/src/test_suffix_coverage.py)

Otomatik doğrulama scripti:
1. Tüm 26,775 TUR kelimesini sorgula
2. Her çıktı kelimesini kontrol et: bare root mu, düzgün çekimli kelime mi?
3. Suffix başarı oranını raporla (hedef: %95+)
4. Bozuk çıktıları kategorize et (eksik ek, yanlış ünlü uyumu, bileşik sözcük hatası)

#### [MODIFY] [test_comparison.py](file:///Users/yasinkuyu/DEV/moonstar-master/src/test_comparison.py)

- `tarihi` (entry 25) ve `yeni` (entry 26) ground truth ekle
- DOSBox-X screenshot doğrulaması yap

---

## Uygulama Öncelik Sırası

> [!IMPORTANT]
> **Faz 1** tek başına 160 bozuk 0xC0 redirect'i düzeltir ve kritik kelimeleri (`yeni`, `problem`, `sorun`, vb.) hemen iyileştirir. Bu en düşük eforla en yüksek kazanım sağlayan değişikliktir.

**Faz 2** en zorlu kısım: 883 bilinmeyen suffix ID'nin her birini tanımlamak gerekiyor. Üç alternatif yaklaşım var:

1. **Mini x86 emülatör** (en doğru, en karmaşık): EXE'nin seg3 suffix decode fonksiyonunu Python'da emüle et
2. **DOSBox otomasyon** (orta zorluk): 100-200 kelimeyi DOSBox'ta sorgula, çıktıları karşılaştır, pattern'ları tespit et
3. **Empirik haritalama** (en basit, kısmi): bytes11 pattern'larını analiz ederek suffix ailelerini grupla, tek tek hardcode et

## Open Questions

> [!IMPORTANT]
> **Faz 2 yaklaşımı**: Hangi stratejiyi tercih edersiniz?
> - A) Mini x86 emülatör (en doğru ama karmaşık)
> - B) DOSBox otomasyon (orta seviye)  
> - C) Empirik haritalama + elle doğrulama (en basit, iteratif)

> [!NOTE]
> 883 bilinmeyen suffix ID'nin çoğu bileşik sözcük bağlantısıdır (iki kelimeyi birleştirme). Bunların bir kısmı aslında "ek" değil, TUR sözlüğündeki başka bir kelimeye referanstır. Bu durumda suffix ID aslında ikinci kelimenin TUR indeksini kodluyor olabilir.

## Doğrulama Planı

### Otomatik Testler
```bash
python3 -m pytest src/test_comparison.py -v  # Mevcut 24 ground truth
python3 src/test_suffix_coverage.py           # Yeni kapsamlı kapsam testi
```

### Manuel Doğrulama
- DOSBox-X'te `yeni`, `eski`, `problem`, `sorun` kelimelerini kontrol et
- UI'da aynı kelimeleri arayıp karşılaştır
