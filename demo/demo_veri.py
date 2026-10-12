"""Kut için tamamen KURGUSAL demo verisi üretir (ekran görüntüsü, tanıtım videosu, deneme).

Kullanım:
    py -3 demo/demo_veri.py                 # geçici bir klasöre yazar, yolunu yazdırır
    py -3 demo/demo_veri.py --hedef KLASÖR  # verilen (boş ya da olmayan) klasöre yazar
Sonra:
    py -3 kut.pyw --veri KLASÖR [--port 47400]

Bütün kişiler, kurumlar ve olaylar uydurmadır; gerçek biriyle ilgisi yoktur. Tarihler bugüne göre göreli üretilir.
Biçimler uygulamanın kendi yazıcılarıyla (ag_cekirdek, ag_hedef, ag_strateji) yazılır; fotoğraflar standart
kütüphaneyle çizilen baş harfli renkli daire PNG'lerdir (gerçek yüz yok). Ağa hiçbir istek atılmaz.
"""
import argparse
import os
import struct
import sys
import tempfile
import zlib
from datetime import date, datetime, timedelta

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_cekirdek as c  # noqa: E402
import ag_hedef as hd  # noqa: E402
import ag_strateji as st  # noqa: E402

BUGUN = date.today()


def gun(n):
    """n gün önce (n negatifse ileride)."""
    return BUGUN - timedelta(days=n)


# ---------- baş harfli avatar PNG (yalnız stdlib) ----------
FONT = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".####|#....|#....|#....|#....|#....|.####", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".####|#....|#....|#..##|#...#|#...#|.####", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "#####|..#..|..#..|..#..|..#..|..#..|#####", "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#", "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
}
RENKLER = [(138, 92, 214), (27, 163, 163), (214, 83, 127), (224, 138, 46), (46, 158, 106), (59, 111, 217),
           (122, 133, 153), (192, 86, 90), (160, 120, 60)]


def _png(w, h, satirlar):
    def parca(tip, veri):
        b = tip + veri
        return struct.pack(">I", len(veri)) + b + struct.pack(">I", zlib.crc32(b) & 0xFFFFFFFF)
    ham = b"".join(b"\x00" + bytes(s) for s in satirlar)
    return (b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + parca(b"IDAT", zlib.compress(ham, 9)) + parca(b"IEND", b""))


def avatar(ad, renk, boyut=160):
    bas = "".join(w[0] for w in c.sade(ad).split() if w not in ("prof", "dr", "doc"))[:2].upper() or "?"
    olcek = 6 if len(bas) == 1 else 5
    gen = len(bas) * 5 * olcek + (len(bas) - 1) * olcek
    x0, y0 = (boyut - gen) // 2, (boyut - 7 * olcek) // 2
    piksel = set()
    for i, ch in enumerate(bas):
        for r, satir in enumerate(FONT.get(ch, FONT["O"]).split("|")):
            for k, v in enumerate(satir):
                if v == "#":
                    for dy in range(olcek):
                        for dx in range(olcek):
                            piksel.add((x0 + i * 6 * olcek + k * olcek + dx, y0 + r * olcek + dy))
    orta, yaricap = (boyut - 1) / 2, boyut / 2 - 1
    satirlar = []
    for y in range(boyut):
        s = []
        for x in range(boyut):
            d = ((x - orta) ** 2 + (y - orta) ** 2) ** 0.5
            a = max(0.0, min(1.0, yaricap - d + 0.5))
            if (x, y) in piksel:
                r_, g_, b_ = 255, 255, 255
            else:   # üstten alta hafif aydınlanan zemin
                t = 0.82 + 0.18 * (1 - y / boyut)
                r_, g_, b_ = (min(255, int(v * t)) for v in renk)
            s += [r_, g_, b_, int(a * 255)]
        satirlar.append(s)
    return _png(boyut, boyut, satirlar)


