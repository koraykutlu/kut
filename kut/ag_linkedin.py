"""LinkedIn "verilerinin kopyasını al" ZIP'i ya da Connections.csv (+ isteğe bağlı messages.csv) → bağlantılar ve mesaj üst verisi.

Tamamen yerel (csv modülü, ağ yok, kazıma yok). ZIP'ten yalnız Connections.csv ve messages.csv okunur (diğer dosyalar açılmaz).
Mesajlarda yalnız kiminle ve ne zaman alınır; CONTENT, SUBJECT hiçbir yerde saklanmaz ya da yazılmaz. Önizleme hiçbir şey yazmaz.
Mevcut kişide yalnız BOŞ alanlar (linkedin, kurum, rol) Doğrula'ya öneri olur; yeni bağlantılar yalnız seçilirse eklenir
(yakınlık 0, tür 'cevre': tür tahmini yok). "Connected On" kişinin ## Kaynaklar bölümüne not olur.
"""
import csv
import io
import os
import re
from datetime import date

import ag_cekirdek as c
import ag_ice_aktar as ia
import ag_ice_ortak as ort

DOSYA_AZAMI = 60_000_000
KANAL = "linkedin"
MESAJ_GUN_AZAMI = 12       # kişi başına en çok bu kadar (en yeni) mesajlaşma günü temas olur
LISTE_AZAMI = 20000
BASLIK_ARAMA_SATIRI = 30   # Connections.csv'de "Notes:" gibi başlıklar sonrası gerçek başlığı bu satıra kadar ara
try:
    csv.field_size_limit(2 ** 24)   # messages.csv içerik alanları uzun olabilir; okunur ama hiçbir yere alınmaz
except (OverflowError, ValueError):
    pass

# sade() başlık adı → alan (dil ve biçim varyantları)
BASLIKLAR = {
    "ad": {"first name", "ad", "adi", "isim", "vorname", "prenom", "nombre", "nome"},
    "soyad": {"last name", "soyad", "soyadi", "nachname", "nom", "apellido", "cognome"},
    "url": {"url", "profile url", "linkedin url", "profil url", "profil", "profile"},
    "eposta": {"email address", "email", "e mail", "e mail address", "e posta", "e posta adresi", "adresse e mail", "e mail adresse", "correo electronico"},
    "kurum": {"company", "sirket", "firma", "kurum", "organization", "unternehmen", "entreprise", "empresa", "azienda"},
    "rol": {"position", "pozisyon", "unvan", "title", "job title", "stelle", "poste", "cargo", "posizione"},
    "tarih": {"connected on", "baglanti tarihi", "baglanilan tarih", "baglanildigi tarih", "verbunden am", "connecte le", "conectado el", "connesso il"},
}
MESAJ_BASLIKLARI = {
    "baslik": {"conversation title"}, "kimden": {"from"}, "kimden_url": {"sender profile url"}, "kime": {"to"},
    "kime_url": {"recipient profile urls", "recipient profile url"}, "tarih": {"date"}, "klasor": {"folder"}, "sohbet": {"conversation id"},
}
AYLAR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
         "oca": 1, "sub": 2, "nis": 4, "haz": 6, "tem": 7, "agu": 8, "eyl": 9, "eki": 10, "kas": 11, "ara": 12}
SISTEM_AD = re.compile(r"^(linkedin( member| uyesi)?|uye)$", re.I)


def baglanti_tarihi(s):
    """'12 Mar 2024', 'Mar 12, 2024', '2024-03-12', '25/12/2024' → date; belirsiz (03/04/2024) ya da tanınmayan → None."""
    s = " ".join(str(s or "").split())
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", s)
    if m:
        a = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        m = re.fullmatch(r"(\d{1,2})[ .-]+([^\W\d_]+)\.?,?[ .-]+(\d{4})", s)
        if m and c.sade(m.group(2))[:3] in AYLAR:
            a = (int(m.group(3)), AYLAR[c.sade(m.group(2))[:3]], int(m.group(1)))
        else:
            m = re.fullmatch(r"([^\W\d_]+)\.? (\d{1,2}),? (\d{4})", s)
            if m and c.sade(m.group(1))[:3] in AYLAR:
                a = (int(m.group(3)), AYLAR[c.sade(m.group(1))[:3]], int(m.group(2)))
            else:
                m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
                if not m:
                    return None
                x, y = int(m.group(1)), int(m.group(2))
                if x > 12 and y <= 12:
                    a = (int(m.group(3)), y, x)
                elif y > 12 and x <= 12:
                    a = (int(m.group(3)), x, y)
                else:
                    return None   # 03/04/2024: gün/ay sırası belirsiz, uydurma
    try:
        return date(*a)
    except ValueError:
        return None


