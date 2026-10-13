"""Söz takibi: kullanıcının bir kişiye verdiği ya da o kişiden aldığı söz ("Ayşe'ye kitabı göndereceğim", "Mehmet bana staj ilanını yollayacak").

Tek doğru kaynak kişi dosyasındaki `## Sözler` bölümü; her söz bir madde satırı:
  `- [ ] 2026-10-13 · ben → o · kitabı göndermek (son: 2026-10-17)`      açık (son tarih isteğe bağlı)
  `- [x] 2026-10-13 · o → ben · staj ilanı (son: 2026-10-20) (tamam: 2026-10-18)`   tamamlandı
  `- [-] 2026-10-13 · ben → o · kitap (iptal: 2026-10-15)`                iptal: satır silinmez, listelerde görünmez
`ben → o` = sen verdin ("verdiğin söz"), `o → ben` = o verdi ("aldığın söz"). Tarihler YYYY-AA-GG.

Yazan her işlev önce kişi dosyasının sürümünü arsiv/surum/'a kopyalar (`ag_cekirdek.surum_al`). Bu modül ağa ve modele çıkmaz; kişi dosyası
gövdesinin parçası olduğu için sözler uzak modele yalnız kişi kapısından (`ag_kapi`) geçen kopyada gider: `remote_allowed: false` ya da hariç
kişinin dosyası (dolayısıyla sözleri) hiç gitmez.

Doğal dil (`oner`): "Ayşe'ye kitabı cuma göndereceğim" gibi bir cümleden kişi, yön, metin ve son tarih YEREL ayrıştırılır (model yok). Hiçbir
şey yazmaz: belirsiz doğal dil cümlesi henüz kullanıcı beyanı sayılmaz, çağıran kullanıcıdan onay ister (ders girdisindeki kalıp, `ag_ders_girdi`).
Soru, olumsuz, geçmiş, koşullu ve varsayımlı cümleler öneri üretmez; kişi belirsizse (aynı ad iki kişide) de üretmez.
"""
import calendar
import os
import re
from datetime import date, timedelta

import ag_cekirdek as c

BASLIK = "Sözler"
YONLER = {"ben": "ben → o", "o": "o → ben"}
ETIKET = {"ben": "verdiğin söz", "o": "aldığın söz"}
ISARET = {"acik": " ", "tamam": "x", "iptal": "-"}
KAPANIS_AD = {"tamam": "tamam", "iptal": "iptal"}
METIN_AZAMI = 200
YAKLASAN_GUN = 7        # "Bu hafta": son tarihi en çok bu kadar gün kaldıysa (ya da geçtiyse) görünür
TARIHSIZ_UYARI_GUN = 21  # son tarihi olmayan söz bu kadar gündür açıksa hatırlatılır
ONERI_AZAMI = 3

SATIR = re.compile(r"^- \[( |x|X|-)\] (\d{4}-\d{2}-\d{2}) · (ben → o|o → ben|ben -> o|o -> ben) · (.*?)((?: \((?:son|tamam|iptal): \d{4}-\d{2}-\d{2}\))*)\s*$")
EK = re.compile(r"\((son|tamam|iptal): (\d{4}-\d{2}-\d{2})\)")


