"""Takvim dışa aktarması (.ics ya da .zip içinde .ics: Google Takeout, Outlook, Apple) → kişi başına temas olayları.

Tamamen yerel (stdlib, RFC 5545): satır katlama, TZID/UTC/tüm gün, RRULE (yalnız geçmişteki tekrarlar, seri başına üst sınır), EXDATE/RDATE,
RECURRENCE-ID geçersiz kılmaları. İlke: içerik değil üst veri. Alınan: katılımcı (e-posta + ad), tarih, ayarlıysa kısaltılmış başlık.
ALINMAYAN: DESCRIPTION, LOCATION, ekler, toplantı bağlantıları. Başlık varsayılan KAPALI ("toplantı" yazılır): başlıklar sağlık, hukuk,
maaş gibi özel konuları taşıyabilir ve kişi dosyalarına düz Markdown olarak yazılır; açıksa hassas anahtar sözcüklü başlıklar yine "toplantı" olur.
Önizleme hiçbir şey yazmaz; yazım yalnız onayla (uygula). Ham dosya diske yazılmaz.
"""
import calendar
import hashlib
import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import ag_cekirdek as c
import ag_ice_aktar as ia
import ag_ice_ortak as ort
import ag_sir

BUYUK_ESIK = 15            # bu sayıdan çok katılımcılı toplantı yakınlık sinyali sayılmaz
TEKRAR_AZAMI = 60          # tek seride en çok bu kadar (en yeni) geçmiş tekrar
TEKRAR_DONGU_AZAMI = 30000  # genişletmede en çok bu kadar dönem (sonsuz döngü koruması)
TOPLAM_DONGU_AZAMI = 2_000_000  # dosya genelinde tüm serilerin toplam genişletme döngüsü; aşılınca kalan seriler tek başlangıç olayına iner
INTERVAL_AZAMI = 10_000    # RRULE INTERVAL üst sınırı (aşırı değerler tarih taşmasına yol açıyordu)
SATIR_AZAMI = 6_000_000    # dosyada işlenecek en çok fiziksel satır
SURE_AZAMI = 90.0          # önizlemede ayrıştırma + genişletme için en çok bu kadar saniye
OLAY_AZAMI = 200_000       # dosyada işlenecek en çok VEVENT
TEMAS_AZAMI = 120          # bir kişiye bu çalışmada en çok bu kadar (en yeni) satır yazılır
DOSYA_AZAMI = 60_000_000   # yüklenen ham dosya (sunucu da base64 gövdeyi ayrıca sınırlar)
BASLIK_AZAMI = 40
KANAL = "takvim"
GUNLER = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
# başlık açıkken bile "toplantı" yazılacak hassas konular (sade() metni üzerinde)
HASSAS = re.compile(r"\b(doktor|hastane|muayene|poliklinik|psikolog|psikiyatr\w*|terapi\w*|terapist|ameliyat|tahlil|saglik|tedavi|diyetisyen|"
                    r"avukat|mahkeme|dava|bosanma|noter|icra|soruşturma|sorusturma|ifade|maas|zam gorusmesi|kredi|borc|"
                    r"cenaze|taziye|dogum|gebelik|hamile\w*|therapy|therapist|doctor|clinic|lawyer|attorney|divorce|court|salary|medical)\b")
# ağdaki gerçek kişi olmayan adresler
KISI_DEGIL = re.compile(r"(@resource\.calendar\.google\.com|@group\.calendar\.google\.com|@import\.calendar\.google\.com|no-?reply|do-?not-?reply|"
                        r"calendar-notification|notifications?@)", re.I)


# ---------- RFC 5545 satırları ----------
def metin_coz(ham):
    for kodlama in ("utf-8-sig", "cp1254"):
        try:
            return ham.decode(kodlama)
        except UnicodeDecodeError:
            continue
    return ham.decode("latin-1", "replace")


class SureAsildi(ValueError):
    """Dosya, süre ya da satır bütçesini aştı (önizleme açıklayıcı bir hatayla biter)."""


class _Butce(Exception):
    """Dosya genelindeki RRULE döngü bütçesi bitti."""


def satirlari_ac(metin):
    """Katlanmış satırları (CRLF/LF + boşluk/tab) birleştirir. Devam parçaları listede toplanıp tek `join` ile birleşir (doğrusal süre);
    SATIR_AZAMI'dan çok satırlı dosya reddedilir."""
    satirlar, parca = [], None
    ham = metin.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(ham) > SATIR_AZAMI:
        raise SureAsildi("Takvim dosyası çok fazla satır içeriyor; bölüp yeniden dene.")
    for s in ham:
        if s[:1] in (" ", "\t") and parca is not None:
            parca.append(s[1:])
        elif s:
            if parca is not None:
                satirlar.append("".join(parca))
            parca = [s]
    if parca is not None:
        satirlar.append("".join(parca))
    return satirlar