def _metin_coz(ham):
    for kodlama in ("utf-8-sig", "utf-16", "cp1254"):
        try:
            return ham.decode(kodlama)
        except UnicodeError:
            continue
    return ham.decode("latin-1", "replace")


def _baslik_haritasi(hucreler, sozluk):
    h = {}
    for i, x in enumerate(hucreler):
        n = c.sade(x)
        for alan, adlar in sozluk.items():
            if n in adlar and alan not in h:
                h[alan] = i
    return h


def baglantilari_oku(metin):
    """Connections.csv metni → [{ad, url, eposta, kurum, rol, tarih (ham metin)}]. Başta 'Notes:' satırları olabilir; sütun eksikse tolere edilir."""
    metin = metin.replace("\r\n", "\n").replace("\r", "\n")
    satirlar = metin.split("\n")
    baslangic = None
    for i, s in enumerate(satirlar[:BASLIK_ARAMA_SATIRI]):
        try:
            hucre = next(csv.reader([s]), [])
        except csv.Error:
            continue
        h = _baslik_haritasi(hucre, BASLIKLAR)
        if "ad" in h and ("soyad" in h or len(h) >= 3):
            baslangic = i
            break
    if baslangic is None:
        raise ValueError("Connections.csv başlık satırı (First Name, Last Name, URL…) bulunamadı")
    okuyucu = csv.reader(io.StringIO("\n".join(satirlar[baslangic:])))
    h = _baslik_haritasi(next(okuyucu), BASLIKLAR)
    al = lambda r, a: (r[h[a]].strip() if a in h and h[a] < len(r) else "")
    sonuc = []
    try:
        for r in okuyucu:
            ad = ort.temiz_ad(f"{al(r, 'ad')} {al(r, 'soyad')}")
            if not ad or c.sade(ad) == "" or SISTEM_AD.match(c.sade(ad)):
                continue
            url = al(r, "url")
            sonuc.append({"ad": ad, "url": url if ort.linkedin_slug(url) else "", "eposta": ort.eposta_norm(al(r, "eposta")),
                          "kurum": ort.formul_temizle(al(r, "kurum"))[:80], "rol": ort.formul_temizle(al(r, "rol"))[:80], "tarih": al(r, "tarih")[:30]})
    except csv.Error:
        pass   # bozuk satırdan sonrasını bırak; o ana kadar okunanlar geçerli
    return sonuc


def mesajlari_oku(metin, ben_adlari):
    """messages.csv metni → ({kimlik: {ad, url, gunler: {iso: sayı}}}, {sohbet, grup, ben_otomatik}). YALNIZ kim ve ne zaman; CONTENT/SUBJECT okunmaz.
    İkiden çok katılımcılı sohbetler (grup) temas sayılmaz."""
    okuyucu = csv.reader(io.StringIO(metin.replace("\r\n", "\n")))
    h = _baslik_haritasi(next(okuyucu, []), MESAJ_BASLIKLARI)
    if not {"kimden", "tarih"} <= set(h):
        raise ValueError("messages.csv başlığı tanınmadı (FROM, DATE sütunları gerekli)")
    al = lambda r, a: (r[h[a]].strip() if a in h and h[a] < len(r) else "")
    sohbetler = {}   # sohbet → {"katilimci": {kimlik: (ad, url)}, "mesajlar": [(kimden_kimlik, iso)]}
    try:
        for r in okuyucu:
            if al(r, "klasor").upper() in ("SPAM", "JUNK"):
                continue
            iso = al(r, "tarih")[:10]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
                continue
            sid = al(r, "sohbet") or al(r, "baslik") or f"{al(r, 'kimden')}|{al(r, 'kime')}"
            kimden_url = al(r, "kimden_url")
            kimden = (ort.linkedin_slug(kimden_url) or c.sade(al(r, "kimden")), ort.temiz_ad(al(r, "kimden")), kimden_url)
            kime_urller = re.findall(r"https?://[^\s,;\"]*linkedin\.com/in/[^\s,;\"]+", al(r, "kime_url"), re.I)
            kime_adlar = [x.strip() for x in re.split(r"[;,]", al(r, "kime")) if x.strip()]
            alicilar = [(ort.linkedin_slug(kime_urller[i]) if i < len(kime_urller) else c.sade(ad), ort.temiz_ad(ad), kime_urller[i] if i < len(kime_urller) else "")
                        for i, ad in enumerate(kime_adlar or [""] * len(kime_urller))]
            if not kimden[0]:
                continue
            s = sohbetler.setdefault(sid, {"katilimci": {}, "mesajlar": []})
            for kim in [kimden] + alicilar:
                if kim[0]:
                    s["katilimci"].setdefault(kim[0], (kim[1], kim[2]))
            s["mesajlar"].append((kimden[0], iso))
            if len(s["katilimci"]) > 12:   # çok büyük grup: ayrıntıyı bellekte tutma
                s["mesajlar"] = s["mesajlar"][-1:]
    except csv.Error:
        pass
    # kendini tanı: ayardaki adlar, yoksa neredeyse her sohbette geçen katılımcı
    ben = {k for s in sohbetler.values() for k, (ad, _) in s["katilimci"].items() if c.sade(ad) in ben_adlari}
    otomatik = ""
    if not ben and len(sohbetler) >= 3:
        sayac = {}
        for s in sohbetler.values():
            for k in s["katilimci"]:
                sayac[k] = sayac.get(k, 0) + 1
        en, n = max(sayac.items(), key=lambda x: x[1], default=("", 0))
        if n >= 0.9 * len(sohbetler):
            ben, otomatik = {en}, next((ad for s in sohbetler.values() for k, (ad, _) in s["katilimci"].items() if k == en), en)
    kisiler, grup = {}, 0
    for s in sohbetler.values():
        digerleri = {k: v for k, v in s["katilimci"].items() if k not in ben}
        if len(s["katilimci"]) > 2 or len(digerleri) != 1:
            grup += 1 if len(digerleri) > 1 else 0
            continue
        kim, (ad, url) = next(iter(digerleri.items()))
        if not ad or SISTEM_AD.match(c.sade(ad)):
            continue
        r = kisiler.setdefault(kim, {"ad": ad, "url": url if ort.linkedin_slug(url) else "", "gunler": {}})
        for _, iso in s["mesajlar"]:
            r["gunler"][iso] = r["gunler"].get(iso, 0) + 1
    return kisiler, {"sohbet": len(sohbetler), "grup": grup, "ben_otomatik": otomatik, "ben_bulundu": bool(ben)}