def _tarih(s):
    """Yalnız YYYY-AA-GG (`date.fromisoformat` 'YYYYMMDD' ve 'YYYY-Www-D' gibi biçimleri de kabul eder; burada reddedilir)."""
    s = str(s or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def metin_temizle(m):
    """Söz metni tek satır, '·' ve '(son: ...)' biçimini bozamaz, en çok METIN_AZAMI karakter."""
    m = " ".join(str(m or "").split()).replace("·", "-")
    m = re.sub(r"\((son|tamam|iptal):", r"(\1 -", m)
    return m[:METIN_AZAMI].strip()


def _icerik(s):
    """Sözün satır metni ('- ' öneki olmadan)."""
    ek = (f" (son: {s['son']})" if s.get("son") else "") + (f" ({KAPANIS_AD[s['durum']]}: {s['kapanis']})" if s.get("kapanis") else "")
    return f"[{ISARET[s['durum']]}] {s['tarih']} · {YONLER[s['yon']]} · {s['metin']}{ek}"


def _coz(satir):
    m = SATIR.match(satir.strip())
    if not m:
        return None
    isaret, tarih, yon, metin, ek = m.groups()
    s = {"durum": {" ": "acik", "x": "tamam", "X": "tamam", "-": "iptal"}[isaret], "tarih": tarih, "yon": "ben" if yon.startswith("ben") else "o",
         "metin": metin.strip(), "son": "", "kapanis": ""}
    for ad, t in EK.findall(ek):
        if ad == "son":
            s["son"] = t
        else:
            s["kapanis"] = t
    return s


def _sinir(satirlar):
    """'## Sözler' bölümünün (başlık satırı, bitiş) sınırı; bölüm yoksa None."""
    bas = next((i for i, l in enumerate(satirlar) if l.strip().lower() == f"## {BASLIK}".lower()), None)
    if bas is None:
        return None
    return bas, next((i for i in range(bas + 1, len(satirlar)) if satirlar[i].startswith("## ")), len(satirlar))


def oku(govde):
    """Gövdedeki sözler (sırayla). Biçimi tanınmayan satır atlanır (elle yazılmış serbest not olabilir). `sira` = tanınan sözler içindeki sıra."""
    satirlar = (govde or "").split("\n")
    sinir = _sinir(satirlar)
    sonuc = []
    for i in range(sinir[0] + 1, sinir[1]) if sinir else []:
        s = _coz(satirlar[i])
        if s:
            s["sira"] = len(sonuc)
            sonuc.append(s)
    return sonuc


def acik_sozler(govde):
    return [s for s in oku(govde) if s["durum"] == "acik"]


def gecikme(s, bugun=None):
    """Açık sözün son tarihine göre gün farkı: pozitif = gecikti, 0 = bugün, negatif = kaç gün kaldı. Kapalı ya da tarihsiz söz için None."""
    bugun = bugun or date.today()
    son = _tarih(s.get("son")) if s.get("durum") == "acik" else None
    return (bugun - son).days if son else None


def durum_yazisi(s, bugun=None):
    """'2 gün gecikti' / 'bugün' / '3 gün kaldı' / '25 gündür açık' (tarihsiz); gösterilecek bir şey yoksa ''."""
    bugun = bugun or date.today()
    g = gecikme(s, bugun)
    if g is not None:
        return f"{g} gün gecikti" if g > 0 else "bugün" if g == 0 else f"{-g} gün kaldı"
    ver = _tarih(s.get("tarih"))
    if s.get("durum") == "acik" and ver:
        return f"{(bugun - ver).days} gündür açık"
    return ""


def hatirlatmalar(kisiler, bugun=None):
    """'Bu hafta' için söz satırları: son tarihi geçmiş ya da YAKLASAN_GUN içinde olan açık sözler, ayrıca TARIHSIZ_UYARI_GUN'dür açık tarihsiz sözler.
    Hariç kişiler girmez. Dönen: [{id, neden, oncelik, tur: "soz", yon, sira}]; `oncelik` ('bu_hafta' ile aynı ölçek) gün farkıdır, gecikmiş olan başa gelir."""
    bugun = bugun or date.today()
    liste = []
    for k in kisiler:
        if k.get("haric"):
            continue
        for s in acik_sozler(k.get("govde") or ""):
            g = gecikme(s, bugun)
            if g is not None:
                if -g > YAKLASAN_GUN:
                    continue
                oncelik = -g
            else:
                ver = _tarih(s["tarih"])
                if not ver or (bugun - ver).days < TARIHSIZ_UYARI_GUN:
                    continue
                oncelik = YAKLASAN_GUN + 1
            liste.append({"id": k["id"], "neden": f"{ETIKET[s['yon']]}: {durum_yazisi(s, bugun)} · {s['metin'][:60]}", "oncelik": oncelik,
                          "tur": "soz", "yon": s["yon"], "sira": s["sira"]})
    return liste


def ozet_ekle(kisiler, bugun=None):
    """Arayüz için her kişiye `sozler` (okunmuş sözler + `yazi`/`gun`) ve açık söz sayısı ekler."""
    bugun = bugun or date.today()
    for k in kisiler:
        sozler = oku(k.get("govde") or "")
        for s in sozler:
            s["yazi"], s["gun"] = durum_yazisi(s, bugun), gecikme(s, bugun)
        k["sozler"] = sozler
        k["acik_soz"] = sum(1 for s in sozler if s["durum"] == "acik")


def sohbet_ozeti(govde):
    """Sohbet istemindeki kişi satırı için kısa açık söz özeti (yalnız kapıdan geçmiş, izinli kişi için çağrılır)."""
    return "; ".join(f"{YONLER[s['yon']]} {s['metin'][:50]}" + (f" (son {s['son']})" if s["son"] else "") for s in acik_sozler(govde)[:3])


# ---------- bölümü değiştiren saf işlevler (gövde → gövde) ----------
def ekle(govde, yon, metin, son="", bugun=None):
    """Gövdeye açık bir söz ekler (yeni gövdeyi döndürür). Aynı yön+metinle zaten açık söz varsa reddeder."""
    if yon not in YONLER:
        raise ValueError("yön 'ben' (sen verdin) ya da 'o' (o verdi) olmalı")
    metin = metin_temizle(metin)
    if not metin:
        raise ValueError("söz metni boş")
    son = _son_norm(son)
    if any(s["yon"] == yon and c.sade(s["metin"]) == c.sade(metin) for s in acik_sozler(govde)):
        raise ValueError("bu söz zaten açık")
    bugun = bugun or date.today()
    return c.bolume_ekle(govde, BASLIK, _icerik({"durum": "acik", "tarih": bugun.isoformat(), "yon": yon, "metin": metin, "son": son, "kapanis": ""}))


def _son_norm(son):
    """Son tarih her zaman ISO `YYYY-AA-GG` saklanır: boş → '', geçerli → normalize (kenar boşluğu atılır), geçersiz → ValueError."""
    son = str(son or "").strip()
    if not son:
        return ""
    t = _tarih(son)
    if not t:
        raise ValueError("son tarih YYYY-AA-GG olmalı")
    return t.isoformat()


def kapat(govde, sira, durum, metin=None, bugun=None):
    """sira'ncı açık sözü 'tamam' ya da 'iptal' yapar (satır silinmez; kapanış tarihi yazılır). `metin` verilirse satırın hâlâ o söz olduğu doğrulanır."""
    if durum not in KAPANIS_AD:
        raise ValueError("durum 'tamam' ya da 'iptal' olmalı")
    sozler = oku(govde)
    try:
        s = sozler[int(sira)]
    except (TypeError, ValueError, IndexError):
        raise ValueError("söz bulunamadı")
    if s["durum"] != "acik":
        raise ValueError("söz zaten kapatılmış")
    if metin is not None and c.sade(metin) != c.sade(s["metin"]):
        raise ValueError("söz değişmiş; sayfayı yenile")
    s.update(durum=durum, kapanis=(bugun or date.today()).isoformat())
    satirlar = govde.split("\n")
    bas, son = _sinir(satirlar)
    taninan = -1
    for i in range(bas + 1, son):
        if _coz(satirlar[i]):
            taninan += 1
            if taninan == s["sira"]:
                satirlar[i] = "- " + _icerik(s)
                break
    return "\n".join(satirlar)


# ---------- kişi dosyası işlemleri (yazım öncesi sürüm kopyası) ----------
def _degistir(kid, yeni_govde):
    yol = os.path.join(c.KISILER, f"{kid}.md")
    if not c.gecerli_id(kid) or not os.path.exists(yol):
        raise ValueError("kişi bulunamadı")
    k = c.kisi_oku(yol)
    govde = k.pop("govde")
    sonuc = yeni_govde(govde)
    c.surum_al(kid)
    c.kisi_yaz(kid, k, sonuc)


def kisi_ekle(kid, yon, metin, son="", bugun=None):
    _degistir(kid, lambda g: ekle(g, yon, metin, son, bugun))


def kisi_kapat(kid, sira, durum, metin=None, bugun=None):
    _degistir(kid, lambda g: kapat(g, sira, durum, metin, bugun))


# ---------- doğal dil: yerel ayrıştırma (model yok, yazma yok) ----------
AYLAR = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
GUNLER = {"pazartesi": 0, "sali": 1, "carsamba": 2, "persembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
SAYILAR = {"bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "onbes": 15, "yirmi": 20, "otuz": 30}
ISIM_EKI = {"ye", "ya", "e", "a", "na", "ne", "yi", "yu", "i", "u", "in", "nin", "un", "nun", "den", "dan", "ten", "tan", "le", "la", "yle", "yla", "ile", "ndan", "nden"}
AY_KALIP = "|".join(["ocak", "[sş]ubat", "mart", "nisan", "may[ıi]s", "haziran", "temmuz", "a[ğg]ustos", "eyl[üu]l", "ekim", "kas[ıi]m", "aral[ıi]k"])
TARIH_ISO = re.compile(r"(?<![\d.\-/])(\d{4})-(\d{2})-(\d{2})(?![\d])")
TARIH_NOKTA = re.compile(r"(?<![\d.\-/])(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?(?![\d./])")
TARIH_AYLI = re.compile(rf"(?<!\d)(\d{{1,2}})\s*({AY_KALIP})\w*(?:['’]\w+)?(?:\s+(\d{{4}}))?", re.I)
BAGLAC = {"ve", "ama", "fakat", "de", "da", "ki", "sonra", "ayrica", "bir de"}
# sade() jetonları üzerinde
SORU_JETON = re.compile(r"^(m[iu](?:yim|yum|yiz|yuz|sin|sun|siniz|sunuz|dir)?|nasil|ne|nedir|neden|niye|nerede|nere|kim|kimdir|hangi|kac|acaba)$")
SUPHE_JETON = {"keske", "eger", "belki", "bilmiyorum", "emin", "olursa", "olsa"}
OLUMSUZ_JETON = re.compile(r"^(?:\w+(?:m[iu]yor\w*|[mM]ayor\w*|meyor\w*|ma(?:yacak|yacag)\w*|me(?:yecek|yeceg)\w*|madi\w*|medi\w*|mamis\w*|memis\w*|mez|maz|mam|mem)|degil|asla|vazgec\w*|iptal\w*|yok|hic|hicbir)$")
GECMIS_JETON = {"dun", "gecen", "evvelki", "onceki", "gecmis", "demistim", "soylemistim", "dedim", "soyledim"}
# Yalnız AÇIK taahhüt fiili söz sayılır: kendi gelecek zaman 1. tekil kipin ("göndereceğim") ve karşı tarafın "bana ...-acak/-ecek" taahhüdü.
# Gereklilik ("-meli", "-mam gerek", "lazım"), olasılık ("-ebilirim"), geçmiş ("söz verdim") ve geniş zaman kendi başına söz değildir.
BEN_GELECEK = re.compile(r"^\w+(?:ecegim|acagim)$")
OBJE_GELECEK = re.compile(r"^\w+(?:ecek|acak)$")
OBJE_DISLA = {"gelecek", "onumuzdeki"}   # "gelecek hafta" bir tarih ifadesidir, taahhüt fiili değil


def _yonelme(ad):
    """'Ayşe' → "Ayşe'ye", 'Ali' → "Ali'ye", 'Selim' → "Selim'e" (basit ünlü uyumu; istisnalarda yanlış olabilir, yalnız soru metni)."""
    ad = ad.strip()
    sesli = next((ch for ch in reversed(ad.lower()) if ch in "aeıioöuü"), "e")
    kalin = sesli in "aıou"
    return f"{ad}'" + (("ya" if kalin else "ye") if ad[-1].lower() in "aeıioöuü" else ("a" if kalin else "e"))


def onay_sorusu(ad, yon, son=""):
    """Kullanıcıya gösterilecek onay sorusu: "Ayşe'ye söz olarak ekleyeyim mi? (son: 16.10)"."""
    ilk = (ad or "").split()[0] if (ad or "").strip() else "Kişi"
    ek = ""
    t = _tarih(son)
    if t:
        ek = f" (son: {t:%d.%m})"
    if yon == "o":
        return f"{ilk} sana verdiği söz olarak ekleyeyim mi?{ek}"
    return f"{_yonelme(ilk)} söz olarak ekleyeyim mi?{ek}"


def _jetonla(metin):
    return [(c.sade(m.group(0)), m.start(), m.end()) for m in re.finditer(r"[\wçğıöşüÇĞİÖŞÜâîû]+", metin)]


def _hafta_basi(g):
    return g - timedelta(days=g.weekday())


def _ay_ekle(g, n):
    ay = g.month - 1 + n
    yil, ay = g.year + ay // 12, ay % 12 + 1
    return date(yil, ay, min(g.day, calendar.monthrange(yil, ay)[1]))


def _gun_sonrasi(bugun, hedef, dahil=False):
    """bugünden sonraki (dahil=True: bugün de) ilk `hedef` haftagünü."""
    fark = (hedef - bugun.weekday()) % 7
    if fark == 0 and not dahil:
        fark = 7
    return bugun + timedelta(days=fark)


def _ay_no(ad):
    a = c.sade(ad)
    return next(no for ay, no in AYLAR.items() if a.startswith(ay[:4]))


def _acik_tarih(metin, bugun):
    """Metindeki açık tarih: 2026-10-17, 17.10(.2026), 17 Ekim (2026). (tarih | "gecmis" | None, karakter aralıkları)"""
    for kalip, coz in ((TARIH_ISO, lambda m: (int(m[1]), int(m[2]), int(m[3]))),
                       (TARIH_NOKTA, lambda m: (int(m[3]) if m[3] else None, int(m[2]), int(m[1]))),
                       (TARIH_AYLI, lambda m: (int(m[3]) if m[3] else None, _ay_no(m[2]), int(m[1])))):
        m = kalip.search(metin)
        if not m:
            continue
        yil, ay, gun = coz(m)
        try:
            if yil is None:
                t = date(bugun.year, ay, gun)
                if t < bugun:
                    t = date(bugun.year + 1, ay, gun)
            else:
                t = date(yil, ay, gun)
        except ValueError:
            continue
        return (t if t >= bugun else "gecmis"), [(m.start(), m.end())]
    return None, []


def _goreli_tarih(jetonlar, bugun):
    """Jetonlardaki göreli ifade (yarın, cuma, haftaya, ay sonu, 3 gün sonra...): (tarih | "gecmis" | None, kullanılan jeton indeksleri)."""
    w = [j[0] for j in jetonlar]
    n = len(w)
    for i, s in enumerate(w):
        onceki = w[i - 1] if i else ""
        sonraki = w[i + 1] if i + 1 < n else ""
        if s == "dun":
            return "gecmis", {i}
        if s == "bugun":
            return bugun, {i}
        if s in ("yarin", "yarina"):
            return bugun + timedelta(days=1), {i}
        if s == "obur" and sonraki == "gun":
            return bugun + timedelta(days=2), {i, i + 1}
        for ad, idx in sorted(GUNLER.items(), key=lambda x: -len(x[0])):
            if re.fullmatch(rf"{ad}(?:ya|ye|da|de|dan|den|nin|ndan|lari)?", s) and not (ad == "pazar" and s.startswith("pazart")):
                kul = {i} | ({i + 1} if sonraki in ("gunu", "gunune", "kadar") else set())
                if onceki == "haftaya":
                    return _hafta_basi(bugun) + timedelta(days=7 + idx), kul | {i - 1}
                return _gun_sonrasi(bugun, idx, dahil=onceki == "bu"), kul | ({i - 1} if onceki in ("bu", "gelecek", "onumuzdeki") else set())
        if s == "haftaya" and not any(re.fullmatch(rf"{ad}\w*", sonraki) for ad in GUNLER):
            return bugun + timedelta(days=7), {i}
        if s in ("gelecek", "onumuzdeki") and re.fullmatch(r"hafta\w*", sonraki):
            if i + 2 < n and w[i + 2].startswith("sonu"):   # "gelecek hafta sonu": gelecek haftanın pazarı
                return _hafta_basi(bugun) + timedelta(days=13), {i, i + 1, i + 2}
            return bugun + timedelta(days=7), {i, i + 1}
        if s.startswith("hafta") and (sonraki.startswith("sonu")):
            return _gun_sonrasi(bugun, 6, dahil=True), {i, i + 1} | ({i - 1} if onceki == "bu" else set())
        if s == "bu" and re.fullmatch(r"hafta\w*", sonraki) and not (i + 2 < n and w[i + 2].startswith("sonu")):
            return _gun_sonrasi(bugun, 6, dahil=True), {i, i + 1}
        if re.fullmatch(r"ay(?:in|a)?", s) and sonraki.startswith("sonu"):
            sonraki_ay = onceki in ("gelecek", "onumuzdeki")
            hedef = _ay_ekle(bugun.replace(day=1), 1 if sonraki_ay else 0)
            return hedef.replace(day=calendar.monthrange(hedef.year, hedef.month)[1]), {i, i + 1} | ({i - 1} if sonraki_ay or onceki == "bu" else set())
        if s in ("gelecek", "onumuzdeki") and re.fullmatch(r"ay\w*", sonraki) and not (i + 2 < n and w[i + 2].startswith("sonu")):   # "gelecek ay sonu" aşağıda (ayın son günü)
            return _ay_ekle(bugun, 1), {i, i + 1}
        if re.fullmatch(r"gun\w*|hafta\w*|ay\w*", s) and (onceki.isdigit() or onceki in SAYILAR) and i + 1 < n and sonraki in ("sonra", "icinde", "icerisinde"):
            adet = int(onceki) if onceki.isdigit() else SAYILAR[onceki]
            if adet < 1 or adet > 366:
                continue
            hedef = bugun + timedelta(days=adet) if s.startswith("gun") else bugun + timedelta(days=7 * adet) if s.startswith("hafta") else _ay_ekle(bugun, adet)
            return hedef, {i - 1, i, i + 1}
    return None, set()


def _kisi_adaylari(kisiler):
    """[(kid, ad, jeton dizisi)] tam ad, ilk ad (en az 3 harf) ve takma adlar; hariç kişi yok."""
    sonuc = []
    for k in kisiler:
        if k.get("haric") or c.haric_mi(k) or not k.get("id") or k.get("tur") == "ben":
            continue
        adlar = [k.get("ad") or ""] + [str(a) for a in c.liste_yap(k.get("aliases"))]
        ilk = c.sade(k.get("ad") or "").split()
        if ilk and len(ilk[0]) >= 3:
            adlar.append(ilk[0])
        for ad in adlar:
            j = tuple(c.sade(ad).split())
            if j and (len(j) > 1 or len(j[0]) >= 3):
                sonuc.append((k["id"], k.get("ad") or k["id"], j))
    return sonuc


def _kisi_bul(jetonlar, adaylar):
    """Cümledeki tek kişi: (kid, ad, [kullanılan jeton indeksleri]) ya da None (hiç yok / belirsiz / birden çok kişi)."""
    w = [j[0] for j in jetonlar]
    eslesen = []
    for kid, ad, j in adaylar:
        for i in range(len(w) - len(j) + 1):
            if tuple(w[i:i + len(j)]) == j:
                bitis = i + len(j)
                if bitis < len(w) and w[bitis] in ISIM_EKI:   # Ayşe'ye → ayse + ye
                    bitis += 1
                eslesen.append((kid, ad, i, bitis))
            elif len(j) == 1 and w[i].startswith(j[0]) and w[i][len(j[0]):] in ISIM_EKI:   # apostrofsuz: Ayşeye
                eslesen.append((kid, ad, i, i + 1))
    # daha uzun bir eşleşmenin içinde kalan kısa eşleşme düşer ("Ayşe Yılmaz" ilk ad "Ayşe"yi de kapsar); aynı aralığı paylaşan iki kişi ikisi de kalır (belirsiz)
    secilen = [e for e in eslesen if not any(f[2] <= e[2] and e[3] <= f[3] and (f[3] - f[2]) > (e[3] - e[2]) for f in eslesen)]
    kimler = {e[0] for e in secilen}
    if len(kimler) != 1:
        return None
    ilk = secilen[0]
    return ilk[0], ilk[1], sorted({i for e in secilen for i in range(e[2], e[3])})


def _yon_bul(w):
    """Cümlenin yönü: 'ben' (sen verdin), 'o' (o verdi) ya da None. Olumsuz/soru/şüphe/geçmiş işaretleri bu aşamadan önce elenmiş olmalı."""
    if any(BEN_GELECEK.match(s) for s in w):
        return "ben"
    if "bana" in w and any(OBJE_GELECEK.match(s) and s not in OBJE_DISLA for s in w):
        return "o"
    return None


def _reddet(w):
    """Cümleyi öneriden eleyen işaret var mı: soru, şüphe/koşul, olumsuzluk, geçmiş."""
    for i, s in enumerate(w):
        if SORU_JETON.match(s) or s in SUPHE_JETON or s in GECMIS_JETON:
            return True
        if OLUMSUZ_JETON.match(s):
            return True
    return False


def _cumleler(metin):
    """[(cümle metni, soru işaretiyle mi bitti)]; '17.10' gibi rakam arası noktada bölmez."""
    return [(m.group(1), "?" in m.group(2)) for m in re.finditer(r"((?:[^.!?;\n]|\.(?=\S))+)([.!?;]*)", metin)]


def _metin_cikar(ham, sil):
    """Cümle parçasından kişi/tarih/"bana" aralıklarını silip söz metnini bırakır ("kitabı göndereceğim")."""
    kalan = list(ham)
    for a, b in sorted(sil):
        for j in range(a - 1 if a and ham[a - 1] in "'’" else a, b):   # ek ayıran kesme işareti de gider
            kalan[j] = " "
    parcalar = " ".join("".join(kalan).split()).split()
    while parcalar and c.sade(parcalar[0]) in BAGLAC | {"kadar", "gunu"}:
        parcalar.pop(0)
    while parcalar and c.sade(parcalar[-1]) in BAGLAC | {"kadar", "gunu"}:
        parcalar.pop()
    return metin_temizle(" ".join(parcalar).strip(" .,:;-"))


def oner(metin, kisiler, bugun=None):
    """Sohbet cümlesinden söz önerileri (en çok ONERI_AZAMI): [{kisi, ad, yon, metin, son, soru}]. HİÇBİR ŞEY yazmaz.
    kisiler: `ag_cekirdek.kisileri_oku()` çıktısı. Soru, olumsuz, geçmiş, koşullu cümle ve belirsiz/çoklu kişi öneri üretmez.
    Her virgülle ayrılmış parça ayrı değerlendirilir; tarih parçada yoksa, kişisiz ve fiilsiz bir kardeş parçadan ("..., cuma.") alınır."""
    bugun = bugun or date.today()
    metin = " ".join(str(metin or "").split())[:2000]
    adaylar = _kisi_adaylari(kisiler)
    if not metin or not adaylar:
        return []
    sonuc = []
    for cumle, soruldu in _cumleler(metin):
        if soruldu:
            continue
        parcalar = []
        for m in re.finditer(r"[^,]+", cumle):
            ham = m.group(0)
            jetonlar = _jetonla(ham)
            parcalar.append({"ham": ham, "jeton": jetonlar, "w": [j[0] for j in jetonlar]})
        for p in parcalar:
            p["kisi"] = _kisi_bul(p["jeton"], adaylar)
            digeri = [s for i, s in enumerate(p["w"]) if not p["kisi"] or i not in p["kisi"][2]]   # kişi adı ("Yılmaz") olumsuzluk eki sayılmaz
            p["yon"] = None if _reddet(digeri) else _yon_bul(p["w"])
            p["tarih"], p["kullan"] = _goreli_tarih(p["jeton"], bugun)
            p["acik"], p["aralik"] = _acik_tarih(p["ham"], bugun)
        yetim = next((p["tarih"] or p["acik"] for p in parcalar if not p["yon"] and not p["kisi"] and (p["tarih"] or p["acik"])), None)
        for p in parcalar:
            if len(p["w"]) < 3 or not p["yon"] or not p["kisi"]:
                continue
            kid, ad, kisi_jeton = p["kisi"]
            tarih = p["tarih"] or p["acik"] or yetim
            if tarih == "gecmis":
                continue
            jt = p["jeton"]
            kullan = set(p["kullan"]) | {i + 1 for i in p["kullan"] if i + 1 < len(jt) and p["w"][i + 1] == "kadar"}
            sil = [(jt[i][1], jt[i][2]) for i in set(kisi_jeton) | kullan] + p["aralik"]
            sil += [(jt[i][1], jt[i][2]) for i, s in enumerate(p["w"]) if s == "bana"]
            for a, b in p["aralik"]:   # "17 Ekim'e kadar": açık tarihten hemen sonraki "kadar" da gider
                k = re.match(r"\s*kadar\b", p["ham"][b:], re.I)
                sil += [(b, b + k.end())] if k else []
            o = _metin_cikar(p["ham"], sil)
            if len(o) < 3 or any(x["kisi"] == kid and x["yon"] == p["yon"] and c.sade(x["metin"]) == c.sade(o) for x in sonuc):
                continue
            son = tarih.isoformat() if tarih else ""
            sonuc.append({"kisi": kid, "ad": ad, "yon": p["yon"], "metin": o, "son": son, "soru": onay_sorusu(ad, p["yon"], son)})
            if len(sonuc) >= ONERI_AZAMI:
                return sonuc
    return sonuc


def oneri_dogrula(o, kisiler):
    """Modelin ya da istemcinin getirdiği öneriyi (sözlük) biçim olarak doğrular ve temizler; geçersizse None. Kişi ağda olmalı, hariç olmamalı."""
    if not isinstance(o, dict):
        return None
    kid, yon = o.get("kisi"), o.get("yon")
    k = next((x for x in kisiler if x.get("id") == kid), None)
    metin = metin_temizle(o.get("metin"))
    try:
        son = _son_norm(o.get("son") or o.get("tarih"))
    except ValueError:
        return None
    if not k or yon not in YONLER or len(metin) < 3 or c.haric_mi(k):
        return None
    ad = k.get("ad") or kid
    return {"kisi": kid, "ad": ad, "yon": yon, "metin": metin, "son": son, "soru": onay_sorusu(ad, yon, son)}