# ---------- kurgusal kişiler ----------
# (ad, tur, kurum, rol, yakinlik, alan, nereden, [(kaç gün önce, kanal, cümle)], ek alanlar)
KISILER = [
    ("Aylin Masalcı", "akademi", "Kuzeyova Üniversitesi", "Doçent, Bilgisayar Mühendisliği", 3, ["açık veri", "makine öğrenmesi"], ["ders"],
     [(95, "yüz yüze", "Bitirme projesi için ofis saatinde görüştük."), (48, "e-posta", "Açık veri panosu fikrini anlattım, kaynak önerdi."),
      (21, "mesaj", "Seminer davetini iletti.")],
     {"ozellikler": ["uzmanlik=9", "destek=8", "guvenilirlik=8"], "ozellik_kaynak": "sen", "neden_onemli": "Projemin akademik danışmanı.",
      "ne_verebilirim": "Öğrencileri için veri seti ve geri bildirim.", "sonraki_adim": "Panonun ilk sürümünü göstermek"}),
    ("Cevdet Hayaloğlu", "akademi", "Kuzeyova Üniversitesi", "Profesör, Mühendislik Fakültesi Dekanı", 2, ["yönetim", "ağ bilimi"], ["ders"],
     [(56, "yüz yüze", "Fakülte tanışma toplantısında kısaca konuştuk."), (44, "e-posta", "Staj izni için teşekkür yazdım.")], {}),
    ("Tuna Kurguner", "is", "Lodos Teknoloji", "Ürün Yöneticisi", 3, ["ürün", "veri analitiği"], ["iş yeri"],
     [(30, "yüz yüze", "Çeyrek planını konuştuk."), (9, "mesaj", "Yeni panonun ekran görüntüsünü paylaştım."),
      (3, "yüz yüze", "Kısa durum toplantısı; hedefler net.")],
     {"temas_sikligi": "haftalik", "kullanici_gorusu": "İşimi öğreten, adil bir yönetici."}),
    ("Selin Uydurmaz", "is", "Lodos Teknoloji", "Arayüz Tasarımcısı", 3, ["tasarım", "erişilebilirlik"], ["iş yeri"],
     [(14, "yüz yüze", "Renk paleti üzerine çalıştık."), (5, "mesaj", "Prototip bağlantısını gönderdi.")], {"temas_sikligi": "haftalik"}),
    ("Barış Denemeci", "is", "Lodos Teknoloji", "Veri Mühendisi", 2, ["veri mühendisliği", "sql"], ["iş yeri"],
     [(75, "yüz yüze", "Veri ambarı mimarisini anlattı."), (41, "mesaj", "Sorgu performansı için ipucu verdi.")],
     {"ne_verebilirim": "Yeni gelen stajyerlere kısa bir tanıtım yapabilirim."}),
    ("Mert Kurgusal", "finans", "Bulutlu Sermaye", "Yatırım Analisti", 1, ["girişim yatırımı"], ["etkinlik"],
     [(66, "e-posta", "Etkinlikte tanıştık, kartını bıraktı.")], {}),
    ("Nehir Hayalbaz", "yakin", "", "Mimar", 3, ["mimari", "fotoğraf"], ["okul"],
     [(12, "yüz yüze", "Pazar kahvaltısı."), (4, "mesaj", "Hafta sonu planı yaptık.")],
     {"temas_sikligi": "haftalik", "kullanici_gorusu": "Çocukluk arkadaşım, her şeyi konuşabildiğim biri."}),
    ("Emre Masalcı", "cevre", "", "Serbest yazılımcı", 1, ["web"], ["akraba"], [(88, "mesaj", "Bayram mesajlaştık.")], {}),
    ("Zeynep Örnekoğlu", "etkinlik", "Mavi Defter Topluluğu", "Meetup Organizatörü", 2, ["topluluk", "etkinlik"], ["etkinlik"],
     [(52, "yüz yüze", "Aylık buluşmada tanıştırıldık."), (17, "mesaj", "Konuşmacı çağrısını paylaştı.")],
     {"sonraki_adim": "Hackathon için başvuru formunu sormak", "sonraki_tarih": gun(-2).isoformat(),
      "ne_verebilirim": "Panomla kısa bir demo sunabilirim."}),
    ("Kerem Kurgun", "etkinlik", "Mavi Defter Hackathonu", "Jüri Üyesi", 1, ["girişimcilik", "ürün"], ["etkinlik"],
     [(63, "yüz yüze", "Hackathon sonrası jüri değerlendirmesini anlattı.")],
     {"sonraki_adim": "Jüri kriterlerini sormak", "sonraki_tarih": gun(2).isoformat()}),
    ("Ece Sahteli", "is", "Pamukova Girişim Merkezi", "Kuluçka Programı Yöneticisi", 2, ["kuluçka", "girişim"], ["etkinlik"],
     [(35, "yüz yüze", "Program tanıtım gününde konuştuk."), (11, "e-posta", "Başvuru takvimini gönderdi.")],
     {"sonraki_adim": "Başvuru taslağını göndermek", "sonraki_tarih": gun(-1).isoformat()}),
    ("Onur Hayalci", "finans", "Rüya Melek Ağı", "Melek Yatırımcı", 1, ["melek yatırım"], ["etkinlik"],
     [(61, "yüz yüze", "Pitch gecesinde kısa sohbet.")], {}),
    ("Defne Yoktur", "cevre", "", "Komşu", 1, [], ["mahalle"], [(70, "yüz yüze", "Apartman toplantısında sohbet ettik.")], {}),
    ("Baran Sanalıoğlu", "akademi", "Kuzeyova Üniversitesi", "Doktora Öğrencisi", 2, ["veri görselleştirme", "makine öğrenmesi"], ["ders"],
     [(26, "yüz yüze", "Laboratuvarda grafik kütüphanelerini karşılaştırdık."), (8, "mesaj", "Makale taslağını paylaştı.")], {}),
    ("Pelin Mavisu", "cevre", "", "Öğretmen", 2, ["eğitim"], ["okul"], [(33, "mesaj", "Mezuniyet buluşması için yazıştık.")], {}),
    ("Umut Kurmaca", "is", "Çınaraltı Vakfı", "Program Yöneticisi", 1, ["sivil toplum", "açık veri"], ["etkinlik"],
     [(54, "e-posta", "Açık veri çalıştayı için bilgi istedi.")], {}),
    ("Gizem Denizci", "yakin", "", "Biyolog", 3, ["deniz biyolojisi"], ["çevre"],
     [(2, "mesaj", "Günlük konuşma."), (1, "yüz yüze", "Akşam yemeği.")], {"temas_sikligi": "gunluk"}),
    ("Rüzgar Tasarlak", "is", "Fırtına Yazılım", "Kurucu", 1, ["girişim", "bulut"], ["etkinlik"],
     [(75, "yüz yüze", "Konferansta rakip ürünleri konuştuk.")], {"neden_onemli": "Rakip firmada çalışıyor; temasta dikkatli ol."}),
    ("Hande Efsane", "siyaset", "Kuzeyova Belediyesi", "Dijital Dönüşüm Danışmanı", 1, ["kamu", "açık veri"], ["etkinlik"],
     [(58, "e-posta", "Açık veri portalı için görüş istedi.")], {}),
    ("Doruk Masalyan", "cevre", "", "Spor arkadaşı", 2, ["koşu"], ["mahalle"], [(20, "yüz yüze", "Sabah koşusu.")], {}),
    ("Sevgi Kurgucu", "akademi", "Kuzeyova Üniversitesi", "Yayın Editörü", 1, ["akademik yayın"], ["ders"],
     [(72, "e-posta", "Dergi çağrısını iletti.")], {}),
    ("Alper Düşsel", "is", "", "Serbest Fotoğrafçı", 2, ["fotoğraf", "video"], ["arkadaş"],
     [(37, "mesaj", "Demo videosu için ekipman konuştuk.")], {}),
    ("İpek Hayalgücü", "etkinlik", "Mavi Defter Topluluğu", "Konuşmacı", 1, ["yapay zekâ", "etik"], ["etkinlik"],
     [(17, "e-posta", "Konuşma slaytlarını paylaştı.")], {}),
    ("Cansu Uydurukoğlu", "yakin", "", "Hemşire", 3, [], ["aile"], [(10, "yüz yüze", "Aile yemeği."), (6, "mesaj", "Hal hatır.")],
     {"temas_sikligi": "aylik"}),
    ("Yiğit Peridağı", "finans", "Peridağı Mali Müşavirlik", "Mali Müşavir", 2, ["vergi", "muhasebe"], ["tavsiye"],
     [(45, "mesaj", "Vergi dönemi hatırlatması."), (16, "e-posta", "Belge listesi gönderdi.")], {}),
    ("Mine Bulutçu", "is", "Lodos Teknoloji", "İnsan Kaynakları Uzmanı", 2, ["işe alım"], ["iş yeri"],
     [(40, "yüz yüze", "Staj süreci hakkında konuştuk.")], {}),
    ("Taner Gölgeli", "cevre", "Fırtına Yazılım", "Eski ortak", 1, ["yazılım"], ["etkinlik"],
     [(80, "mesaj", "Kısa selamlaşma.")], {}),
    ("Aslı Rüyalı", "akademi", "Kuzeyova Üniversitesi", "Yüksek Lisans Öğrencisi", 1, ["açık veri"], ["ders"],
     [(6, "yüz yüze", "Seminerde yan yana oturduk, ortak ilgimiz çıktı.")], {"sonraki_adim": "Panoyu göstermek için yazmak"}),
    ("Kuzey Sahaf", "is", "Bulutlu Sermaye", "Ortak", 1, ["yatırım"], ["etkinlik"], [(63, "e-posta", "Tanışma e-postası.")], {}),
    # dolaylı kişiler: seninle doğrudan bağı yok, yalnız bir yakınının üzerinden tanınıyor (varsayılan olarak haritada gizli)
    ("Gülten Hayalbaz", "cevre", "", "Nehir'in annesi", 0, [], ["nehir"], [], {}),
    ("Orhan Hayalbaz", "cevre", "", "Nehir'in babası", 0, [], ["nehir"], [], {}),
]

