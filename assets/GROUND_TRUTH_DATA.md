# MoonStar Win16 Orijinal Ekran Görüntüleri ve Ground Truth Veri Tabanı

Bu klasör, DOSBox-X / Windows 3.11 üzerinde çalışan orijinal 16-bit **MoonStar (`MTU.EXE`)** uygulamasından alınmış doğrudan ekran görüntülerini ve tersine mühendislik referanslarını içerir.

---

## 📸 Ekran Görüntüleri ve Kesin Eşleşme Listesi

### 1. `öz` (1.Anlam)
- **Ekran Dosyası**: `media_1788356020019.png`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`, `3.Anlam`, `Türemiş`
- **1.Anlam Kelimeleri**:
  ```text
  arı, arık, damıtık, halis, has, katıksız, katışıksız, katkısız, mukattar, özbeöz, sade, saf, safi, som, yalın
  ```

### 2. `öz` (Türemiş Grubu)
- **Ekran Dosyası**: `mehmetkut_sc01_oz_turemis.jpg`
- **Türemiş Kelimeleri**:
  ```text
  özalgı, özbağışık, özbeöz, özbeslenme, özdenetim, özdenge, özdeş, özdevim, özdevinim, özdeyiş, özdışı, özdirenç, özeleştiri, özezer, özgeçmiş, özgüven, özışın...
  ```

### 3. `kitap` (1.Anlam)
- **Ekran Dosyası**: `media_1788356031167.png`
- **Anlam Grupları**: `1.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  elkitabı
  ```
- **Kural**: `MTU.TUR` içindeki `Elkitab` bileşiği kök sonu eşlemesiyle `-ı` iyelik eki alarak üretilir.

### 4. `elma` (1.Anlam)
- **Ekran Dosyası**: `media_1788356046323.png`
- **Anlam Grupları**: `1.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  amerikaelması, kirazelması
  ```
- **Kural**: `MTU.TUR` içindeki `Amerikaelma` ve `Kirazelma` bileşik gövdeleri `-sı` iyelik ekiyle üretilir.

### 5. `ekmek` (1.Anlam)
- **Ekran Dosyası**: `media_1788356060246.png`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  baston, dikmek, ekip biçmek, francala, gevrek, pide, sandviç, serpmek, simit, somun, tohum atmak, üretmek, yetiştirmek, yufka
  ```
- **Kural**: İsim (fırın/ekmek ürünleri) ve Fiil (tarım/ekim eylemleri) sesteş kavram alanlarının birleşimi.

### 6. `gelmek` (1.Anlam)
- **Ekran Dosyası**: `media_1788356074658.png`
- **Anlam Grupları**: `1.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  basmak, bastırmak, buyurmak, çıkagelmek, dönmek, erişmek, görünmek, gözükmek, onurlandırmak, sökün etmek, şeref vermek, şereflendirmek, teşrif etmek, uğramak, ulaşmak, varmak, yaklaşmak
  ```

### 7. `yüz` (1.Anlam & Mecaz)
- **Ekran Dosyası**: `media_1788356305130.png`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`, `Mecaz`
- **1.Anlam Kelimeleri**:
  ```text
  beniz, bet, bet beniz, çehre, fizyonomi, sıfat, sima, surat, vecih
  ```

### 8. `göz` (1.Anlam)
- **Ekran Dosyası**: `media_1788356313232.png`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  bakış, bakış açısı, bakma, görme, görüş, görüş açısı, nazar, yaklaşım
  ```

### 9. `akıl` (1.Anlam)
- **Ekran Dosyası**: `media_1788356323903.png`
- **Anlam Grupları**: `1.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  algı, an, anlak, anlayış, anlık, bellek, beyin, bilinç, eseme, feraset, hafıza, havsala, huş, idrak, ihata, irfan, izan
  ```