def _tirnak_disi_bol(s, ayirac, bir_kez=False):
    parcalar, simdiki, tirnak = [], [], False
    for i, ch in enumerate(s):
        if ch == '"':
            tirnak = not tirnak
        if ch == ayirac and not tirnak:
            parcalar.append("".join(simdiki)); simdiki = []
            if bir_kez:
                parcalar.append(s[i + 1:])
                return parcalar
        else:
            simdiki.append(ch)
    parcalar.append("".join(simdiki))
    return parcalar


def ozellik_coz(satir):
    """'ATTENDEE;CN="Deneme, Ada";PARTSTAT=ACCEPTED:mailto:ada@ornek.test' → ('ATTENDEE', {'CN': 'Deneme, Ada', ...}, 'mailto:...')."""
    if ":" not in satir:
        return None
    bas, deger = _tirnak_disi_bol(satir, ":", bir_kez=True)
    adi, *params = _tirnak_disi_bol(bas, ";")
    p = {}
    for x in params:
        if "=" in x:
            a, v = x.split("=", 1)
            p[a.strip().upper()] = v.strip().strip('"')
    return adi.strip().upper(), p, deger


def metin_coz_kacis(v):
    return re.sub(r"\\([nN,;\\])", lambda m: " " if m.group(1) in "nN" else m.group(1), v or "")


def zaman_coz(deger, params):
    """(naive datetime | date, tum_gun). UTC ('Z') sistem saatine çevrilir; TZID/yüzen zaman duvar saati olarak kalır (yalnız tarih kullanılır)."""
    deger = (deger or "").strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", deger):
        return datetime.strptime(deger[:8], "%Y%m%d").date(), True
    m = re.fullmatch(r"(\d{8})T(\d{2})(\d{2})(\d{2})?(Z)?", deger, re.I)
    if not m:
        raise ValueError("tarih biçimi tanınmadı")
    d = datetime.strptime(m.group(1), "%Y%m%d").replace(hour=int(m.group(2)), minute=int(m.group(3)), second=int(m.group(4) or 0))
    if m.group(5):
        try:
            d = d.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            pass
    return d, False


def _tarih_kismi(z):
    return z.date() if isinstance(z, datetime) else z


def kural_coz(deger):
    k = {"freq": "", "interval": 1, "count": None, "until": None, "byday": [], "bymonthday": [], "bymonth": [], "bysetpos": [], "wkst": 0}
    for parca in (deger or "").split(";"):
        if "=" not in parca:
            continue
        a, v = parca.split("=", 1)
        a, v = a.strip().upper(), v.strip().upper()
        try:
            if a == "FREQ":
                k["freq"] = v
            elif a == "INTERVAL":
                k["interval"] = max(1, min(INTERVAL_AZAMI, int(v)))
            elif a == "COUNT":
                k["count"] = max(0, int(v))
            elif a == "UNTIL":
                k["until"] = _tarih_kismi(zaman_coz(v, {})[0])
            elif a == "BYDAY":
                for x in v.split(","):
                    m = re.fullmatch(r"([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)", x.strip())
                    if m:
                        k["byday"].append((int(m.group(1)) if m.group(1) else None, GUNLER[m.group(2)]))
            elif a in ("BYMONTHDAY", "BYMONTH", "BYSETPOS"):
                k[a.lower()] = [int(x) for x in v.split(",") if x.strip()]
            elif a == "WKST":
                k["wkst"] = GUNLER.get(v, 0)
        except ValueError:
            continue
    return k


def _ay_gunleri(yil, ay, k, varsayilan_gun):
    son = calendar.monthrange(yil, ay)[1]
    gunler = set()
    if k["bymonthday"]:
        for g in k["bymonthday"]:
            d = g if g > 0 else son + g + 1
            if 1 <= d <= son:
                gunler.add(d)
    if k["byday"]:
        kume = set()
        for sira, wd in k["byday"]:
            tum = [d for d in range(1, son + 1) if date(yil, ay, d).weekday() == wd]
            if sira is None:
                kume.update(tum)
            else:
                i = sira - 1 if sira > 0 else sira
                if -len(tum) <= i < len(tum):
                    kume.add(tum[i])
        gunler = (gunler & kume) if k["bymonthday"] else kume
    elif not k["bymonthday"] and varsayilan_gun <= son:
        gunler = {varsayilan_gun}
    gunler = sorted(gunler)
    if k["bysetpos"] and gunler:
        sec = []
        for p in k["bysetpos"]:
            i = p - 1 if p > 0 else p
            if -len(gunler) <= i < len(gunler):
                sec.append(gunler[i])
        gunler = sorted(set(sec))
    return [date(yil, ay, d) for d in gunler]