def _dosyalar(dosya_adi, ham):
    """(connections metni | None, messages metni | None). ZIP'te yalnız bu iki dosya açılır."""
    if len(ham) > DOSYA_AZAMI:
        raise ValueError("LinkedIn dosyası çok büyük")
    bag = msg = None
    if ham[:2] == b"PK":
        for ad, veri in ia.zip_icerik(ham, lambda a: os.path.basename(a).lower() in ("connections.csv", "messages.csv")):
            if os.path.basename(ad).lower() == "connections.csv":
                bag = _metin_coz(veri)
            else:
                msg = _metin_coz(veri)
        if bag is None and msg is None:
            raise ValueError("ZIP içinde Connections.csv ya da messages.csv bulunamadı")
    else:
        metin = _metin_coz(ham)
        baslik = c.sade(metin.split("\n", 1)[0])
        if "conversation id" in baslik and "from" in baslik:
            msg = metin
        else:
            bag = metin
    return bag, msg


def onizle(dosyalar, secenek=None):
    """dosyalar: [(ad, bayt)] (Connections.csv, messages.csv ve/veya LinkedIn ZIP). HİÇBİR ŞEY yazmaz.
    Dönen: özet, eşleşen kişiler (boş alan önerileri, temas), yeni bağlantılar (seçimli), onay belirteci."""
    bag_metin = msg_metin = None
    for ad, ham in dosyalar:
        b, m = _dosyalar(ad, ham)
        bag_metin = b if b is not None else bag_metin
        msg_metin = m if m is not None else msg_metin
    if bag_metin is None and msg_metin is None:
        raise ValueError("Connections.csv ya da messages.csv gerekli")
    baglantilar = baglantilari_oku(bag_metin) if bag_metin is not None else []
    with ort.okuma_kilidi():
        ben_ad, _ = ort.ben_kimligi()
    mesaj, mist = (mesajlari_oku(msg_metin, ben_ad) if msg_metin is not None else ({}, {"sohbet": 0, "grup": 0, "ben_otomatik": "", "ben_bulundu": True}))

    # kayıtları birleştir: LinkedIn adresi (slug) öncelikli, yoksa ad
    kayitlar, slug_idx, ad_idx = {}, {}, {}

    def bul_ya_ac(ad, url):
        s, a = ort.linkedin_slug(url), c.sade(ad)
        k = slug_idx.get(s) if s else None
        k = k or ad_idx.get(a)
        if k is None:
            k = f"k{len(kayitlar)}"
            kayitlar[k] = {"k": k, "ad": ad, "url": "", "eposta": "", "kurum": "", "rol": "", "tarih": "", "gunler": {}, "baglanti": False}
        if s:
            slug_idx[s] = k
        ad_idx.setdefault(a, k)
        return kayitlar[k]

    for b in baglantilar:
        r = bul_ya_ac(b["ad"], b["url"])
        r.update({x: b[x] for x in ("url", "eposta", "kurum", "rol", "tarih") if b[x]}, baglanti=True)
    for kim, m in mesaj.items():
        r = bul_ya_ac(m["ad"], m["url"])
        r["url"] = r["url"] or m["url"]
        for iso, n in m["gunler"].items():
            r["gunler"][iso] = r["gunler"].get(iso, 0) + n
    with ort.okuma_kilidi():   # ağır ayrıştırma kilitsiz bitti; kişi dosyalarını okuyan kısa bölüm yazımlarla yarışmasın
        return _onizle_esle(baglantilar, mist, kayitlar)


