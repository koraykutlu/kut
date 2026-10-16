"""Haftalık özet ("Kut sana gelir"): bu hafta kimle ilgilenmen gerektiği, tek somut adım ve yazmaya hazır taslakla.

`hazirla` saf işlevdir (veri sözlüğü → özet; dosya yazmaz, model/ağ yok). `olustur` onu çalıştırır, her kişi maddesini sonuç defterine
(`ag_sonuc`) kaydeder ve `<veri>/ozet/<YYYY-Www>.md` olarak yazar (okunur Markdown + sonda ```json kut bloğu); aynı hafta tekrar istenirse dosyayı okur.

Seçim (deterministik, açıklanabilir): `veri["bu_hafta"]` adayları (sonraki adım, ihmal, söz). Hariç kişi hiçbir maddede yoktur. Kişi başına
`ag_sonuc.ayar`: bekleme süresi dolmamışsa aday düşer, `carpan` aciliyeti büyütür/küçültür. En çok 3 kişi + en çok 3 söz. Partner/akraba ya da
günlük görüşülen kişiye ihmal maddesi çıkmaz. Sözler kullanıcının kendi verdiği/aldığı sözdür; "dinlendirme" ve çarpan onlara uygulanmaz.
"""
import json
import os
import re
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

import ag_cekirdek as c
import ag_ice_aktar as ia
import ag_sir
import ag_soz
import ag_sonuc

KISI_AZAMI = 3
SOZ_AZAMI = 3
SAKLA_HAFTA = 12            # bundan eski özet dosyası silinir
KONU_AZAMI = 60             # ihmal taslağında anılan son temas konusu
TASLAK_AZAMI = 320
HAFTA_KALIP = re.compile(r"^(\d{4})-W(\d{2})$")
DOSYA_KALIP = re.compile(r"^(\d{4})-W(\d{2})\.md$")
IHMAL_KALIP = re.compile(r"gündür temas yok", re.I)
TEMAS_SATIRI = re.compile(r"^-\s*(\d{2})\.(\d{2})\.(\d{4})\s*·\s*([^·]*?)\s*(?:·\s*(.*?))?\s*$")
UNVAN_ON = {"dr", "prof", "doc", "av", "sayin", "uzm", "yrd", "op", "mt"}   # ilk ad değildir: atlanır
UNVAN_SON = {"hoca", "bey", "hanim", "abla", "abi"}                          # ilk adla birlikte kalır ("Selin Hoca")
UNVANLAR = {"hoca", "dr", "prof", "doc", "ogr", "av", "muh", "uzm", "yrd", "op", "bey", "hanim", "abi", "abla"}   # ag_yol._UNVAN ile aynı
GENEL_KONU = {"toplanti", "gorusme", "mesajlasma", "yazisma", "arama", "gorusme yapildi", "henuz yok"}   # konu sayılmaz
_KILIT = threading.Lock()


# ---------- yardımcılar ----------
def _bugun(b=None):
    if b is None:
        return date.today()
    return b.date() if isinstance(b, datetime) else b


def hafta_anahtari(bugun=None):
    """ISO hafta anahtarı: '2026-W42'."""
    y, h, _ = _bugun(bugun).isocalendar()
    return f"{y}-W{h:02d}"


def _klasor():
    return os.path.join(c.VERI, "ozet")


def _ilk_ad(ad):
    """Hitap: ilk ad (baştaki unvanlar atlanır); 'Selin Hoca' gibi saygı eki ilk adla kalır."""
    j = str(ad or "").split()
    while len(j) > 1 and c.sade(j[0]) in UNVAN_ON:
        j.pop(0)
    if not j:
        return ""
    if len(j) > 1 and c.sade(j[1]) in UNVAN_SON:
        return f"{j[0]} {j[1]}"
    return j[0]


def _kes(s, azami):
    s = " ".join(str(s or "").split())
    if len(s) <= azami:
        return s
    kes = s[:azami - 1]
    if " " in kes and s[azami - 1] != " ":
        kes = kes.rsplit(" ", 1)[0]
    return kes.rstrip(" ,;:.-") + "…"


