"""Kut demo önizlemesi: "Deniz'in salısı". Yeni kullanıcı kendi verisini girmeden Kut'un değerini sahnelenmiş bir hikâyeyle görür.

Yalıtım (güvenlik): demo kullanıcının verisine ve ayar klasörüne ASLA dokunmaz.
  * Veri, geçici bir klasörde (tempfile) KURGUSAL senaryodan üretilir; demo kapanınca klasör silinir.
  * ag_cekirdek / ag_soz modüllerinin ÖZEL bir kopyası (kapsül) yüklenir: kendi yol değişkenleri vardır. Gerçek modülün
    VERI/KISILER yolları çalışma anında DEĞİŞTİRİLMEZ; yarış koşulu ve yanlış yere yazma riski yoktur.
  * Demo sayfası gerçek oturum anahtarını görmez; yalnız bu modülün ürettiği demo anahtarını taşır. Gerçek uçlar demo
    anahtarını reddeder, demo uçları gerçek anahtarı reddeder (baslat hariç).
  * Bu modül ağa çıkmaz ve model çağırmaz: "Kut'a sor" cevapları önceden yazılmıştır (kural motoru yalnız söz yakalar).
Anlatım sesi isteğe bağlıdır: kut/demo_ses/<sahne>.wav|.ogg varsa çalınır, yoksa demo sessiz sürer (paketleme/demo_seslendir.py üretir).
"""
import atexit
import builtins
import importlib.util
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import types
from datetime import date, datetime, timedelta

KOK = os.path.dirname(os.path.abspath(__file__))
DIZIN_ONEKI = "kut-demo-sali-"
ISARET = ".kut-demo"            # yalnız bu işaretli geçici klasörler silinir
OMUR_SN = 45 * 60               # demo bu kadar sessiz kalırsa kendiliğinden kapanır
ESKI_SN = 3 * 3600              # çökmüş bir önceki sürecin artığı sayılan yaş
SELIN = "selin-hoca"
SES_UZANTILARI = (".wav", ".ogg")

# ---------- sahne metinleri (tek kaynak: arayüz, anlatım sesi ve üretim betiği) ----------
# metin: sahne kartında görünen; anlatim: seslendirilen (aynı anlam, biraz daha konuşma dili).
SAHNELER = [
    {"id": "ag", "baslik": "Deniz'in ağı",
     "metin": "Bu Deniz'in ağı. Halkalar yakınlığı, renkler sıcaklığı gösterir. Gri-mavi, soğumuş kare Selin Hoca: eski proje danışmanın, beş aydır konuşmadınız.",
     "anlatim": "Bu, Deniz'in ağı. Halkalar yakınlığı, renkler sıcaklığı gösterir. Şuradaki gri-mavi, soğumuş kare Selin Hoca. Eski proje danışmanı, ve beş aydır konuşmadılar."},
    {"id": "pusula", "baslik": "Pusula fark etti",
     "metin": "Selin Hoca'nın açık veri çağrısı Cuma kapanıyor; son konuşmanız staj başvurusuydu. Pusula, hedefinle bu soğumuş bağı yan yana koyup ilk adımı önerir.",
     "anlatim": "Pusula bir şeyi fark etti. Selin Hoca'nın açık veri çağrısı Cuma kapanıyor, son konuşmaları ise staj başvurusuydu. Hedefle soğumuş bağı yan yana koyup ilk adımı öneriyor."},
    {"id": "sor", "baslik": "Kut'a sor",
     "metin": "Ağına doğal dille sorabilirsin. Kut, kayıtlarına bakıp kimleri tanıdığını ve nedenini söyler; cevaplar bu örnekte önceden yazılmıştır.",
     "anlatim": "Ağına doğal dille sorabilirsin. Kut, kayıtlara bakıp kimi tanıdığını ve nedenini söyler."},
    {"id": "soz", "baslik": "Söz verdin, Kut yakaladı",
     "metin": "Cümlenin içindeki sözü Kut fark eder ve önce sana sorar. «Evet, ekle» demeden hiçbir şey kaydedilmez.",
     "anlatim": "Bir söz verdiğinde Kut cümlenin içinden yakalar, ama önce sana sorar. Sen onaylamadan hiçbir şey kaydedilmez."},
    {"id": "isinma", "baslik": "Bağ yeniden ısındı",
     "metin": "Birkaç gün sonra: taslak gitti, Selin Hoca dönüş yaptı. Kare soğuktan sıcağa döndü, halkası sana yaklaştı. Kut olmasaydı bu bağ sessizce kopacaktı.",
     "anlatim": "Birkaç gün sonra taslak gitti, Selin Hoca da dönüş yaptı. Kare soğuktan sıcağa döndü, halkası yaklaştı. Kut olmasaydı, bu bağ sessizce kopacaktı."},
    {"id": "kilit", "baslik": "Hepsi sende kalır",
     "metin": "Hepsi bu bilgisayarda; sen istemeden hiçbir şey dışarı çıkmaz.",
     "anlatim": "Hepsi bu bilgisayarda kalır. Sen istemeden hiçbir şey dışarı çıkmaz."},
]
SAHNE_IDLERI = [s["id"] for s in SAHNELER]
ZAMAN_ETIKETI = "3 gün sonra · Perşembe"

