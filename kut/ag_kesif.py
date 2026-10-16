"""Kut keşfi: ağında olmayan ama hedeflerine yarayabilecek kişi ve etkinlikleri herkese açık kaynaklardan bulur.

Bulunanlar ağa girmez; "Keşfet"te aday olarak durur, kullanıcı karar verir (ilgileniyorum → ağa ekle / takvime; ilgilenmiyorum → bir daha
önerilmez). Kararlar <veri>/kesif.md'de (Markdown, kullanıcı verisi); çekilen ham kaynak önbelleği %LOCALAPPDATA%\\agim\\kesif\\.
Kaynaklar:
- Vekiller: Vekilpedia açık verisi (CC BY 4.0, TBMM kayıtlarından): milletvekilleri, soru önergeleri, kanun teklifleri, konuşmalar.
  Her vekilin son 2 yıldaki önerge/teklif/konuşma konuları hedeflerin anahtar kelimeleriyle eşleşir; kanıt satırları numarasıyla gelir.
- Etkinlikler: sayfalara gömülü schema.org Event verisi (Coderspace, Luma, Eventbrite), Devpost JSON, profildeki okulun etkinlik listesi (ag_kaynak.OKULLAR, varsa).
  robots.txt izin vermeyen adres okunmaz; giriş isteyen ya da bot korumalı siteler kullanılmaz. Liste ayarlar.json → kesif.etkinlik_kaynaklari.
Hariç listesi (haric.md) her öneriye uygulanır. Model kullanılmaz; seçim ve gerekçe strateji okumasında (ag_strateji.py).
"""
import csv
import hashlib
import html as htmlmod
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timedelta

import ag_cekirdek as c
import ag_hedef as hd
import ag_ice_aktar as ia

KLASOR = os.path.join(ia.DEPO, "kesif")
TARAYICI = "Mozilla/5.0 (compatible; Kut/1; yerel kisisel ag araci)"
VEKILPEDIA = "https://vekilpedia.com/veri/{}.csv"
VEKIL_DOSYALAR = ("milletvekilleri", "soru-onergeleri", "kanun-teklifleri", "konusmalar")
VEKIL_YENILE_GUN = 7
ETKINLIK_YENILE_SAAT = 12
VARSAYILAN_ETKINLIK = [
    {"ad": "Coderspace", "url": "https://coderspace.io/etkinlikler"},
    {"ad": "Luma İstanbul", "url": "https://lu.ma/istanbul"},
    {"ad": "Eventbrite İstanbul · iş", "url": "https://www.eventbrite.com/d/turkey--istanbul/business--events/"},
    {"ad": "Eventbrite İstanbul · teknoloji", "url": "https://www.eventbrite.com/d/turkey--istanbul/science-and-tech--events/"},
    {"ad": "Devpost (çevrim içi hackathon)", "url": "https://devpost.com/api/hackathons?status[]=upcoming&status[]=open", "tur": "devpost"},
]
_durum = {"calisiyor": False, "son": "", "hata": "", "mesaj": ""}
_kilit = threading.Lock()


# ---------- ortak ----------
def _istek(url, zaman=30, azami=40_000_000):
    import ag_kaynak as k   # SSRF korumalı ortak yardımcılar (özel ağ reddi, yönlendirme denetimi)
    try:
        k._guvenli_url(url)
    except ValueError as e:
        raise OSError("adres reddedildi: " + str(e))
    r = k.guvenli_acici().open(urllib.request.Request(url, headers={"User-Agent": TARAYICI, "Accept-Language": "tr,en"}), timeout=zaman)
    with r:
        return k.sinirli_oku(r, azami)


_robots = {}
ROBOT_AJANI = "Kut"            # robots.txt'te sorgulanan ürün adı; User-Agent'taki ürün belirteciyle AYNI olmalı (TARAYICI içindeki Kut/1)
ROBOTS_UZUN_SAAT = 24          # kesin cevaplar (var / 404 / 410 / 401 / 403) bu süre önbellekte kalır
ROBOTS_KISA_DAKIKA = 10        # geçici hatalar (5xx, zaman aşımı, SSRF reddi, ağ) kısa süre "yasak" sayılır, sonra yeniden denenir