### 10. `güzel` (1.Anlam)
- **Ekran Dosyası**: `media_1788356335603.png`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  afet, ahu, albenili, alımlı, ay parçası, bediî, biçimli, bir içim su, cazibeli, cazip, cemal, çekici, dilber, edalı, enfes, estetik, gelgelli
  ```

### 11. `test` (1.Anlam)
- **Ekran Dosyası**: Canlı DOSBox-X `test` sorgusu
- **Anlam Grupları**: `1.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  deneme, denetim, denetleme, imtihan, kontrol, prova, sınama, sınav, sözlü, tartma, tatma, yazılı, yoklama
  ```
- **Kural**: `MTU.TES` yuva 23717 (`0xC0` yönlendirmesiyle 5406 `dene` ve morfolojik `-me` ekiyle `deneme`), bağlı sınav kümesi (`sına` 21080) ve `tatma` (`tat` + `0xC5 0x04`) ile tam 13 kelimelik liste.

### 12. `mali` / `malî` (1.Anlam)
- **Ekran Dosyası**: Canlı DOSBox-X `mali` sorgusu
- **Sözcük**: `mali`
- **Kök Sözcük**: `malî` (düzeltme/şapkalı biçim)
- **Anlam Grupları**: `1.Anlam`
- **1.Anlam Kelimeleri**:
  ```text
  mal ile ilgili, para ile ilgili, parasal
  ```
- **Kural**: Çok kelimeli sözcük öbeği formülü `count = ((flag >> 4) & 3) + 1` (yuva 15361: `0x20` -> 3 kelimelik öbekler: `mal ile ilgili`, `para ile ilgili` ve `0x00` -> `parasal` [-sal eki (0x97, 0x07)]).

### 13. `hafif` (1.Anlam)
- **Ekran Dosyası**: Canlı DOSBox-X `hafif` sorgusu
- **Sözcük**: `hafif`
- **Kök Sözcük**: `hafif`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`, `3.Anlam` (Yalnızca 3 grup; Türemiş/Mecaz yok)
- **1.Anlam Kelimeleri**:
  ```text
  ağır olmayan, ağırlığı olmayan, belli belirsiz, ciddî olmayan, ciddiyetten uzak, emeksiz, etkisiz, eziyetsiz, güçlüksüz, kolay, külfetsiz, önemsiz, rahat, sıkıntısız, silik, tartıda az çeken, tüy gibi
  ```
- **Kural**: Section 3 16-bit ek zincirleme (`bit 15` continuation bayrağı) ve morfem ID'leri: `0x07ef` (-siz), `0x04bb` (-lüksüz), `0x0488`+`0x028f` (-lığı), `0x0834` (-ten), `0x0127` (-de), `0x0245` (-en).

### 14. `dolu`
- **Ekran Dosyası**: Canlı DOSBox-X `dolu` sorgusu
- **Sözcük**: `dolu`
- **Kök Sözcük**: `dolu`
- **Anlam Grupları**: `1.Anlam` (Yalnızca 1 grup; Mecaz yok)
- **1.Anlam Kelimeleri (Başlıca)**:
  ```text
  avuç avuç, az buz değil, bin bir, bir alay, bir dolu, bir hayli, bir nice, bir sürü, bir yığın, birçok, bol, bol bol, bunca, çok, dopdolu, dünya kadar, fazla
  ```
- **Kural**: Eşadlı kök çözümlemesi (6100 `0xFF` yönlendirmesi atlanır, 6101 ana yuva çözülür; `0x10` ve `0x20` çok kelimeli deyim öbekleri).

### 15. `ağır`
- **Ekran Dosyası**: Canlı DOSBox-X `ağır` sorgusu
- **Sözcük**: `ağır`
- **Kök Sözcük**: `ağır`
- **Anlam Grupları**: `1.Anlam`, `Mecaz` (2 grup; 2.Anlam yok)
- **1.Anlam Kelimeleri**:
  ```text
  balyoz gibi, battal, cıva gibi, gülle gibi, hantal, kilolu, kunt, kurşun gibi, külçe gibi, lök gibi, okkalı, yüklü
  ```
- **Kural**: `0x10` bayraklı "... gibi" benzetme öbekleri ve `0x04A2` (-lu), `0x0486` (-lı), `0x04B0` (-lü) ekleri.