ILISKILER = [   # (a, b, tip, not)   yönlü tiplerde A → B
    ("tuna-kurguner", "ben", "yonetici", "Lodos'ta doğrudan yöneticim"), ("cevdet-hayaloglu", "ben", "hocasi", "Bilgisayar ağları dersi"),
    ("aylin-masalci", "ben", "mentor", "Proje danışmanı"), ("nehir-hayalbaz", "ben", "arkadas", "Çocukluktan"),
    ("gizem-denizci", "ben", "partner", ""), ("cansu-uydurukoglu", "ben", "akraba", "Kuzen"),
    ("selin-uydurmaz", "ben", "birlikte-calisiyor", "Aynı ekip"),
    ("aylin-masalci", "cevdet-hayaloglu", "birlikte-calisiyor", "Aynı fakülte"), ("aylin-masalci", "baran-sanalioglu", "hocasi", "Doktora danışmanı"),
    ("cevdet-hayaloglu", "sevgi-kurgucu", "tanisiyor", "Dergi kurulu"), ("tuna-kurguner", "selin-uydurmaz", "birlikte-calisiyor", ""),
    ("tuna-kurguner", "baris-denemeci", "birlikte-calisiyor", ""), ("tuna-kurguner", "mine-bulutcu", "birlikte-calisiyor", ""),
    ("selin-uydurmaz", "baris-denemeci", "birlikte-calisiyor", ""), ("zeynep-ornekoglu", "kerem-kurgun", "birlikte-calisiyor", "Hackathon ekibi"),
    ("zeynep-ornekoglu", "ipek-hayalgucu", "tanisiyor", ""), ("ece-sahteli", "onur-hayalci", "tanisiyor", ""),
    ("ece-sahteli", "umut-kurmaca", "tanisiyor", ""), ("onur-hayalci", "mert-kurgusal", "is-ortagi", "Ortak fon"),
    ("mert-kurgusal", "kuzey-sahaf", "birlikte-calisiyor", "Aynı fon"), ("mert-kurgusal", "yigit-peridagi", "tanisiyor", ""),
    ("ruzgar-tasarlak", "tuna-kurguner", "rakip", "Rakip ürünler"), ("ruzgar-tasarlak", "taner-golgeli", "is-ortagi", "Eski ortaklık"),
    ("taner-golgeli", "tuna-kurguner", "gerginlik", "Eski sözleşme anlaşmazlığı"), ("nehir-hayalbaz", "pelin-mavisu", "arkadas", ""),
    ("nehir-hayalbaz", "doruk-masalyan", "arkadas", ""), ("nehir-hayalbaz", "gulten-hayalbaz", "akraba", "Annesi"),
    ("nehir-hayalbaz", "orhan-hayalbaz", "akraba", "Babası"), ("gulten-hayalbaz", "orhan-hayalbaz", "partner", ""),
    ("hande-efsane", "umut-kurmaca", "tanisiyor", "Açık veri çalıştayı"), ("alper-dussel", "selin-uydurmaz", "arkadas", ""),
    ("asli-ruyali", "baran-sanalioglu", "arkadas", "Aynı laboratuvar"), ("kuzey-sahaf", "onur-hayalci", "tanisiyor", ""),
    ("ipek-hayalgucu", "kerem-kurgun", "arkadas", ""), ("defne-yoktur", "pelin-mavisu", "tanisiyor", ""),
    ("gizem-denizci", "cansu-uydurukoglu", "tanisiyor", ""), ("emre-masalci", "aylin-masalci", "akraba", "Kuzenler"),
]