# ---------- hazır "Kut'a sor" cevapları (model yok) ----------
CEVAP_CAGRI = ("Bu çağrı için iki kişi öne çıkıyor:\n\n"
               "- **Baran Sanalıoğlu**: Selin Hoca'nın laboratuvarında doktora yapıyor; çağrının veri görselleştirme tarafında sana en yakın kişi. "
               "Geçen ay grafik kütüphanelerini birlikte karşılaştırdınız.\n"
               "- **Hande Efsane**: Belediyede açık veri portalını yürütüyor, çağrının uygulama paydaşı olabilir. İki ay önce senden görüş istemişti.\n\n"
               "İkisinin de ortak bağı Selin Hoca. Önce ona yazmak iki kapıyı birden açar.")
SORU_CEVAPLARI = [   # (anahtar sözcük grupları, cevap); ilk eşleşen kazanır. Hepsi kurgusal veriye dayanır.
    (("cagri", "kimi tan"), CEVAP_CAGRI),
    (("kime yaz",), "Bu hafta ilk sırada **Selin Hoca** var: 150 günü aşkın süredir konuşmadınız ve açık veri çağrısı Cuma kapanıyor. "
                    "İkinci olarak **Hande Efsane**'ye kısa bir dönüş yapabilirsin."),
    (("cevre", "zayif"), "Finans ve girişim çevren ince: Mert Kurgusal ile tek bir tanışma notun var. Akademi çevren ise güçlü ama Selin Hoca soğuyor."),
    (("cikar", "catisma"), "Kayıtlarında belirgin bir çıkar çatışması görünmüyor. Selin Hoca hem Baran'ın hocası hem senin eski danışmanın; "
                           "ikisine de aynı çağrı için yazarsan bunu açıkça söylemen iyi olur."),
]
CEVAP_BILINMEYEN = ("Bu örnekte yalnızca hazır sorulara cevap verebiliyorum; gerçek Kut ağındaki kayıtları okuyarak cevaplar. "
                    "Şunu deneyebilirsin: «Bu çağrı için kimi tanıyorum?»")
CEVAP_SOZ_ONERI = "Bunu bir söz olarak anladım. Aşağıdaki karttan onaylarsan kaydederim; sen demeden hiçbir şey yazılmaz."
ORNEK_SORULAR = ["Bu çağrı için kimi tanıyorum?", "Bu hafta kime yazayım?", "Ağımda hangi çevre zayıf?"]
SOZ_CUMLESI = "Selin Hoca'ya taslağı Perşembe göndereceğim."
SORU_CUMLESI = "Bu çağrı için kimi tanıyorum?"

# ---------- kurgusal kişiler (tüm adlar uydurmadır) ----------
BEN = {"ad": "Deniz Demo", "kurum": "Lodos Teknoloji", "rol": "Yazılım Geliştirici (stajyer)", "asistan": "Kut",
       "ilgiler": ["açık veri", "veri görselleştirme", "girişimcilik", "topluluk"], "karakter": "", "okul": "", "dersler": []}

