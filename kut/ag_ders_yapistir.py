"""Yapıştırılan ders programı metni → ders kodları + hocalar. Ağ isteği yok, model yok (okulların çoğu robots.txt ile kapalı).

Biçimler: "ISE 424 Sistem Analizi · Dr. Dilara Tuna Örnek", sekmeli/çok boşluklu tablo kopyası, "ISE 424-1 | Ad | Prof. Dr. …",
satır satır (kod satırı, altında ad, altında hoca). Unvanlar (Prof. Dr., Doç. Dr., Dr. Öğr. Üyesi, Öğr. Gör., Arş. Gör. …) ayıklanır.
Önizleme hiçbir şey yazmaz. Onayla: dersler profile (ben.md), hocalar ağa (yakınlık 0, tür akademi, `## Dersler`), `hocasi` bağı
ag_baglam kural b ile kurulur.
"""
import os
import re
from datetime import date

import ag_baglam as bg
import ag_cekirdek as c
import ag_ders_girdi as dg
import ag_ice_ortak as ort
import ag_kaynak as kn
import ag_tutarlilik as tu

METIN_AZAMI = 200_000
DERS_AZAMI = 400
HOCA_AZAMI = 600
UNVAN_PARCALARI = {"prof", "doc", "dr", "ogr", "uyesi", "gor", "ars", "yrd", "okt", "uzm", "assoc", "asst", "assist", "lecturer", "instructor",
                   "ogretim", "gorevlisi", "arastirma", "profesor", "docent", "hoca"}
# hoca adı olamayacak sözcükler (başlık, gün, yer, dönem…)
ADDISI = {"donem", "donemi", "bahar", "guz", "yaz", "program", "programi", "ders", "dersler", "listesi", "sinav", "final", "vize", "salon", "bina",
          "fakulte", "fakultesi", "bolum", "bolumu", "universite", "universitesi", "kredi", "akts", "teorik", "uygulama", "laboratuvar", "lab",
          "zorunlu", "secmeli", "sinif", "derslik", "saat", "gun", "pazartesi", "sali", "carsamba", "persembe", "cuma", "cumartesi", "pazar",
          "pzt", "sal", "car", "per", "cum", "cmt", "paz", "mon", "tue", "wed", "thu", "fri", "sat", "sun", "course", "class", "section", "room",
          "semester", "fall", "spring", "summer", "schedule", "instructor", "kod", "adi", "ad", "hocasi", "ogretim"}
AYRAC = re.compile(r"\t+|\s*[·•|;]\s*|\s{2,}|\s+[-–—]\s+")
KOD_BAS = re.compile(r"^\s*(?:\d{1,3}[.)]\s+|[-*•]\s+)?([A-ZÇĞİÖŞÜ]{2,5})\s?(\d{3}[A-Za-z]?)(?:\s?[-/]\s?(\d{1,5}(?!\d)|[A-Za-z](?![\w])))?(?![\w])\s*(.*)$")
UNVAN_BAS = re.compile(r"(?<!\S)(?:Prof|Doç|Doc|Dr|Öğr|Ogr|Arş|Ars|Yrd|Okt|Uzm|Assoc|Asst)\.", re.I)
AD_AYRAC = re.compile(r"\s*(?:/|&|\+|,|;|\bve\b|\band\b)\s*", re.I)
ETIKET = re.compile(r"^\s*(?:hoca|ö[ğg]retim\s+(?:üyesi|elemanı)|instructor|teacher|e[ğg]itmen)\s*[:\-]\s*", re.I)


def unvan_ayir(metin):
    """'Dr. Öğr. Üyesi Dilara Tuna Örnek' → ('Dr. Öğr. Üyesi', 'Dilara Tuna Örnek'). Yalnız baştaki unvan sözcükleri atılır."""
    metin = ETIKET.sub("", " ".join(str(metin or "").split()))
    parcalar = metin.split(" ")
    i = 0
    while i < len(parcalar) and c.sade(parcalar[i].rstrip(".")) in UNVAN_PARCALARI and c.sade(parcalar[i].rstrip(".")):
        i += 1
    return " ".join(parcalar[:i]), " ".join(parcalar[i:])


def ad_gibi_mi(ad):
    """2–5 sözcük, yalnız harf (kısaltma 'A.' olabilir), rakam yok, ders/gün/yer sözcüğü yok."""
    parcalar = ad.split()
    if not 2 <= len(parcalar) <= 5 or any(c.sade(p.rstrip(".")) in ADDISI for p in parcalar):
        return False
    if not all(re.fullmatch(r"[^\W\d_]+(?:['’-][^\W\d_]+)*\.?", p) for p in parcalar):
        return False
    return any(len(p.rstrip(".")) >= 2 for p in parcalar)


def _ad_duzelt(ad):
    ad = " ".join(ad.split()).strip(" .-,")
    return kn.tr_ad(ad) if ad == ad.upper() else ad


