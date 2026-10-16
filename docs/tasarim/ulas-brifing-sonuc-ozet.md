# Kut v1.2 tasarımı: Tanıştırma yolu, Görüşme brifingi, Sonuç döngüsü, Haftalık özet + bildirim

Umut'un isteği (15 Ekim 2026): "Tanıştırma yolu, sonuç döngüsü, görüşme öncesi brifing, Kut'un sana gelmesi. Production seviyesinde."
Bu belge modüller arası **sözleşmedir**. Her modül yalnız kendi dosyasına yazılır; ortak dosyalara (ag_cekirdek.py, ag_sunucu.py,
ag_sablon.html, kut.pyw, README.md, AGENTS.md) yalnız entegrasyon aşaması dokunur.

## Ortak ilkeler (hepsi için zorunlu)
- **Yerel ve deterministik.** Bu dört özellik model çağırmaz, ağa çıkmaz. Taslak mesajlar yerel şablondur. (README "Ağa çıkabilen yollar"a yeni satır gerekmez.)
- **Hariç listesi kesin.** `k["haric"]` doğru olan kişi hiçbir çıktıda (yol düğümü, hedef, özet maddesi, brifingdeki ortak tanıdık, bildirim) görünmez.
- **Kullanıcı beyanı önce gelir.** Kullanıcının "işe yaramadı / atla" kararı sonraki önerileri değiştirir; Kut aynı şeyi ısrarla önermez.
- **Kaynak Markdown.** Yeni kalıcı veri `<veri>/` altında okunur Markdown'dır (JSON yalnız ayarlar.json'da). Yazma atomiktir (geçici dosya + `os.replace`).
- **Saf işlevler.** Hesaplama işlevleri `veri` sözlüğünü parametre alır (aşağıda); dosya okuyan ince sarmalayıcılar ayrıdır. Böylece demo
  (kapsül modüllerle üretilen kurgusal veri) aynı işlevleri çağırabilir ve testler dosya sistemi olmadan çalışır.
- **Dil ve ton.** Türkçe, "sen" hitabı, kısa, somut; guru/kanca dili yok; insanları puanlayan dil yok ("bağ", "sıcaklık" de; "puanı düşük kişi" deme).
- **Güvenlik.** Yol üretiminde kişi id'si `c.gecerli_id` ile doğrulanır. Dışarıdan gelen metin (hedef araması, not) uzunluk sınırlı ve tek satıra indirgenir.
  Sırlar: Markdown'a yazılan serbest metin `ag_sir.temizle(metin, "<yer>", entropi=False)` süzgecinden geçer.