# (ad, tur, kurum, rol, yakinlik, alan, nereden, [(kaç gün önce, kanal, cümle)], ek alanlar)
KISILER = [
    ("Selin Hoca", "akademi", "Kuzeyova Üniversitesi", "Öğretim Üyesi, eski proje danışmanı", 1, ["açık veri", "veri etiği"], ["ders"],
     [(158, "yüz yüze", "Bitirme projesi kapanış görüşmesi; sunumu beğendi."), (150, "e-posta", "Staj başvurusu için referans rica ettim, hemen kabul etti.")],
     {"neden_onemli": "Projemin danışmanı; açık veri çağrılarını ilk o duyar.", "ne_verebilirim": "Staj projesinin ilk çıktısını gösterebilirim."}),
    ("Baran Sanalıoğlu", "akademi", "Kuzeyova Üniversitesi", "Doktora Öğrencisi", 2, ["veri görselleştirme", "açık veri"], ["ders"],
     [(26, "yüz yüze", "Laboratuvarda grafik kütüphanelerini karşılaştırdık."), (8, "mesaj", "Makale taslağını paylaştı.")], {}),
    ("Hande Efsane", "is", "Kuzeyova Belediyesi", "Dijital Dönüşüm Danışmanı", 1, ["kamu", "açık veri"], ["etkinlik"],
     [(58, "e-posta", "Açık veri portalı için görüş istedi.")], {}),
    ("Tuna Kurguner", "is", "Lodos Teknoloji", "Ürün Yöneticisi", 3, ["ürün", "veri analitiği"], ["iş yeri"],
     [(30, "yüz yüze", "Çeyrek planını konuştuk."), (3, "yüz yüze", "Kısa durum toplantısı; hedefler net.")],
     {"temas_sikligi": "haftalik", "kullanici_gorusu": "İşimi öğreten, adil bir yönetici."}),
    ("Ceren Uydurmaz", "is", "Lodos Teknoloji", "Arayüz Tasarımcısı", 3, ["tasarım", "erişilebilirlik"], ["iş yeri"],
     [(14, "yüz yüze", "Renk paleti üzerine çalıştık."), (5, "mesaj", "Prototip bağlantısını gönderdi.")], {"temas_sikligi": "haftalik"}),
    ("Barış Denemeci", "is", "Lodos Teknoloji", "Veri Mühendisi", 2, ["veri mühendisliği", "sql"], ["iş yeri"],
     [(41, "mesaj", "Sorgu performansı için ipucu verdi.")], {}),
    ("Nehir Hayalbaz", "yakin", "", "Mimar", 3, ["mimari", "fotoğraf"], ["okul"],
     [(12, "yüz yüze", "Pazar kahvaltısı."), (4, "mesaj", "Hafta sonu planı yaptık.")],
     {"temas_sikligi": "haftalik", "kullanici_gorusu": "Çocukluk arkadaşım, her şeyi konuşabildiğim biri."}),
    ("Cansu Uydurukoğlu", "yakin", "", "Hemşire", 3, [], ["aile"], [(10, "yüz yüze", "Aile yemeği."), (6, "mesaj", "Hal hatır.")],
     {"temas_sikligi": "aylik"}),
    ("Zeynep Örnekoğlu", "etkinlik", "Mavi Defter Topluluğu", "Meetup Organizatörü", 2, ["topluluk", "etkinlik"], ["etkinlik"],
     [(52, "yüz yüze", "Aylık buluşmada tanıştırıldık."), (17, "mesaj", "Konuşmacı çağrısını paylaştı.")], {}),
    ("Kerem Kurgun", "etkinlik", "Mavi Defter Hackathonu", "Jüri Üyesi", 1, ["girişimcilik", "ürün"], ["etkinlik"],
     [(63, "yüz yüze", "Hackathon sonrası jüri değerlendirmesini anlattı.")], {}),
    ("Aslı Rüyalı", "akademi", "Kuzeyova Üniversitesi", "Yüksek Lisans Öğrencisi", 1, ["açık veri"], ["ders"],
     [(6, "yüz yüze", "Seminerde yan yana oturduk, ortak ilgimiz çıktı.")], {}),
    ("Ece Sahteli", "is", "Pamukova Girişim Merkezi", "Kuluçka Programı Yöneticisi", 2, ["kuluçka", "girişim"], ["etkinlik"],
     [(35, "yüz yüze", "Program tanıtım gününde konuştuk."), (11, "e-posta", "Başvuru takvimini gönderdi.")], {}),
    ("Mert Kurgusal", "finans", "Bulutlu Sermaye", "Yatırım Analisti", 1, ["girişim yatırımı"], ["etkinlik"],
     [(66, "e-posta", "Etkinlikte tanıştık, kartını bıraktı.")], {}),
    ("Pelin Mavisu", "cevre", "", "Öğretmen", 2, ["eğitim"], ["okul"], [(33, "mesaj", "Mezuniyet buluşması için yazıştık.")], {}),
]
ILISKILER = [   # (a, b, tip, not)   yönlü tiplerde A → B
    ("tuna-kurguner", "ben", "yonetici", "Lodos'ta doğrudan yöneticim"), ("selin-hoca", "ben", "mentor", "Bitirme projesi danışmanım"),
    ("nehir-hayalbaz", "ben", "arkadas", "Çocukluktan"), ("cansu-uydurukoglu", "ben", "akraba", "Kuzen"),
    ("ceren-uydurmaz", "ben", "birlikte-calisiyor", "Aynı ekip"),
    ("selin-hoca", "baran-sanalioglu", "hocasi", "Doktora danışmanı"), ("selin-hoca", "hande-efsane", "tanisiyor", "Açık veri çalıştayı"),
    ("baran-sanalioglu", "asli-ruyali", "arkadas", "Aynı laboratuvar"),
    ("tuna-kurguner", "ceren-uydurmaz", "birlikte-calisiyor", ""), ("tuna-kurguner", "baris-denemeci", "birlikte-calisiyor", ""),
    ("ceren-uydurmaz", "baris-denemeci", "birlikte-calisiyor", ""), ("zeynep-ornekoglu", "kerem-kurgun", "birlikte-calisiyor", "Hackathon ekibi"),
    ("ece-sahteli", "mert-kurgusal", "tanisiyor", ""), ("nehir-hayalbaz", "pelin-mavisu", "arkadas", ""),
]
CIKARIMLAR = [
    {"kisi": "baran-sanalioglu", "alan": "etiketler", "deger": "veri-gorsellestirme, acik-veri",
     "gerekce": "temas notları: grafik kütüphaneleri, makale taslağı", "kaynak": "demo"},
    {"kisi": "hande-efsane", "alan": "soru", "deger": "Açık veri portalı çalışması hâlâ sürüyor mu?",
     "gerekce": "son kayıt 58 gün önce", "kaynak": "demo"},
]
HEDEF_DURUMLARI = {"taslak": "Taslak (onay bekliyor)", "aktif": "Aktif", "beklemede": "Beklemede", "tamam": "Tamamlandı", "birakildi": "Bırakıldı"}
HEDEF_TURLERI = {"ag": "Ağ ve ilişkiler", "kariyer": "Kariyer", "akademik": "Akademik / sınav", "proje": "Proje / ürün",
                 "etkinlik": "Etkinlik / yarışma", "finans": "Finans", "kisisel": "Kişisel"}