def _son_temas(k):
    """Gövdedeki en yeni temas satırı: (tarih, kanal, konu) ya da None. 'Kut önerisi:' satırları konu sayılmaz (Kut'un kendi notu)."""
    en = None
    for satir in (k.get("govde") or "").split("\n"):
        m = TEMAS_SATIRI.match(satir.strip())
        if not m:
            continue
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        kanal, konu = (m.group(4) or "").strip(), (m.group(5) or "").strip()
        if m.group(5) is None:   # '- 12.10.2026 · X' tek parça: X yalnız kanal adıysa kanal, değilse konu
            kanal, konu = ("", kanal) if c.sade(kanal) not in c.KANAL_NEREDEN | {"takvim", "arama", "gorusme"} else (kanal, "")
        if konu.lower().startswith("kut önerisi"):
            konu = ""
        if en is None or d >= en[0]:
            en = (d, kanal, konu)
    return en


def _konu(k):
    """İhmal taslağında anılacak son konuşma konusu (≤ 60 karakter); anlamlı konu yoksa ''. Önce en yeni temas, yoksa onun öncesi aranmaz."""
    t = _son_temas(k)
    if not t or not t[2]:
        return ""
    konu = t[2].strip(" .")
    if c.sade(konu) in GENEL_KONU or len(c.sade(konu)) < 3 or OTOMATIK_NOT.search(c.sade(konu)):
        return ""
    return _kes(konu, KONU_AZAMI)


# İçe aktarma ya da analizden gelen, konuşmayı değil ilişkiyi tarif eden üçüncü şahıs notlar ("Grup sohbetinde ders ve staj konularında yazışan bir…",
# "WhatsApp grubu üyesi"): "son konuştuğunuz … hakkında sor" kalıbına girince anlamsızlaşır; konu sayılmaz (16 Ekim 2026, gerçek kullanımda görüldü).
OTOMATIK_NOT = re.compile(r"^(grup sohbet|whatsapp grub|ortak grup|ayni grup|grupta|gruptan)|yazisan|konularinda yazis|grubu uyesi|grup uyesi|sohbet(e|te) (katil|yaz)")


def _kanal_onerisi(k):
    t = _son_temas(k)
    if t and t[1] and c.sade(t[1]) not in ("diger", "gorusme"):
        return t[1]
    if k.get("telefon"):
        return "mesaj"
    if k.get("eposta"):
        return "e-posta"
    return ""


def _yakin_mi(k, veri):
    """Partner/akraba ya da günlük görüşülen kişi: Kut bunlara 'çok zamandır konuşmadın' demez."""
    if k.get("tur") in ("partner", "akraba") or k.get("temas_sikligi") == "gunluk":
        return True
    ben = (veri.get("kisiler") or [{}])[0].get("id")
    return any(i.get("tip") in ("partner", "akraba") and {i.get("a"), i.get("b")} == {ben, k.get("id")} for i in veri.get("iliskiler") or [])


def _neden_turu(a):
    t = a.get("tur")
    if t in ("soz", "ihmal", "adim"):
        return t
    return "ihmal" if IHMAL_KALIP.search(a.get("neden") or "") else "adim"


def _adim_metni(k, a):
    adim = " ".join(str(k.get("sonraki_adim") or "").split())
    if not adim:
        adim = re.sub(r"\s*\([^()]*\)\s*$", "", a.get("neden") or "").strip()
    return adim or "Kısa bir not yaz"


# ---------- hitap ve taslak metinleri ----------
SIZ_UNVAN = {"hoca", "dr", "prof", "doc"}   # adında bunlardan biri geçen kişiye "siz" denir
SIZ_TURLER = ("siyaset", "is")              # bu türlerde yakınlık ≤ 1 ise "siz"