- **Kod biçimi.** Mevcut Kut kodu gibi: Türkçe adlar, kısa docstring, yoğun ama okunur satırlar, stdlib yalnız (ek paket yok). Python 3.10+.
- **Testler.** `tests/test_<modul>.py`; ilk satırlarda `import _yalitim` (bkz. tests/test_soz.py). Kurgusal adlar (Ayşe Yılmaz, Mehmet Kaya, Deniz Demo...).
  Gerçek veri klasörüne, gerçek LOCALAPPDATA'ya, gerçek Görev Zamanlayıcı'ya dokunulmaz (subprocess mock'lanır).

## `veri` sözlüğü (girdi biçimi)
`c.veri_hazirla(foto_gom=False)` çıktısı: `kisiler[0]` merkez (ben, `id` = `c.ben_id()`, `tur` "ben" değil, kaydına bakma), `kisiler[1:]` kişiler:
`id, ad, tur, kurum, rol, alan[], etiketler[], nereden[], yakinlik (0–3 int), son_temas, etkin_son_temas (iso|""), sonraki_adim, sonraki_tarih,
neden_onemli, ne_verebilirim, kullanici_gorusu, haric (bool), uzak_kapali, govde (Markdown gövdesi: ## Temas, ## Sözler, ## Senin beyanların...),
puan {sicaklik, derinlik, karsiliklilik, sureklilik, kopru, ortak_zemin, _trend}, sozler [ag_soz.oku + yazi/gun], acik_soz`.
`iliskiler`: `[{a, b, tip, not, kaynak, tarih}]` (tip ∈ `c.TIPLER`; yönlü tipler mentor/yonetici/asistan/hocasi A → B). Merkez de `a`/`b` olabilir.
`dikkatler`: `[{kisiler: [id], seviye, metin}]`. `bu_hafta`: `[{id, neden, oncelik, tur?, yon?, sira?}]`. `ben`: merkez alanları (ilgiler dahil).
Merkez ile kişi arasındaki bağ ayrıca kişinin `yakinlik` alanıdır (0 = tanımıyor/hedef; doğrudan bağ değildir).

---

## 1. `kut/ag_yol.py`: Tanıştırma yolu
"X'e ulaşmak istiyorum" → en sıcak bağ zinciri + ilk adım + taslak mesaj.

### Graf
- Düğümler: merkez + hariç olmayan kişiler.
- Merkez–kişi kenarı: yakınlık 3 → 0,92; 2 → 0,75; 1 → 0,45; 0 → kenar yok. Sıcaklıkla çarp: `0,55 + 0,45 * sicaklik/100` (sıcaklık yoksa 0,7).
  Merkezi içeren `iliskiler` satırı varsa (ör. hocasi hoca → ben) güçlüsü alınır.
- Kişi–kişi kenarı (`iliskiler`): partner 0,9; akraba 0,85; arkadas 0,8; birlikte-calisiyor 0,7; is-ortagi 0,7; mentor 0,7; yonetici 0,65;
  hocasi 0,65; asistan 0,65; tanisiyor 0,4. `rakip` ve `gerginlik` **kenar değildir**; ayrıca o çiftin yolda yan yana gelmesi yasaktır.
  Kenar yönsüzdür (tanıştırma iki yöne de istenebilir). Aynı çift için birden çok satır varsa en güçlüsü.
- Ara düğüm (köprü) çarpanı: köprü kişinin merkeze yakınlığı da önemlidir ama zaten ilk kenar merkez–köprü kenarıdır. 2. ve sonraki ara
  düğümler için `0,9` atlama cezası uygulanır (uzun zincir zayıflar).

### Arama
- Skor = kenar ağırlıkları çarpımı × atlama cezaları; 0–100'e `round(100 * skor)`.
- En çok 4 kenar (3 ara kişi). Dijkstra (−log ağırlık) + Yen k-en-kısa yol; k = 3. **İlk adımları farklı** yollar tercih edilir
  (aynı ilk adımla gelen ikinci yol, farklı ilk adımlı bir yol varsa sona itilir).
- Hedef zaten yakınlık ≥ 1 ise sonuç `dogrudan: true` ve tek "yol" merkez → hedef (taslak doğrudan hedefe).

### Hedef türleri
- `hedef_id`: ağdaki bir kişi. Hariçse `ValueError("Bu kişi hariç listende; öneri üretilmez.")`; yoksa `ValueError("kişi bulunamadı")`.
- `ara` (serbest metin, ≤ 80 karakter): kurum, rol, alan, etiketler, ad içinde `c.sade` ile jeton eşleşmesi ("Şişecam", "finans", "yapay zeka").
  Eşleşen kişiler iki gruba ayrılır: `tanidiklarin` (yakınlık ≥ 1: "zaten tanıyorsun") ve `hedefler` (yakınlık 0: her biri için en iyi yol).
  En çok 8 hedef, skora göre sıralı.

### API
```python
def yollar(veri, hedef_id, k=3, amac="") -> dict
# {"hedef": {id, ad, tur, kurum, rol}, "dogrudan": bool,
#  "yollar": [{"skor": 0-100, "dugumler": [{id, ad, tur, yakinlik}], "kenarlar": [{a, b, tip, etiket, guc}],
#              "ilk_adim": {id, ad}, "gerekce": [str], "uyarilar": [str], "taslak": str}],
#  "yok_nedeni": str}   # yol yoksa ("Ağında bu kişiye giden bir bağ yok. Bir bağ ekle ya da doğrudan yaz.")
def ara(veri, metin, amac="") -> dict
# {"sorgu": metin, "tanidiklarin": [{id, ad, kurum, rol, yakinlik, sicaklik}], "hedefler": [{hedef, en_iyi (yol), skor}]}
def taslak(yol, veri, amac="") -> str
```
- `gerekce`: her kenar için bir cümle: "Baran ile yakınsın; son temas 3 gün önce." / "Baran ve Selin Hoca birlikte çalışıyor." (yönlü tiplerde
  doğru yön: "Selin Hoca, Baran'ın hocası.").
- `uyarilar`: yoldaki kişilerle ilgili `dikkatler` metinleri (yalnız yol üzerindeki kişileri içerenler) + soğuk ilk adım ("Baran ile 90 gündür
  konuşmadın; tanıştırma istemeden önce bağı ısıt.") + tanisiyor zayıf kenar ("Baran ile Selin yalnız tanışıyor; tanıştırma zayıf kalabilir.").
- `taslak`: ilk adıma yazılacak kısa mesaj. 2 kişilik yolda: "Selam Baran, nasılsın? Bir ricam olacak: Selin Hoca ile tanışmak istiyorum{amac}.
  Sen onu tanıyorsun diye düşündüm; uygun görürsen bizi tanıştırabilir misin? İstersen kısa bir tanıtım metni de hazırlayayım." Daha uzun yolda
  ilk adımdan bir sonraki kişiye ulaşmasını ister ("...Baran üzerinden Selin Hoca'ya ulaşmaya çalışıyorum"). Doğrudan durumda hedefe kısa
  tanışma/yeniden temas mesajı. `amac` boşsa cümle doğal kalır. Ad olarak ilk ad (`ad.split()[0]`), "Hoca/Dr." unvanlı adlar olduğu gibi.
- Performans: 500 kişi + 2000 bağda tek `yollar` < 200 ms (testte ölç).

## 2. `kut/ag_brifing.py`: Görüşme öncesi brifing
Bir kişiyle görüşmeden önce tek sayfa: kim, nasıl tanıştınız, son konuştuklarınız, açık sözler, sonraki adım, ortak tanıdıklar, dikkat,
konuşma önerileri, Kut'un geçmiş önerileri ve sonuçları.

```python
def brifing(veri, kid, bugun=None, sonuclar=None, hedefler=None, strateji=None) -> dict
def markdown(b) -> str      # Kopyala/Yazdır için okunur Markdown
```
Çıktı (`dict`): `kisi {id, ad, tur, tur_ad, kurum, rol, yakinlik, yakinlik_yazi}`, `ozet` (1–2 cümle: "Selin Hoca, Kuzeyova Üniversitesi'nde ...; yakınlığınız 2,
son temas 34 gün önce, bağ soğuyor."), `neden_onemli`, `ne_verebilirim`, `senin_gorusun`, `beyanlar [str]` (## Senin beyanların),
`son_temaslar [{tarih, kanal, metin}]` (en yeni 5; gövdedeki `- GG.AA.YYYY · kanal · metin` satırları), `sicaklik {deger, trend, son_temas_gun}`,
`sozler {senin [..], onun [..]}` (açık sözler, `yazi` ile; gecikmiş olan başta), `sonraki {adim, tarih, gun}`, `ortak_tanidiklar [{id, ad, tip_etiket}]`
(kişinin komşularından merkeze yakınlığı ≥ 1 olanlar, hariç yok, en çok 6), `nasil_tanistiniz` (nereden + varsa ilk temas tarihi), `yol`
(yakınlık 0 ise `ag_yol.yollar(veri, kid, k=1)` sonucu, yoksa None), `dikkat [str]` (kişiyi içeren dikkatler), `hedefler [{id, baslik}]`
(parametreyle verilen hedeflerden `anahtar`/başlık/gövde metni kişinin adını ya da kurumunu anan aktif/taslak hedefler), `strateji [{baslik, sonuc}]`
(parametreyle verilen son strateji okumasında bu kişiyi kanıt gösteren hamleler), `gecmis [{tarih, oneri, sonuc}]` (ag_sonuc kayıtlarından bu
kişi, en yeni 5), `konusma [str]` (3–6 madde; aşağıda), `uretildi`.
- `konusma` (deterministik, öncelik sırasıyla): gecikmiş senin sözün ("Söz verdiğin X'i teslim et ya da yeni tarih ver"), onun açık sözü
  ("Söz verdiği Y'yi nazikçe hatırlat"), sonraki adım, son temas konusu üzerinden takip ("Geçen sefer konuştuğunuz ... ne oldu?"),
  ortak zemin (ilgilerinle kesişen alan/etiket: "İkiniz de veri görselleştirmeyle ilgileniyorsunuz"), ne verebilirim ("Ona ... teklif et"),
  hedefle bağ ("<hedef başlığı> için ondan ne isteyeceğini netleştir"). Boş alandan madde üretme.
- Kişi hariçse `ValueError("Bu kişi hariç listende.")`. Yoksa `ValueError("kişi bulunamadı")`.
- `markdown()` başlıklı, kısa, yazdırmaya uygun; boş bölüm yazılmaz.

## 3. `kut/ag_sonuc.py`: Sonuç döngüsü
Kut'un önerdiği her somut adım (haftalık özet maddesi, tanıştırma yolu ilk adımı) bir kayıt olur; kullanıcı sonucu işaretler; sonraki öneriler
buna göre değişir. Strateji hamlelerinin kendi sonuç kaydı (`ag_strateji.sonuc_yaz`) aynen kalır; bu modül yalnız okur ve istatistiğe katar.

### Kaynak: `<veri>/sonuclar.md`
```
# Kut önerileri ve sonuçları
Kut'un önerdiği adımlar ve senin kararın. Bu dosyayı elle de düzenleyebilirsin; satır silmek yerine sonucu değiştir.

| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-19 | ozet | selin-hoca | Açık veri çağrısı için yaz | bekliyor |  |  |
```
- `kaynak` ∈ `ozet | yol | brifing | elle`. `sonuc` ∈ `bekliyor | yaptim | ise_yaradi | ise_yaramadi | ertelendi | atlandi`.
  `SONUCLAR = {"bekliyor": "Bekliyor", "yaptim": "Yaptım", "ise_yaradi": "İşe yaradı", "ise_yaramadi": "İşe yaramadı", "ertelendi": "Ertelendi", "atlandi": "Atlandı"}`.
- Hücre metni: `|` → `/`, satır sonu → boşluk, ≤ 200 karakter, `ag_sir.temizle`.
- `anahtar` (tekrar kaydı önleme): (kaynak, kisi, oneri sadeleştirilmiş, ISO hafta). Aynı haftada aynı öneri ikinci kez eklenmez, var olanın `no`'su döner.

### API
```python
def oku() -> list[dict]                       # [{no:int, tarih, kaynak, kisi, oneri, sonuc, not, kapanis}]
def kaydet(kaynak, kisi, oneri, bugun=None) -> int   # no; aynı hafta+anahtar varsa mevcut no
def isaretle(no, sonuc, not_="", temas=False, kanal="", bugun=None) -> dict
#   sonuc doğrulanır; kapanis = bugün (bekliyor'a dönüşte boş). temas=True ve sonuc ∈ {yaptim, ise_yaradi, ise_yaramadi}:
#   kişinin ## Temas bölümüne "GG.AA.YYYY · <kanal> · Kut önerisi: <oneri>" eklenir (aynı gün aynı satır varsa eklenmez),
#   son_temas ileri alınır; yazmadan önce c.surum_al(kid). Kişi hariç/yok ise temas eklenmez, sonuç yine kaydedilir.
#   Döner: {"no", "sonuc", "temas_eklendi": bool}
def kisi_gecmisi(kid, kayitlar=None) -> list   # en yeni önce
def bekleyenler(bugun=None, kayitlar=None) -> list   # "bekliyor" (≥ 3 gün) ve "yaptim" (≥ 5 gün, sonucu sorulacak) kayıtlar; en eski 10
def ayar(kid, bugun=None, kayitlar=None) -> dict
#   Öğrenme (açıklanabilir, kural tabanlı): {"bekle_gun": int, "carpan": float, "neden": str}
#   - Son 2 kayıt "atlandi" → bekle 28 gün; son 3 kayıt "atlandi"/"ertelendi" karışık → 21 gün; tek "ertelendi" → 7 gün (kapanıştan itibaren).
#   - Son 2 sonuçlanmış kayıt "ise_yaramadi" → carpan 0,5 ve neden "Son iki deneme işe yaramadı; farklı bir yol dene (ortak tanıdık, yüz yüze)".
#   - Son kayıt "ise_yaradi" → carpan 1,15 (ritmi koru). Varsayılan {0, 1.0, ""}.
def istatistik(bugun=None, kayitlar=None, strateji_sonuclari=None) -> dict
#   {"son_8_hafta": {"toplam", "yapilan", "ise_yarayan", "oran" (işe yarayan / sonuçlanmış, None if 0)}, "kaynaklara_gore": {...}}
```
- Dosya yoksa `oku()` boş liste; ilk `kaydet` başlıkla oluşturur. Bozuk satır atlanır (uyarı yok, elle düzenleme olabilir).
- Eşzamanlılık: modül düzeyinde `threading.Lock`; yazma atomik.

## 4. `kut/ag_ozet.py`: Haftalık özet ("Kut sana gelir")
```python
def hazirla(veri, bugun=None, kayitlar=None) -> dict      # saf: dosya yazmaz
def hafta_anahtari(bugun=None) -> str                     # "2026-W42"
def olustur(bugun=None, yenile=False) -> dict             # c.veri_hazirla(foto_gom=False) + hazirla + kaydet; aynı hafta varsa okur
def son() -> dict | None                                  # bu haftanın kayıtlı özeti (yoksa None)
def goruldu(hafta) -> None                                # arayüz özeti gösterdi: ayarlar.json → "ozet": {"goruldu": hafta}
```
`hazirla` çıktısı: `{"hafta", "tarih", "selam" (kısa, sıcak: "Günaydın Umut. Bu hafta 3 kişi ve 1 söz seni bekliyor."), "maddeler": [...], "sozler": [...],
"sonuc_bekleyen": [...], "istatistik": {...}, "bos": bool}`.
- Adaylar: `veri["bu_hafta"]` (sonraki adım, ihmal, söz). Hariç yok. Her kişi için `ag_sonuc.ayar(kid)`: `bekle_gun` dolmadıysa aday düşer;
  öncelik `carpan` ile yeniden sıralanır. Kişi maddeleri en çok **3**, söz maddeleri ayrı listede en çok 3 (gecikmiş önce).
- Madde: `{"id", "ad", "tur", "neden", "adim", "taslak", "kanal_onerisi", "no" (ag_sonuc kaydı; hazirla'da None, olustur doldurur), "not" (ayar.neden)}`.
  `adim` neden türüne göre tek somut eylem: sonraki adım varsa o; ihmal: "Kısa bir selam yaz: son konuştuğunuz ... hakkında sor"; söz: sözü kapat.
  `taslak` 1–3 cümle, doğal Türkçe, kişiye ilk adıyla; ihmalde son temas konusunu anar (gövdedeki son temas metni, ≤ 60 karakter). Kişi `tur` partner/akraba
  ya da `temas_sikligi` gunluk ise ihmal maddesi üretilmez (zaten bu_hafta üretmez; yine de koru).
- `sonuc_bekleyen`: `ag_sonuc.bekleyenler()` → "Selin Hoca'ya yazdın mı? Nasıl geçti?" sorusu için.
- `olustur`: `<veri>/ozet/<hafta>.md` (okunur Markdown + sonda ```json bloğu, ag_strateji.kaydet ile aynı yaklaşım) yazar; her kişi maddesi için
  `ag_sonuc.kaydet("ozet", kid, adim)` ile `no` alır. Aynı hafta dosyası varsa `yenile=False` iken onu okur ve döndürür (kayıtlar tekrar eklenmez).
  Eski özetler 12 haftadan sonra silinir (bakım `olustur` içinde).
- `bos`: madde ve söz yoksa True; selam "Bu hafta acil bir şey yok. Ağın sakin." olur.

## 5. `kut/ag_bildirim.py`: Kut sana gelsin (bildirim + zamanlayıcı)
Kut kapalıyken de haftada bir (ya da her sabah, yalnız o gün bir şey varsa) işletim sisteminin bildirimiyle haber verir.
**Varsayılan kapalı**; yalnız kullanıcı Ayarlar'dan açınca zamanlanmış görev kurulur, kapatınca kaldırılır (kalıcı yapılandırma, açık onay).

### Ayar (`ayarlar.json` → `"bildirim"`)
`{"acik": false, "siklik": "haftalik"|"gunluk", "gun": 0 (Pzt=0), "saat": "09:00", "adlar": false, "veri": "<mutlak veri yolu>", "kurulum": "zamanlayici"|"", "son": ""}`
- `adlar: false` (varsayılan): bildirimde kişi adı yok ("Bu hafta 3 kişi ve 1 söz seni bekliyor."). PIN kilidini aşmamak için; kilit ekranında
  ve bildirim merkezinde ad görünmez. `true` ise ilk 2 ad: "Selin Hoca ve Mert seni bekliyor (+1)".
- Kişi notlarındaki metin, söz içeriği, taslak **hiçbir zaman** bildirime girmez.

### API
```python
def durum() -> dict          # ayar + {"destek": bool, "platform", "kurulu": bool (görev gerçekten var mı), "komut": str (gösterim için)}
def ayarla(g) -> dict        # {acik, siklik, gun, saat, adlar} doğrula; acik → kur(), kapalı → kaldir(); ayarı yaz; durum() döndür
def kur(ayar) -> None        # platforma göre zamanlanmış görev
def kaldir() -> None
def calistir(argv) -> int    # `kut.pyw --ozet [--veri X] [--sessiz]`: özeti üret (ag_ozet.olustur), gerekiyorsa bildir; sunucu AÇMAZ
def bildir(baslik, metin) -> bool   # platform bildirimi; başarısızsa False (asla istisna fırlatma)
def metin(ozet, adlar=False) -> tuple[str, str] | None   # bildirim başlığı + gövdesi; gösterilecek bir şey yoksa None
```
- Komut: Windows'ta kaynak kurulumda `pythonw.exe` (sys.executable'ın yanındaki; yoksa sys.executable) + `<depo>/kut.pyw --ozet --veri "<veri>"`;
  .exe kurulumunda (`c.DONDURULDU`) `sys.executable --ozet --veri "<veri>"`. Argümanlar listeyle, kabuksuz.
- Windows: `schtasks /Create /F /TN "Kut\Haftalik ozet" /SC WEEKLY /D MON /ST 09:00 /TR "<komut>"` (günlük: `/SC DAILY`). Kaldırma `/Delete /F`.
  Varlık: `/Query /TN`. `/TR` 261 karakter sınırını aşarsa hata ver (yolu kısaltma önerisiyle). `creationflags=CREATE_NO_WINDOW`.
- Windows bildirimi: PowerShell 5.1 + WinRT `Windows.UI.Notifications.ToastNotificationManager` (AppId: PowerShell'in kayıtlı AUMID'i
  `{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe`). Toast XML'i Python'da üretilir ve **ortam değişkeniyle**
  aktarılır (komut satırına metin gömülmez; XML kaçışı `xml.sax.saxutils.escape`). Betik saf ASCII (PowerShell 5.1), `-NoProfile -NonInteractive
  -ExecutionPolicy Bypass`, `CREATE_NO_WINDOW`, zaman aşımı 20 sn.
- macOS: `~/Library/LaunchAgents/com.koraykutlu.kut.ozet.plist` (StartCalendarInterval), `launchctl bootstrap gui/<uid>` / `bootout`;
  bildirim `osascript -e 'display notification ...'` (metin argv ile, betik içine gömülmez: `on run argv`).
- Linux: `systemd --user` timer + service (`~/.config/systemd/user/kut-ozet.{service,timer}`, `systemctl --user enable --now`); yoksa `destek: false`.
  Bildirim `notify-send`.
- `calistir`: Kut sunucusu çalışıyor olsa da güvenlidir (yalnız okur + ag_ozet/ag_sonuc dosyalarına atomik yazar). Günlük modda bugün tarihli/gecikmiş
  bir şey yoksa bildirim yok. Haftalık modda `bos` ise bildirim yok. Kullanıcı Kut'u açtığında özet zaten hazırdır.
  Hata olursa ia.DEPO/sunucu.log'a tek satır yazar (içerik değil, yalnız hata türü) ve 0 dışı döner.
- Bildirim tıklaması bir şey açmak zorunda değil ("Kut'u açınca özet seni bekliyor" metni yeter); Windows'ta toast'a `launch` verilmez.

## 6. Entegrasyon (sunucu + arayüz) — ayrı aşama
Uçlar (hepsi kilit + `X-Ag-Anahtar`; yazanlar ayrıca `KOKEN_DENETIMLI`; hepsi `DEGISTIRMEYEN`, sayfa yenilenmez):
- `POST /api/yol` `{id?, ara?, amac?}` → `ag_yol.yollar` / `ag_yol.ara` (veri: `c.veri_hazirla(foto_gom=False)`).
- `POST /api/brifing` `{id}` → `ag_brifing.brifing(...)` + `markdown`.
- `POST /api/ozet` `{yenile?}` → `ag_ozet.olustur`; `POST /api/ozet/goruldu` `{hafta}`.
- `POST /api/sonuc` `{no, sonuc, not?, temas?, kanal?}` → `ag_sonuc.isaretle` (KOKEN). `POST /api/sonuc/kaydet` `{kaynak: "yol", kisi, oneri}` → no (KOKEN).
- `GET /api/sonuclar` → `{kayitlar (son 60), istatistik, etiketler: SONUCLAR}`.
- `GET /api/bildirim` → `ag_bildirim.durum()`; `POST /api/bildirim` → `ayarla` (KOKEN); `POST /api/bildirim/dene` → test bildirimi (KOKEN).
- Demo: `/api/demo/yol` ve `/api/demo/brifing` (demo anahtarı, demo veri sözlüğüyle aynı saf işlevler). Özet/sonuç/bildirim demoda "örnekte kapalı".
- `kut.pyw`: `--ozet` varsa `ag_bildirim.calistir(sys.argv)` (sunucu açılmaz).

Arayüz (kut-marka: lacivert + az sarı, Liquid Glass, Bahnschrift başlık, Consolas mono etiket, ölçülü yuvarlak; glow/neon yok):
- Kişi kartı: "Nasıl ulaşırım?" (yakınlık 0–1'de öne çıkar) ve "Brifing" düğmeleri.
- Tanıştırma yolu paneli: zincir (tür renkli kareler + bağ tipi), skor çubuğu, gerekçe, uyarılar, taslak (Kopyala), "Bu adımı takip et" → `/api/sonuc/kaydet`.
  Haritada yol vurgulanır (yol dışı soluk), panel kapanınca geri döner.
- Pusula'da "Kime ulaşmak istiyorsun?" alanı → `ara`.
- Brifing penceresi: bölümler, "Kopyala" (Markdown), "Yazdır".
- Haftalık özet kartı: açılışta bu hafta görülmediyse kendiliğinden açılır; maddeler: neden, adım, taslak (Kopyala), Yaptım / Ertele / Atla;
  "Nasıl geçti?" bölümü: İşe yaradı / İşe yaramadı (+ "Temas olarak kaydet" kutusu, varsayılan işaretli).
- Pusula → "Sonuçlar" sekmesi: kayıtlar + son 8 hafta istatistiği.
- Ayarlar → "Kut sana gelsin": aç/kapa, sıklık, gün/saat, "Bildirimde adları göster" (uyarı metniyle), "Deneme bildirimi".