### 16. `boş`
- **Ekran Dosyası**: Canlı DOSBox-X `boş` sorgusu
- **Sözcük**: `boş`
- **Kök Sözcük**: `boş`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam` (2 grup; Mecaz yok)
- **1.Anlam Kelimeleri**:
  ```text
  abes, anlamsız, beyhude, değersiz, hor, nafile, önemsiz, yararsız
  ```
- **Kural**: `flag & 0x40` bit 6 kesme bayrağı (yuva sonundaki zıt anlam ve ek verileri kesilir); `0x07EF` (-siz) ve `0x07DC` (-sız) ekleri.

### 17. `adalet`
- **Ekran Dosyası**: Canlı DOSBox-X `adalet` sorgusu
- **Sözcük**: `adalet`
- **Kök Sözcük**: `adalet`
- **Anlam Grupları**: `1.Anlam` (Yalnızca 1 grup; Mecaz yok)
- **1.Anlam Kelimeleri**:
  ```text
  âlicenaplık, doğruluk, dürüstlük, eşitlik, hâk, hâk yemezlik, hakkaniyet, hakseverlik, haktanırlık, hoşgörü, insaf, insaniyet, insanlık, iyilik, merhamet, meşruluk, tarafsızlık
  ```
- **Kural**: `0x048A`/`0x0498`/`0x04A6`/`0x04B4` (-lık/lik/luk/lük), `0x07DF` (-sızlık) ekleri ve `0x10` öbeği `hâk yemezlik` (`ye` + `0x0507` [-me] + `0x0C36` [-z] + `0x0498` [-lik]).

### 18. `cesaret`
- **Ekran Dosyası**: Canlı DOSBox-X `cesaret` sorgusu
- **Sözcük**: `cesaret`
- **Kök Sözcük**: `cesaret`
- **Anlam Grupları**: `1.Anlam` (Yalnızca 1 grup; Mecaz yok)
- **1.Anlam Kelimeleri**:
  ```text
  ataklık, atılganlık, babayiğitlik, bahadırlık, celâdet, cesurluk, cüret, cüretkârlık, çekinmezlik, efelik, fedaîlik, hamaset, kahramanlık, korkusuzluk, maneviyat, mertlik
  ```
- **Kural**: `çekinmezlik` morfem zinciri (`çek` + `0x035C` [-in] + `0x0507` [-me] + `0x0C36` [-z] + `0x0498` [-lik]), `Hamasev` yumuşak kök sertleşmesi (`v -> t` -> `hamaset`).

### 19. `hürriyet`
- **Ekran Dosyası**: Canlı DOSBox-X `hürriyet` sorgusu
- **Sözcük**: `hürriyet`
- **Kök Sözcük**: `hürriyet`
- **Anlam Grupları**: `1.Anlam` (Yalnızca 1 grup)
- **1.Anlam Kelimeleri**:
  ```text
  azadelik, azatlık, bağımsızlık, başıboşluk, başına buyrukluk, erkinlik, hürlük, istiklâl, muhtariyet, muhtarlık, müstakillik, özerklik, özgürlük, serbestî, serbestlik
  ```
- **Kural**: `0x02AA` (-ına / -ine) ve `0x04A6` (-luk) ile `başına buyrukluk` öbeği.

### 20. `barış`
- **Ekran Dosyası**: Canlı DOSBox-X `barış` sorgusu
- **Sözcük**: `barış`
- **Kök Sözcük**: `barış`
- **Anlam Grupları**: `1.Anlam` (Yalnızca 1 grup)
- **1.Anlam Kelimeleri**:
  ```text
  ateşkes, hazar, sulh, uyuşma
  ```
- **Kural**: Birincil eşadlı yuva seçimi (2295 isim yuvası seçilir, 2296 fiil kökü kirletmesi engellenir); `uy` + `0x0980` (-uş) + `0x04C5` (-ma) -> `uyuşma`.

### 21. `zengin`
- **Ekran Dosyası**: Canlı DOSBox-X `zengin` sorgusu
- **Sözcük**: `zengin`
- **Kök Sözcük**: `zengin`
- **Anlam Grupları**: `1.Anlam`, `2.Anlam`, `3.Anlam` (3 grup)
- **1.Anlam Kelimeleri**:
  ```text
  artık, bereketli, bol, çok, dolgun, dolu, dünya kadar, fazlasıyla, gani, gümrah, gür, hayli, hesapsız, ibadullah, kabarık, külliyeli, mebzul
  ```
- **Kural**: `grp_code = flag & 0x0F` alt nibble kuralı (`0x11` -> `2.Anlam` öbeği `altın babası`, `1.Anlam`'dan ayrılır); `0x07DB` (-sıyla) eki (`fazlasıyla`); `dolgur` -> `dolgun` kök yumuşaması.

### 22. `ölüm`
- **Ekran Dosyası**: Canlı DOSBox-X `ölüm` sorgusu
- **Sözcük**: `ölüm`
- **Kök Sözcük**: `ölüm`
- **Anlam Grupları**: `1.Anlam` (1 grup)
- **1.Anlam Kelimeleri**:
  ```text
  adem, akıbet, cana kıyma, düşük, ecel, emrihak, göçme, göçüp gitme, göçüş, idam, intihar, kayıp, memat, mevt, sıkıt, songu, şahadet
  ```
- **Kural**:
  - `0x0000` yönelme/dative eki (`can` + `0x0000` -> `cana` -> `cana kıyma`)
  - `0x09FF` zarf-fiil eki (`göç` + `0x09FF` -> `göçüp` -> `göçüp gitme`)
  - `0x0A32` eylem adı eki (`göç` + `0x0A32` -> `göçüş`)
  - `ğ -> k` morfolojik sertleşme (`düşüğ` -> `düşük`)
  - `akıbes` -> `akıbet` dişsel sertleşme.

### 23. `giriş`
- **Ekran Dosyası**: Canlı DOSBox-X `giriş` sorgusu
- **Sözcük**: `giriş`
- **Kök Sözcük**: `giriş`
- **Anlam Grupları**: `1.Anlam` (1 grup)
- **1.Anlam Kelimeleri**:
  ```text
  açılış, açış, aralık, aşama, atılım, basamak, başlama, başlangıç, başlayış, bidayet, duhuliye, en başta, en önce, girişlik, hamle, ilk başta, ilk bölüm
  ```
- **Kural**:
  - `0x80` Morfolojik Başlık: Yuva 8646 (`Gir`) başındaki `[0x80, 0xAC, 0x03]` morfem başlığı ile doğrudan `giriş` türemiş başlığına (`gir` + `0x03AC` [-iş]) endekslenir.
  - `0x0292` + `0x02F9` morfem zinciri: `aç` + `-ıl` + `-ış` -> `açılış`
  - `0x02F9` morfem: `aç` + `-ış` -> `açış`
  - `0x0407` + `0x0B7E` morfem zinciri: `baş` + `-la` + `-yış` -> `başlayış`
  - `0x03AC` + `0x0498` morfem zinciri: `gir` + `-iş` + `-lik` -> `girişlik`
  - `0x0831` bulunma/locative eki: `baş` + `-ta` -> `başta` (`en başta`, `ilk başta`).

### 24. `çıkış`
- **Ekran Dosyası**: Canlı DOSBox-X `çıkış` sorgusu
- **Sözcük**: `çıkış`
- **Kök Sözcük**: `çıkış`
- **Anlam Grupları**: `1.Anlam` (1 grup)
- **1.Anlam Kelimeleri**:
  ```text
  çıkak, çıkıt, kaynak, köken, mahreç, menşe, orijin, öz, soy, töz
  ```
- **Kural**:
  - `0x40` Alt-Kayıt (Sub-record): Yuva 4569 (`çık`) içinde `0x40` sınırından sonra gelen `0x02F9` (-ış) morfem başlığı ile doğrudan `çıkış` alt-kaydı olarak ayrıştırılır.
  - Tam 10 kelimelik köken/menşe eş anlam kümesi.

---

*Tüm bu listeler `src/engine/thesaurus.py` motorunun ve `src/test_comparison.py` doğrulama paketinin otomatik test referansıdır.*