def hitap(kisi):
    """Kişiye hangi dille yazılır: {"selam": "Selam"|"Merhaba", "ad": hitap adı, "siz_mi": bool}. ag_yol'daki kuralla aynıdır.

    "Siz" (Merhaba, ...): tür `akademi`; adında Hoca/Dr./Prof./Doç. geçen kişi; tür `siyaset`/`is` olup yakınlığı ≤ 1 olan (tanışıklığı yeni ya da
    resmî) kişi. Diğerlerine "sen" + "Selam". Hitap adı ag_yol ile aynı biçimde: adında bir unvan (Hoca, Dr., Prof., Doç., Av., Bey, Hanım...) varsa
    unvanlı ad olduğu gibi ('Dr. Ayşe Kaya', 'Kerem Bey'); "siz"de Hoca sonda/ortada ise adın Hoca'ya kadar olan kısmı + 'Hocam' ('Selin Hoca Demir' →
    'Selin Hocam'). Unvansız adda ilk ad. Kişi sözlüğünden `ad`, `tur`, `yakinlik` okunur."""
    j = str((kisi or {}).get("ad") or "").split()
    sade = [c.sade(x) for x in j]
    try:
        yakinlik = int((kisi or {}).get("yakinlik") or 0)
    except (TypeError, ValueError):
        yakinlik = 0
    tur = (kisi or {}).get("tur")
    siz = tur == "akademi" or any(x in SIZ_UNVAN for x in sade) or (tur in SIZ_TURLER and yakinlik <= 1)
    if not j:
        return {"selam": "Merhaba" if siz else "Selam", "ad": "", "siz_mi": siz}
    unvanli = any(x in UNVANLAR for x in sade)
    if siz and "hoca" in sade:
        ad = " ".join(j[:sade.index("hoca")] + ["Hocam"])
    elif unvanli:
        ad = " ".join(j)
    else:
        ad = j[0]
    return {"selam": "Merhaba" if siz else "Selam", "ad": ad, "siz_mi": siz}


def _mesaj(h, sen, siz):
    """'sen' ya da 'siz' kalıbı: {selam} ve {ad} doldurulur. Kullanıcının kendi metni (not, adım, söz) kalıba hiç girmez."""
    return (siz if h["siz_mi"] else sen).format(selam=h["selam"], ad=h["ad"])


def _adim_ve_taslak(k, a, tur):
    """Taslak karşı tarafa gider: temas notu (kullanıcının kendine yazdığı) ve sonraki adım (kullanıcının yapılacak işi) taslağa GİRMEZ,
    yalnız kullanıcıya görünen `adim` satırında durur."""
    h = hitap(k)
    if tur == "ihmal":
        konu = _konu(k)
        taslak = _mesaj(h, "{selam} {ad}, nasılsın? Epeydir konuşmadık, aklıma geldin. Müsait olduğunda kısa bir sohbet edelim mi?",
                        "{selam} {ad}, nasılsınız? Epeydir görüşemedik, aklıma geldiniz. Uygun olduğunuzda kısa bir sohbet edelim mi?")
        return (f"Kısa bir selam yaz: son konuştuğunuz “{konu}” hakkında sor" if konu else "Kısa bir selam yaz: nasıl olduğunu sor"), taslak
    return _adim_metni(k, a), _mesaj(h, "{selam} {ad}, nasılsın? Sana bir konuda dönecektim; uygun olduğunda kısa konuşalım mı?",
                                     "{selam} {ad}, nasılsınız? Size bir konuda dönecektim; uygun olduğunuzda kısa görüşebilir miyiz?")


def _soz_bul(k, a):
    sozler = k.get("sozler") or ag_soz.oku(k.get("govde") or "")
    s = next((x for x in sozler if x.get("sira") == a.get("sira") and x.get("durum", "acik") == "acik"), None)
    if s:
        return s
    m = re.search(r"·\s*(.+)$", a.get("neden") or "")   # sözler değişmişse neden satırındaki metne düş
    return {"yon": a.get("yon") or "ben", "metin": m.group(1).strip() if m else "", "son": ""}


def _soz_maddesi(k, a):
    """Söz metni yalnız kullanıcıya görünen `adim` satırında durur; taslak karşı tarafa gideceği için nötrdür (söz metni kullanıcının kendi
    notudur ve başka şeyler de içerebilir)."""
    s = _soz_bul(k, a)
    h, metin = hitap(k), s.get("metin") or "verilen söz"
    if s.get("yon") == "o":
        adim = f"Nazikçe hatırlat: {metin}"
        taslak = _mesaj(h, "{selam} {ad}, nasılsın? Konuştuğumuz konuyu nazikçe hatırlatmak istedim; uygun olduğunda bakabilir misin?",
                        "{selam} {ad}, nasılsınız? Konuştuğumuz konuyu nazikçe hatırlatmak istedim; uygun olduğunuzda bakabilir misiniz?")
    else:
        adim = f"Sözünü yerine getir ya da yeni bir tarih ver: {metin}"
        taslak = _mesaj(h, "{selam} {ad}, nasılsın? Sana söz verdiğim konuda dönmek istedim; kısa bir güncelleme vereyim mi?",
                        "{selam} {ad}, nasılsınız? Size söz verdiğim konuda dönmek istedim; kısa bir güncelleme vermemi ister misiniz?")
    return adim, taslak, s