def hocalari_ayikla(parca):
    """Bir parçadaki (virgül, /, & ya da 've' ile ayrılmış) hocalar → [{ad, unvan, unvanli}]. Ad gibi görünmeyenler atılır."""
    sonuc = []
    for p in AD_AYRAC.split(parca):
        unvan, ad = unvan_ayir(p)
        ad = _ad_duzelt(ad)
        unvan = kn.tr_ad(unvan) if unvan and unvan == unvan.upper() else unvan
        if ad and ad_gibi_mi(ad):
            sonuc.append({"ad": ad, "unvan": unvan, "unvanli": bool(unvan)})
    return sonuc


def _parca_isle(ders, p):
    """Tek parça: unvanlı ad(lar) → hoca; ders adı boşsa → ders adı; ad dolu, hoca yoksa ve ad gibiyse → unvansız hoca. Tüketildiyse True."""
    p = p.strip(" -–—:,")
    if not p:
        return True
    u = UNVAN_BAS.search(p)
    if u:
        if u.start() > 0 and not ders["ad"]:   # "Sistem Analizi Dr. Dilara Tuna Örnek": ad ile hoca bitişik
            ders["ad"] = p[:u.start()].strip(" -–—:,")[:80]
        p = p[u.start():]
        h = hocalari_ayikla(p)
        for x in h:
            if c.sade(x["ad"]) not in {c.sade(y["ad"]) for y in ders["hocalar"]}:
                ders["hocalar"].append(x)
        return bool(h)
    if re.search(r"\d{1,2}[:.]\d{2}", p):   # saat
        return False
    if not ders["ad"]:
        ders["ad"] = p[:80]
        return True
    if not ders["hocalar"]:   # unvansız tek ad: hoca olabilir ama emin değiliz (önizlemede işaretsiz gelir)
        h = hocalari_ayikla(p)
        if h:
            ders["hocalar"].extend(h[:1])
            return True
    return False


def ayikla(metin):
    """Yapıştırılan metin → {dersler: [{k, kod, sube, ad, hocalar: [{k, ad, unvan, unvanli}]}], tanimayan: [satır…]}. Yazmaz."""
    metin = str(metin or "")[:METIN_AZAMI]
    dersler, harita, tanimayan, ders = [], {}, [], None
    for ham in metin.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        satir = ham.strip()
        if not satir:
            continue   # tablo kopyalarında hücreler arasında boş satır olabilir
        m = KOD_BAS.match(satir)
        if m and m.group(1) not in dg.YASAK_ONEK:
            kod, sube = f"{m.group(1)} {m.group(2).upper()}", (m.group(3) or "").upper()
            anahtar = f"{kod}-{sube}" if sube else kod
            if anahtar not in harita:
                if len(dersler) >= DERS_AZAMI:
                    ders = None
                    continue
                harita[anahtar] = {"k": anahtar, "kod": kod, "sube": sube, "ad": "", "hocalar": []}
                dersler.append(harita[anahtar])
            ders = harita[anahtar]
            parcalar = AYRAC.split(m.group(4))
        elif ders is not None:
            parcalar = AYRAC.split(satir)
        else:
            tanimayan.append(satir[:80])
            continue
        if not any([_parca_isle(ders, p) for p in parcalar if p.strip(" -–—:,")]) and not (m and not m.group(4).strip()):
            tanimayan.append(satir[:80])
    hoca_say = 0
    for d in dersler:
        d["hocalar"] = d["hocalar"][: max(0, HOCA_AZAMI - hoca_say)]
        for i, h in enumerate(d["hocalar"]):
            h["k"] = f"{d['k']}:{i}"
        hoca_say += len(d["hocalar"])
    return {"dersler": dersler, "tanimayan": tanimayan[:15]}


def onizle(metin, mevcut_dersler=None):
    """Metni ayrıştırır; ne yapılacağını gösterir. HİÇBİR ŞEY yazmaz."""
    s = ayikla(metin)
    if not s["dersler"]:
        raise ValueError("Metinde ders kodu bulunamadı (ör. 'ISE 424 Sistem Analizi · Dr. Dilara Tuna Örnek').")
    with ort.okuma_kilidi():   # ayrıştırma kilitsiz bitti; kişi dosyalarını okuyan kısa bölüm yazımlarla yarışmasın
        mevcut = c.kisileri_oku()
        profilde = {x.upper().replace(" ", "") for x in c.liste_yap((mevcut_dersler if mevcut_dersler is not None else c.ben().get("dersler")))}
    for d in s["dersler"]:
        d["profilde"] = (d["k"].upper().replace(" ", "") in profilde) or (d["kod"].upper().replace(" ", "") in profilde)
        for h in d["hocalar"]:
            k = kn._kisi_esle(h["ad"], mevcut)
            h["agda"] = k["id"] if k else ""
            h["agda_ad"] = (k.get("ad") or k["id"]) if k else ""
    token = ort.sakla("ders", s)
    return {"token": token, "dersler": s["dersler"], "tanimayan": s["tanimayan"],
            "ozet": {"ders": len(s["dersler"]), "hoca": len({c.sade(h["ad"]) for d in s["dersler"] for h in d["hocalar"]}),
                     "yeni_hoca": len({c.sade(h["ad"]) for d in s["dersler"] for h in d["hocalar"] if not h["agda"]})}}