def tekrarlari_ac(bas, kural, bugun, butce=None):
    """Başlangıç tarihinden bugüne kadar olan tekrar tarihleri (artan). Gelecek tekrarlar üretilmez.
    butce: {"kalan": N} paylaşılan döngü bütçesi (dosya geneli); biterse `_Butce` fırlatır. Tarih taşması OverflowError/ValueError olarak çağırana çıkar."""
    f, aralik = kural["freq"], min(INTERVAL_AZAMI, max(1, kural["interval"]))

    def harca():
        if butce is not None:
            butce["kalan"] -= 1
            if butce["kalan"] < 0:
                raise _Butce()
    son = min(bugun, kural["until"]) if kural["until"] else bugun
    sonuc, say = [], 0

    def ekle(d):
        nonlocal say
        if d < bas or d > son:
            return d > son
        if kural["count"] is not None and say >= kural["count"]:
            return True
        say += 1
        sonuc.append(d)
        return False

    if kural["count"] == 0:
        return []
    if f == "DAILY":
        for i in range(TEKRAR_DONGU_AZAMI):
            harca()
            d = bas + timedelta(days=i * aralik)
            if d > son or (kural["count"] is not None and say >= kural["count"]):
                break
            if (not kural["byday"] or d.weekday() in {w for _, w in kural["byday"]}) and (not kural["bymonth"] or d.month in kural["bymonth"]):
                ekle(d)
    elif f == "WEEKLY":
        gunler = sorted({w for _, w in kural["byday"]} or {bas.weekday()}, key=lambda w: (w - kural["wkst"]) % 7)
        hafta0 = bas - timedelta(days=(bas.weekday() - kural["wkst"]) % 7)
        bitti = False
        for i in range(TEKRAR_DONGU_AZAMI):
            harca()
            hb = hafta0 + timedelta(days=7 * aralik * i)
            if hb > son:
                break
            for w in gunler:
                d = hb + timedelta(days=(w - kural["wkst"]) % 7)
                if not kural["bymonth"] or d.month in kural["bymonth"]:
                    if ekle(d):
                        bitti = True
                        break
            if bitti:
                break
    elif f in ("MONTHLY", "YEARLY"):
        bitti = False
        for i in range(TEKRAR_DONGU_AZAMI):
            harca()
            if f == "MONTHLY":
                ay_toplam = bas.year * 12 + bas.month - 1 + i * aralik
                donem = [(ay_toplam // 12, ay_toplam % 12 + 1)]
            else:
                yil = bas.year + i * aralik
                donem = [(yil, m) for m in sorted(kural["bymonth"] or [bas.month])]
            if donem[0][0] * 12 + donem[0][1] > son.year * 12 + son.month:
                break
            for yil, ay in donem:
                for d in _ay_gunleri(yil, ay, kural, bas.day):
                    if ekle(d):
                        bitti = True
                        break
                if bitti:
                    break
            if bitti:
                break
    else:
        return []   # SECONDLY/MINUTELY/HOURLY ve bilinmeyenler: tek başlangıç olayı yeter
    return sonuc


# ---------- VEVENT'ler ----------
def olaylari_oku(metin):
    """Ham VEVENT sözlükleri + takvim sahibi ipucu (X-WR-CALNAME). VALARM içi özellikler atlanır."""
    olaylar, ipuclari, o, derin = [], [], None, 0
    bitis = time.monotonic() + SURE_AZAMI
    for sira, satir in enumerate(satirlari_ac(metin)):
        if sira % 20000 == 0 and time.monotonic() > bitis:
            raise SureAsildi("Takvim dosyası okunurken süre sınırı aşıldı; dosyayı küçültüp yeniden dene.")
        ust = satir[:16].upper()
        if ust.startswith("BEGIN:VEVENT"):
            o, derin = {"ozellik": []}, 0
            continue
        if o is None:
            if satir.upper().startswith("X-WR-CALNAME"):
                p = ozellik_coz(satir)
                if p:
                    ipuclari.append(p[2])
            continue
        if ust.startswith("BEGIN:"):
            derin += 1
        elif ust.startswith("END:VEVENT") and derin == 0:
            olaylar.append(o)
            o = None
            if len(olaylar) >= OLAY_AZAMI:
                break
        elif ust.startswith("END:"):
            derin = max(0, derin - 1)
        elif derin == 0:
            p = ozellik_coz(satir)
            if p and p[0] in ("UID", "SUMMARY", "DTSTART", "STATUS", "RRULE", "EXDATE", "RDATE", "RECURRENCE-ID", "ATTENDEE", "ORGANIZER"):
                o["ozellik"].append(p)   # DESCRIPTION, LOCATION, URL, ATTACH vb. hiç okunmaz/saklanmaz
    return olaylar, ipuclari


def _kisi(adi, params, deger):
    eposta = ort.eposta_norm(deger if deger.lower().startswith("mailto:") else params.get("EMAIL", "")) or ort.eposta_norm(deger)
    ad = ort.temiz_ad(metin_coz_kacis(params.get("CN", "")))
    if ort.eposta_norm(ad):
        ad = ""
    return {"eposta": eposta, "ad": ad, "durum": params.get("PARTSTAT", "").upper(), "tur": params.get("CUTYPE", "").upper(),
            "organizer": adi == "ORGANIZER"}


def olay_coz(ham):
    """Ham VEVENT → {uid, baslik, durum, bas (date|datetime), tum_gun, rid, kural, exdate, rdate, kisiler}. Başlangıcı olmayan None."""
    o = {"uid": "", "baslik": "", "durum": "", "kural": None, "exdate": set(), "rdate": [], "rid": None, "kisiler": [], "bas": None, "tum_gun": False}
    for adi, p, v in ham["ozellik"]:
        try:
            if adi == "UID":
                o["uid"] = v.strip()
            elif adi == "SUMMARY":
                o["baslik"] = metin_coz_kacis(v)
            elif adi == "STATUS":
                o["durum"] = v.strip().upper()
            elif adi == "DTSTART":
                o["bas"], o["tum_gun"] = zaman_coz(v, p)
            elif adi == "RECURRENCE-ID":
                o["rid"] = _tarih_kismi(zaman_coz(v, p)[0])
            elif adi == "RRULE":
                o["kural"] = kural_coz(v)
            elif adi in ("EXDATE", "RDATE"):
                for x in v.split(","):
                    z = _tarih_kismi(zaman_coz(x.strip().split("/")[0], p)[0])
                    (o["exdate"].add(z) if adi == "EXDATE" else o["rdate"].append(z))
            elif adi in ("ATTENDEE", "ORGANIZER"):
                o["kisiler"].append(_kisi(adi, p, v))
        except ValueError:
            continue
    return o if o["bas"] is not None else None


def baslik_kisalt(b, azami=BASLIK_AZAMI):
    """Kısaltılmış başlık; hassas konu (sağlık, hukuk, maaş…) ya da boşsa 'toplantı'. Bağlantı, e-posta ve sırlar atılır."""
    b = re.sub(r"https?://\S+|www\.\S+", " ", b or "")
    b = ort.EPOSTA.sub(" ", b)
    b = " ".join(b.replace("|", "/").split()).strip(" -–·:/")
    if not b or HASSAS.search(c.sade(b)):
        return "toplantı"
    b = ag_sir.temizle(b, "takvim başlığı", entropi=False)
    if len(b) > azami:
        b = b[:azami].rsplit(" ", 1)[0].rstrip(" -–·:,/") + "…"
    return b or "toplantı"


def gecmis_mi(bas, tum_gun, simdi):
    return bas < simdi.date() if tum_gun else bas <= simdi


def olaylari_ac(ham_olaylar, simdi=None):
    """VEVENT'leri tekrarlarıyla genişletir. Dönen: ([{uid, tarih, baslik, kisiler}], istatistik). Yalnız geçmiş, iptal olmayan; (UID, tarih) tek."""
    simdi = simdi or datetime.now()
    bugun = simdi.date()
    olaylar = [o for o in (olay_coz(h) for h in ham_olaylar) if o]
    gecersiz = {(o["uid"], o["rid"]) for o in olaylar if o["rid"] and o["uid"]}   # geçersiz kılınan tekrar tarihleri
    sonuc, gorulen = [], set()
    ist = {"ham": len(ham_olaylar), "iptal": 0, "gelecek": 0, "tekrar_acilan": 0}

    def ekle(o, tarih, bas, tum_gun):
        if o["durum"] == "CANCELLED":
            ist["iptal"] += 1
            return
        if not gecmis_mi(bas, tum_gun, simdi):
            ist["gelecek"] += 1
            return
        anahtar = (o["uid"] or hashlib.sha1(f"{o['baslik']}{bas}{sorted(k['eposta'] for k in o['kisiler'])}".encode()).hexdigest(), tarih)
        if anahtar in gorulen:
            return
        gorulen.add(anahtar)
        sonuc.append({"uid": o["uid"], "tarih": tarih, "baslik": o["baslik"], "kisiler": o["kisiler"]})

    butce = {"kalan": TOPLAM_DONGU_AZAMI}   # dosya geneli RRULE döngü bütçesi
    ist["butce_asildi"] = ist["bozuk_seri"] = 0
    bitis = time.monotonic() + SURE_AZAMI
    for n, o in enumerate(olaylar):
        if n % 512 == 0 and time.monotonic() > bitis:
            raise SureAsildi("Takvim dosyası işlenirken süre sınırı aşıldı; dosyayı küçültüp yeniden dene.")
        bas = o["bas"]
        t0 = _tarih_kismi(bas)
        tarihler = None
        if o["kural"] and o["kural"]["freq"] and not o["rid"] and butce["kalan"] > 0:
            try:
                tarihler = tekrarlari_ac(t0, o["kural"], bugun, butce)
            except _Butce:
                ist["butce_asildi"] = 1   # bu seri ve kalanlar tek başlangıç olayına iner
            except (OverflowError, ValueError):
                ist["bozuk_seri"] += 1    # bozuk seri tek olay olarak kalır, içe aktarma düşmez
        elif o["kural"] and o["kural"]["freq"] and not o["rid"]:
            ist["butce_asildi"] = 1
        if tarihler is not None:
            tarihler = sorted(set(tarihler + [d for d in o["rdate"] if d <= bugun] + ([t0] if not tarihler else [])) - o["exdate"])
            tarihler = [d for d in tarihler if (o["uid"], d) not in gecersiz]
            ist["tekrar_acilan"] += max(0, len(tarihler) - 1)
            for d in tarihler[-TEKRAR_AZAMI:]:
                ekle(o, d, datetime.combine(d, bas.time()) if isinstance(bas, datetime) else d, o["tum_gun"])
        else:
            tarihler = [t0] + [d for d in o["rdate"] if not o["rid"]]
            for d in tarihler:
                if d in o["exdate"] and not o["rid"]:
                    continue
                ekle(o, d, datetime.combine(d, bas.time()) if isinstance(bas, datetime) else d, o["tum_gun"])
    return sonuc, ist


# ---------- içe aktarma ----------
def _dosyalardan_metin(dosya_adi, ham):
    if len(ham) > DOSYA_AZAMI:
        raise ValueError("takvim dosyası çok büyük")
    if ham[:2] == b"PK":
        metinler = [metin_coz(v) for _, v in ia.zip_icerik(ham, lambda a: a.lower().endswith(".ics"))]
        if not metinler:
            raise ValueError("ZIP içinde .ics dosyası bulunamadı")
        return metinler
    metin = metin_coz(ham)
    if "BEGIN:VCALENDAR" not in metin.upper():
        raise ValueError("Bu bir takvim (.ics) dosyası gibi görünmüyor")
    return [metin]


def _kimlik(k):
    return k["eposta"] or c.sade(k["ad"])


def _turetilmis_ad(eposta):
    """'ada.deneme@ornek.test' → 'Ada Deneme' (yalnız ayraçlı ve harf-only yerel kısımdan; tek parça tahmin edilmez)."""
    yerel = eposta.split("@")[0]
    parcalar = [p for p in re.split(r"[._-]+", yerel) if p]
    if len(parcalar) >= 2 and all(p.isalpha() and len(p) > 1 for p in parcalar):
        return " ".join(p.capitalize() for p in parcalar[:3])
    return ""


def ayarlar_baslik():
    return bool(ia.ayarlar().get("takvim_baslik", False))


def onizle(dosya_adi, ham, secenek=None):
    """Dosyayı çözümler ve ne olacağını gösterir; HİÇBİR ŞEY yazmaz. secenek: {baslik: bool, buyuk_dahil: bool, buyuk_esik: int, ben: [e-posta/ad]}.
    Dönen: özet + eşleşenler + yeni kişi önerileri + onay belirteci (token)."""
    secenek = secenek or {}
    baslik_ac = bool(secenek.get("baslik", ayarlar_baslik()))
    buyuk_dahil = bool(secenek.get("buyuk_dahil"))
    esik = max(3, min(500, int(secenek.get("buyuk_esik") or BUYUK_ESIK)))
    simdi = datetime.now()

    ham_olaylar, ipuclari = [], []
    for metin in _dosyalardan_metin(dosya_adi, ham):
        o, i = olaylari_oku(metin)
        ham_olaylar += o
        ipuclari += i
    olaylar, ist = olaylari_ac(ham_olaylar, simdi)
    # Ağır ayrıştırma bitti (kilitsiz); kişi dosyalarını okuyan kalan kısım yazımlarla yarışmasın diye okuma kilidi altında (kısa).
    with ort.okuma_kilidi():
        return _onizle_planla(dosya_adi, secenek, baslik_ac, buyuk_dahil, esik, ipuclari, olaylar, ist)


def _onizle_planla(dosya_adi, secenek, baslik_ac, buyuk_dahil, esik, ipuclari, olaylar, ist):
    # --- kendini tanı: ayar/profil + yazılan + takvim adı + her toplantıda görünen tek adres ---
    ben_ad, ben_eposta = ort.ben_kimligi([x for x in secenek.get("ben", []) if "@" not in str(x)], [x for x in secenek.get("ben", []) if "@" in str(x)])
    kayit_edilecek = {ort.eposta_norm(x) for x in secenek.get("ben", []) if ort.eposta_norm(x)}
    otomatik = {ort.eposta_norm(x) for x in ipuclari if ort.eposta_norm(x)}
    sayac, toplam = {}, 0
    for o in olaylar:
        anahtarlar = {_kimlik(k) for k in o["kisiler"] if _kimlik(k) and not KISI_DEGIL.search(k["eposta"]) and k["tur"] not in ("RESOURCE", "ROOM")}
        if len(anahtarlar) >= 2:
            toplam += 1
            for a in anahtarlar:
                sayac[a] = sayac.get(a, 0) + 1
    uyari = []
    if toplam >= 5 and not (ben_eposta or otomatik):   #kendi adresin bilinmiyorsa: her toplantıda görünen tek adres sensin
        sirali = sorted(((n, a) for a, n in sayac.items() if "@" in a and a not in ben_eposta), reverse=True)
        if sirali and sirali[0][0] >= 0.6 * toplam:
            if len(sirali) < 2 or sirali[1][0] <= 0.6 * sirali[0][0]:
                otomatik.add(sirali[0][1])
            else:
                uyari.append(f"Kendi adresini ayırt edemedim ({sirali[0][1]}, {sirali[1][1]} her toplantıda görünüyor): 'Takvimdeki adresin' alanına yaz.")
    ben_eposta |= otomatik   # bu içe aktarmada kendini tanımak için kullanılır; KALICI kaydı ayrı onaya bağlı (plan["ben_otomatik"], varsayılan: kaydetme)
    otomatik -= kayit_edilecek   # kullanıcının kendi yazdığı adres tahmin sayılmaz

    mevcut = c.kisileri_oku()
    dizin = ort.Dizin(mevcut)
    kimlikler = {}          # kimlik → {ad, eposta, olaylar: {(uid-ya-da-başlık, tarih): metin}}
    sayilan = buyuk = bensiz = 0
    for o in olaylar:
        kisiler = {}
        for k in o["kisiler"]:
            if k["tur"] in ("RESOURCE", "ROOM") or KISI_DEGIL.search(k["eposta"]) or not _kimlik(k):
                continue
            onceki = kisiler.get(_kimlik(k))
            if onceki:   # aynı kişi hem ORGANIZER hem ATTENDEE: durumu ve adı birleştir
                onceki["ad"] = onceki["ad"] or k["ad"]
                onceki["durum"] = k["durum"] or onceki["durum"]
            else:
                kisiler[_kimlik(k)] = dict(k)
        benler = [x for x in kisiler.values() if (x["eposta"] and x["eposta"] in ben_eposta) or (x["ad"] and c.sade(x["ad"]) in ben_ad)]
        if any(b["durum"] == "DECLINED" for b in benler):
            continue
        digerleri = [x for x in kisiler.values() if x not in benler and x["durum"] != "DECLINED"]
        if not digerleri:
            continue
        if len(kisiler) > esik and not buyuk_dahil:
            buyuk += 1
            continue
        if not benler:
            bensiz += 1
        sayilan += 1
        metin = baslik_kisalt(o["baslik"]) if baslik_ac else "toplantı"
        for x in digerleri:
            kimlikler.setdefault(_kimlik(x), {"ad": "", "eposta": "", "olaylar": {}})
            r = kimlikler[_kimlik(x)]
            r["ad"], r["eposta"] = r["ad"] or x["ad"], r["eposta"] or x["eposta"]
            r["olaylar"][(o["uid"] or o["baslik"], o["tarih"])] = metin

    # --- eşleştirme ---
    eslesen, yeni, eposta_oneri = {}, {}, {}
    belirsiz = 0
    for kim, r in kimlikler.items():
        kid, neden = dizin.bul(r["ad"], r["eposta"])
        if kid:
            h = eslesen.setdefault(kid, {})
            h.update(r["olaylar"])
            if neden == "ad" and r["eposta"]:
                k = next(x for x in mevcut if x["id"] == kid)
                if not ort.eposta_norm(k.get("eposta")):
                    eposta_oneri[kid] = r["eposta"]
        elif neden == "belirsiz":
            belirsiz += 1
        else:
            ad = r["ad"] or (_turetilmis_ad(r["eposta"]) if r["eposta"] else "")
            yeni[kim] = {"ad": ad or r["eposta"], "eposta": r["eposta"], "olaylar": r["olaylar"], "ad_turetildi": bool(not r["ad"] and ad)}

    def satirlar(olaylar_sozlugu):
        s = sorted(((d, m) for (_, d), m in olaylar_sozlugu.items()), key=lambda x: x[0])
        return s[-TEMAS_AZAMI:]

    plan = {"eslesen": {kid: [(d.isoformat(), m) for d, m in satirlar(o)] for kid, o in eslesen.items()},
            "yeni": {kim: {"ad": r["ad"], "eposta": r["eposta"], "olaylar": [(d.isoformat(), m) for d, m in satirlar(r["olaylar"])]} for kim, r in yeni.items()},
            "eposta_oneri": eposta_oneri, "ben_epostalari": sorted(kayit_edilecek), "ben_otomatik": sorted(otomatik), "baslik": baslik_ac}
    adlar = {k["id"]: k.get("ad") or k["id"] for k in mevcut}
    liste_eslesen = []
    for kid, satir in plan["eslesen"].items():
        yazilacak = ort.temas_satirlari_yaz(kid, [(date.fromisoformat(d), m) for d, m in satir], KANAL, yaz=False)
        liste_eslesen.append({"id": kid, "ad": adlar.get(kid, kid), "n": len(satir), "yazilacak": yazilacak, "son": satir[-1][0] if satir else ""})
    liste_eslesen.sort(key=lambda x: (-x["n"], x["ad"]))
    liste_yeni = []
    for kim, r in plan["yeni"].items():
        k_yeni = yeni[kim]
        liste_yeni.append({"k": kim, "ad": r["ad"], "eposta": r["eposta"], "n": len(r["olaylar"]), "ilk": r["olaylar"][0][0] if r["olaylar"] else "",
                           "son": r["olaylar"][-1][0] if r["olaylar"] else "", "ad_turetildi": k_yeni["ad_turetildi"]})
    liste_yeni.sort(key=lambda x: (-x["n"], x["ad"]))
    if belirsiz:
        uyari.append(f"{belirsiz} katılımcı birden çok kişiyle eşleşti (belirsiz); atlandı.")
    if bensiz:
        uyari.append(f"{bensiz} etkinlikte senin adresin katılımcılarda yoktu; yine de sayıldı.")
    if ist["ham"] >= OLAY_AZAMI:
        uyari.append(f"Dosya çok büyük: ilk {OLAY_AZAMI} etkinlik işlendi.")
    if ist.get("butce_asildi"):
        uyari.append("Çok sayıda tekrarlayan etkinlik var: toplam genişletme bütçesi aşıldı; kalan tekrarlı seriler yalnız ilk etkinliğiyle sayıldı.")
    if ist.get("bozuk_seri"):
        uyari.append(f"{ist['bozuk_seri']} tekrarlayan etkinliğin kuralı bozuktu; yalnız ilk etkinliği sayıldı.")
    token = ort.sakla("takvim", plan)
    return {"token": token, "dosya": dosya_adi,
            "ozet": {"etkinlik": sayilan, "ham_etkinlik": ist["ham"], "kisi_eslesen": len(liste_eslesen), "yeni_oneri": len(liste_yeni),
                     "temas_satiri": sum(x["yazilacak"] for x in liste_eslesen), "eposta_onerisi": len(eposta_oneri), "buyuk_atlanan": buyuk,
                     "buyuk_esik": esik, "iptal": ist["iptal"], "gelecek_atlanan": ist["gelecek"], "tekrar_acilan": ist["tekrar_acilan"], "baslik": baslik_ac},
            "eslesenler": liste_eslesen, "yeni": liste_yeni[:20000],
            "ben": {"eposta": sorted(ben_eposta), "otomatik": sorted(otomatik), "kaydet": False}, "uyari": uyari}


def uygula(token, secimler=None):
    """Onaylanan önizlemeyi yazar. secimler: {yeni: [{k, ad}], eslesen: bool (varsayılan true)}. Temas satırları idempotenttir;
    yeni kişiler yakınlık 0, tür 'cevre' (tahmin yok) ile eklenir; e-posta önerileri Doğrula'ya düşer."""
    plan = ort.al(token, "takvim")
    secimler = secimler or {}
    bugun = date.today()
    sonuc = {"eslesen": 0, "satir": 0, "yeni": [], "eposta_onerisi": 0, "atlanan": []}
    if secimler.get("eslesen", True):
        for kid, satir in plan["eslesen"].items():
            if not c.gecerli_id(kid) or not os.path.exists(os.path.join(c.KISILER, kid + ".md")):
                continue
            n = ort.temas_satirlari_yaz(kid, [(date.fromisoformat(d), m) for d, m in satir], KANAL, bugun)
            sonuc["satir"] += n
            sonuc["eslesen"] += 1 if n else 0
        oneriler = [{"kisi": kid, "alan": "eposta", "deger": e, "gerekce": "Takvimdeki katılımcı adı bu kişiyle eşleşti; kişide e-posta yok.",
                     "kaynak": "Kut · takvim içe aktarma"} for kid, e in plan["eposta_oneri"].items() if c.gecerli_id(kid)]
        if oneriler:
            sonuc["eposta_onerisi"] = c.cikarim_ekle(oneriler)
    dizin = ort.Dizin(c.kisileri_oku())
    for s in secimler.get("yeni") or []:
        r = plan["yeni"].get(str(s.get("k")))
        if not r:
            continue
        ham_ad = str(s.get("ad") or r["ad"])
        ad = "" if "@" in ham_ad else (ort.temiz_ad(ham_ad) or " ".join(ham_ad.split()))
        if not ad:
            sonuc["atlanan"].append(f"{r['eposta'] or r['ad']}: ad gerekli")
            continue
        olaylar = [(date.fromisoformat(d), m) for d, m in r["olaylar"]]
        kid, _ = dizin.bul(ad, r["eposta"])
        if kid:   # bu arada ağa girmiş (ör. aynı dosya ikinci kez): yeni dosya açma, satırları ekle
            sonuc["satir"] += ort.temas_satirlari_yaz(kid, olaylar, KANAL, bugun)
            continue
        kid = c.bos_slug(ad)
        satirlar = [f"{ort.tarih_tr(d)} · {KANAL} · {m}" for d, m in olaylar if d <= bugun]
        son = max((d for d, _ in olaylar if d <= bugun), default=None)
        alanlar = {"ad": ad, "foto": "", "tur": "cevre", "kurum": "", "rol": "", "alan": [], "nereden": ["takvim"], "yakinlik": "0",
                   "telefon": [], "eposta": r["eposta"], "son_temas": son.isoformat() if son else "", "sonraki_adim": ""}
        govde = c.yeni_govde(ad, f"takvim dışa aktarması ({ort.bugun_tr()}); yalnız katılımcı, tarih ve kısa başlık alındı, açıklama ve konum alınmadı.", satirlar)
        c.kisi_yaz(kid, alanlar, govde)
        sonuc["yeni"].append(kid)
        sonuc["satir"] += len(satirlar)
        dizin.ekle(kid, ad, r["eposta"])
    # Kullanıcının yazdığı adresler kaydedilir; takvimden TAHMİN edilen adres yalnız önizlemedeki ayrı kutu işaretliyse (secimler.ben_kaydet: true)
    ort.ben_epostasi_kaydet(list(plan["ben_epostalari"]) + (list(plan.get("ben_otomatik") or []) if secimler.get("ben_kaydet") is True else []))
    if "baslik" in secimler:
        a = ia.ayarlar()
        a["takvim_baslik"] = bool(secimler["baslik"])
        ia.ayar_yaz(a)
    return sonuc