# ---------- hazırla (saf) ----------
def _iso(t):
    t = str(t or "").strip()
    return t if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t) else ""


def _madde(k, a, tur, adim, taslak, ayar=None, tarih=""):
    """`tarih` (ISO): sonraki adımda `sonraki_tarih`, sözde son tarih, ihmalde ''. Bildirim bu alanı ve `sonuc`u kullanır."""
    return {"tarih": _iso(tarih), "id": k["id"], "ad": k.get("ad") or k["id"], "tur": k.get("tur") or "", "neden": a.get("neden") or "", "adim": adim,
            "taslak": _kes(taslak, TASLAK_AZAMI), "kanal_onerisi": _kanal_onerisi(k), "no": None,
            "not": (ayar or {}).get("neden", ""), "neden_turu": tur, "sonuc": "bekliyor"}


def _saat():
    return datetime.now().hour


def _selam_sozu(saat):
    return "Günaydın" if 5 <= saat < 11 else "Merhaba" if 11 <= saat < 17 else "İyi akşamlar" if 17 <= saat < 22 else "İyi geceler"


def _selam(ben, kisi, soz, bos):
    """Saate duyarlı selam (okuma anındaki saat): 05–11 Günaydın, 11–17 Merhaba, 17–22 İyi akşamlar, diğer İyi geceler."""
    ad = _ilk_ad((ben or {}).get("ad"))
    ad = "" if c.sade(ad) in ("", "ben") else ad
    bas = _selam_sozu(_saat()) + (f" {ad}" if ad else "") + "."
    if bos:
        return f"{bas} Bu hafta acil bir şey yok. Ağın sakin."
    parca = [x for x in (f"{kisi} kişi" if kisi else "", f"{soz} söz" if soz else "") if x]
    return f"{bas} Bu hafta {' ve '.join(parca)} seni bekliyor."


def _soru(r, kisi):
    ad = kisi.get("ad") or r.get("kisi")
    if r.get("asama") == "yaptim":
        return f"{ad} ile nasıl geçti? İşe yaradı mı?"
    return f"{ad} için önerdiğim adımı attın mı?"


def _bekleyenler(kisiler, bugun, kayitlar):
    sonuc = []
    for r in ag_sonuc.bekleyenler(bugun, kayitlar):
        k = kisiler.get(r.get("kisi"))
        if not k or k.get("haric"):
            continue
        sonuc.append({"no": r["no"], "kisi": r["kisi"], "ad": k.get("ad") or r["kisi"], "oneri": r["oneri"], "sonuc": r["sonuc"],
                      "gun": r["gun"], "soru": _soru(r, k)})
    return sonuc