def _onizle_esle(baglantilar, mist, kayitlar):
    mevcut = c.kisileri_oku()
    dizin = ort.Dizin(mevcut)
    haric = c.haric_listesi()
    kmap = {k["id"]: k for k in mevcut}
    eslesen, yeni, belirsiz = {}, [], 0
    for r in kayitlar.values():
        gunler = sorted(r["gunler"].items())[-MESAJ_GUN_AZAMI:]
        r["temas"] = [(iso, f"mesajlaşma ({n} mesaj)" if n > 1 else "mesajlaşma") for iso, n in gunler]
        kid, neden = dizin.bul(r["ad"], r["eposta"], r["url"])
        if kid:
            k = kmap[kid]
            onerilen = {}
            if r["url"] and not (k.get("linkedin") or "").strip():
                onerilen["linkedin"] = r["url"]
            if r["kurum"] and not (k.get("kurum") or "").strip():
                onerilen["kurum"] = r["kurum"]
            if r["rol"] and not (k.get("rol") or "").strip():
                onerilen["rol"] = r["rol"]
            if c.haric_mi(k, haric):
                onerilen = {}
            e = eslesen.setdefault(kid, {"id": kid, "ad": k.get("ad") or kid, "alan": {}, "temas": [], "tarih": "", "neden": neden})
            e["alan"].update(onerilen)
            e["temas"] += r["temas"]
            e["tarih"] = e["tarih"] or r["tarih"]
        elif neden == "belirsiz":
            belirsiz += 1
        elif r["ad"]:
            yeni.append(r)
    for e in eslesen.values():
        e["temas"] = sorted(set(e["temas"]))[-MESAJ_GUN_AZAMI:]
        e["yazilacak"] = ort.temas_satirlari_yaz(e["id"], [(date.fromisoformat(i), m) for i, m in e["temas"]], KANAL, yaz=False)
    yeni.sort(key=lambda r: (not r["gunler"], c.sade(r["ad"])))
    plan = {"eslesen": eslesen, "yeni": {r["k"]: {x: r[x] for x in ("ad", "url", "eposta", "kurum", "rol", "tarih", "temas")} for r in yeni}}
    uyari = []
    if belirsiz:
        uyari.append(f"{belirsiz} kayıt birden çok kişiyle eşleşti (belirsiz); atlandı.")
    if not mist["ben_bulundu"]:
        uyari.append("Mesajlarda kendi adın bulunamadı; hiçbir sohbet temas sayılmadı. 'WhatsApp'taki adın' alanına LinkedIn adını yaz.")
    if mist["grup"]:
        uyari.append(f"{mist['grup']} grup sohbeti temas sayılmadı.")
    if mist["ben_otomatik"]:
        uyari.append(f"Mesajlarda kendi adın olarak '{mist['ben_otomatik']}' varsayıldı; yanlışsa 'WhatsApp'taki adın' alanına gerçek adını yaz.")
    if len(yeni) > LISTE_AZAMI:
        uyari.append(f"Yeni bağlantı listesi {LISTE_AZAMI} ile sınırlandı.")
    token = ort.sakla("linkedin", plan)
    return {"token": token,
            "ozet": {"baglanti": len(baglantilar), "mesaj_sohbet": mist["sohbet"], "kisi_eslesen": len(eslesen), "yeni_oneri": len(yeni),
                     "alan_onerisi": sum(len(e["alan"]) for e in eslesen.values()), "temas_satiri": sum(e["yazilacak"] for e in eslesen.values())},
            "eslesenler": [{"id": e["id"], "ad": e["ad"], "alan": e["alan"], "yazilacak": e["yazilacak"]} for e in
                           sorted(eslesen.values(), key=lambda e: (-len(e["alan"]) - e["yazilacak"], e["ad"]))],
            "yeni": [{"k": r["k"], "ad": r["ad"], "kurum": r["kurum"], "rol": r["rol"], "url": r["url"], "tarih": r["tarih"],
                      "mesaj_gun": len(r["gunler"])} for r in yeni[:LISTE_AZAMI]],
            "uyari": uyari}


