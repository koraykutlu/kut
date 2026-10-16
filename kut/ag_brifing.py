"""Görüşme öncesi brifing: bir kişiyle konuşmadan önce tek sayfa (kim, nasıl tanıştınız, son konuştuklarınız, açık sözler, sonraki adım,
ortak tanıdıklar, dikkat, konuşma önerileri, Kut'un geçmiş önerileri ve sonuçları).

Yerel ve deterministiktir: model çağırmaz, ağa çıkmaz, hiçbir şey yazmaz. `brifing(veri, kid, ...)` saf işlevdir; `veri`, `c.veri_hazirla()` çıktısı
(ya da demo'nun aynı biçimdeki kurgusal verisi) olarak verilir. Yalnız parametresi `None` bırakılan girdiler (sonuçlar, hedefler, strateji)
ve yakınlığı 0 olan kişi için yol, ilgili modülden GEÇ içe aktarılarak okunur; modül yoksa ya da hata verirse o bölüm boş kalır.

Hariç kişi: `ValueError`; ayrıca başka bir kişinin brifinginde hariç kişinin adı (ortak tanıdık, dikkat, hedef/strateji/geçmiş başlıkları,
yol) görünmez. Kullanıcının kendi yazdığı metinler (temas satırları, beyanlar, sözler) olduğu gibi aktarılır.
Dil: "sen" hitabı; insanları puanlayan ifade yok ("bağ soğuyor" der, "puanı düşük" demez).
"""
import re
from datetime import date, datetime

import ag_cekirdek as c
import ag_soz

TEMAS_AZAMI = 5       # brifingteki son temas sayısı
ORTAK_AZAMI = 6       # ortak tanıdık sayısı
GECMIS_AZAMI = 5      # Kut'un geçmiş önerileri
BEYAN_AZAMI = 10      # en yeni beyanlar
KONUSMA_AZAMI = 6     # konuşma maddesi
SOZ_YAKIN_GUN = 7     # "yakında dolacak" söz eşiği (gün)
ALINTI_AZAMI = 90     # konuşma maddelerindeki alıntı uzunluğu

def _red_yazi(n):
    """"Uymuyor" kaydının notundaki "[kod] metin" → "Etiket: metin" (ag_sonuc.RED_NEDENLERI)."""
    m = re.match(r"^\[([a-z_]+)\]\s*(.*)$", str(n or ""), re.S)
    if not m:
        return n
    try:
        import ag_sonuc
        etiket = ag_sonuc.RED_NEDENLERI.get(m.group(1), (m.group(1),))[0]
    except Exception:
        etiket = m.group(1)
    return etiket + (": " + m.group(2) if m.group(2).strip() else "")


SONUC_YAZI = {"bekliyor": "Bekliyor", "yaptim": "Yaptım", "ise_yaradi": "İşe yaradı", "ise_yaramadi": "İşe yaramadı",
              "ertelendi": "Ertelendi", "atlandi": "Atlandı", "reddedildi": "Uymuyor", "yapmadim": "Yapmadım", "gecersiz": "Geçersiz / yanlış"}
KANALLAR = {"whatsapp", "telefon", "tel", "arama", "e posta", "eposta", "mail", "email", "linkedin", "x", "twitter", "instagram", "dm", "mesaj", "sms",
            "yuz yuze", "gorusme", "toplanti", "takvim", "etkinlik", "zoom", "meet", "teams", "video", "kahve", "yemek", "sohbet", "rehber",
            "telegram", "signal", "kut sohbeti"}
UNVANLAR = {"dr", "prof", "doc", "hoca", "av", "uzm", "ogr", "sayin", "mr", "mrs", "ms"}
# yönlü bağda (a, b'nin mentoru/yöneticisi/asistanı/hocasıdır) komşu a ise kişiye göre, b ise tersi
YON_ETIKET = {"mentor": ("Mentoru", "Yetiştirdiği kişi"), "yonetici": ("Yöneticisi", "Yönettiği kişi"),
              "asistan": ("Asistanı", "Asistanlığını yaptığı kişi"), "hocasi": ("Hocası", "Öğrencisi")}
TIP_AGIRLIK = {"partner": 9, "akraba": 8, "arkadas": 8, "birlikte-calisiyor": 7, "is-ortagi": 7, "mentor": 7, "hocasi": 6, "yonetici": 6,
               "asistan": 6, "tanisiyor": 3}

TEMAS_BOLUMU = re.compile(r"(?ims)^## [^\n]*temas[ \t]*(?:\n|\Z)(.*?)(?=^## |\Z)")
TEMAS_SATIRI = re.compile(r"^\s*[-*]\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:[·\-–—]\s*)?(.*?)\s*$")
ISO_TARIH = re.compile(r"\d{4}-\d{2}-\d{2}")