def hazirla(veri, bugun=None, kayitlar=None):
    """Haftalık özet (saf: dosya yazmaz). `kayitlar`: `ag_sonuc.oku()` çıktısı (verilmezse okunur)."""
    bugun = _bugun(bugun)
    kayitlar = ag_sonuc.oku() if kayitlar is None else kayitlar
    kisiler = {k["id"]: k for k in (veri.get("kisiler") or [])[1:] if k.get("id")}   # [0] merkez (ben)
    adaylar, sozler = [], []
    for sira, a in enumerate(veri.get("bu_hafta") or []):
        k = kisiler.get(a.get("id"))
        if not k or k.get("haric"):
            continue
        tur = _neden_turu(a)
        if tur == "soz":
            sozler.append((a.get("oncelik", 0), sira, a, k))
            continue
        if tur == "ihmal" and _yakin_mi(k, veri):
            continue
        ayar = ag_sonuc.ayar(k["id"], bugun, kayitlar)
        if ayar["bekle_gun"] > 0:
            continue
        # oncelik küçük = acil (gecikmiş negatif): 31 − oncelik pozitif aciliyet olur, çarpan onu büyütür/küçültür
        adaylar.append(((31 - a.get("oncelik", 0)) * ayar["carpan"], sira, a, k, tur, ayar))
    adaylar.sort(key=lambda x: (-x[0], x[1]))
    maddeler, gorulen = [], set()
    for _, _, a, k, tur, ayar in adaylar:
        if k["id"] in gorulen:
            continue
        gorulen.add(k["id"])
        adim, taslak = _adim_ve_taslak(k, a, tur)
        maddeler.append(_madde(k, a, tur, adim, taslak, ayar, k.get("sonraki_tarih") if tur == "adim" else ""))
        if len(maddeler) == KISI_AZAMI:
            break
    sozler.sort(key=lambda x: (x[0] >= 0, x[0], x[1]))   # gecikmiş (oncelik < 0) önce, sonra yaklaşan
    soz_maddeleri = []
    for oncelik, _, a, k in sozler[:SOZ_AZAMI]:
        adim, taslak, s = _soz_maddesi(k, a)
        m = _madde(k, a, "soz", adim, taslak, tarih=s.get("son"))
        m.pop("sonuc", None)   # sözün sonucu defterde değil, kişi dosyasındaki işaretinde tutulur
        m.update(yon=s.get("yon", ""), metin=s.get("metin", ""), son=s.get("son", ""), gecikme=max(0, -oncelik))
        soz_maddeleri.append(m)
    bos = not maddeler and not soz_maddeleri
    return {"hafta": hafta_anahtari(bugun), "tarih": bugun.isoformat(),
            "selam": _selam(veri.get("ben"), len(maddeler), len(soz_maddeleri), bos),
            "maddeler": maddeler, "sozler": soz_maddeleri, "sonuc_bekleyen": _bekleyenler(kisiler, bugun, kayitlar),
            "istatistik": ag_sonuc.istatistik(bugun, kayitlar), "bos": bos}


# ---------- Markdown (okunur) + JSON bloğu (Kut için) ----------
def _sir_ic(x):
    """Özet verisindeki tüm metinler sır süzgecinden geçer (kişi notundan gelen konu/adım sır taşıyamaz)."""
    if isinstance(x, str):
        return ag_sir.temizle(x, "haftalık özet", entropi=False)
    if isinstance(x, list):
        return [_sir_ic(i) for i in x]
    if isinstance(x, dict):
        return {k: _sir_ic(v) for k, v in x.items()}
    return x


_KACIS = re.compile(r"([\\`*_\[\]<>|~])")


def _kac(x):
    """Okunur Markdown kısmındaki kullanıcı metni: tek satır, özel karakterler (``` dahil) ve satır başı işaretleri kaçırılır (JSON bloğunu taklit edemez)."""
    x = _KACIS.sub(r"\\\1", " ".join(str(x or "").split()))
    x = re.sub(r"^([#+\-])(?=\s|$)", r"\\\1", x)
    return re.sub(r"^(\d+)([.)])(?=\s|$)", r"\1\\\2", x)


def _md(o):
    s = ["---", "visibility: private", "---", "", f"# Haftalık özet · {o['hafta']}", "", _kac(o.get("selam", "")), ""]

    def madde(i, m):
        s.append(f"### {i}. {_kac(m['ad'])}")
        if m.get("neden"):
            s.append(f"- Neden: {_kac(m['neden'])}")
        s.append(f"- Adım: {_kac(m['adim'])}")
        if m.get("tarih"):
            s.append(f"- Tarih: {m['tarih']}")
        if m.get("kanal_onerisi"):
            s.append(f"- Kanal: {_kac(m['kanal_onerisi'])}")
        if m.get("not"):
            s.append(f"- Not: {_kac(m['not'])}")
        s.extend(["", "> " + _kac(m["taslak"]), ""])

    if o.get("maddeler"):
        s.append("## Kişiler")
        for i, m in enumerate(o["maddeler"], 1):
            madde(i, m)
    if o.get("sozler"):
        s.append("## Sözler")
        for i, m in enumerate(o["sozler"], 1):
            madde(i, m)
    if o.get("sonuc_bekleyen"):
        s.append("## Sonucunu merak ettiklerim")
        s += [f"- {_kac(r['soru'])} ({_kac(r['oneri'])})" for r in o["sonuc_bekleyen"]] + [""]
    st = (o.get("istatistik") or {}).get("son_8_hafta") or {}
    if st.get("toplam"):
        oran = f", işe yarayan oranı %{round(st['oran'] * 100)}" if st.get("oran") is not None else ""
        s += ["## Son 8 hafta", f"- {st['toplam']} öneri, {st['yapilan']} tanesini yaptın, {st['ise_yarayan']} tanesi işe yaradı{oran}.", ""]
    s += ["<!-- Aşağıdaki blok Kut içindir; sonuçları sayfadan işaretle. -->", "```json kut", json.dumps(o, ensure_ascii=False), "```", ""]
    return "\n".join(s)