STRATEJI_SONUCLARI = {"yaptim": "Yaptım", "yapmadim": "Yapmadım", "ise_yaradi": "İşe yaradı", "ise_yaramadi": "İşe yaramadı", "gecersiz": "Geçersiz / yanlış"}


def _gun(n, bugun=None):
    return (bugun or date.today()) - timedelta(days=n)


def _cuma(bugun=None):
    b = bugun or date.today()
    return b + timedelta(days=(4 - b.weekday()) % 7 or 7)


def _kod_al(ad):
    """Modülün kod nesnesi ve dosya yolu. Önce içe aktarma sistemi (`get_code`: kaynak ağaç ve PyInstaller PYZ yükleyicisi); olmazsa
    kaynak dosya (kaynak ağaçta kut/, donmuş .exe'de `datas` ile _MEIPASS köküne konan <ad>.py). İkisi de yoksa demo kapalı kalır (ValueError)."""
    spec = None
    try:
        spec = importlib.util.find_spec(ad)
        if spec is not None and spec.loader is not None and hasattr(spec.loader, "get_code"):
            kod = spec.loader.get_code(ad)
            if kod is not None:
                return kod, spec.origin or os.path.join(KOK, ad + ".py")
    except Exception:
        pass
    for kok in (KOK, getattr(sys, "_MEIPASS", "")):
        yol = os.path.join(kok, ad + ".py") if kok else ""
        if yol and os.path.isfile(yol):
            with open(yol, encoding="utf-8") as f:
                return compile(f.read(), yol, "exec"), yol
    raise ValueError("Örnek bu kurulumda kullanılamıyor (demo bileşeni yüklenemedi)")