def _robots_getir(kok):
    """robots.txt kararı: RobotFileParser | True (her şeye izin) | False (hiçbirine izin yok), ve geçerlilik saniyesi.
    404/410: dosya yok → serbest (RFC 9309'daki 'bulunamadı'). 401/403: erişim kısıtlı → yasak (kullanıcı kararı: sitenin kapısı kapalıysa girme).
    5xx, zaman aşımı, SSRF reddi, diğer ağ hataları: belirsiz → geçici yasak, kısa süre sonra yeniden sorulur (hata 'izin' demek değildir)."""
    try:
        govde = _istek(kok + "/robots.txt", 15, 500_000)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return True, ROBOTS_UZUN_SAAT * 3600
        if e.code in (401, 403):
            return False, ROBOTS_UZUN_SAAT * 3600
        return False, ROBOTS_KISA_DAKIKA * 60
    except Exception:   # zaman aşımı, SSRF reddi (OSError), bağlantı hatası
        return False, ROBOTS_KISA_DAKIKA * 60
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(govde.decode("utf-8", "replace").splitlines())
    return rp, ROBOTS_UZUN_SAAT * 3600


def robots_izin(url):
    kok = "/".join(url.split("/")[:3])
    simdi = time.time()
    kayit = _robots.get(kok)
    if kayit is None or kayit[1] <= simdi:
        karar, sure = _robots_getir(kok)
        kayit = _robots[kok] = (karar, simdi + sure)
    karar = kayit[0]
    if isinstance(karar, bool):
        return karar
    return karar.can_fetch(ROBOT_AJANI, url)


def kelimeler(metin):
    return re.findall(r"[a-z0-9]+", c.sade(metin))


KISA_EK = r"(?:yu|yun|ya|yla|da|dan|de|den|lar|ler|lari|leri|larin|lerin|in|un|i|u)?"


def _anahtar_kalip(anahtarlar):
    """Hedef anahtar kelimelerinden (sade metin üzerinde) kelime eşleşmesi. Türkçe ekler: 4+ harfte kelime + ek ('yatirimci' →
    yatırımcılar; 'yatırım' yatırımcıyı da tutar, bu yüzden genel kelime seçme); sonu k/p/t/ç ise yumuşama için son harf düşer
    ('kuraklik' → kuraklığı); 1–3 harfte ('su') yalnız yaygın ekler (suyu, sular; 'suç' değil)."""
    parcalar = []
    for a in anahtarlar:
        k = kelimeler(a)
        if not k:
            continue
        son = k[-1]
        if len(son) >= 4:
            kok = re.escape(son[:-1] if len(son) >= 5 and son[-1] in "kptc" else son) + r"[a-z]*"
        else:
            kok = re.escape(son) + KISA_EK
        on = "".join(re.escape(x) + r"\s+" for x in k[:-1])
        parcalar.append(r"\b" + on + kok + r"\b")
    return re.compile("|".join(parcalar)) if parcalar else None


def kararlar():
    """<veri>/kesif.md: | anahtar | karar | tarih | not |  (karar: ilgileniyorum | ilgilenmiyorum | katilacagim)"""
    yol = os.path.join(c.VERI, "kesif.md")
    sonuc = {}
    if os.path.exists(yol):
        for satir in open(yol, encoding="utf-8"):
            p = [x.strip() for x in satir.strip().strip("|").split("|")]
            if len(p) >= 3 and p[0] not in ("anahtar", "---") and not p[0].startswith("-"):
                sonuc[p[0]] = {"karar": p[1], "tarih": p[2], "not": p[3] if len(p) > 3 else ""}
    return sonuc