def _dosya_yaz(o):
    """Atomik: benzersiz geçici dosya (aynı anda iki süreç yazsa da çakışmaz) + `os.replace`."""
    os.makedirs(_klasor(), exist_ok=True)
    hedef = os.path.join(_klasor(), o["hafta"] + ".md")
    fd, gecici = tempfile.mkstemp(prefix=o["hafta"] + ".", suffix=".tmp", dir=_klasor())
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(_md(o))
        for deneme in range(6):   # Windows: tarayıcı/okuyucu anlık tutarsa PermissionError verebilir
            try:
                os.replace(gecici, hedef)
                return
            except PermissionError:
                if deneme == 5:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(gecici)
        except OSError:
            pass
        raise


def _dosya_oku(hafta):
    """Kayıtlı özet ya da None (dosya yok/bozuk)."""
    if not HAFTA_KALIP.fullmatch(hafta or ""):
        return None
    try:
        with open(os.path.join(_klasor(), hafta + ".md"), encoding="utf-8-sig") as f:
            metin = f.read()
        govde, ayrac, blok = metin.rstrip().rpartition("\n```json kut\n")   # blok dosyanın SONUNDAKİ fence'tir; okunur kısım onu taklit edemez
        o = json.loads(blok[:-4]) if ayrac and blok.endswith("\n```") else None
    except (OSError, ValueError):
        return None
    if not isinstance(o, dict) or o.get("hafta") != hafta or not isinstance(o.get("maddeler"), list) or not isinstance(o.get("sozler"), list):
        return None
    return o


def _taze(o, bugun):
    """Kayıtlı özetin canlı kısımları, her okumada: kişi dosyası artık yoksa ya da kişi sonradan hariç listesine girmişse maddesi/sözü düşer (dosya da
    güncellenir); maddelerin güncel sonucu, sonucu sorulanlar, istatistik ve saate göre selam (`bos` dahil) yeniden hesaplanır."""
    kayitlar = ag_sonuc.oku()
    sonuc = {r["no"]: r["sonuc"] for r in kayitlar}
    durum = {k["id"]: k for k in _kisi_adlari({m.get("id") for m in o["maddeler"] + o["sozler"]})}
    uygun = lambda m: m.get("id") in durum and not durum[m["id"]]["haric"]
    onceki = len(o["maddeler"]) + len(o["sozler"])
    o["maddeler"], o["sozler"] = [m for m in o["maddeler"] if uygun(m)], [m for m in o["sozler"] if uygun(m)]
    for m in o["maddeler"]:
        if m.get("no") in sonuc:
            m["sonuc"] = sonuc[m["no"]]
    kisiler = {k["id"]: k for k in _kisi_adlari({r["kisi"] for r in ag_sonuc.bekleyenler(bugun, kayitlar)})}
    o["sonuc_bekleyen"] = _bekleyenler(kisiler, bugun, kayitlar)
    o["istatistik"] = ag_sonuc.istatistik(bugun, kayitlar)
    o["bos"] = not o["maddeler"] and not o["sozler"]
    o["selam"] = _selam(c.ben(), len(o["maddeler"]), len(o["sozler"]), o["bos"])
    if len(o["maddeler"]) + len(o["sozler"]) != onceki:
        try:
            _dosya_yaz(o)   # hariç kişi kayıtlı dosyada da kalmasın
        except OSError:
            pass
    return o


