# Kut

**Kişisel ilişki ağın, yalnız senin bilgisayarında.** Tanıdığın insanları fotoğraflı bir haritada gör, her görüşmeden sonra tek cümle not düş,
kimi ihmal ettiğini ve bu hafta kime yazman gerektiğini hatırla. Hesap yok, bulut yok; verin düz Markdown dosyaları olarak diskinde durur.

![Kut: harita, kişi kartı, bu hafta ve Pusula](docs/img/kut-demo.gif)

> *Kut (formerly "Ağım") is a local, private personal-network app: a photo map of the people you know, contact log, relationship graph,
> conflict-of-interest hints and a "who should I reach out to this week" list. It is a Python 3 standard-library HTTP server bound to
> `127.0.0.1` plus a single-page HTML UI; no accounts, no cloud, no dependencies. Your data lives as plain Markdown files and never enters
> this repository. An optional AI assistant (Claude Code) can analyse notes, but every record passes a local privacy gate first (see
> [Gizlilik](#gizlilik)). Try it without any personal data: `py -3 demo/demo_veri.py --hedef demo-veri`, then
> `py -3 kut.pyw --veri demo-veri` ([Demo verisiyle deneme](#demo-verisiyle-deneme)). Licence: MIT.*

Bu README'deki tüm ekran görüntüleri ve GIF, `demo/demo_veri.py`'nin ürettiği **tamamen kurgusal** verilerle çekilmiştir; gerçek kişi yoktur.

## İçindekiler
[Neler yapar](#neler-yapar) · [Gizlilik](#gizlilik) · [Kurulum](#kurulum) · [Demo verisiyle deneme](#demo-verisiyle-deneme) ·
[Kullanım ayrıntıları](#kullanım-ayrıntıları) · [Okul bağdaştırıcısı ekleme](#okul-bağdaştırıcısı-ekleme) · [Testler](#testler) · [Lisans](#lisans)

## Neler yapar

### Ağ haritası
Merkezde sen, çevrende tanıdıkların. Renk kişinin türünü (akademi, iş, yakın, çevre, etkinlik, finans, siyaset), halka yakınlığı gösterir;
bağlar arkadaşlık, mentorluk, yöneticilik, iş ortaklığı, akrabalık, rekabet ya da gerginlik gibi tiplerle çizilir.
Sol menüdeki **Dikkat** listesi bağlardan olası çıkar çatışmalarını işaretler (ör. rakip firmadaki bir tanıdık, gergin bir üçgen).

![Ağ haritası](docs/img/harita.png)

### Kişi kartı ve temas ritmi
Her kişi bir Markdown dosyasıdır: kurum, rol, "neden önemli", "ne verebilirim", sonraki adım ve tarihi. Görüşme sonrası tek cümlelik
**temas** eklenir; son temas, görüşme sıklığı beyanın ve yakınlığa göre ihmal eşiği (yakınlık 3: 14 gün, 2: 30, 1: 60) hesaplanır.
Altı ilişki puanı (sıcaklık, derinlik, karşılıklılık, süreklilik, köprü, ortak zemin) ve isteğe bağlı özellik puanları (uzmanlık, destek, güvenilirlik...)
kayıtlardan hesaplanır, "Puanlar neye göre?" bölümünde ölçütleri görünür.

| Profil ve özellikler | Temaslar ve zaman çizelgesi |
|---|---|
| ![Kişi kartı](docs/img/kisi-karti.png) | ![Temaslar](docs/img/kisi-temaslar.png) |

### Bu hafta
Tarihi gelen sonraki adımlar ve ihmal edilenler tek listede; bir tıkla haritada yalnız onlar öne çıkar. Hariç listesindeki kişiler hiçbir öneriye girmez.

![Bu hafta görünümü](docs/img/bu-hafta.png)

### Çıkarım onay kuyruğu ("Asistan soruyor")
Asistanın (yapay zekâ) kişiler hakkındaki çıkarımları (ilişki özeti, etiket, puan, bağ, kurum/rol, sorular) **sen onaylamadıkça kişi dosyasına yazılmaz**.
Her biri için *Doğru / Düzelt / Yanlış* dersin; reddedilen çıkarım tekrar önerilmez. Senin doğrudan söylediğin (görüş, görüşme sıklığı)
çıkarımdan önce gelir ve onu ezmez. Kural motoru (`ag_tutarlilik.py`, model yok) bağlamla çelişen önerileri silmeden kapatır.

### Pusula: hedefler, keşif, strateji
Hedeflerini (başlık, tür, son tarih, öncelik, başarı ölçütü, konu kelimeleri) yazarsın; ilerleme satırı eklenir, tamamlanır, arşivlenir.
*Keşfet* sekmeleri herkese açık kaynakları (TBMM vekil faaliyetleri, schema.org etkinlik sayfaları) hedeflerinin konu kelimeleriyle eşleştirir;
"Ağa ekle" demeden kimse ağına girmez. Vekil verisi (Vekilpedia) ve etkinlik taraması yeni kurulumda **kapalıdır**; Pusula → *Kaynaklar* sekmesinden açılır (ya da `ayarlar.json` → `kesif.vekilpedia` / `kesif.etkinlik: true`). Eski kurulumlar, daha önce veri indirdiyse, özelliği kaybetmesin diye açık kalır. *Stratejik okuma* hedefleri ve ağını bir modele okutup kanıtlı, hedefe bağlı "görmediğin hamleler" üretir.

| Hamleler | Hedefler |
|---|---|
| ![Pusula, hamleler](docs/img/pusula-hamleler.png) | ![Pusula, hedefler](docs/img/pusula-hedefler.png) |

> Ekran görüntülerindeki "Stratejik okuma" içeriği demo veri üreticisinin yazdığı örnek metindir; model çağrılmamıştır.

### Diğer özellikler
- **WhatsApp ve rehber içe aktarma:** WhatsApp sohbetini (.txt/.zip, "medya olmadan") ya da .vcf rehberi sayfaya bırakırsın, gelen adaylardan seçtiklerin ağa eklenir. Mesaj içerikleri saklanmaz; yalnız ad, mesaj sayısı, tarih.
- **Okul bağdaştırıcısı:** profilindeki okul ve derslerden hocaları, ders saatlerini ve kadro sayfasından unvan/e-posta/özgeçmişi (kaynağıyla, yalnız boş alanlara) doldurur. Okul tanımlı değilse kapalıdır; kendi okulun için eklenebilir ([aşağıda](#okul-bağdaştırıcısı-ekleme)).
- **Kut'a sor (`/`):** "Ayşe hocayla bugün konuştum, başvurum onaylanmış, Berk'le artık haftada bir görüşüyoruz" gibi serbest metni temas, beyan, sonraki adım ve bağlara ayırıp kaydeder; her yazımdan önce kişinin eski hali `veri/arsiv/surum/`'e kopyalanır.
- **PIN kilidi:** açılışta PIN sorulur; kilitliyken sunucu hiçbir kişisel veri göndermez (görsel örtü değil, sunucu tarafında).
- **İkinci beyin köprüsü (isteğe bağlı, salt okur):** bir not kasasındaki açık işleri ve kişinin geçtiği satırları gösterir; kasaya hiçbir şey yazmaz.
- **Yerel ses (isteğe bağlı):** Whisper ile konuşmayı yazıya çevirir, EMA Lightning ile cevapları Türkçe okur; hepsi bu bilgisayarda çalışır, ses diske yazılmaz.
- **Görünüm:** bu bilgisayarda çizilen WebGL gökyüzü, gündüz/gece teması.

![Kilit ekranı](docs/img/kilit.png)

## Gizlilik

**İlke: Kut yalnız senin bilgisayarında çalışır.** Bulut, hesap, senkronizasyon, mobil uygulama, telemetri yok. Sunucu yalnız `127.0.0.1`'de dinler
(dışarıdan erişilemez; Host/Origin denetimi yapılır) ve sayfa kapandıktan ~20 dk sonra kendiliğinden durur.
Verin `veri/` klasöründe düz Markdown olarak durur ve `.gitignore` ile depodan dışlanmıştır; içe aktarma adayları `%LOCALAPPDATA%\agim` (macOS/Linux `~/.agim`) altında bekler.

**Kut sen açmadıkça internete çıkmaz.** Yeni kurulumda hiçbir dış kaynak açık değildir. Pusula → **Kaynaklar** sekmesi, açabileceğin isteğe bağlı kaynakları, neyi nereden indirdiklerini ve açma/kapama düğmelerini tek yerde gösterir:

| Kaynak | Ne indirir | Nereden | Varsayılan |
|---|---|---|---|
| TBMM / Vekilpedia | milletvekilleri, soru önergeleri, kanun teklifleri (CSV, CC BY 4.0), haftada bir | vekilpedia.com | kapalı |
| Etkinlikler | yaklaşan etkinlik sayfaları (robots.txt izinli), 12 saatte bir | coderspace.io, lu.ma, eventbrite.com, devpost.com (+ seçili okulun etkinlik sayfası) | kapalı |
| Okul bağdaştırıcısı | ders programı, akademik kadro sayfası (yalnız profilinde okul ve ders kodu varsa) | `ag_kaynak.OKULLAR` içindeki okulun siteleri (örnek: yeditepeders.com, yeditepe.edu.tr) | yok |

Ağa çıkabilen yollar ve sınırları:

1. **Herkese açık sayfalar** (yukarıdaki tablo). Yalnız herkese açık, girişsiz sayfaları indirir; ağındaki hiçbir bilgi bu isteklerle gönderilmez. Önceden veri indirmiş eski kurulumlarda Vekilpedia ve Etkinlikler açık sayılır; Kaynaklar sekmesinden kapatılır.
2. **İsteğe bağlı yapay zekâ asistanı.** Analiz, "Kut'a sor" ve stratejik okuma, bilgisayarında kurulu **Claude Code** (`claude -p`) üzerinden bir modele gider.
   Claude Code yoksa bu özellikler çalışmaz (düğmeler Türkçe bir uyarı gösterir), geri kalan her şey çalışır. Bunlar yalnız sen kullanınca çalışır; tek istisna: Claude Code kuruluysa ve **onayladığın (aktif) bir hedefin** varsa, son stratejik okumadan 7 gün geçince Kut açılışta okumayı kendiliğinden başlatır. Kapatmak için `ayarlar.json` → `"otomatik_strateji": false`. Modele giden her kişi verisi önce yerel **kapıdan** (`ag_kapi.py`) geçer:
   - `remote_allowed: false` olan kişi (ya da dosyası okunamayan) ne istemde ne de modele hazırlanan geçici veri kopyasında bulunur;
   - `veri/haric.md` ile eşleşen kurum/parti kişileri aynı şekilde dışarıda kalır; kopyada ayrıca `haric.md`, `ag.html`, `arsiv/`, kilit ve ayar dosyaları yoktur;
   - **sır filtresi** (`ag_sir.py`) anahtar, token, parola gibi değerleri (kodlanmış halleriyle) `[gizlendi]` yapar;
   - model dosyaları yalnız okuyabilir (yazma, kabuk ve web araçları kapalı); kopya çıkışta silinir.
   Modeller `ayarlar.json` içinden değiştirilebilir (`analiz_modeli`, `sohbet_modeli`, `strateji_modeli`).
3. **Sürüm denetimi (GitHub).** Yalnız `api.github.com/repos/koraykutlu/kut/releases/latest` adresine, sürüm bilgisini almak için bir GET gider; hiçbir veri gönderilmez. Otomatik denetim, ilk açılışta sorulan soruya **Evet** dersen haftada bir yapılır (`ayarlar.json` → `guncelleme.otomatik`; sormadan ve Hayır dersen asla). Pusula → Kaynaklar → *Güncelleme var mı?* düğmesi elle her zaman çalışır.
4. **Senin seçimin: kendi AI ajanın.** Bu klasörü bir ajanla (ör. Claude Code) açarsan ajanın okuduğu dosyalar o ajanın modeline gider; yalnız görev için gerekenleri okumasını söyle.

**Kilit (`ag_kilit.py`):** PIN düz yazılmaz (PBKDF2-SHA256, `ayarlar.json` → `kilit`); 5 yanlış denemeden sonra bekleme artar; kilitliyken tüm `/api` istekleri 401 döner.
Kut yeniden başlayınca, ayarlanan süre işlem yapılmayınca (varsayılan 15 dk) ya da 🔒 ile kilitlenir. Unutursan `ayarlar.json`'dan `"kilit"` anahtarını sil.
Kilit ekranı korur; diskteki Markdown dosyaları için disk şifrelemesi (BitLocker, FileVault) gerekir.
Ağına yazdığın kişiler senin notlarındır: sağlık, özel hayat, dedikodu yazma; klasörü başkasıyla paylaşma.

## Kurulum

Yalnız Python 3 (standart kütüphane) yeter; harici paket yok. Ses özelliği isteğe bağlıdır ve ayrıca kurulmuş Whisper / EMA ortamları gerektirir.

### Windows (.exe)

Python gerekmez.

1. GitHub **Releases** sayfasından `Kut.exe` dosyasını indir ve çift tıkla.
2. Windows "bilinmeyen yayımcı" (SmartScreen) uyarısı gösterirse: **Daha fazla bilgi → Yine de çalıştır**.
3. İlk açılışta bir **PIN** belirlersin.

Verin `Belgeler\Kut` klasöründe Markdown olarak durur; ayarlar ve günlükler `%LOCALAPPDATA%\agim` altındadır. Başka bir klasör için: `Kut.exe --veri KLASÖR`.
Ses (Whisper / EMA) ve yapay zekâ analizi (Claude Code) isteğe bağlıdır; kurulu değillerse ilgili düğmeler Türkçe bir uyarı gösterir, geri kalan her şey çalışır.

Kendin derlemek istersen: `powershell -ExecutionPolicy Bypass -File paketleme\paketle.ps1` (çıktı `build-exe\dist\Kut.exe`).

### Yapay zekâ ajanınla kur

Claude Code, Codex ya da benzeri bir ajanın varsa kurulumu ona yaptırabilirsin. Ajana şunu söylemen yeter:

> `https://github.com/koraykutlu/kut adresindeki Kut'u kur.`

Ajan depodaki [AGENTS.md](AGENTS.md) dosyasının "Kurulum (ajan için)" bölümünü izler: Python 3.10+ var mı bakar (Windows'ta yoksa `Kut.exe`'yi önerir),
depoyu klonlar, **kişisel verini depo dışında** bir klasöre (örneğin `<kasa>/notes/ag` ya da `~/Documents/Kut`) koyar, Windows'ta masaüstü/Başlat kısayolunu kurar,
istersen ikinci beyin kasanı salt okunur köprüyle bağlar. Dış kaynakları senin onayın olmadan açmaz, verini depoya koymaz.

### Python ile

Python 3'ü kur (Windows: `winget install Python.Python.3.12` ya da python.org, "Add to PATH" işaretli), depoyu indir/klonla, sonra:

```powershell
# Windows
py -3 kut.pyw
```
```sh
# macOS / Linux
python3 kut.pyw
```

Sunucu varsayılan olarak `http://127.0.0.1:47318/` adresinde açılır ve tarayıcıyı açar (`--tarayicisiz` ile açmaz, `--port N` portu değiştirir,
`--veri KLASÖR` başka bir veri klasörü kullanır; `AGIM_PORT` ortam değişkeni de portu belirler, `--port` önceliklidir).

- **Windows kısayolu:** `baslatma\kur.ps1`'e sağ tık → *PowerShell ile çalıştır* (verini başka bir klasörde tutmak için: `powershell -ExecutionPolicy Bypass -File baslatma\kur.ps1 -Veri KLASÖR`). Masaüstü ve Başlat menüsüne **Kut** kısayolu gelir; Kut, Edge/Chrome uygulama penceresinde (ayrı profil) açılır. Varsayılan tarayıcı için `ayarlar.json`'a `"tarayici": "varsayilan"` yaz.
- **macOS:** Terminal'de bir kez `chmod +x baslatma/Kut.command`, sonra `baslatma/Kut.command`'a çift tıkla (Python 3 gerekli: `python3 --version`).

İlk açılışta bir PIN belirlersin, sonra merkezdeki kendi düğümüne tıkla → **Profilimi düzenle** (ad, fotoğraf, asistanının adı).

## Güncelleme

Sürüm numarası ve güncelleme denetimi **Pusula → Kaynaklar → Güncelleme** kartındadır (sürüm `kut/surum.py`'de). Kut ilk açılışta *"Güncellemeleri haftada bir denetleyeyim mi?"* diye bir kez sorar; Evet dersen haftada bir GitHub'dan yalnız sürüm bilgisini alır, Hayır dersen kendiliğinden hiç bakmaz. *Güncelleme var mı?* düğmesi her zaman elle çalışır. Güncelleme yalnız programı değiştirir, veri klasörüne dokunmaz; önceki program geri dönüş için saklanır.

- **Kut.exe:** *Şimdi güncelle* yeni `Kut.exe`'yi GitHub Releases'tan indirir (en çok 50 MB; yalnız github.com ve GitHub'ın yayın CDN adreslerinden), **SHA-256 sağlama toplamını doğrular** (yayındaki `digest` alanı ya da `Kut.exe.sha256` dosyası; toplam yoksa ya da uyuşmazsa kurmaz), eskisini `Kut.prev.exe` olarak yanına koyar, yenisini `Kut.exe` yapar ve yeniden başlatır. *Önceki sürüme dön* ikisini geri takas eder. Kut.exe'nin klasörüne yazılamıyorsa (ör. Program Files) elle indir.
- **Git ile kurulum:** depoyu `git fetch --tags` ile günceller ve **yalnız ileri sarar** (`git merge --ff-only`, yayın etiketi). Çalışma ağacı kirliyse, yerel commit'ler ileri sarmayı engelliyorsa ya da klasör `github.com/koraykutlu/kut`'u izlemiyorsa dokunmaz, sadece yeni sürümü bildirir. Önceki commit kaydedilir; *Önceki sürüme dön* (`git reset --hard`, yalnız ağaç temizse) onu geri getirir. Elle: `git pull --ff-only`.
- **Zip / kopya:** yalnız bildirim ve sürüm sayfası bağlantısı; yeni dosyaları `veri/` hariç üzerine kopyala.
- **Veri göçü:** bir sürüm veri biçimini değiştirirse `kut/goc.py` gerekli göçü çalıştırır ve önce veri klasörünü `<veri>/arsiv/goc/` altına zip'ler. Şimdilik göç yoktur, hiçbir şey yazılmaz.

**Yayın çıkaranlar için:** `kut/surum.py`'deki `SURUM`'u artır, `paketleme\paketle.ps1` çalıştır, `vX.Y.Z` etiketli bir GitHub Release oluştur ve **`build-exe\dist\Kut.exe` ile `Kut.exe.sha256` dosyalarının ikisini de** yükle (dosya adları tam bu olmalı; etiket `SURUM` ile aynı). Yayın *pre-release/draft* olmamalı (`releases/latest` onları görmez).

## Demo verisiyle deneme

Kendi verini girmeden denemek (ya da ekran görüntüsü/video çekmek) için `demo/demo_veri.py` 31 kurgusal kişi (ikisi dolaylı), ilişkiler, bekleyen çıkarımlar,
iki hedef ve örnek bir strateji okuması üretir. Tüm adlar ve kurumlar uydurmadır; fotoğraflar standart kütüphaneyle çizilen baş harfli renkli dairelerdir.
Tarihler bugüne göre göreli üretilir, böylece "Bu hafta" listesi her zaman dolu gelir.

```powershell
py -3 demo/demo_veri.py --hedef "$env:TEMP\kut-demo"        # --hedef verilmezse geçici klasör açılır ve yolu yazdırılır
py -3 kut.pyw --veri "$env:TEMP\kut-demo" --port 47400
```

Kendi kurulumunu etkilememesi için demoyu ayrı bir ayar klasörüyle çalıştırabilirsin (PIN ve ayarlar `%LOCALAPPDATA%\agim`, macOS/Linux `~/.agim` altındadır):

```powershell
$env:LOCALAPPDATA = "$env:TEMP\kut-demo-ayar"
py -3 kut.pyw --veri "$env:TEMP\kut-demo" --port 47400
```

Demoda çevrimdışı kalmak ve model çağrısını kapatmak istersen, `kut-demo-ayar\agim\ayarlar.json` içine
`{"otomatik_strateji": false, "otomatik_analiz": false, "kesif": {"etkinlik_kaynaklari": [], "vekilpedia": false}}` yaz
(böylece Pusula keşfi hiçbir siteye gitmez ve model çağrısı yapılmaz). İlk açılışta kendi PIN'ini belirlersin.

## Kullanım ayrıntıları

- **+ Kişi ekle / Düzenle:** fotoğraf, isim, tür, yakınlık (0 tanımıyor · 1 yazıştık · 2 görüştük · 3 güçlü), kurum, iletişim,
  sonraki adım + tarihi, "neden önemli", "ne verebilirim".
- **Temas ekle:** kişiyle her konuşmadan sonra tek cümle; son temas ve "Bu hafta" listesi buna göre güncellenir.
- **Senin beyanın:** düzenle penceresinde "Ne sıklıkla görüşüyorsunuz?" (her gün / haftalık / aylık) ve "Senin görüşün".
  Kayıt tutmasan da puanlar buna göre hesaplanır; asistanın çıkarımları bunu ezmez.
- **Bağ kur:** haritada bir kişiden diğerine **Shift + sürükle** (ya da kartta *Bağ kur* → hedefe tıkla), tipi tek tıkla seç:
  arkadaş, birlikte çalışıyor, mentor, yönetici, iş ortağı, akraba, partner, rakip, gerginlik.
- **Asistan soruyor / Doğrula:** her çıkarım için *Doğru / Düzelt / Yanlış*; soruları da cevapla. Cevapların sonraki analizlere yön verir.
- **Fotoğraf:** yükleyince görünecek kısmı sürükleyip yakınlaştırarak seç; mevcut fotoğrafa tıklayıp yeniden kırpabilirsin.
- **Sol panel:** kenardaki kulp ya da `[` tuşu ile gizle/aç.
- **Özgeçmiş ve belgeler:** kişinin *Özgeçmiş* sekmesine özgeçmiş, profil sayfası, haber, PDF ya da ekran görüntüsü bırak
  (ya da metni yapıştır). Asistan özetler; özet, özgeçmiş maddeleri, kurum/rol ve iletişim *Doğrula*'ya düşer, onaylayınca yazılır.
  Dosya `veri/belgeler/<kişi>/`'de kalır; içerik özet için asistan modeline gider (kapıdan geçerek).
- **Kut'a sor (alt çubuk, `/`):** ağına soru sor ya da bilgi yaz; art arda, birbiriyle ilgisiz kişiler hakkında yazabilirsin. Asistan bunları ayırıp
  ilgili kişilere temas, beyan, görüş, görüşme sıklığı, sonraki adım, iletişim bilgisi ya da bağ olarak kaydeder; yeni kişiyi açar. Senin söylediğin
  beyandır, doğrudan yazılır; ad belirsizse sorar. Asistanın kendi çıkarımları yine Doğrula'ya düşer.
- **Asistanın karakteri:** Profilimi düzenle → "Asistanının karakteri" (boşsa sıcak, doğrudan, meraklı; "sen" diye hitap eder).
- **İçe aktar:** telefonda WhatsApp sohbeti/grubu → *Sohbeti dışa aktar → Medya olmadan* (.txt/.zip), rehber → .vcf.
  Dosyayı sayfaya bırak, gelen adaylardan istediklerini seç. Önce "WhatsApp'taki adın" alanını doldur.
- **Hariç listesi:** `veri/haric.md`'ye iletişim kurmak istemediğin kurum/parti adlarını yaz; bunlar hiçbir öneriye girmez ve modele gitmez.
- **Dolaylı kişiler ve odak:** seninle doğrudan bağı olmayan, yalnız başkası üzerinden tanıdığın kişiler (yakınlık 0, temas kaydı yok) haritada
  varsayılan olarak gizlidir. Bir kişiye **çift tıkla**: o kişi merkeze geçer, yalnız onun bağları görünür; **Esc** ya da "← Ağıma dön" geri alır.
  Hepsini görmek için Görünüm → "Dolaylı kişileri de göster".
- **Giriş animasyonu:** pencere ilk açılışta kısa bir giriş oynatır; tık, Esc ya da Enter atlar. Tamamen kapatmak için tarayıcı konsolunda
  `localStorage.setItem("kut-giris", "0")`, sesi kapatmak için `localStorage.setItem("kut-ses", "0")`.
- **İkinci beyin köprüsü:** `%LOCALAPPDATA%\agim\ayarlar.json`'a `"vault": {"yol": "C:\\...\\kasa"}` yazarsan sol panelde kasadaki açık işler (`tasks/*.md`) ve
  fikirler (`notes/fikirler.md`), kişi kartında kişinin kasada geçtiği satırlar görünür. Köprü kasaya yazmaz; kişisel notlar, kurallar ve günce okunmaz (`ag_vault.py`, `HARIC`).
- **Pusula (P):** hedefler `veri/hedefler/<id>.md`; keşif `ag_kesif.py` (vekil verisi (açıksa) haftada bir, etkinlikler 12 saatte bir; kaynak listesi
  `ayarlar.json` → `kesif.etkinlik_kaynaklari`); strateji `ag_strateji.py` (`veri/strateji/<tarih>.md`, hamleleri *yaptım / işe yaradı* diye işaretlersin,
  sonraki okuma bunu görür). Aktif hedef ve Claude Code varsa haftada bir kendiliğinden çalışır (`"otomatik_strateji": false` ile kapanır).
- **Ses:** Kut'a sor çubuğunda 🎙 (Ctrl+Boşluk) konuşmayı yazıya çevirir, "🔈 Sesli cevap" cevapları okur. Modeller Kut'un Python'unda değil, kurulu oldukları
  ortamlarda çalışır (`ag_ses.py` → `ag_ses_isci.py`): `ayarlar.json` → `"ses": {"oku_python": "<ema ortamı>\\Scripts\\python.exe",
  "yaz_python": "<faster-whisper ortamı>\\Scripts\\python.exe", "yaz_model": "large-v3"}`. Bulunamazsa düğmeler görünmez.
  Ses kaydı diske yazılmaz, hiçbir şey internete gitmez.

### Veri dosyaları
Tek doğru kaynak Markdown'dır (`veri/` klasörü; ayrıntı için `AGENTS.md`):

| Dosya | İçerik |
|---|---|
| `ben.md` | merkezdeki kişi (sen): ad, ilgiler, asistan adı, okul |
| `kisiler/<id>.md` | kişi: frontmatter (`ad, tur, kurum, rol, yakinlik, son_temas, sonraki_adim, ...`) + `## Temas` satırları (`- GG.AA.YYYY · kanal · cümle`) |
| `iliskiler.md` | `\| a \| b \| tip \| not \| kaynak \| tarih \|` tablosu |
| `cikarimlar.md` | onay bekleyen asistan çıkarımları ve soruları |
| `hedefler/<id>.md` | Pusula hedefleri |
| `haric.md` | iletişim kurulmayacak kurum/partiler |

### Kendi ajanın
Bu klasör aynı zamanda bir yapay zekâ ajanının çalışma alanıdır (`AGENTS.md` talimatları): Claude gibi bir ajanla klasörü açıp
"Ali'yle kahve içtik, staj konuştuk, 2 hafta sonra yazacağım" dersen temas, yakınlık ve sonraki adım kaydedilir; "Bu hafta kimle ilgileneyim?" diye sorabilirsin.
Ajan çıkarımlarını önerinin ötesinde kişi dosyasına doğrudan yazmaz.

## Okul bağdaştırıcısı ekleme

Okul özellikleri `kut/ag_kaynak.py` içindeki `OKULLAR` sözlüğüyle tanımlanır; anahtar, profildeki `okul` alanının sadeleştirilmiş hâlidir (küçük harf, Türkçe karakter ve aksansız).
Depodaki `yeditepe` kaydı yalnızca bir **örnek bağdaştırıcıdır**; aynı alanlarla kendi okulunu ekleyebilirsin:

```python
OKULLAR = {
    "okulum": {
        "ad": "Okulum Üniversitesi", "kisa": "Okulum",
        "ders_json": "https://ornek.edu/data/courses-{donem}.json",   # herkese açık ders programı (JSON)
        "ders_kaynak": "ornek.edu", "donem": "2026G", "donem_adi": "Güz 2026",
        "kadro": {"ABC": ("https://fakulte.ornek.edu", "12")},         # ders kodu öneki → akademik kadro sayfası, bölüm no
        "kadro_adi": {"ABC": "Okulum Örnek Mühendisliği"},
        "kadro_plugin": "...", "eposta_alani": "ornek.edu",
        "profil_ornek": "ornek.edu/akademik-kadro/<n>",
        "etkinlik_url": "https://ornek.edu/etkinlikler",
    },
}
```

Alanların tam anlamı için mevcut kayda ve `ag_kaynak.py` içindeki kullanımlarına bak; ders JSON'u ve kadro sayfası biçimi uyumluysa başka kod gerekmez, değilse ilgili ayrıştırıcıyı genişlet.
İlkeler: yalnız herkese açık, girişsiz sayfalar; giriş isteyen ya da bot korumalı (CAPTCHA, engelleme) siteleri aşmaya çalışma; kaynaktan gelen bilgi kaynağıyla yazılır, yalnız boş alanları doldurur, senin yazdığını ezmez.
Profilinde `okul` boşsa ya da tanımsızsa bu özellik kapalıdır ve hiçbir okul sitesine istek atılmaz.

## Kaynak ekleme

- **Yeni üniversite:** `ag_kaynak.OKULLAR`'a bir kayıt eklemek yeter (yukarıdaki biçim); *Kaynaklar* sekmesindeki okul listesine kendiliğinden gelir.
- **Yeni etkinlik kaynağı:** `ayarlar.json` → `kesif.etkinlik_kaynaklari` listesine adres eklenir (sayfada schema.org Event varsa kod gerekmez). Etkinlik taraması `kesif.etkinlik` ayarıyla açıksa taranır.
- **Yeni isteğe bağlı kaynak türü:** `ag_kesif.KAYNAK_AYARLARI`'na bir kayıt ve `kesif.<kimlik>` kapısı; kapı kapalıyken ağa çıkılmamalı (örnek: `etkinlik_acik()`).

## Depo düzeni

```
kut.pyw        başlatıcı (kut/ klasörünü yola ekler, sunucuyu açar)
kut/           uygulama kodu (ag_*.py), sürüm (surum.py), güncelleme (ag_guncelle.py), veri göçleri (goc.py), arayüz (ag_sablon.html), simge
tests/         birim testleri
demo/          kurgusal demo verisi üreticisi
docs/          ekran görüntüleri (img/) ve tasarım taslakları (tasarim/)
paketleme/     Kut.exe derleme (kut.spec, paketle.ps1; Kut.exe.sha256 de üretir)
baslatma/      Windows kısayol kurucu (kur.ps1), macOS başlatıcı (Kut.command)
AGENTS.md      ajan talimatları (kurulum + uygulama içi asistan)
```

Kişisel verin (`veri/`, ya da `--veri` ile verdiğin klasör) depoya girmez.

## Testler

```powershell
py -3 -m unittest discover -s tests          # macOS/Linux: python3 -m unittest discover -s tests
```

Testler yalnız standart kütüphaneye dayanır ve gerçek verine dokunmaz (her biri geçici bir veri klasörü kullanır).

## Lisans

[MIT](LICENSE) © koraykutlu