CIKARIMLAR = [
    {"kisi": "asli-ruyali", "alan": "ozet", "deger": "Aylin Hoca'nın seminerinden tanıştığın, açık veri ilgisini paylaşan yüksek lisans öğrencisi",
     "gerekce": "temas notu: Seminerde yan yana oturduk, ortak ilgimiz çıktı", "kaynak": "demo"},
    {"kisi": "baran-sanalioglu", "alan": "etiketler", "deger": "makine-ogrenmesi, veri-gorsellestirme",
     "gerekce": "temas notları: grafik kütüphaneleri, makale taslağı", "kaynak": "demo"},
    {"kisi": "zeynep-ornekoglu", "alan": "iliski", "deger": "tanisiyor ipek-hayalgucu",
     "gerekce": "ikisi de Mavi Defter etkinliklerinde geçiyor", "kaynak": "demo"},
    {"kisi": "ece-sahteli", "alan": "ozellikler", "deger": "destek=7, uyum=6",
     "gerekce": "destek: başvuru takvimini kendiliğinden gönderdi ; uyum: iki görüşmede de aynı hedeflerden söz ettiniz", "kaynak": "demo"},
    {"kisi": "umut-kurmaca", "alan": "rol", "deger": "Program Direktörü", "gerekce": "son e-postasının imzasında yazıyor", "kaynak": "demo"},
    {"kisi": "kerem-kurgun", "alan": "soru", "deger": "Hackathon jürisindeki rolü bu yıl da sürüyor mu?",
     "gerekce": "son kayıt 63 gün önce", "kaynak": "demo"},
]