def _kaynak_notu(tarih_ham):
    d = baglanti_tarihi(tarih_ham)
    gun = ort.tarih_tr(d) if d else (tarih_ham or "tarih yok")
    return f"{ort.bugun_tr()} · LinkedIn bağlantı listesi: bağlantı tarihi {gun}", f"bağlantı tarihi {gun}"


def uygula(token, secimler=None):
    """secimler: {yeni: [{k, ad}], eslesen: bool (varsayılan true)}. Eşleşen kişilere temas satırı + kaynak notu yazılır, boş alanlar Doğrula'ya
    öneri olur; seçilen yeni bağlantılar yakınlık 0 ile açılır. İdempotent."""
    plan = ort.al(token, "linkedin")
    secimler = secimler or {}
    bugun = date.today()
    sonuc = {"eslesen": 0, "satir": 0, "oneri": 0, "yeni": [], "atlanan": []}
    if secimler.get("eslesen", True):
        oneriler = []
        for kid, e in plan["eslesen"].items():
            if not c.gecerli_id(kid) or not os.path.exists(os.path.join(c.KISILER, kid + ".md")):
                continue
            not_, ayirt = _kaynak_notu(e["tarih"]) if e["tarih"] else (None, None)
            n = ort.temas_satirlari_yaz(kid, [(date.fromisoformat(i), m) for i, m in e["temas"]], KANAL, bugun,
                                       kaynak_notu=not_, ayirt=ayirt, nereden=["linkedin"])
            sonuc["satir"] += n
            sonuc["eslesen"] += 1
            for alan, deger in e["alan"].items():
                oneriler.append({"kisi": kid, "alan": alan, "deger": deger, "gerekce": "LinkedIn bağlantı listesinde yazıyor; kişide bu alan boş.",
                                 "kaynak": "Kut · LinkedIn içe aktarma"})
        if oneriler:
            sonuc["oneri"] = c.cikarim_ekle(oneriler)
    dizin = ort.Dizin(c.kisileri_oku())
    for s in secimler.get("yeni") or []:
        r = plan["yeni"].get(str(s.get("k")))
        if not r:
            continue
        ham_ad = str(s.get("ad") or r["ad"])
        ad = "" if "@" in ham_ad else (ort.temiz_ad(ham_ad) or " ".join(ham_ad.split()))
        if not ad:
            sonuc["atlanan"].append(f"{r['url'] or r['ad']}: ad gerekli")
            continue
        olaylar = [(date.fromisoformat(i), m) for i, m in r["temas"]]
        kid, _ = dizin.bul(ad, r["eposta"], r["url"])
        if kid:   # bu arada ağa girmiş (aynı dosya ikinci kez): yeni dosya açma
            not_, ayirt = _kaynak_notu(r["tarih"]) if r["tarih"] else (None, None)
            sonuc["satir"] += ort.temas_satirlari_yaz(kid, olaylar, KANAL, bugun, kaynak_notu=not_, ayirt=ayirt, nereden=["linkedin"])
            continue
        kid = c.bos_slug(ad)
        satirlar = [f"{ort.tarih_tr(d)} · {KANAL} · {m}" for d, m in olaylar if d <= bugun]
        son = max((d for d, _ in olaylar if d <= bugun), default=None)
        alanlar = {"ad": ad, "foto": "", "tur": "cevre", "kurum": r["kurum"], "rol": r["rol"], "alan": [], "nereden": ["linkedin"], "yakinlik": "0",
                   "telefon": [], "eposta": r["eposta"], "linkedin": r["url"], "son_temas": son.isoformat() if son else "", "sonraki_adim": ""}
        govde = c.yeni_govde(ad, f"LinkedIn veri kopyası ({ort.bugun_tr()}); yalnız ad, kurum, rol ve tarih alındı, mesaj içeriği alınmadı.", satirlar)
        if r["tarih"]:
            govde = c.bolume_ekle(govde, "Kaynaklar", _kaynak_notu(r["tarih"])[0])
        c.kisi_yaz(kid, alanlar, govde)
        sonuc["yeni"].append(kid)
        sonuc["satir"] += len(satirlar)
        dizin.ekle(kid, ad, r["eposta"], r["url"])
    return sonuc