def karar_yaz(anahtar, karar, not_=""):
    if karar not in ("ilgileniyorum", "ilgilenmiyorum", "katilacagim", "sil"):
        raise ValueError("bilinmeyen karar")
    if not re.fullmatch(r"(vekil|etkinlik):[\w.-]{1,80}", anahtar or ""):
        raise ValueError("geçersiz aday")
    k = kararlar()
    if karar == "sil":
        k.pop(anahtar, None)
    else:
        k[anahtar] = {"karar": karar, "tarih": date.today().isoformat(), "not": " ".join(str(not_).split())[:200].replace("|", "/")}
    with open(os.path.join(c.VERI, "kesif.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Keşif kararları\n\nKut'un keşif önerilerine verdiğin kararlar. İlgilenmediklerin bir daha önerilmez.\n\n"
                "| anahtar | karar | tarih | not |\n|---|---|---|---|\n")
        for a, v in sorted(k.items()):
            f.write(f"| {a} | {v['karar']} | {v['tarih']} | {v.get('not', '')} |\n")


# ---------- vekiller ----------
def vekil_klasoru():
    """Önce Kut'un kendi önbelleği; yoksa kasadaki vekil-agi verisi (ayar: kesif.vekilpedia_klasoru)."""
    ayar = (ia.ayarlar().get("kesif") or {}).get("vekilpedia_klasoru")
    if ayar and os.path.isdir(ayar):
        return ayar
    kendi = os.path.join(KLASOR, "vekilpedia")
    if os.path.exists(os.path.join(kendi, "milletvekilleri.csv")):
        return kendi
    d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _ in range(3):
        aday = os.path.join(d, "vekil-agi", "veri")
        if os.path.exists(os.path.join(aday, "milletvekilleri.csv")):
            return aday
        d = os.path.dirname(d)
    return kendi


def vekilpedia_acik():
    """Vekilpedia indirmesi açık mı? Ayar `kesif.vekilpedia` (true/false). Ayar yoksa: önceden indirilmiş CSV varsa açık
    (eski kurulum özelliği kaybetmesin), yoksa kapalı (yeni kurulum açılışta ağa çıkmaz)."""
    ayar = (ia.ayarlar().get("kesif") or {}).get("vekilpedia")
    if isinstance(ayar, bool):
        return ayar
    try:
        return any(a.lower().endswith(".csv") for a in os.listdir(os.path.join(KLASOR, "vekilpedia")))
    except OSError:
        return False


def vekilpedia_ayarla(acik):
    a = ia.ayarlar()
    k = a.get("kesif") if isinstance(a.get("kesif"), dict) else {}
    k["vekilpedia"] = bool(acik)
    a["kesif"] = k
    ia.ayar_yaz(a)


def etkinlik_acik():
    """Etkinlik taraması açık mı? Ayar `kesif.etkinlik` (true/false). Ayar yoksa: bu kurulum daha önce etkinlik verisi çekmişse
    (kesif/etkinlikler.json var) açık, yoksa kapalı (yeni kurulum açılışta ağa çıkmaz)."""
    ayar = (ia.ayarlar().get("kesif") or {}).get("etkinlik")
    if isinstance(ayar, bool):
        return ayar
    return os.path.exists(os.path.join(KLASOR, "etkinlikler.json"))


def kaynak_ayarla(kimlik, acik):
    """İsteğe bağlı dış kaynağı aç/kapat (ayarlar.json → kesif.<kimlik>)."""
    if kimlik not in KAYNAK_AYARLARI:
        raise ValueError("bilinmeyen kaynak")
    a = ia.ayarlar()
    k = a.get("kesif") if isinstance(a.get("kesif"), dict) else {}
    k[kimlik] = bool(acik)
    a["kesif"] = k
    ia.ayar_yaz(a)


# Kaynaklar paneli kayıtları. Yeni bir dış kaynak = buraya bir kayıt + `kesif.<kimlik>` kapısı; okullar ag_kaynak.OKULLAR'dan gelir.
KAYNAK_AYARLARI = {
    "vekilpedia": {"ad": "TBMM / Vekilpedia", "acik": lambda: vekilpedia_acik(), "dosya": lambda: os.path.join(KLASOR, "vekilpedia", "milletvekilleri.csv"),
                   "aciklama": "Milletvekilleri, soru önergeleri ve kanun teklifleri; hedeflerine uyan vekilleri önerir.",
                   "indirir": "Vekilpedia CSV dosyaları (CC BY 4.0, TBMM kayıtları), haftada bir", "nereden": "vekilpedia.com"},
    "etkinlik": {"ad": "Etkinlikler", "acik": lambda: etkinlik_acik(), "dosya": lambda: os.path.join(KLASOR, "etkinlikler.json"),
                 "aciklama": "Yaklaşan etkinlikler; hedeflerinle eşleşenler Pusula'da üstte çıkar.",
                 "indirir": "Herkese açık etkinlik sayfaları (robots.txt izinli), 12 saatte bir; seçili okulun etkinlik sayfası da varsa",
                 "nereden": "coderspace.io, lu.ma, eventbrite.com, devpost.com"},
    "akademik": {"ad": "Akademik profiller", "acik": lambda: __import__("ag_akademik").acik(), "dosya": lambda: __import__("ag_kaynak").DURUM,
                 "aciklama": "Okulundan eklenen hocaların kurumu, yayın sayısı ve çalışma alanları; hepsi Doğrula'ya öneri olarak düşer.",
                 "indirir": "Yalnız hocanın adı sorulur; sonuç kişi dosyasına doğrudan yazılmaz. Okul bağdaştırıcısı seçiliyken, kaynaktan doldurma sırasında",
                 "nereden": "api.openalex.org, pub.orcid.org"},
}


def kaynaklar_durum():
    """Kaynaklar paneli: her isteğe bağlı dış kaynak (açık mı, son indirme) ve okul bağdaştırıcıları (OKULLAR'dan, seçili olan)."""
    k = __import__("ag_kaynak")
    liste = []
    for kimlik, r in KAYNAK_AYARLARI.items():
        try:
            son = datetime.fromtimestamp(os.path.getmtime(r["dosya"]())).isoformat(timespec="minutes")
        except OSError:
            son = ""
        liste.append({"id": kimlik, "ad": r["ad"], "aciklama": r["aciklama"], "indirir": r["indirir"], "nereden": r["nereden"], "acik": r["acik"](), "son": son})
    secili = c.sade(c.ben().get("okul") or "")
    okullar = [{"anahtar": a, "ad": o["ad"], "ders_kaynak": o.get("ders_kaynak", ""), "etkinlik_url": o.get("etkinlik_url", ""), "secili": a == secili}
               for a, o in k.OKULLAR.items()]
    return {"kaynaklar": liste, "okullar": okullar, "okul": secili if secili in k.OKULLAR else "", "calisiyor": _durum["calisiyor"]}


def vekil_verisi_yenile(zorla=False):
    """Vekilpedia CSV'lerini haftada bir Kut önbelleğine indirir (herkese açık, CC BY 4.0). Ayar kapalıysa hiçbir şey yapmaz."""
    if not vekilpedia_acik():
        return False
    hedef = os.path.join(KLASOR, "vekilpedia")
    os.makedirs(hedef, exist_ok=True)
    ilk = os.path.join(hedef, "milletvekilleri.csv")
    if not zorla and os.path.exists(ilk) and time.time() - os.path.getmtime(ilk) < VEKIL_YENILE_GUN * 86400:
        return False
    for ad in VEKIL_DOSYALAR:
        url = VEKILPEDIA.format(ad)
        if not robots_izin(url):
            raise RuntimeError(f"robots.txt {url} okumaya izin vermiyor")
        ham = _istek(url, 120)
        if not ham.lstrip(b"\xef\xbb\xbf").startswith((b"ad,", b"esas_no", b"tarih", b"\"")) or len(ham) < 1000:
            raise RuntimeError(f"{ad}.csv beklenen biçimde değil")
        with open(os.path.join(hedef, ad + ".csv.yeni"), "wb") as f:
            f.write(ham)
    for ad in VEKIL_DOSYALAR:
        os.replace(os.path.join(hedef, ad + ".csv.yeni"), os.path.join(hedef, ad + ".csv"))
    return True


def _csv(ad):
    with open(os.path.join(vekil_klasoru(), ad + ".csv"), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


_vekil_onbellek = {"anahtar": None, "veri": None, "hazirlaniyor": False}
BILGI_ALANLARI = ("ad", "il", "parti", "meslek", "tbmm_gorev", "x_hesap", "tbmm_adresi", "vekilpedia_adresi")


def _vekil_imza():
    kl = vekil_klasoru()
    return [kl, [os.path.getmtime(os.path.join(kl, a + ".csv")) for a in VEKIL_DOSYALAR if os.path.exists(os.path.join(kl, a + ".csv"))], date.today().isoformat()[:7]]


def _vekil_kayitlari():
    """{vekil adı: {bilgi, n_gorev, kayitlar: [(tur, tarih, metin, no, durum, url, muhatap, sade_metin)]}} son 2 yıl.
    CSV'ler (75 MB) bir kez işlenir; sonuç bellekte ve %LOCALAPPDATA%\\agim\\kesif\\vekil-dizin.json'da (dosyalar ya da ay değişince yenilenir)."""
    imza = _vekil_imza()
    if _vekil_onbellek["anahtar"] == imza and _vekil_onbellek["veri"]:
        return _vekil_onbellek["veri"]
    dizin = os.path.join(KLASOR, "vekil-dizin.json")
    try:
        d = json.load(open(dizin, encoding="utf-8"))
        if d.get("imza") == imza:
            _vekil_onbellek.update(anahtar=imza, veri=d["veri"])
            return d["veri"]
    except (OSError, ValueError):
        pass
    sinir = (date.today() - timedelta(days=730)).isoformat()
    sade = lambda s: " " + " ".join(kelimeler(s)) + " "
    v = {r["ad"]: {"bilgi": {a: r.get(a) or "" for a in BILGI_ALANLARI}, "n_gorev": sade(r.get("tbmm_gorev") or ""), "kayitlar": []}
         for r in _csv("milletvekilleri") if (r.get("aktif") or "").lower() == "evet"}
    for r in _csv("soru-onergeleri"):
        if r.get("vekil") in v and (r.get("tarih") or "") >= sinir:
            m = r.get("ozet") or ""
            v[r["vekil"]]["kayitlar"].append(("soru", r["tarih"], m[:300], r.get("esas_no"), r.get("durum"), r.get("tbmm_adresi"), (r.get("muhatap") or "")[:80], sade(m)))
    for r in _csv("kanun-teklifleri"):
        if r.get("ilk_imza") in v and (r.get("tarih") or "") >= sinir:
            m = (r.get("baslik") or "") + ". " + (r.get("ozet") or "")
            v[r["ilk_imza"]]["kayitlar"].append(("teklif", r["tarih"], m[:300], r.get("esas_no"), r.get("durum"), r.get("tbmm_adresi"), r.get("esas_komisyon") or "", sade(m)))
    for r in _csv("konusmalar"):
        if r.get("vekil") in v and (r.get("tarih") or "") >= sinir and r.get("konu") and len(r["konu"]) > 12:
            v[r["vekil"]]["kayitlar"].append(("konusma", r["tarih"], r["konu"][:300], "", r.get("tur"), r.get("tbmm_adresi"), r.get("komisyon") or "", sade(r["konu"])))
    os.makedirs(KLASOR, exist_ok=True)
    gecici = dizin + ".yeni"
    json.dump({"imza": imza, "veri": v}, open(gecici, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(gecici, dizin)
    _vekil_onbellek.update(anahtar=imza, veri=v)
    return v


def vekil_hazir():
    return _vekil_onbellek["anahtar"] == _vekil_imza() and bool(_vekil_onbellek["veri"])


def vekil_isit():
    """Vekil dizinini arka planda hazırla (Pusula beklemesin)."""
    with _kilit:
        if _vekil_onbellek["hazirlaniyor"]:
            return
        _vekil_onbellek["hazirlaniyor"] = True

    def calis():
        try:
            _vekil_kayitlari()
        except Exception as e:
            _durum["hata"] = f"vekil dizini: {type(e).__name__}"
        finally:
            _vekil_onbellek["hazirlaniyor"] = False
    threading.Thread(target=calis, daemon=True).start()


def vekil_adaylari(hedefler=None, azami=12, bekle=True):
    """Her hedef için en ilgili vekiller (hariç partiler ve 'ilgilenmiyorum' denenler yok). Kanıt: eşleşen kayıtlar.
    bekle=False: dizin hazır değilse beklemeden {"hazirlaniyor": True} döner ve arka planda hazırlar."""
    hedefler = hd.hepsi(("aktif", "taslak")) if hedefler is None else hedefler
    if not os.path.exists(os.path.join(vekil_klasoru(), "milletvekilleri.csv")):
        return {"veri_yok": True, "kapali": not vekilpedia_acik(), "hedefler": []}
    if not bekle and not vekil_hazir():
        dizin = os.path.join(KLASOR, "vekil-dizin.json")
        if not os.path.exists(dizin):   # diskte dizin varsa okumak hızlı (~1 sn); yoksa arka planda kur
            vekil_isit()
            return {"veri_yok": False, "hazirlaniyor": True, "hedefler": []}
    veri = _vekil_kayitlari()
    hl = c.haric_listesi()
    karar = kararlar()
    agdakiler = {c.sade(k.get("ad") or ""): k["id"] for k in c.kisileri_oku()}
    ben = c.ben()
    ilgi = {"id": "_ilgiler", "baslik": "İlgi alanların", "anahtar": c.liste_yap(ben.get("ilgiler"))}
    sonuc = []
    bugun = date.today()
    for h in [*hedefler, ilgi]:
        kalip = _anahtar_kalip(h.get("anahtar") or [])
        if not kalip:
            continue
        puanli = []
        for ad, x in veri.items():
            b = x["bilgi"]
            if c.haric_mi({"parti": b.get("parti")}, hl):
                continue
            vid = c.slug(ad)
            if karar.get("vekil:" + vid, {}).get("karar") == "ilgilenmiyorum":
                continue
            kanit, puan = [], 0.0
            for tur, tarih, metin, no, durum, url, muhatap, n in x["kayitlar"]:
                if kalip.search(n):
                    yas = max(0, (bugun - date.fromisoformat(tarih[:10])).days) if tarih else 365
                    agirlik = {"soru": 1.0, "teklif": 3.0, "konusma": 0.6}[tur] * (1.6 if yas < 90 else 1.0 if yas < 365 else 0.6)
                    puan += agirlik
                    kanit.append({"tur": tur, "tarih": tarih, "metin": metin[:220], "no": no, "durum": durum, "url": url, "muhatap": muhatap[:80], "a": agirlik})
            if kalip.search(x["n_gorev"]):
                kanit.append({"tur": "komisyon", "tarih": "", "metin": (b.get("tbmm_gorev") or "")[:220], "no": "", "durum": "", "url": b.get("tbmm_adresi"), "a": 4})
            # odak: her konuda soru veren vekil öne geçmesin; eşleşen payı (eşleşen / tüm kayıt) puanı ölçekler
            soru_konusma = sum(1 for k in kanit if k["tur"] != "komisyon")
            odak = (soru_konusma / max(20, len(x["kayitlar"]))) ** 0.5
            puan = puan * odak * 3 + (4 if any(k["tur"] == "komisyon" for k in kanit) else 0)
            if puan >= 1.5:
                kanit.sort(key=lambda k: k["tarih"] or "", reverse=True)          # en yeni önce,
                kanit.sort(key=lambda k: (k["tur"] != "komisyon", -k["a"]))       # sonra komisyon ve ağırlık (sıralama kararlı)
                puanli.append({"anahtar": "vekil:" + vid, "ad": ad, "parti": b.get("parti"), "il": b.get("il"), "meslek": b.get("meslek"),
                               "gorev": (b.get("tbmm_gorev") or "")[:200], "x": b.get("x_hesap"), "tbmm": b.get("tbmm_adresi"),
                               "vekilpedia": b.get("vekilpedia_adresi"), "puan": round(puan, 1), "eslesme": len(kanit),
                               "cevapsiz": sum(1 for k in kanit if k["tur"] == "soru" and k["durum"] != "cevaplandi"),
                               "kanit": kanit[:5], "agda": agdakiler.get(c.sade(ad), ""), "karar": karar.get("vekil:" + vid, {}).get("karar", "")})
        puanli.sort(key=lambda x: -x["puan"])
        sonuc.append({"hedef": h["id"], "baslik": h.get("baslik"), "adaylar": puanli[:azami]})
    kl = vekil_klasoru()
    return {"veri_yok": False, "kaynak": "Vekilpedia (CC BY 4.0, TBMM kayıtları)",
            "tarih": datetime.fromtimestamp(os.path.getmtime(os.path.join(kl, "milletvekilleri.csv"))).date().isoformat(), "hedefler": sonuc}


# ---------- etkinlikler ----------
def etkinlik_kaynaklari():
    ozel = (ia.ayarlar().get("kesif") or {}).get("etkinlik_kaynaklari")
    if ozel:
        return ozel
    import ag_kaynak as k
    ay = k.okul_ayar()   # okul bağdaştırıcısı varsa etkinlik sayfası da eklenir; yoksa yalnız genel kaynaklar
    return VARSAYILAN_ETKINLIK + ([{"ad": ay["kisa"] + " etkinlikleri", "url": ay["etkinlik_url"], "tur": "okul"}] if ay and ay.get("etkinlik_url") else [])


def _metin(x):
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", str(x or ""))).split())


def _yer(loc):
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    if not isinstance(loc, dict):
        return _metin(loc), False
    if loc.get("@type") == "VirtualLocation":
        return "Çevrim içi", True
    adres = loc.get("address")
    if isinstance(adres, dict):
        adres = ", ".join(x for x in (adres.get("addressLocality"), adres.get("addressRegion")) if x)
    return _metin(" · ".join(x for x in (loc.get("name"), adres if isinstance(adres, str) else "") if x)), False


def _ld_etkinlikler(sayfa, kaynak):
    out = []

    def gez(o):
        if isinstance(o, list):
            for x in o:
                gez(x)
        elif isinstance(o, dict):
            t = o.get("@type")
            t = t if isinstance(t, list) else [t]
            if any(str(x).endswith("Event") for x in t) and o.get("name") and o.get("startDate"):
                yer, cevrimici = _yer(o.get("location"))
                cevrimici = cevrimici or "Online" in str(o.get("eventAttendanceMode") or "")
                org = o.get("organizer")
                org = org.get("name") if isinstance(org, dict) else (org[0].get("name") if isinstance(org, list) and org and isinstance(org[0], dict) else "")
                out.append({"ad": _metin(o["name"])[:160], "baslangic": str(o["startDate"])[:16], "bitis": str(o.get("endDate") or "")[:16],
                            "yer": yer[:120], "cevrimici": cevrimici, "url": o.get("url") or o.get("@id") or "",
                            "aciklama": _metin(o.get("description"))[:500], "duzenleyen": _metin(org)[:80], "kaynak": kaynak})
            for k in ("itemListElement", "item", "@graph", "subEvent"):
                if k in o:
                    gez(o[k])
    for s in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', sayfa, re.S):
        try:
            gez(json.loads(s.strip()))
        except ValueError:
            continue
    return out


def _devpost(ham, kaynak):
    out = []
    for h in json.loads(ham).get("hackathons", [])[:60]:
        tarih = h.get("submission_period_dates") or ""
        out.append({"ad": _metin(h.get("title"))[:160], "baslangic": "", "bitis": "", "tarih_metni": tarih,
                    "yer": (h.get("displayed_location") or {}).get("location") or "", "cevrimici": ((h.get("displayed_location") or {}).get("location") or "").lower() == "online",
                    "url": h.get("url") or "", "aciklama": ", ".join(t.get("name", "") for t in h.get("themes") or [])[:300] + (f" · ödül {_metin(h.get('prize_amount'))}" if h.get("prize_amount") else ""),
                    "duzenleyen": _metin(h.get("organization_name"))[:80], "kaynak": kaynak, "kalan": h.get("time_left_to_submission") or ""})
    return out


def _okul(sayfa, kaynak):
    """Okul etkinlik listesi (ÖRNEK biçim: yeditepe.edu.tr). Okul adı ve adres bağdaştırıcıdan gelir."""
    import ag_kaynak as k
    ay = k.okul_ayar() or {}
    kok = re.match(r"https?://[^/]+", ay.get("etkinlik_url") or "")
    kok = kok.group(0) if kok else ""
    out = []
    for m in re.finditer(r'<a href="(/tr/etkinlik/[^"]+)"[^>]*>\s*<img[^>]+alt="([^"]+)"', sayfa):
        blok = sayfa[m.end():m.end() + 3000]
        t = re.search(r"(\d{1,2})[./](\d{1,2})[./](20\d\d)", blok)
        bas = f"{t.group(3)}-{int(t.group(2)):02d}-{int(t.group(1)):02d}" if t else ""
        out.append({"ad": _metin(m.group(2))[:160], "baslangic": bas, "bitis": "", "yer": ay.get("ad", ""), "cevrimici": False,
                    "url": kok + m.group(1), "aciklama": "", "duzenleyen": ay.get("ad", ""), "kaynak": kaynak})
    return out


def etkinlikleri_cek(zorla=False):
    yol = os.path.join(KLASOR, "etkinlikler.json")
    if not etkinlik_acik():   # kapalıyken ağa çıkılmaz
        return {"tarih": "", "etkinlikler": [], "hatalar": [], "kapali": True}
    if not zorla and os.path.exists(yol) and time.time() - os.path.getmtime(yol) < ETKINLIK_YENILE_SAAT * 3600:
        return json.load(open(yol, encoding="utf-8"))
    tum, hatalar = [], []
    for k in etkinlik_kaynaklari():
        try:
            if not robots_izin(k["url"]):
                hatalar.append(f"{k['ad']}: robots.txt izin vermiyor")
                continue
            ham = _istek(k["url"], 30, 6_000_000)
            tur = k.get("tur") or "ld"
            parca = _devpost(ham, k["ad"]) if tur == "devpost" else _okul(ham.decode("utf-8", "replace"), k["ad"]) if tur in ("okul", "yeditepe") \
                else _ld_etkinlikler(ham.decode("utf-8", "replace"), k["ad"])
            tum += parca
            if not parca:
                hatalar.append(f"{k['ad']}: etkinlik bulunamadı")
        except Exception as e:
            hatalar.append(f"{k['ad']}: {type(e).__name__}")
    gorulen, temiz = set(), []
    bugun = date.today().isoformat()
    for e in tum:
        anahtar = re.sub(r"[?#].*$", "", e["url"] or e["ad"]).rstrip("/")
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        son = (e.get("bitis") or e.get("baslangic") or "")[:10]
        if son and son < bugun:
            continue
        e["anahtar"] = "etkinlik:" + hashlib.sha1(anahtar.encode()).hexdigest()[:12]
        temiz.append(e)
    temiz.sort(key=lambda e: e.get("baslangic") or "9999")
    veri = {"tarih": datetime.now().isoformat(timespec="minutes"), "etkinlikler": temiz, "hatalar": hatalar}
    os.makedirs(KLASOR, exist_ok=True)
    json.dump(veri, open(yol, "w", encoding="utf-8"), ensure_ascii=False)
    return veri


def etkinlik_onerileri(hedefler=None, azami=40):
    """Önbellekteki etkinlikleri hedef/ilgi anahtarlarıyla puanlar. Eşleşmeyen etkinlik de (puan 0) listede kalır; sıralama puana göre."""
    hedefler = hd.hepsi(("aktif", "taslak")) if hedefler is None else hedefler
    yol = os.path.join(KLASOR, "etkinlikler.json")
    if not etkinlik_acik():
        return {"veri_yok": True, "kapali": True, "etkinlikler": [], "hatalar": []}
    if not os.path.exists(yol):
        return {"veri_yok": True, "etkinlikler": [], "hatalar": []}
    veri = json.load(open(yol, encoding="utf-8"))
    karar = kararlar()
    ilgiler = c.liste_yap(c.ben().get("ilgiler"))
    kaliplar = [(h["id"], h.get("baslik"), _anahtar_kalip(h.get("anahtar") or [])) for h in hedefler]
    kaliplar.append(("_ilgiler", "İlgi alanların", _anahtar_kalip(ilgiler)))
    liste = []
    for e in veri["etkinlikler"]:
        if karar.get(e["anahtar"], {}).get("karar") == "ilgilenmiyorum":
            continue
        metin = " " + " ".join(kelimeler(e["ad"] + " " + e.get("aciklama", "") + " " + e.get("duzenleyen", ""))) + " "
        eslesen = [{"hedef": hid, "baslik": b} for hid, b, k in kaliplar if k and k.search(metin)]
        x = dict(e)
        x["eslesen"] = eslesen
        x["puan"] = sum(2 if m["hedef"] != "_ilgiler" else 1 for m in eslesen) + (0.5 if not e.get("cevrimici") and "stanbul" in (e.get("yer") or "") else 0)
        x["karar"] = karar.get(e["anahtar"], {}).get("karar", "")
        liste.append(x)
    liste.sort(key=lambda x: (-x["puan"], x.get("baslangic") or "9999"))
    return {"veri_yok": False, "tarih": veri["tarih"], "etkinlikler": liste[:azami], "toplam": len(veri["etkinlikler"]), "hatalar": veri.get("hatalar", []),
            "okul_adi": __import__("ag_kaynak").okul_adi()}


# ---------- arka planda yenileme ----------
def durum():
    return {**_durum, "vekil_hazirlaniyor": _vekil_onbellek["hazirlaniyor"]}


def yenile(zorla=False, bitince=None):
    """Vekil verisini (haftalık) ve etkinlikleri (12 saatte bir) arka planda tazeler."""
    with _kilit:
        if _durum["calisiyor"]:
            return False
        _durum.update(calisiyor=True, hata="", mesaj="Keşif kaynakları okunuyor…")

    def calis():
        notlar = []
        try:
            try:
                if vekil_verisi_yenile(zorla):
                    notlar.append("vekil verisi güncellendi")
            except Exception as e:
                notlar.append(f"vekil verisi indirilemedi ({type(e).__name__}); eldeki veri kullanılıyor")
            if vekilpedia_acik() and os.path.exists(os.path.join(vekil_klasoru(), "milletvekilleri.csv")):
                _durum["mesaj"] = "vekil dizini hazırlanıyor…"
                try:
                    _vekil_kayitlari()
                except Exception as e:
                    notlar.append(f"vekil dizini hazırlanamadı ({type(e).__name__})")
            elif not vekilpedia_acik():
                notlar.append("vekil verisi kapalı (Ayarlar → Kaynaklar)")
            else:
                notlar.append("vekil verisi yok")
            if etkinlik_acik():
                v = etkinlikleri_cek(zorla)
                notlar.append(f"{len(v['etkinlikler'])} yaklaşan etkinlik")
            else:
                notlar.append("etkinlik taraması kapalı (Ayarlar → Kaynaklar)")
            _durum.update(son=datetime.now().isoformat(timespec="minutes"), mesaj=" · ".join(notlar))
            if bitince:
                bitince()
        except Exception as e:
            _durum.update(hata=f"{type(e).__name__}: {e}"[:300])
        finally:
            _durum["calisiyor"] = False
    threading.Thread(target=calis, daemon=True).start()
    return True


def istem_blogu(hedefler=None, vekil_azami=6, etkinlik_azami=25):
    """Strateji okumasına giden keşif özeti (kanıt numaralarıyla)."""
    v = vekil_adaylari(hedefler, vekil_azami)
    e = etkinlik_onerileri(hedefler, etkinlik_azami)
    satir = ["VEKİL ADAYLARI (Vekilpedia/TBMM; ağda değiller, hariç partiler çıkarıldı):"]
    for g in v.get("hedefler", []):
        if not g["adaylar"]:
            continue
        satir.append(f"  hedef [{g['hedef']}] {g['baslik']}:")
        for a in g["adaylar"]:
            k = "; ".join(f"{x['tur']} {x['no'] or ''} {x['tarih']} [{x['durum'] or ''}] {x['metin'][:110]}" for x in a["kanit"][:3])
            satir.append(f"   - {a['anahtar']} {a['ad']} ({a['parti']}, {a['il']}; {a['meslek'] or '?'}) puan {a['puan']}"
                         f"{' · AĞINDA: ' + a['agda'] if a['agda'] else ''}{' · karar: ' + a['karar'] if a['karar'] else ''} · kanıt: {k}")
    satir.append("\nYAKLAŞAN ETKİNLİKLER (herkese açık sayfalardan):")
    for x in e.get("etkinlikler", []):
        satir.append(f"   - {x['anahtar']} {x['ad']} · {x.get('baslangic') or x.get('tarih_metni') or '?'} · {x.get('yer') or ''}"
                     f" · {x['kaynak']} · eşleşen: {', '.join(m['hedef'] for m in x['eslesen']) or '-'}{' · karar: ' + x['karar'] if x['karar'] else ''}"
                     f" · {x.get('aciklama', '')[:140]} · {x['url']}")
    return "\n".join(satir)