BEN = {"ad": "Deniz Demo", "kurum": "Lodos Teknoloji", "rol": "Yazılım Geliştirici (stajyer)", "asistan": "Kut",
       "ilgiler": ["açık veri", "girişimcilik", "veri görselleştirme", "topluluk"], "karakter": "", "okul": "", "dersler": []}


def tarih_tr(n):
    return gun(n).strftime("%d.%m.%Y")


def uret(hedef):
    hedef = os.path.abspath(hedef)
    os.makedirs(hedef, exist_ok=True)
    c.veri_klasoru(hedef)
    c.ben_yaz({**BEN, "foto": c.foto_kaydet("ben", avatar(BEN["ad"], (212, 167, 44)))})
    for i, (ad, tur, kurum, rol, yak, alan, nereden, temaslar, ek) in enumerate(KISILER):
        kid = c.slug(ad)
        satirlar = [f"{tarih_tr(n)} · {kanal} · {metin}" for n, kanal, metin in sorted(temaslar, reverse=True)]
        alanlar = {"ad": ad, "tur": tur, "kurum": kurum, "rol": rol, "alan": alan, "nereden": nereden, "yakinlik": str(yak),
                   "foto": c.foto_kaydet(kid, avatar(ad, RENKLER[i % len(RENKLER)]))}
        if temaslar:
            alanlar["son_temas"] = gun(min(n for n, _, _ in temaslar)).isoformat()
        alanlar.update(ek)
        c.kisi_yaz(kid, alanlar, c.yeni_govde(ad, "kurgusal demo verisi", satirlar))
    c.iliskileri_yaz([{"a": a, "b": b, "tip": t, "not": n, "kaynak": "demo", "tarih": gun(30).isoformat()} for a, b, t, n in ILISKILER])
    c.cikarim_ekle(CIKARIMLAR)
    # hedefler
    h1 = hd.kaydet({"baslik": "Açık veri panosu için 3 mentor görüşmesi", "tur": "proje", "oncelik": "1", "son_tarih": gun(-45).isoformat(),
                    "olcut": "3 görüşme yapılmış; her birinden bir somut geri bildirim yazılmış",
                    "anahtar": "açık veri, veri görselleştirme, mentorluk",
                    "neden": "Staj projesini bitirme projesine çevirmek için dışarıdan göz lazım."}, kaynak="demo")
    hd.ilerleme_ekle(h1, "Aylin Hoca ile ilk görüşme yapıldı, kaynak listesi alındı", gun(48).isoformat())
    hd.ilerleme_ekle(h1, "Baran ile grafik kütüphaneleri karşılaştırıldı", gun(26).isoformat())
    h2 = hd.kaydet({"baslik": "Mavi Defter Hackathonu'nda ilk üçe girmek", "tur": "etkinlik", "oncelik": "2", "son_tarih": gun(-25).isoformat(),
                    "olcut": "Takım kuruldu, başvuru yapıldı, demo sunuldu", "anahtar": "hackathon, girişimcilik, topluluk",
                    "neden": "Pano fikrini kamuya açık bir sahnede sınamak."}, kaynak="demo")
    hd.ilerleme_ekle(h2, "Başvuru formu incelendi", gun(5).isoformat())
    # örnek strateji okuması (modele gitmeden, kurgusal içerik); ekran görüntüsü ve demo için
    j = {"tarih": datetime.now().isoformat(timespec="minutes"), "model": "demo (örnek içerik, model çağrısı yok)",
         "ozet": "Bu hafta iki hedef de aynı çevreden beslenebilir: Mavi Defter topluluğu hem hackathona hem de mentor görüşmelerine kapı açıyor. "
                 "En kritik nokta, Ece'nin başvuru takvimi: sonraki adım tarihi bir gün gecikmiş durumda.",
         "hedefler": [{"hedef": h1, "durum": "yolunda", "yorum": "İki görüşme tamam, üçüncüsü için aday var.",
                       "sonraki_kilometre_tasi": f"{gun(-10).isoformat()} öncesi Aslı ile kısa bir tanışma", "netlestir": ""},
                      {"hedef": h2, "durum": "riskte", "yorum": "Başvuru henüz gönderilmedi.",
                       "sonraki_kilometre_tasi": f"{gun(-7).isoformat()} öncesi başvuru", "netlestir": ""}],
         "hamleler": [
             {"hedef": h2, "tur": "ag", "baslik": "Zeynep üzerinden jüriye ulaş", "neden_simdi": "Başvuru kapanmadan jüri kriterlerini öğrenmek avantaj.",
              "gormedigin": "Zeynep ve Kerem aynı hackathon ekibinde; iki sonraki adımın tek bir mesajla çözülebilir.", "kim": "zeynep-ornekoglu",
              "kim_uzerinden": "", "ilk_adim": "Zeynep'e başvuru formunu ve jüri kriterlerini sor.", "son_tarih": gun(-2).isoformat(),
              "taslak": "Merhaba Zeynep, hackathon başvurusu için formun son halini paylaşabilir misin? Jüri kriterlerini de merak ediyorum.",
              "kanit": ["zeynep-ornekoglu: sonraki adım kaydı", "iliskiler.md: zeynep-ornekoglu birlikte-calisiyor kerem-kurgun"],
              "guven": "yuksek", "sonuc": "", "sonuc_not": ""},
             {"hedef": h1, "tur": "ag", "baslik": "Aslı ile açık veri sohbeti", "neden_simdi": "Seminerde ortak ilgi çıktı, bağ henüz taze.",
              "gormedigin": "Aslı, Baran'ın laboratuvar arkadaşı; üçüncü mentor görüşmesi için kısa yoldur.", "kim": "asli-ruyali",
              "kim_uzerinden": "baran-sanalioglu", "ilk_adim": "Aslı'ya panonun ekran görüntüsüyle kısa bir mesaj yaz.", "son_tarih": "",
              "taslak": "", "kanit": ["asli-ruyali: temas notu (seminer)", "iliskiler.md: asli-ruyali arkadas baran-sanalioglu"],
              "guven": "orta", "sonuc": "", "sonuc_not": ""}],
         "sorular": ["Mentor görüşmelerinden birini akademi dışından birine ayırmak ister misin?"]}
    st._yaz(j, f"{datetime.now():%Y-%m-%d-%H%M}.md")
    return hedef


def main():
    p = argparse.ArgumentParser(description="Kut için kurgusal demo verisi üretir.")
    p.add_argument("--hedef", help="Yazılacak klasör (varsayılan: geçici klasör)")
    a = p.parse_args()
    hedef = a.hedef or tempfile.mkdtemp(prefix="kut-demo-")
    print(uret(hedef))


if __name__ == "__main__":
    main()