def _kisi_adlari(idler):
    """Sonucu sorulacak kayıtlar için kişi adı/hariç bilgisi: [{id, ad, haric}] (kişi dosyası yoksa listeye girmez)."""
    sonuc = []
    hl = c.haric_listesi()
    for kid in idler:
        if not c.gecerli_id(kid):
            continue
        yol = os.path.join(c.KISILER, kid + ".md")
        try:
            k = c.kisi_oku(yol) if os.path.exists(yol) else None
        except OSError:
            k = None
        if k:
            sonuc.append({"id": kid, "ad": k.get("ad") or kid, "haric": c.haric_mi(k, hl)})
    return sonuc


def _eskileri_sil(bugun):
    """12 haftadan eski özet dosyaları silinir (yalnız '<YYYY>-W<hh>.md' adlıları; yeniden üretilebilir türev dosyalardır)."""
    try:
        adlar = os.listdir(_klasor())
    except OSError:
        return
    sinir = bugun - timedelta(weeks=SAKLA_HAFTA)
    for ad in adlar:
        m = DOSYA_KALIP.match(ad)
        if not m:
            continue
        try:
            pazartesi = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            continue
        if pazartesi < sinir:
            try:
                os.remove(os.path.join(_klasor(), ad))
            except OSError:
                pass


def _veri_hazirla(bugun):
    veri = c.veri_hazirla(foto_gom=False)
    if bugun != date.today():   # veri_hazirla "bugün"e göre hesaplar; başka tarih istenmişse adayları o tarihe göre yeniden kur
        veri["bu_hafta"] = c.bu_hafta(veri["kisiler"][1:], bugun)
    return veri


def olustur(bugun=None, yenile=False):
    """Bu haftanın özetini döndürür: dosya varsa okur (kayıtlar tekrar eklenmez; sonuç alanları güncellenir), yoksa ya da `yenile` ise üretir,
    kişi maddelerini sonuç defterine yazar (`no`) ve dosyaya kaydeder. Aynı haftada aynı öneri defterde bir kez durur. Eski özetleri siler."""
    bugun = _bugun(bugun)
    hafta = hafta_anahtari(bugun)
    with _KILIT:
        _eskileri_sil(bugun)
        if not yenile:
            mevcut = _dosya_oku(hafta)
            if mevcut is not None:
                return _taze(mevcut, bugun)
        o = hazirla(_veri_hazirla(bugun), bugun)
        for m in o["maddeler"]:
            try:
                m["no"] = ag_sonuc.kaydet("ozet", m["id"], m["adim"], bugun)
            except (ValueError, OSError):
                m["no"] = None
        kayitlar = ag_sonuc.oku()
        sonuc = {r["no"]: r["sonuc"] for r in kayitlar}
        for m in o["maddeler"]:
            m["sonuc"] = sonuc.get(m["no"], "bekliyor")
        o["uretildi"] = datetime.now().isoformat(timespec="seconds")
        o = _sir_ic(o)
        _dosya_yaz(o)
        return o


def son():
    """Bu haftanın kayıtlı özeti (üretmez); yoksa None."""
    bugun = date.today()
    with _KILIT:
        o = _dosya_oku(hafta_anahtari(bugun))
        return _taze(o, bugun) if o is not None else None


def goruldu(hafta):
    """Arayüz özeti gösterdi: ayarlar.json → "ozet": {"goruldu": hafta}. Diğer anahtarlar korunur."""
    m = HAFTA_KALIP.fullmatch(str(hafta or ""))
    try:
        date.fromisocalendar(int(hafta[:4]), int(hafta[-2:]), 1) if m else None   # 2026-W99 gibi var olmayan hafta reddedilir
    except ValueError:
        m = None
    if not m:
        raise ValueError("geçersiz hafta")
    a = ia.ayarlar()
    ozet = a.get("ozet") if isinstance(a.get("ozet"), dict) else {}
    a["ozet"] = {**ozet, "goruldu": hafta}
    ia.ayar_yaz(a)


def gorulen():
    """Arayüzün en son gösterdiği hafta ('' = hiç)."""
    o = ia.ayarlar().get("ozet")
    return str(o.get("goruldu") or "") if isinstance(o, dict) else ""