def _kod_sube(d):
    return f"{d['kod']}-{d['sube']}" if d["sube"] else d["kod"]


def uygula(token, secimler=None):
    """secimler: {dersler: [ders anahtarı…], hocalar: [hoca anahtarı…]}; verilmezse unvanlı hocalarla birlikte hepsi. Dersleri profile ekler,
    hocaları ağa ekler/günceller (yakınlık 0, tür akademi), hocasi bağlarını kural motoruyla kurar."""
    plan = ort.al(token, "ders")
    secimler = secimler or {}
    sec_ders = set(secimler["dersler"]) if secimler.get("dersler") is not None else {d["k"] for d in plan["dersler"]}
    sec_hoca = set(secimler["hocalar"]) if secimler.get("hocalar") is not None else {h["k"] for d in plan["dersler"] for h in d["hocalar"] if h["unvanli"]}
    secili = [d for d in plan["dersler"] if d["k"] in sec_ders]
    if not secili:
        raise ValueError("Önce en az bir ders seç.")
    bugun = date.today().strftime("%d.%m.%Y")
    mevcut_dersler = c.liste_yap(c.ben().get("dersler"))
    yeni_dersler = dg.birlestir(mevcut_dersler, [_kod_sube(d) for d in secili])
    if yeni_dersler != mevcut_dersler:
        c.ben_yaz({"dersler": yeni_dersler})   # ağ isteği yok: kaynak doldurma tetiklenmez
    sonuc = {"ders": len(secili), "eklenen": [], "guncellenen": [], "baglar": [], "bag_onerisi": [], "soru": 0}
    # hoca → [(ders, hoca)] (aynı hoca birden çok derste tek kişi)
    gruplar = {}
    for d in secili:
        for h in d["hocalar"]:
            if h["k"] in sec_hoca:
                gruplar.setdefault(c.sade(h["ad"]), {"ad": h["ad"], "unvan": h["unvan"], "dersler": []})["dersler"].append(d)
    kisiler = c.kisileri_oku()
    sorular = []
    kaynak_adi = f"yapıştırılan ders listesi ({bugun})"
    okul = kn.okul_ayar() or {}
    for g in gruplar.values():
        k = kn._kisi_esle(g["ad"], kisiler)
        satirlar = lambda govde: [f"{_kod_sube(d)} {d['ad']}".strip() + f" · profildeki dersin · kaynak: {kaynak_adi}" for d in g["dersler"]
                                  if not re.search(rf"\b{re.escape(_kod_sube(d))}\b", c.bolum_oku(govde, "Dersler"))]
        if k is None:
            kid = c.bos_slug(g["ad"])
            alanlar = {"ad": g["ad"], "foto": "", "tur": "akademi", "kurum": okul.get("ad") or "", "rol": g["unvan"] or "Öğretim elemanı",
                       "alan": ["egitim"], "nereden": ["ders-listesi"], "yakinlik": "0"}   # yakınlık yalnız kullanıcı onayıyla artar
            govde = c.yeni_govde(g["ad"], f"{kaynak_adi}; Kut yerelde ayrıştırdı.")
            for s in satirlar(govde):
                govde = c.bolume_ekle(govde, "Dersler", s)
            c.kisi_yaz(kid, alanlar, govde)
            kisiler.append({"id": kid, "ad": g["ad"]})
            sonuc["eklenen"].append(g["ad"])
            sorular.append({"kisi": kid, "alan": "soru", "deger": f"{g['ad']} ile dersi dışında birebir tanışıklığın var mı?",
                            "kaynak": "Kut · ders listesi"})
        else:
            kid = k["id"]
            alanlar = c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))
            govde = alanlar.pop("govde")
            yeni = satirlar(govde)
            if not yeni:
                continue
            for s in yeni:
                govde = c.bolume_ekle(govde, "Dersler", s)
            c.surum_al(kid)
            c.kisi_yaz(kid, alanlar, govde)
            sonuc["guncellenen"].append(g["ad"])
    if sorular:
        sonuc["soru"] = c.cikarim_ekle(sorular)
    b = bg.bag_cikar(kaydet=True)   # hocasi (hoca → ben) kural b; çıkarım gerektirenler Doğrula'ya
    tu.kuyrugu_temizle()
    sonuc["baglar"], sonuc["bag_onerisi"] = b["yazilan"], b["onerilen"]
    return sonuc