# ---------- özel modül kapsülü ----------
class Kapsul:
    """ag_cekirdek + ag_soz'un ÖZEL kopyaları. Kendi modül sözlükleri (VERI, KISILER...) vardır; gerçek modüllere dokunulmaz.
    Kopyaların içindeki `import ag_cekirdek` / `import ag_soz` (geç içe aktarma dahil) bu sözlüğe yönlenir."""

    def __init__(self):
        self.modul = {}

        def yonlendir(ad, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and ad in self.modul:
                return self.modul[ad]
            return builtins.__import__(ad, globals, locals, fromlist, level)

        for ad in ("ag_cekirdek", "ag_soz"):
            kod, kaynak = _kod_al(ad)
            m = types.ModuleType(ad + "__demo")
            m.__file__ = kaynak
            m.DEMO_KAPSULU = True   # ag_cekirdek: gerçek veri klasörünü iskeletleme
            m.__dict__["__builtins__"] = {**vars(builtins), "__import__": yonlendir}
            self.modul[ad] = m
            exec(kod, m.__dict__)
        self.c, self.soz = self.modul["ag_cekirdek"], self.modul["ag_soz"]


_kapsul = None
_kilit = threading.RLock()
_durum = None   # {"dizin", "anahtar", "t"} ya da None


def kapsul():
    global _kapsul
    with _kilit:
        if _kapsul is None:
            _kapsul = Kapsul()
        return _kapsul


# ---------- senaryo yazımı (gerçek ya da özel ag_cekirdek ile) ----------
def uret(c, hedef, bugun=None, ben_foto=None):
    """Senaryo verisini `hedef` klasörüne yazar. `c`: yazıcıların bulunduğu ag_cekirdek (kapsül ya da demo_veri.py için gerçek modül)."""
    hedef = os.path.abspath(hedef)
    os.makedirs(hedef, exist_ok=True)
    c.veri_klasoru(hedef)
    foto = c.foto_kaydet("ben", ben_foto) if ben_foto else ""
    c.ben_yaz({**BEN, "foto": foto})
    for ad, tur, kurum, rol, yak, alan, nereden, temaslar, ek in KISILER:
        kid = c.slug(ad)
        satirlar = [f"{_gun(n, bugun):%d.%m.%Y} · {kanal} · {metin}" for n, kanal, metin in sorted(temaslar, reverse=True)]
        alanlar = {"ad": ad, "tur": tur, "kurum": kurum, "rol": rol, "alan": alan, "nereden": nereden, "yakinlik": str(yak), "foto": "",
                   "son_temas": _gun(min(n for n, _, _ in temaslar), bugun).isoformat()}
        alanlar.update(ek)
        c.kisi_yaz(kid, alanlar, c.yeni_govde(ad, "kurgusal demo verisi", satirlar))
    t = _gun(30, bugun).isoformat()
    c.iliskileri_yaz([{"a": a, "b": b, "tip": tip, "not": n, "kaynak": "demo", "tarih": t} for a, b, tip, n in ILISKILER])
    c.cikarim_ekle(CIKARIMLAR)
    return hedef


def pusula_verisi(bugun=None):
    """Pusula penceresi ve sol kart için kurgusal hedef + strateji (dosya/ağ/model yok). Şekil ag_sunucu.pusula() ile aynıdır."""
    b = bugun or date.today()
    cuma = _cuma(b).isoformat()
    hedefler = [
        {"id": "acik-veri-cagrisi", "baslik": "Açık veri çağrısına staj projesiyle başvurmak", "durum": "aktif", "tur": "proje", "son_tarih": cuma,
         "oncelik": "1", "olcut": "Başvuru Cuma kapanmadan gönderilmiş", "anahtar": ["açık veri", "veri görselleştirme"],
         "neden": "Staj projesini kamuya açık bir sahnede sınamak.", "kaynak": "demo", "olusturma": _gun(20, b).isoformat(),
         "ilerleme": ["Başvuru taslağının ilk sayfası yazıldı"]},
        {"id": "staj-kadro", "baslik": "Stajı kalıcı kadro görüşmesine çevirmek", "durum": "aktif", "tur": "kariyer",
         "son_tarih": (b + timedelta(days=40)).isoformat(), "oncelik": "2", "olcut": "Tuna ile kadro görüşmesi yapılmış",
         "anahtar": ["staj", "ürün"], "neden": "İş yerinde kalıcı olmak.", "kaynak": "demo", "olusturma": _gun(60, b).isoformat(), "ilerleme": []},
    ]
    taslak = ("Merhaba Selin Hocam, açık veri çağrısı Cuma kapanıyor. Staj projemin başvuru taslağını Perşembe size göndermek istiyorum; "
              "bakabilir misiniz? Sizi uzun zamandır aramadım, nasılsınız?")
    strateji = {
        "dosya": "demo-sali.md", "tarih": datetime.now().isoformat(timespec="minutes"), "model": "örnek içerik (model çağrısı yok)",
        "ozet": "Bu hafta en değerli hamle soğumuş bir bağı geri açmak: Selin Hoca hem çağrının ilk duyurulduğu çevrede hem Baran ve Hande ile ortak bağın.",
        "hedefler": [
            {"hedef": "acik-veri-cagrisi", "durum": "yolunda", "yorum": "Taslağın ilk sayfası hazır; fikir alacağın kişi eksik.",
             "sonraki_kilometre_tasi": f"{cuma} öncesi başvuru", "netlestir": ""},
            {"hedef": "staj-kadro", "durum": "yolunda", "yorum": "Tuna ile haftalık temasın düzenli.", "sonraki_kilometre_tasi": "", "netlestir": ""}],
        "hamleler": [
            {"hedef": "acik-veri-cagrisi", "tur": "ag", "baslik": "Selin Hoca'yla bağı yeniden kur",
             "neden_simdi": "Çağrı Cuma kapanıyor; Selin Hoca ile son konuşmanız 5 ay önceydi (staj başvurusu).",
             "gormedigin": "Selin Hoca Baran'ın hocası ve Hande ile tanışık: ona yazmak çağrı için iki kapıyı birden açar.",
             "kim": SELIN, "kim_uzerinden": "", "ilk_adim": "Taslağın ilk sayfasını gönder, fikrini sor.", "son_tarih": cuma, "taslak": taslak,
             "kanit": ["selin-hoca: son temas 150 gün önce (e-posta, staj başvurusu)", "iliskiler.md: selin-hoca hocasi baran-sanalioglu"],
             "guven": "yuksek", "sonuc": "", "sonuc_not": ""},
            {"hedef": "acik-veri-cagrisi", "tur": "ag", "baslik": "Baran'dan veri görselleştirme fikri iste",
             "neden_simdi": "Çağrının değerlendirmesinde görsel anlatım ağırlıklı.", "gormedigin": "Baran, Selin Hoca'nın laboratuvarında; birlikte bakabilirsiniz.",
             "kim": "baran-sanalioglu", "kim_uzerinden": SELIN, "ilk_adim": "Panonun ekran görüntüsünü gönder.", "son_tarih": "", "taslak": "",
             "kanit": ["baran-sanalioglu: temas notu (grafik kütüphaneleri)"], "guven": "orta", "sonuc": "", "sonuc_not": ""}],
        "sorular": [],
    }
    return {"hedefler": hedefler, "durumlar": HEDEF_DURUMLARI, "turler": HEDEF_TURLERI,
            "vekil": {"veri_yok": True, "kapali": True, "hedefler": []}, "etkinlik": {"kapali": True},
            "kesif_durum": {"calisiyor": False, "mesaj": "", "vekil_hazirlaniyor": False}, "vekilpedia_acik": False,
            "kaynaklar": {"kaynaklar": [], "okullar": [], "okul": "", "calisiyor": False},
            "strateji": strateji, "strateji_durum": {"calisiyor": False, "hata": "", "son": ""}, "strateji_model": "örnek içerik",
            "sonuclar": STRATEJI_SONUCLARI, "kararlar": {}}


# ---------- yaşam döngüsü ----------
def _gercek_klasor(yol):
    """Sembolik bağ ya da junction (yeniden ayrıştırma noktası) olmayan gerçek klasör mü? Silme yanlış yere yönlenmesin."""
    try:
        st = os.lstat(yol)
    except OSError:
        return False
    if os.path.islink(yol) or getattr(st, "st_file_attributes", 0) & 0x400:   # FILE_ATTRIBUTE_REPARSE_POINT
        return False
    return os.path.isdir(yol)


def _artik_temizle():
    """Çökmüş bir süreçten kalan, işaretli ve eski demo klasörlerini siler (yalnız sistem geçici klasöründe)."""
    kok = tempfile.gettempdir()
    try:
        adlar = os.listdir(kok)
    except OSError:
        return
    for ad in adlar:
        yol = os.path.join(kok, ad)
        try:
            if (ad.startswith(DIZIN_ONEKI) and _gercek_klasor(yol) and os.path.isfile(os.path.join(yol, ISARET))
                    and time.time() - os.path.getmtime(yol) > ESKI_SN):
                shutil.rmtree(yol, ignore_errors=True)
        except OSError:
            pass


def _yaz_senaryo(dizin):
    ev = kapsul()
    for ad in os.listdir(dizin):
        if ad == ISARET:
            continue
        yol = os.path.join(dizin, ad)
        shutil.rmtree(yol, ignore_errors=True) if os.path.isdir(yol) else os.remove(yol)
    uret(ev.c, dizin)


def baslat():
    """Yeni demo bağlamı: geçici klasör + senaryo verisi + demo anahtarı. Önceki demo varsa kapatılır."""
    global _durum
    with _kilit:
        kapat()
        _artik_temizle()
        dizin = tempfile.mkdtemp(prefix=DIZIN_ONEKI)
        with open(os.path.join(dizin, ISARET), "w", encoding="utf-8") as f:
            f.write("Kut demo geçici verisi; silinebilir.\n")
        try:
            _yaz_senaryo(dizin)
        except Exception:
            shutil.rmtree(dizin, ignore_errors=True)
            raise
        _durum = {"dizin": dizin, "anahtar": secrets.token_urlsafe(24), "t": time.time()}
    return {"adres": "/demo"}


def kapat():
    """Geçici klasörü siler, anahtarı iptal eder. Etkin demo yoksa sessizce döner."""
    global _durum
    with _kilit:
        d, _durum = _durum, None
        if d and _gercek_klasor(d["dizin"]) and os.path.isfile(os.path.join(d["dizin"], ISARET)):
            shutil.rmtree(d["dizin"], ignore_errors=True)
    return {}


atexit.register(kapat)


def _taze():
    """Etkin demoyu döndürür; boşta kalma süresi dolduysa kapatır ve None verir."""
    with _kilit:
        if _durum is None:
            return None
        if time.time() - _durum["t"] > OMUR_SN:
            kapat()
            return None
        _durum["t"] = time.time()
        return _durum


def aktif():
    with _kilit:
        return _durum is not None and time.time() - _durum["t"] <= OMUR_SN


def anahtar():
    d = _taze()
    return d["anahtar"] if d else None


def dizin():
    d = _taze()
    return d["dizin"] if d else None


def durum(_=None):
    return {"aktif": _taze() is not None}


# ---------- anlatım sesi ----------
def ses_dosyasi(sahne):
    """kut/demo_ses/<sahne>.wav|.ogg varsa yolu, yoksa None. Sahne kimliği beyaz listeden gelir (yol gezintisi yok)."""
    if sahne not in SAHNE_IDLERI:
        return None
    for kok in {os.path.join(getattr(sys, "_MEIPASS", KOK), "demo_ses"), os.path.join(KOK, "demo_ses")}:   # .exe'de paketlenmiş varlık klasörü
        for u in SES_UZANTILARI:
            yol = os.path.join(kok, sahne + u)
            if os.path.isfile(yol):
                return yol
    return None


def ses_tipi(yol):
    return "audio/ogg" if yol.endswith(".ogg") else "audio/wav"


# ---------- sayfa verisi ----------
def _veri(ev):
    ev.c.veri_klasoru(_durum["dizin"])
    return ev.c.veri_hazirla()


def sayfa_verisi():
    """Demo sayfası için (veri, demo_meta). Sayfa her açılışında senaryo sıfırlanır (yenileme sahneyi baştan başlatır)."""
    with _kilit:
        d = _taze()
        if d is None:
            return None
        ev = kapsul()
        _yaz_senaryo(d["dizin"])
        veri = _veri(ev)
    meta = {"sahneler": [{"id": s["id"], "baslik": s["baslik"], "metin": s["metin"], "ses": ses_dosyasi(s["id"]) is not None} for s in SAHNELER],
            "pusula": pusula_verisi(), "zaman": ZAMAN_ETIKETI, "selin": SELIN, "soz": SOZ_CUMLESI, "soru": SORU_CUMLESI,
            "ornekler": ORNEK_SORULAR}
    return veri, meta, d["anahtar"]


# ---------- demo uçları (hepsi kapsülde, geçici klasöre; ağ ve model yok) ----------
def _sade(m, metin):
    return m.c.sade(metin)


def sor(g):
    """Hazır cevaplı "Kut'a sor". Cümlede söz varsa kural motoru (model yok) onay önerisi çıkarır; HİÇBİR ŞEY yazılmaz."""
    soru = " ".join(str(g.get("soru") or "").split())[:400]
    if not soru:
        raise ValueError("soru boş")
    with _kilit:
        if _taze() is None:
            raise ValueError("demo etkin değil")
        ev = kapsul()
        ev.c.veri_klasoru(_durum["dizin"])
        oneri = ev.soz.oner(soru, ev.c.kisileri_oku())
        r = {"cevap": "", "kaydedilen": [], "atlanan": [], "oturum": "demo"}
        if oneri:
            r["cevap"], r["soz_onay"] = CEVAP_SOZ_ONERI, [{**o, "soru": ev.soz.onay_sorusu(_ad(ev, o["kisi"]), o["yon"], o.get("son", ""))} for o in oneri]
            return r
    s = _sade(ev, soru)
    r["cevap"] = next((cvp for anahtarlar, cvp in SORU_CEVAPLARI if all(a in s for a in anahtarlar)), CEVAP_BILINMEYEN)
    return r


def _ad(ev, kid):
    return (ev.c.kisi_oku(os.path.join(ev.c.KISILER, kid + ".md")) or {}).get("ad") or kid


def soz_onayla(g):
    """Onay kartındaki «Evet, ekle»: sözü DEMO klasöründeki kişiye yazar; yeni veriyi döndürür."""
    with _kilit:
        if _taze() is None:
            raise ValueError("demo etkin değil")
        ev = kapsul()
        ev.c.veri_klasoru(_durum["dizin"])
        o = ev.soz.oneri_dogrula(g, ev.c.kisileri_oku())
        if not o:
            raise ValueError("söz önerisi geçersiz")
        try:
            ev.soz.kisi_ekle(o["kisi"], o["yon"], o["metin"], o["son"])
        except ValueError:
            pass   # aynı söz zaten açık (çift tıklama): sessizce aynı veri döner
        ad = _ad(ev, o["kisi"])
        return {"kisi": o["kisi"], "oturum": "demo", "cevap": f"{ad} için söz kaydedildi: {o['metin']}" + (f" (son: {o['son']})" if o["son"] else ""),
                "veri": ev.c.veri_hazirla()}


def isinma(_=None):
    """Zaman birkaç gün ileri: Selin Hoca ile temas işlenir, söz tamamlanır, yakınlık 1 → 2. Yalnız DEMO klasörüne yazar."""
    with _kilit:
        if _taze() is None:
            raise ValueError("demo etkin değil")
        ev = kapsul()
        c, soz = ev.c, ev.soz
        c.veri_klasoru(_durum["dizin"])
        yol = os.path.join(c.KISILER, SELIN + ".md")
        k = c.kisi_oku(yol)
        govde = k.pop("govde")
        if not any(s["durum"] == "acik" for s in soz.oku(govde)):
            govde = soz.ekle(govde, "ben", "taslağı Perşembe göndermek", "")
        sozler = soz.oku(govde)
        sira = next(s["sira"] for s in sozler if s["durum"] == "acik")
        govde = soz.kapat(govde, sira, "tamam")
        bugun = date.today()
        govde = c.temas_ekle(govde, f"{bugun:%d.%m.%Y} · e-posta · Taslağı gönderdim; çağrı için kendi ağından iki ismi de önerdi.")
        k.update(son_temas=bugun.isoformat(), yakinlik="2", sonraki_adim="Başvuruyu birlikte son haline getirmek",
                 sonraki_tarih=(bugun + timedelta(days=2)).isoformat())
        c.kisi_yaz(SELIN, k, govde)
        return {"veri": c.veri_hazirla(), "zaman": ZAMAN_ETIKETI}