# ---------- küçük yardımcılar ----------
def _tarih(s):
    """Yalnız YYYY-AA-GG; geçersizse None."""
    s = str(s or "").strip()
    if not ISO_TARIH.fullmatch(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _bugun(bugun):
    if isinstance(bugun, datetime):
        return bugun.date()
    if isinstance(bugun, date):
        return bugun
    if isinstance(bugun, str) and _tarih(bugun):
        return _tarih(bugun)
    return date.today()


def _gg(d):
    """date ya da ISO metin → GG.AA.YYYY."""
    d = d if isinstance(d, date) else _tarih(d)
    return d.strftime("%d.%m.%Y") if d else ""


def _tek_satir(s):
    return " ".join(str(s or "").split())


def _kisalt(s, n=ALINTI_AZAMI):
    s = _tek_satir(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _liste(v):
    """Alan listesi: liste → temiz metinler; metin → virgülle bölünür."""
    if isinstance(v, str):
        v = v.split(",")
    return [_tek_satir(x) for x in (v or []) if _tek_satir(x)]


def _hitap(ad):
    """Cümlede kullanılacak ad: ilk ad; 'Hoca/Dr./Prof.' gibi unvanlı adlar olduğu gibi."""
    parcalar = _tek_satir(ad).split()
    if not parcalar:
        return "Kişi"
    if len(parcalar) > 1 and any(c.sade(p).rstrip(".") in UNVANLAR for p in parcalar):
        return " ".join(parcalar)
    return parcalar[0]


def _birlestir(parcalar):
    """['a', 'b', 'c'] → 'a, b ve c'."""
    parcalar = list(parcalar)
    return parcalar[0] if len(parcalar) == 1 else ", ".join(parcalar[:-1]) + " ve " + parcalar[-1]


def _tam_gecer(metin, adlar):
    """Metinde (sade, sözcük sınırıyla) adlardan biri geçiyor mu? 'Mehmet Kaya'nın' → 'mehmet kaya nin' içinde 'mehmet kaya' bulunur."""
    t = " " + c.sade(metin) + " "
    return any(f" {a} " in t for a in adlar)


def _haric_adlari(kisiler, kid, kendi_ad):
    """Hariç kişilerin sade tam adları (çok kısa adlar yanlış eşleşmesin diye 4+ karakter); brifingi yapılan kişinin adıyla aynı olanlar hariç."""
    sonuc = set()
    for k in kisiler:
        if k.get("haric") and k.get("id") != kid:
            a = c.sade(k.get("ad") or "")
            if len(a) > 3 and a != kendi_ad:
                sonuc.add(a)
    return sorted(sonuc)


# ---------- gövdeden okuma ----------
def temaslar(govde):
    """Gövdedeki '## Temas' satırları: [{tarih (ISO), kanal, metin, sira}] (dosya sırasıyla). Kanallı `- GG.AA.YYYY · kanal · metin`, kanalsız
    `- GG.AA.YYYY · metin`; '(henüz yok)' ve tarihsiz/geçersiz tarihli satırlar atlanır. İki parçalı satırda ilk parça yalnız bilinen bir kanal
    adıysa (WhatsApp, telefon, yüz yüze...) kanal sayılır; üç ve fazla parçada ilk parça kanaldır."""
    sonuc = []
    for bolum in TEMAS_BOLUMU.findall(govde or ""):
        for satir in bolum.splitlines():
            m = TEMAS_SATIRI.match(satir)
            if not m:
                continue
            try:
                d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                continue
            parcalar = [p.strip() for p in re.split(r"\s+·\s+", m.group(4)) if p.strip()]
            if len(parcalar) >= 3 or (len(parcalar) == 2 and c.sade(parcalar[0]) in KANALLAR):
                kanal, metin = parcalar[0], " · ".join(parcalar[1:])
            else:
                kanal, metin = "", " · ".join(parcalar)
            if metin.strip("()").strip().lower() == "henüz yok":
                continue
            sonuc.append({"tarih": d.isoformat(), "kanal": kanal, "metin": metin, "sira": len(sonuc)})
    return sonuc


def _beyanlar(govde):
    satirlar = [s.strip()[2:].strip() for s in c.bolum_oku(govde, c.BEYAN_BASLIK).splitlines() if s.strip().startswith("- ")]
    return [_tek_satir(s) for s in satirlar if s][-BEYAN_AZAMI:]


# ---------- sözler ----------
def _soz_sirasi(s):
    g = s.get("gun")
    if g is not None and g > 0:
        return (0, -g, s.get("sira", 0))               # gecikmiş: en çok geciken önce
    if g is not None:
        return (1, -g, s.get("sira", 0))               # tarihli: son tarihi en yakın önce
    return (2, str(s.get("tarih") or ""), s.get("sira", 0))   # tarihsiz: en eski açık önce


def _sozler(k, bugun):
    """Açık sözler: {senin: [...], onun: [...]}. Her söz: {metin, son, tarih, yazi, gun, gecikmis, sira}; gecikmiş olan başta.
    `gun` ag_soz.gecikme gibidir: pozitif = gecikti, 0 = bugün, negatif = kaç gün kaldı, tarihsiz sözde None."""
    ham = k.get("sozler")
    ham = ag_soz.oku(k.get("govde") or "") if ham is None else ham
    sonuc = {"senin": [], "onun": []}
    for s in ham:
        if not isinstance(s, dict) or s.get("durum") != "acik" or s.get("yon") not in ("ben", "o"):
            continue
        g = ag_soz.gecikme(s, bugun)
        sonuc["senin" if s["yon"] == "ben" else "onun"].append({
            "metin": _tek_satir(s.get("metin")), "son": s.get("son") or "", "tarih": s.get("tarih") or "", "yazi": ag_soz.durum_yazisi(s, bugun),
            "gun": g, "gecikmis": g is not None and g > 0, "sira": s.get("sira", 0)})
    for liste in sonuc.values():
        liste.sort(key=_soz_sirasi)
    return sonuc


# ---------- ortak tanıdıklar ----------
def _tip_etiket(tip, komsu_a_mi):
    """Komşunun kişiyle bağı, kişi açısından. Yönlü tipte A, B'nin mentoru/yöneticisi/asistanı/hocasıdır."""
    if tip in YON_ETIKET:
        return YON_ETIKET[tip][0 if komsu_a_mi else 1]
    return c.TIPLER[tip][0].split(" (")[0]


def _ortak_tanidiklar(veri, kid, merkez_id, kmap):
    """Kişinin komşularından merkeze yakınlığı ≥ 1 olan, hariç olmayan en çok 6 kişi (bir kişi bir kez, en güçlü bağıyla).
    Rakip/gerginlik ortak tanıdıklık sayılmaz (dikkat bölümünde ele alınır)."""
    en_iyi = {}
    for i in veri.get("iliskiler") or []:
        a, b, tip = i.get("a"), i.get("b"), i.get("tip")
        if kid not in (a, b) or a == b or tip not in c.TIPLER or c.TIPLER[tip][3] == "negatif":
            continue
        komsu = b if a == kid else a
        k = kmap.get(komsu)
        if not k or komsu in (kid, merkez_id) or k.get("haric") or _yakinlik(k) < 1:
            continue
        agirlik = TIP_AGIRLIK.get(tip, 1)
        if komsu not in en_iyi or agirlik > en_iyi[komsu][0]:
            en_iyi[komsu] = (agirlik, tip, a == komsu)
    sirali = sorted(en_iyi.items(), key=lambda x: (-_yakinlik(kmap[x[0]]), -x[1][0], c.sade(kmap[x[0]].get("ad") or "")))
    return [{"id": kimlik, "ad": kmap[kimlik].get("ad") or kimlik, "tip": tip, "tip_etiket": _tip_etiket(tip, komsu_a),
             "yakinlik": _yakinlik(kmap[kimlik])} for kimlik, (_, tip, komsu_a) in sirali[:ORTAK_AZAMI]]


def _yakinlik(k):
    try:
        return max(0, min(3, int(k.get("yakinlik") or 0)))
    except (TypeError, ValueError):
        return 0


# ---------- dış kaynaklar (parametre None ise geç içe aktarma) ----------
def _gec_oku(modul, islev, *args):
    """Başka modülden geç içe aktararak okur; modül yok/hata → None (çağıran boş kabul eder)."""
    try:
        mod = __import__(modul)
        return getattr(mod, islev)(*args)
    except Exception:
        return None


def _sonuclari_al(sonuclar):
    if sonuclar is None:
        sonuclar = _gec_oku("ag_sonuc", "oku")
    return [r for r in (sonuclar or []) if isinstance(r, dict)]


def _hedefleri_al(hedefler):
    if hedefler is None:
        hedefler = _gec_oku("ag_hedef", "hepsi", ("aktif", "taslak"))
    return [h for h in (hedefler or []) if isinstance(h, dict)]


def _hamleleri_al(strateji):
    if strateji is None:
        strateji = _gec_oku("ag_strateji", "son")
    hamleler = strateji.get("hamleler") if isinstance(strateji, dict) else strateji
    return [h for h in (hamleler or []) if isinstance(h, dict)]


def _yol_al(veri, kid, haric_idler, haric_adlar):
    """Yakınlığı 0 olan kişi için ag_yol.yollar(veri, kid, k=1) sonucu; modül yok/hata → None. Hariç düğüm/ad içeren yol ve metin düşer."""
    try:
        import ag_yol
        s = ag_yol.yollar(veri, kid, k=1)
    except Exception:
        return None
    if not isinstance(s, dict):
        return None
    yollar = []
    for y in s.get("yollar") or []:
        if not isinstance(y, dict) or any((d or {}).get("id") in haric_idler for d in y.get("dugumler") or []):
            continue
        y = dict(y)
        y["gerekce"] = [g for g in y.get("gerekce") or [] if not _tam_gecer(g, haric_adlar)]
        y["uyarilar"] = [u for u in y.get("uyarilar") or [] if not _tam_gecer(u, haric_adlar)]
        if _tam_gecer(y.get("taslak") or "", haric_adlar):
            y["taslak"] = ""
        yollar.append(y)
    return dict(s, yollar=yollar)


def _hedef_eslesmeleri(hedefler, k, haric_adlar):
    """Aktif/taslak hedeflerden anahtar/başlık/neden/ölçüt/gövde metni kişinin tam adını ya da kurumunu anan olanlar (aktif önce)."""
    anahtarlar = [a for a in (c.sade(k.get("ad") or ""), c.sade(k.get("kurum") or "")) if len(a) > 3]
    if not anahtarlar:
        return []
    sonuc = []
    for h in hedefler:
        if h.get("durum") not in ("aktif", "taslak") or not _tek_satir(h.get("baslik")):
            continue
        metin = " ".join([str(h.get("baslik") or ""), str(h.get("neden") or ""), str(h.get("olcut") or ""), str(h.get("govde") or ""),
                          " ".join(_liste(h.get("anahtar"))), " ".join(_liste(h.get("ilerleme")))])
        t = " " + c.sade(metin) + " "
        if any(f" {a} " in t for a in anahtarlar) and not _tam_gecer(h.get("baslik"), haric_adlar):
            sonuc.append({"id": h.get("id") or "", "baslik": _tek_satir(h["baslik"]), "durum": h["durum"]})
    return sorted(sonuc, key=lambda x: x["durum"] != "aktif")


def _strateji_eslesmeleri(hamleler, kid, haric_adlar):
    """Son strateji okumasında bu kişiyi `kim`, `kim_uzerinden` ya da kanıt olarak anan hamleler."""
    kalip = re.compile(rf"(?<![a-z0-9-]){re.escape(kid.lower())}(?![a-z0-9-])")
    sonuc = []
    for h in hamleler:
        baslik = _tek_satir(h.get("baslik"))
        if not baslik or _tam_gecer(baslik, haric_adlar):
            continue
        kanit = h.get("kanit") if isinstance(h.get("kanit"), list) else [h.get("kanit") or ""]
        if kid in (h.get("kim"), h.get("kim_uzerinden")) or any(kalip.search(str(x).lower()) for x in kanit):
            kod = h.get("sonuc") or ""
            sonuc.append({"baslik": baslik, "sonuc": SONUC_YAZI.get(kod, kod) if kod else SONUC_YAZI["bekliyor"], "sonuc_kodu": kod,
                          "ilk_adim": _tek_satir(h.get("ilk_adim")), "hedef": h.get("hedef") or ""})
    return sonuc


def _gecmis(sonuclar, kid, haric_adlar):
    """Bu kişiyle ilgili Kut önerileri ve sonuçları, en yeni 5 (tarih, sonra no, azalan)."""
    uygun = [r for r in sonuclar if r.get("kisi") == kid and _tek_satir(r.get("oneri")) and not _tam_gecer(r.get("oneri"), haric_adlar)]

    def no(r):
        try:
            return int(r.get("no") or 0)
        except (TypeError, ValueError):
            return 0
    uygun.sort(key=lambda r: (str(r.get("tarih") or ""), no(r)), reverse=True)
    sonuc = []
    for r in uygun[:GECMIS_AZAMI]:
        kod = r.get("sonuc") or "bekliyor"
        not_ = "" if _tam_gecer(r.get("not"), haric_adlar) else _tek_satir(_red_yazi(r.get("not")))
        sonuc.append({"tarih": str(r.get("tarih") or ""), "oneri": _tek_satir(r["oneri"]), "sonuc": SONUC_YAZI.get(kod, kod), "sonuc_kodu": kod,
                      "not": not_, "no": r.get("no")})
    return sonuc


# ---------- anlatım: özet ve konuşma ----------
def _ozet(ad, k, y, gun, bag, sozler, sonraki):
    kimlik = ", ".join(x for x in (_tek_satir(k.get("kurum")), _tek_satir(k.get("rol"))) if x)
    bas = ad + (f" ({kimlik})" if kimlik else "")
    ilk = f"{bas} ile henüz birebir temasın yok" if y == 0 else f"{bas} ile yakınlığınız {y}"
    parca = []
    if gun is not None:
        parca.append("son temas bugün" if gun == 0 else "son temas dün" if gun == 1 else f"son temas {gun} gün önce")
    elif y > 0:
        parca.append("kayıtlı temas yok")
    if bag:
        parca.append(f"bağ {bag}")
    cumle = ilk + ("; " + ", ".join(parca) if parca else "") + "."
    senin_gec = sum(1 for s in sozler["senin"] if s["gecikmis"])
    onun_gec = sum(1 for s in sozler["onun"] if s["gecikmis"])
    toplam = len(sozler["senin"]) + len(sozler["onun"])
    if senin_gec:
        ikinci = f"Verdiğin {'bir' if senin_gec == 1 else senin_gec} söz gecikmiş durumda."
    elif onun_gec:
        ikinci = f"Ondan beklediğin {'bir' if onun_gec == 1 else onun_gec} söz gecikmiş durumda."
    elif sonraki["adim"] and sonraki["gun"] is not None and sonraki["gun"] < 0:
        ikinci = "Planladığın sonraki adım gecikmiş durumda."
    elif sonraki["adim"] and sonraki["gun"] is not None:
        ikinci = f"Sonraki adımın: {_kisalt(sonraki['adim'], 80)} ({sonraki['yazi']})."
    elif sonraki["adim"]:
        ikinci = f"Sonraki adımın: {_kisalt(sonraki['adim'], 80)}."
    elif toplam:
        ikinci = f"{toplam} açık söz var."
    else:
        ikinci = ""
    return (cumle + " " + ikinci).strip()


def _sonraki(k, bugun):
    adim = _tek_satir(k.get("sonraki_adim"))
    t = _tarih(k.get("sonraki_tarih"))
    if not t:
        return {"adim": adim, "tarih": "", "gun": None, "yazi": ""}
    g = (t - bugun).days   # kalan gün: negatif = gecikmiş
    yazi = "bugün" if g == 0 else f"{-g} gün gecikti" if g < 0 else f"{g} gün kaldı"
    return {"adim": adim, "tarih": t.isoformat(), "gun": g, "yazi": yazi}


def _ortak_zemin(ilgiler, k):
    """Kullanıcının ilgileriyle kişinin alan/etiketlerinin kesişimi (sade eşitlik); en çok 3, ilgi alanının kendi yazımıyla."""
    onda = {c.sade(x) for x in _liste(k.get("alan")) + _liste(k.get("etiketler"))}
    gorulen, sonuc = set(), []
    for ilgi in _liste(ilgiler):
        s = c.sade(ilgi)
        if s and s in onda and s not in gorulen:
            gorulen.add(s)
            sonuc.append(ilgi)
    return sonuc[:3]


def _konusma(ad, y, sozler, sonraki, yol, temas_listesi, zemin, k, hedef_listesi, strateji_listesi):
    """Görüşmede işe yarayacak maddeler (öncelik sırasıyla, en çok 6). Boş alandan madde üretilmez."""
    hitap = _hitap(ad)
    m = []
    for s in [s for s in sozler["senin"] if s["gun"] is not None and s["gun"] >= -SOZ_YAKIN_GUN][:2]:
        if s["gecikmis"]:
            m.append(f"Gecikmiş bir sözün var: «{_kisalt(s['metin'])}» ({s['yazi']}). Görüşmede teslim et ya da yeni bir tarih ver.")
        else:
            m.append(f"Yakında dolacak bir sözün var: «{_kisalt(s['metin'])}» ({s['yazi']}). Görüşmeden önce hazırla ya da tarihi konuş.")
    for s in sozler["onun"][:2]:
        yazi = f" ({s['yazi']})" if s["yazi"] else ""
        m.append(f"{hitap} sana bir söz vermişti: «{_kisalt(s['metin'])}»{yazi}. Nazikçe hatırlat.")
    if sonraki["adim"]:
        yazi = f" ({sonraki['yazi']})" if sonraki["yazi"] else ""
        m.append(f"Planladığın sonraki adım: {_kisalt(sonraki['adim']).rstrip('.')}{yazi}. Görüşmede netleştir.")
    if y == 0 and yol and (yol.get("yollar") or []):
        d = [x for x in (yol["yollar"][0].get("dugumler") or []) if isinstance(x, dict)]
        aracilar = [_hitap(x.get("ad")) for x in d[1:-1]]
        if aracilar:
            sonra = "onunla" if len(aracilar) == 1 else f"{aracilar[0]} ile"
            m.append(f"Henüz tanışmıyorsunuz. Ona {_birlestir(aracilar)} üzerinden ulaşabilirsin; önce {sonra} konuş.")
        elif len(d) >= 2:
            m.append("Henüz tanışmıyorsunuz. Ona doğrudan yazabilirsin; kısa bir tanışma mesajı yeterli.")
    konu = next((t for t in temas_listesi if t["metin"] and not t["metin"].lower().startswith("kut önerisi")), None)
    if konu:
        m.append(f"Geçen sefer ({_gg(konu['tarih'])}) şunu konuşmuşsunuz: «{_kisalt(konu['metin'])}». Ne oldu, nasıl ilerledi diye sor.")
    if zemin:
        m.append(f"Ortak zemin: ikiniz de {_birlestir(zemin)} ile ilgileniyorsunuz. Sohbeti buradan açabilirsin.")
    verebilirim = _tek_satir(k.get("ne_verebilirim"))
    if verebilirim:
        m.append(f"Ona katkı olarak şunu sunabilirsin: {_kisalt(verebilirim).rstrip('.')}.")
    if hedef_listesi:
        m.append(f"«{_kisalt(hedef_listesi[0]['baslik'], 70)}» hedefin için ondan ne isteyeceğini netleştir.")
    bekleyen = next((h for h in strateji_listesi if not h["sonuc_kodu"] and h["ilk_adim"]), None)
    if bekleyen:
        m.append(f"Strateji okumasındaki ilk adım: {_kisalt(bekleyen['ilk_adim']).rstrip('.')}.")
    return m[:KONUSMA_AZAMI]


def _yakinlik_yazi(y):
    try:
        etiket = c.YAKINLIK_OLCUT[y]
        return etiket.split("·", 1)[1].split(":", 1)[0].strip()
    except (IndexError, TypeError):
        return ""


def _bag_durumu(y, gun, trend):
    """'soğuyor' (ihmal eşiği aşıldı ya da mesaj eğilimi düşüyor), 'ısınıyor', 'canlı' ya da ''. Yalnız bağ için; kişiyi puanlamaz."""
    esik = c.IHMAL_GUN.get(y)
    if y == 0 or gun is None:
        return ""
    if trend == "soğuyor" or (esik and gun >= esik):
        return "soğuyor"
    if trend == "ısınıyor":
        return "ısınıyor"
    return "canlı" if esik and gun <= esik // 2 else ""


# ---------- ana işlev ----------
def brifing(veri, kid, bugun=None, sonuclar=None, hedefler=None, strateji=None):
    """Kişi için görüşme öncesi brifing sözlüğü (alanlar için bkz. docs/tasarim/ulas-brifing-sonuc-ozet.md, "2. kut/ag_brifing.py").
    `veri` değiştirilmez. `sonuclar` (ag_sonuc kayıtları), `hedefler` (ag_hedef kayıtları) ve `strateji` (ag_strateji.son()) verilmezse (None)
    ilgili modülden okunur; okunamazsa boş sayılır. Hariç kişi: ValueError("Bu kişi hariç listende."); yok: ValueError("kişi bulunamadı")."""
    bugun = _bugun(bugun)
    kisiler = [k for k in (veri or {}).get("kisiler") or [] if isinstance(k, dict) and k.get("id")]
    merkez_id = ((veri or {}).get("ben") or {}).get("id") or (kisiler[0]["id"] if kisiler else "")
    k = next((x for x in kisiler if x["id"] == kid), None)
    if k is None or kid == merkez_id:
        raise ValueError("kişi bulunamadı")
    if k.get("haric"):
        raise ValueError("Bu kişi hariç listende.")
    kmap = {x["id"]: x for x in kisiler}
    ad = _tek_satir(k.get("ad")) or kid
    y = _yakinlik(k)
    haric_idler = {x["id"] for x in kisiler if x.get("haric")}
    haric_adlar = _haric_adlari(kisiler, kid, c.sade(ad))

    tum_temas = temaslar(k.get("govde"))
    son_temaslar = sorted(tum_temas, key=lambda t: (t["tarih"], t["sira"]), reverse=True)[:TEMAS_AZAMI]
    adaylar = [d for d in (_tarih(k.get("etkin_son_temas")), _tarih(k.get("son_temas")), *(_tarih(t["tarih"]) for t in tum_temas)) if d]
    gun = max(0, (bugun - max(adaylar)).days) if adaylar else None
    puan = k.get("puan") if isinstance(k.get("puan"), dict) else {}
    trend = puan.get("_trend") or ""
    bag = _bag_durumu(y, gun, trend)
    sozler = _sozler(k, bugun)
    sonraki = _sonraki(k, bugun)

    ilk_temas = min((t["tarih"] for t in tum_temas), default="") or (_tarih(k.get("wa_ilk")) or "")
    ilk_temas = ilk_temas.isoformat() if isinstance(ilk_temas, date) else ilk_temas
    nereden = []
    for x in _liste(k.get("nereden")):
        if x.lower() not in [n.lower() for n in nereden]:
            nereden.append(x)
    nasil = " ".join(p for p in (f"Nereden: {', '.join(nereden[:4])}." if nereden else "",
                                 f"İlk kayıtlı temas: {_gg(ilk_temas)}." if ilk_temas else "") if p)

    dikkat = [d["metin"] for d in (veri.get("dikkatler") or []) if isinstance(d, dict) and kid in (d.get("kisiler") or []) and d.get("metin")
              and not any(i in haric_idler for i in d.get("kisiler") or []) and not _tam_gecer(d["metin"], haric_adlar)]

    hedef_listesi = _hedef_eslesmeleri(_hedefleri_al(hedefler), k, haric_adlar)
    strateji_listesi = _strateji_eslesmeleri(_hamleleri_al(strateji), kid, haric_adlar)
    gecmis = _gecmis(_sonuclari_al(sonuclar), kid, haric_adlar)
    yol = _yol_al(veri, kid, haric_idler, haric_adlar) if y == 0 else None
    zemin = _ortak_zemin((veri.get("ben") or {}).get("ilgiler"), k)

    return {
        "kisi": {"id": kid, "ad": ad, "tur": k.get("tur") or "", "tur_ad": (c.TURLER.get(k.get("tur")) or ("", ""))[0], "kurum": _tek_satir(k.get("kurum")),
                 "rol": _tek_satir(k.get("rol")), "yakinlik": y, "yakinlik_yazi": _yakinlik_yazi(y)},
        "ozet": _ozet(ad, k, y, gun, bag, sozler, sonraki),
        "neden_onemli": _tek_satir(k.get("neden_onemli")),
        "ne_verebilirim": _tek_satir(k.get("ne_verebilirim")),
        "senin_gorusun": _tek_satir(k.get("kullanici_gorusu")),
        "beyanlar": _beyanlar(k.get("govde")),
        "son_temaslar": [{"tarih": t["tarih"], "kanal": t["kanal"], "metin": t["metin"]} for t in son_temaslar],
        "sicaklik": {"deger": puan.get("sicaklik"), "trend": trend, "son_temas_gun": gun, "bag": bag},
        "sozler": sozler,
        "sonraki": sonraki,
        "ortak_tanidiklar": _ortak_tanidiklar(veri, kid, merkez_id, kmap),
        "nasil_tanistiniz": nasil,
        "yol": yol,
        "dikkat": dikkat,
        "hedefler": hedef_listesi,
        "strateji": strateji_listesi,
        "gecmis": gecmis,
        "konusma": _konusma(ad, y, sozler, sonraki, yol, son_temaslar, zemin, k, hedef_listesi, strateji_listesi),
        "uretildi": bugun.isoformat(),
    }


# ---------- Markdown ----------
_KACIS = re.compile(r"([\\`*_\[\]<>|~])")


def _kac(s):
    """Tek satıra indirger ve Markdown özel karakterlerini kaçırır (`*`, `_`, `|`, `[`, `<`...; satır başındaki `#`, `-`, `+`, `1.` dahil)."""
    s = _KACIS.sub(r"\\\1", _tek_satir(s))
    s = re.sub(r"^([#+\-])(?=\s|$)", r"\\\1", s)            # satır başı başlık / madde işareti
    return re.sub(r"^(\d+)([.)])(?=\s|$)", r"\1\\\2", s)    # "1. " → "1\. " (numaralı liste)


def markdown(b):
    """Kopyala/Yazdır için okunur Markdown. Boş bölüm yazılmaz; her dinamik metin kaçırılır."""
    kisi = b.get("kisi") or {}
    s = [f"# Brifing: {_kac(kisi.get('ad') or '')}", ""]
    alt = [kisi.get("tur_ad"), kisi.get("kurum"), kisi.get("rol")]
    if kisi.get("yakinlik") is not None:
        alt.append(f"Yakınlık {kisi['yakinlik']}" + (f" ({kisi['yakinlik_yazi']})" if kisi.get("yakinlik_yazi") else ""))
    alt = " · ".join(_kac(x) for x in alt if x not in (None, ""))
    if alt:
        s += [alt, ""]

    def bolum(baslik, satirlar, numarali=False):
        satirlar = [x for x in satirlar if x]
        if satirlar:
            s.extend([f"## {baslik}", ""])
            s.extend(f"{i}. {x}" if numarali else f"- {x}" for i, x in enumerate(satirlar, 1))
            s.append("")

    def paragraf(baslik, metin):
        if _tek_satir(metin):
            s.extend([f"## {baslik}", "", _kac(metin), ""])

    if _tek_satir(b.get("ozet")):
        s += [_kac(b["ozet"]), ""]
    bolum("Görüşmede konuşabileceklerin", [_kac(x) for x in b.get("konusma") or []], numarali=True)

    def soz(x):
        return _kac(x.get("metin")) + (f" ({_kac(x['yazi'])})" if x.get("yazi") else "") + (f" · son: {_gg(x['son'])}" if x.get("son") else "")
    sozler = b.get("sozler") or {}
    if sozler.get("senin") or sozler.get("onun"):
        s.extend(["## Açık sözler", ""])
        for baslik, liste in (("Sen verdin", sozler.get("senin")), ("O verdi", sozler.get("onun"))):
            if liste:
                s.extend([f"**{baslik}**", ""] + [f"- {soz(x)}" for x in liste] + [""])

    sonraki = b.get("sonraki") or {}
    if _tek_satir(sonraki.get("adim")) or sonraki.get("tarih"):
        ek = " · ".join(x for x in (_gg(sonraki.get("tarih")), _tek_satir(sonraki.get("yazi"))) if x)
        paragraf("Sonraki adım", (_tek_satir(sonraki.get("adim")) or "Tarih belirlenmiş") + (f" ({ek})" if ek else ""))

    def temas(x):
        return " · ".join(p for p in (_gg(x.get("tarih")), _kac(x.get("kanal") or ""), _kac(x.get("metin") or "")) if p)
    bolum("Son temaslar", [temas(x) for x in b.get("son_temaslar") or []])
    paragraf("Nasıl tanıştınız", b.get("nasil_tanistiniz"))
    paragraf("Neden önemli", b.get("neden_onemli"))
    paragraf("Ona ne verebilirsin", b.get("ne_verebilirim"))
    paragraf("Senin görüşün", b.get("senin_gorusun"))
    bolum("Senin beyanların", [_kac(x) for x in b.get("beyanlar") or []])
    bolum("Ortak tanıdıklar", [f"{_kac(x.get('ad'))} ({_kac(x.get('tip_etiket') or '')})" if x.get("tip_etiket") else _kac(x.get("ad"))
                               for x in b.get("ortak_tanidiklar") or []])

    yol = b.get("yol") or {}
    for y in (yol.get("yollar") or [])[:1]:
        zincir = " → ".join(_kac(d.get("ad")) for d in y.get("dugumler") or [])
        bolum("Ulaşma yolu", [zincir] + [_kac(g) for g in y.get("gerekce") or []] + [f"Uyarı: {_kac(u)}" for u in y.get("uyarilar") or []]
              + ([f"Taslak: {_kac(y['taslak'])}"] if y.get("taslak") else []))
    if yol and not yol.get("yollar") and _tek_satir(yol.get("yok_nedeni")):
        paragraf("Ulaşma yolu", yol["yok_nedeni"])

    bolum("Dikkat", [_kac(x) for x in b.get("dikkat") or []])
    bolum("Hedeflerinle bağı", [_kac(x.get("baslik")) for x in b.get("hedefler") or []])
    bolum("Strateji okumasında", [f"{_kac(x.get('baslik'))} ({_kac(x.get('sonuc') or '')})" for x in b.get("strateji") or []])
    bolum("Kut'un geçmiş önerileri", [" · ".join(p for p in (_gg(x.get("tarih")), _kac(x.get("oneri")), f"**{_kac(x.get('sonuc') or '')}**"
                                                          + (f" ({_kac(x['not'])})" if x.get("not") else "")) if p) for x in b.get("gecmis") or []])
    s += ["---", "", f"Kut ile hazırlandı · {_gg(b.get('uretildi')) or '-'} · yalnız bu bilgisayarda üretildi.", ""]
    return "\n".join(s)
