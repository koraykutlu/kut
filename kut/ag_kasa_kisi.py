"""Kasadan kişileri al: ikinci beyin kasasındaki `kind: person` notlarını Kut kişilerine önizlemeli, onaylı aktarır.

Kasaya HİÇ yazmaz (yalnız okur); model ve ağ kullanmaz. Köprü kuralları (`ag_vault`) aynen geçerlidir: `HARIC` yolları ve Kut'un
kendi verisi okunmaz. Bunlara avenox kasasının hassas klasör kuralı eklenir (`HASSAS_KELIME`, beyin V3 `sensitive_excluded` ile aynı):
adında kasa/şifre/kimlik/finans/müşteri/özel/gizli gibi sözcük geçen klasörler hiç taranmaz, onay istenmez; `visibility: private`
notlar da alınmaz. Gerekçe: kasa bu klasörleri hafıza ve aramadan "kesin" dışarıda tutar; Kut'un onay kutusu bu garantiyi gevşetmemeli.

Eşleme: title→ad, aliases, facts.kurum/rol/son_temas → alanlar, Beyan → `## Senin beyanların` (kullanıcı beyanı), Temaslar → `## Temas`,
Çıkarım (onay bekliyor) → `cikarimlar.md` Doğrula kuyruğu (doğrudan yazılmaz), Kaynaklar → `## Kaynaklar` (+ kaynak notun yolu).
`trust: untrusted` vb. güvenilmez notta kurum, rol, aliases, Temaslar ve son_temas da doğrudan yazılmaz: hepsi Doğrula önerisi olur ve takma ad eşleşmede sayılmaz.
Mevcut kişiyle ad/alias eşleşirse birleştirir: yalnız boş alanı doldurur, satır ekler, var olanı ezmez. Yer tutucu resim üretmez;
`foto` yalnız notta kasa içindeki gerçek bir resim dosyasına açık bağlantı varsa kopyalanır (uzak URL, mutlak yol, kasa dışı ya da sembolik bağ
reddedilir); güvenilmez işaretli notun resim bağlantısı hiç izlenmez.
"""
import json
import os
import re
import unicodedata
from datetime import date
from urllib.parse import unquote

import ag_cekirdek as c
import ag_vault as v

# beyin V3 `SENSITIVE_WORDS` ile aynı (template/.claude/scripts/beyin_v3.py); orada değişirse burası da güncellenir
HASSAS_KELIME = re.compile(
    r"(?:kasa|sifre|parola|kimlik|kimlig|finans|finansal|musteri|vergi|fatura|maas|ozel|gizli|gizlilik)"
    r"(?:ler|lar)?(?:i|im|in|imiz|leri|lari)?"
    r"|(?:private|secret|password|credential)s?")
_HASSAS_KATLA = str.maketrans({"ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "ı": "i", "â": "a", "î": "i", "û": "u"})
TARAMA_AZAMI = 30000     # gezilen dosya sayısı üst sınırı
KISI_AZAMI = 500
SATIR_AZAMI = 500
BOLUM_AZAMI = 60
CIKARIM_AZAMI = 12
FOTO_AZAMI = c.FOTO_AZAMI
ON_BILGI_BASI = 4096
BASLIKLAR = {"beyan": "beyan", "cikarim": "cikarim", "temaslar": "temas", "temas": "temas", "kaynaklar": "kaynak", "kaynak": "kaynak"}
GORSEL = re.compile(r"!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]|!\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")
FOTO_ANAHTARLARI = ("foto", "photo", "image", "avatar", "resim")


def hassas_klasor_mu(ad):
    """Klasör adında kasa-sınıfı sözcük var mı (büyük/küçük harf, aksan, NFD'den bağımsız)."""
    s = unicodedata.normalize("NFC", str(ad)).replace("İ", "i").replace("I", "i").lower()
    s = unicodedata.normalize("NFC", s.replace("̇", "")).translate(_HASSAS_KATLA)
    return any(HASSAS_KELIME.fullmatch(w) for w in re.findall(r"[^\W\d_]+", s))


def _hassas_yol(goreli):
    return any(hassas_klasor_mu(p) for p in goreli.replace("\\", "/").split("/")[:-1])


# ---------- ön bilgi (JSON ya da düz YAML) ----------
def _skaler(s):
    s = s.strip()
    if s[:1] == '"':
        try:
            r = json.loads(s)
            if isinstance(r, str):
                return r
        except ValueError:
            pass
        return s.strip('"')
    if s[:1] == "'" and s.endswith("'") and len(s) > 1:
        return s[1:-1].replace("''", "'")
    s = re.split(r"(?:^|\s)#", s, maxsplit=1)[0].strip()
    return s


def _deger(s):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        return [_skaler(x) for x in re.findall(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^']|'')*'|[^,]+", s[1:-1]) if x.strip()]
    return _skaler(s)


def on_bilgi(metin):
    """(ön bilgi sözlüğü, gövde). Çözülemezse ({}, gövde). Yalnız düz YAML (tek düzey eşleme, liste) ve JSON okunur."""
    m = re.match(r"﻿?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", metin, re.S)
    if not m:
        return {}, metin
    govde, baslik = metin[m.end():], m.group(1).strip()
    if baslik.startswith("{"):
        try:
            b = json.loads(baslik)
        except ValueError:
            return {}, govde
        return (b if isinstance(b, dict) else {}), govde
    sonuc, satirlar, i = {}, baslik.splitlines(), 0
    while i < len(satirlar):
        s, i = satirlar[i], i + 1
        e = re.fullmatch(r"([^\W\d][\w-]*):[ \t]*(.*)", s)
        if not e or s.lstrip().startswith("#"):
            continue
        anahtar, deger = e.groups()
        if deger.strip():
            sonuc[anahtar] = _deger(deger)
            continue
        liste, harita = [], {}
        while i < len(satirlar) and satirlar[i].startswith((" ", "\t")):
            a = satirlar[i].strip()
            i += 1
            lm, hm = re.fullmatch(r"-\s+(.+)", a), re.fullmatch(r"([^\W\d][\w-]*):[ \t]*(.*)", a)
            if lm:
                liste.append(_skaler(lm.group(1)))
            elif hm:
                harita[hm.group(1)] = _deger(hm.group(2)) if hm.group(2).strip() else ""
        sonuc[anahtar] = liste if liste else harita if harita else None
    return sonuc, govde


def _bolumler(govde):
    """Gövdeyi 'beyan' | 'cikarim' | 'temas' | 'kaynak' bölümlerine ayırır (yorumlar atılır); değer: temiz satır listesi."""
    govde = re.sub(r"<!--.*?-->", "", govde, flags=re.S)
    cikti, mevcut = {}, None
    for satir in govde.splitlines():
        if satir.startswith("## "):
            ilk = (c.sade(satir[3:]).split() or [""])[0]
            mevcut = BASLIKLAR.get(ilk)
            continue
        if satir.startswith("#"):
            mevcut = None
            continue
        if not mevcut:
            continue
        t = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", satir).strip()
        t = re.sub(r"\s+", " ", t).lstrip("#").strip()
        if t and not t.startswith("---"):
            cikti.setdefault(mevcut, []).append(t[:SATIR_AZAMI])
    return {k: s[:BOLUM_AZAMI] for k, s in cikti.items()}


def _temas_satiri(t):
    """'2026-10-01: kahve' → '01.10.2026 · kahve'; başka biçim olduğu gibi kalır."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s*[:·\-–—]?\s*(.*)$", t)
    if m:
        try:
            date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return t, ""
        return (f"{m[3]}.{m[2]}.{m[1]} · {m[4]}" if m[4] else ""), f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\b", t)
    if m:
        try:
            date(int(m[3]), int(m[2]), int(m[1]))
            return t, f"{m[3]}-{m[2]}-{m[1]}"
        except ValueError:
            pass
    return t, ""


# ---------- fotoğraf: yalnız kasa içindeki gerçek resme açık bağlantı ----------
def _foto_adaylari(b, govde):
    for a in FOTO_ANAHTARLARI:
        x = b.get(a)
        if isinstance(x, str) and x.strip():
            yield re.sub(r"^\[\[|\]\]$", "", x.strip()).split("|")[0]
    for m in GORSEL.finditer(govde):
        yield m.group(1) or m.group(2)


def _foto_oku(kok, not_yolu, b, govde):
    """Bağlantılı resmin baytları ya da None. Kasa dışına çıkan, hariç/hassas klasördeki, sembolik, resim olmayan, büyük dosya reddedilir."""
    for ham in _foto_adaylari(b, govde):
        ref = unquote(str(ham)).strip().split("#")[0]
        if (not ref or "\x00" in ref or "://" in ref or ref.lower().startswith(("data:", "file:")) or ref.startswith(("/", "\\"))
                or re.match(r"^[A-Za-z]:", ref) or os.path.splitext(ref)[1].lower() not in c.FOTO_UZANTI):
            continue
        for taban in (os.path.dirname(not_yolu), kok):
            yol = os.path.normpath(os.path.join(taban, ref))
            if os.path.islink(yol) or not os.path.isfile(yol):
                continue
            g = v._izinli(kok, yol)   # kasa dışı, sembolik bağla çıkış, HARIC ve Kut verisi
            if not g or _hassas_yol(v._goreli(kok, g)) or os.path.getsize(g) > FOTO_AZAMI:
                continue
            with open(g, "rb") as f:
                veri = f.read(FOTO_AZAMI + 1)
            if len(veri) <= FOTO_AZAMI and (veri[:3] == b"\xff\xd8\xff" or veri[1:4] == b"PNG"):
                return veri
    return None


# ---------- tarama ----------
def _kisi_notu_mu(g):
    try:
        with open(g, "rb") as f:
            bas = f.read(ON_BILGI_BASI).decode("utf-8", "replace")
    except OSError:
        return False
    return bool(re.search(r"(?i)[\"']?\bkind[\"']?\s*:\s*[\"']?person\b", bas))


def tara(a=None):
    """Kasadaki kişi notları: {notlar: [...], hassas_klasor, ozel, okunamayan, kesildi}. Kasaya yazmaz."""
    a = a or v.ayar()
    if not a:
        raise ValueError("İkinci beyin kasası ayarlı değil (ayarlar.json → vault.yol).")
    kok = a["kok"]
    sonuc = {"notlar": [], "hassas_klasor": 0, "ozel": 0, "okunamayan": 0, "kesildi": False}
    gezilen = 0
    for dizin, altlar, dosyalar in os.walk(kok, followlinks=False):
        temiz = []
        for d in sorted(altlar):
            tam = os.path.join(dizin, d)
            if d.startswith(".") or os.path.islink(tam) or not v._izinli(kok, tam):
                continue
            if hassas_klasor_mu(d):
                sonuc["hassas_klasor"] += 1
                continue
            temiz.append(d)
        altlar[:] = temiz
        for ad in sorted(dosyalar):
            if not ad.lower().endswith(".md"):
                continue
            gezilen += 1
            if gezilen > TARAMA_AZAMI or len(sonuc["notlar"]) >= KISI_AZAMI:
                sonuc["kesildi"] = True
                return sonuc
            yol = os.path.join(dizin, ad)
            if os.path.islink(yol) or not v._izinli(kok, yol) or not _kisi_notu_mu(yol):
                continue
            metin = v._oku(kok, yol)
            if metin is None:
                sonuc["okunamayan"] += 1
                continue
            b, govde = on_bilgi(metin)
            if str(b.get("kind", "")).strip().lower() != "person":
                continue
            if str(b.get("visibility") or "internal").strip().lower() not in ("public", "internal"):
                sonuc["ozel"] += 1
                continue
            n = _not_coz(kok, yol, b, govde)
            if n:
                sonuc["notlar"].append(n)
            else:
                sonuc["okunamayan"] += 1
    return sonuc


def guvenilmez_mi(b):
    """Not 'güvenilmez' mi? avenox beyin V3 (`_trusted_record`) `trust: untrusted`, `trusted: false`, `status: untrusted`, `kind: untrusted` notlarını
    güvenilmez sayar; etiket yoksa güvenilir varsayar. Kut ek olarak `quarantined` ve tanınmayan her `trust` değerini (hata durumunda kapalı kal)
    güvenilmez sayar. Etiketsiz not güvenilirdir: avenox kişi notları kullanıcının/ajanın kendi yazdığı notlardır ve `trust` yalnız dışarıdan
    gelen içeriği işaretlemek için konur; `source` avenox'ta kaynak dosya yoludur (kaynak türü değil), bu yüzden etiket olarak kullanılmaz."""
    kotu = {"untrusted", "quarantined", "quarantine", "unverified", "false", "no", "0"}
    tr = b.get("trust")
    if tr is not None and not (isinstance(tr, str) and tr.strip().lower() in ("trusted", "")):
        return True
    td = b.get("trusted")
    if td is False or (isinstance(td, str) and td.strip().lower() in kotu):
        return True
    return any(isinstance(b.get(a), str) and b.get(a).strip().lower() in ("untrusted", "quarantined", "quarantine") for a in ("status", "kind"))


def _not_coz(kok, yol, b, govde):
    ad = re.sub(r"\s+", " ", str(b.get("title") or "")).strip()
    if not ad:
        m = re.search(r"(?m)^# +(.+)$", govde)
        ad = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    if not ad or len(ad) > 120:
        return None
    takma = b.get("aliases") or []
    takma = takma if isinstance(takma, list) else [x for x in re.split(r"[,;]", str(takma))]
    takma = [t for t in dict.fromkeys(re.sub(r"\s+", " ", str(t)).replace(",", " ").strip() for t in takma)
             if 3 <= len(t) <= 80 and c.sade(t) != c.sade(ad)][:10]
    f = b.get("facts") if isinstance(b.get("facts"), dict) else {}
    temiz = lambda x: re.sub(r"\s+", " ", str(x or "")).strip()[:SATIR_AZAMI] if not isinstance(x, (list, dict)) else ""
    son = temiz(f.get("son_temas"))
    try:
        date.fromisoformat(son)
    except ValueError:
        son = ""
    return {"yol": v._goreli(kok, yol), "ad": ad, "aliases": takma, "kurum": temiz(f.get("kurum")), "rol": temiz(f.get("rol")),
            "iliski": temiz(f.get("iliski")), "son_temas": son, "remote_allowed": str(b.get("remote_allowed")).lower() == "false", "guvenilmez": guvenilmez_mi(b),
            "bolumler": _bolumler(govde), "_foto_var": any(True for _ in _foto_adaylari(b, govde)), "_foto": lambda k=kok, y=yol, bb=b, g=govde: _foto_oku(k, y, bb, g)}


# ---------- birleştirme ----------
def _ekle(govde, baslik, satirlar, var):
    """Var olmayan satırları '## baslik' bölümüne ekler; (yeni gövde, eklenen satır sayısı)."""
    n = 0
    for s in satirlar:
        if c.sade(s) in var:
            continue
        govde = c.bolume_ekle(govde, baslik, s) if baslik != "Temas" else c.temas_ekle(govde, s)
        var.add(c.sade(s))
        n += 1
    return govde, n


def _bolum_kumesi(govde, baslik_kalibi):
    m = re.search(rf"(?msi)^## {baslik_kalibi}[^\n]*\n(.*?)(?=^## |\Z)", govde or "")
    return {c.sade(re.sub(r"^\s*[-*]\s+", "", s)) for s in (m.group(1).splitlines() if m else []) if s.strip()}


def _adlar(n):
    """Notun eşleşmede ve yinelenen-not denetiminde sayılan adları. Güvenilmez notun takma adları sayılmaz: onaysız bir not, takma ad yazarak
    başka bir kişiyle eşleşemez ya da başka bir notu 'aynı kişi' diye eleyemez (takma ad yalnız Doğrula önerisi olur)."""
    return {c.sade(n["ad"])} | (set() if n.get("guvenilmez") else {c.sade(t) for t in n["aliases"]})


def _esle(n, kisiler):
    """Notun Kut kişisi: önce kaynak yolu satırı, sonra ad = ad/alias (güvenilmez notta takma ad sayılmaz). (kişi | None, belirsiz mi)"""
    yol_satiri = "Kasa notu: " + n["yol"]
    ad, takmalar = c.sade(n["ad"]), _adlar(n) - {c.sade(n["ad"])}
    bulunan = []
    for k in kisiler:
        k_ad, k_takma = c.sade(k.get("ad")), {c.sade(t) for t in c.liste_yap(k.get("aliases"))}
        if yol_satiri in (k.get("govde") or "") or ad == k_ad or ad in k_takma or k_ad in takmalar:
            bulunan.append(k)
    return (bulunan[0] if len(bulunan) == 1 else None), len(bulunan) > 1


def birlestir(n, k, bugun=None):
    """Notu Kut kişisine (k=None: yeni) uygular, YAZMAZ. Dönen: {alanlar, govde, degisiklik, cikarimlar, foto}."""
    bugun = bugun or date.today().strftime("%d.%m.%Y")
    yeni = k is None
    alanlar = {"ad": n["ad"], "tur": "cevre", "yakinlik": "0", "foto": ""} if yeni else {a: x for a, x in k.items() if a not in ("govde", "id")}
    govde = c.yeni_govde(n["ad"], f"Kasa notu: {n['yol']} ({bugun})") if yeni else k.get("govde", "")
    deg, bol = [], n["bolumler"]
    guvenilmez = bool(n.get("guvenilmez"))
    oneri = []   # güvenilmez notta doğrudan yazılmayan alanlar: Doğrula önerisi [{alan, deger}] (kullanıcı onaylayana kadar kişi dosyasına girmez)
    onek = "Kasa notu güvenilmez işaretli; şunu doğrula: "
    for alan in ("kurum", "rol"):
        if n[alan] and not str(alanlar.get(alan) or "").strip():
            if guvenilmez:
                oneri.append({"alan": alan, "deger": n[alan]})
                continue
            alanlar[alan] = n[alan]
            deg.append(f"{alan}: {n[alan]}")
    eski_takma = c.liste_yap(alanlar.get("aliases"))
    mevcut_ad = {c.sade(alanlar.get("ad"))} | {c.sade(t) for t in eski_takma}
    ek = [t for t in n["aliases"] if c.sade(t) not in mevcut_ad]
    if ek and guvenilmez:
        oneri += [{"alan": "hakkinda", "deger": f"{onek}takma ad: {t}"} for t in ek]
    elif ek:
        alanlar["aliases"] = eski_takma + ek
        deg.append("takma ad: " + ", ".join(ek))
    if n["remote_allowed"] and not alanlar.get("remote_allowed"):
        alanlar["remote_allowed"] = "false"
        deg.append("uzak modele gitmez (kasadaki işaret)")
    beyan = list(bol.get("beyan", []))
    if n["iliski"]:
        beyan.append(f"İlişki (kasa notunun facts alanı): {n['iliski']}")
    if guvenilmez:   # güvenilmez/karantina etiketli notun "Beyan" satırları kullanıcı beyanı DEĞİLDİR: Doğrula önerisi olur
        oneri += [{"alan": "hakkinda", "deger": onek + t} for t in beyan]
        beyan = []
    govde, s = _ekle(govde, c.BEYAN_BASLIK, beyan, _bolum_kumesi(govde, re.escape(c.BEYAN_BASLIK)))
    if s:
        deg.append(f"{s} beyan")
    temas, tarihler = [], []
    for t in bol.get("temas", []):
        satir, tarih = _temas_satiri(t)
        if satir:
            temas.append(satir)
            if tarih:
                tarihler.append(tarih)
    if guvenilmez:   # temas satırları ve son temas tarihi de (zaman çizelgesini ve "Bu hafta" ihmal hesabını etkiler) Doğrula önerisi olur
        var = _bolum_kumesi(govde, r"[^\n]*temas")
        oneri += [{"alan": "hakkinda", "deger": f"{onek}temas kaydı: {t}"} for t in temas if c.sade(t) not in var]
        temas = []
    govde, s = _ekle(govde, "Temas", temas, _bolum_kumesi(govde, r"[^\n]*temas"))
    if s:
        deg.append(f"{s} temas")
    son = n["son_temas"] or (max(tarihler) if tarihler else "")
    if son and not str(alanlar.get("son_temas") or "").strip():
        if guvenilmez:
            oneri.append({"alan": "hakkinda", "deger": f"{onek}son temas tarihi: {son}"})
        else:
            alanlar["son_temas"] = son
            deg.append(f"son temas: {son}")
    if guvenilmez:
        deg.append(f"{len(oneri)} alan/satır Doğrula'ya düştü (not güvenilmez işaretli)" if oneri else "not güvenilmez işaretli")
    kaynaklar = ["Kasa notu: " + n["yol"]] + bol.get("kaynak", [])
    govde, s = _ekle(govde, "Kaynaklar", kaynaklar, _bolum_kumesi(govde, "Kaynaklar"))
    if s:
        deg.append("kaynak bağlantısı")
    foto = None
    if not str(alanlar.get("foto") or "").strip() or c.foto_yolu(alanlar.get("foto")) is None:
        if guvenilmez:   # güvenilmez notun resim bağlantısı hiç izlenmez (kurum/rol gibi onaysız kişiye girmez)
            if n.get("_foto_var", True):
                deg.append("fotoğraf alınmadı (not güvenilmez işaretli)")
        else:
            foto = n["_foto"]()
            if foto:
                deg.append("fotoğraf (kasadaki resim)")
    cikarimlar = oneri + [{"alan": "hakkinda", "deger": t} for t in bol.get("cikarim", []) if "reddedildi" not in c.sade(t).split()]
    cikarimlar = cikarimlar[:CIKARIM_AZAMI]
    return {"alanlar": alanlar, "govde": govde, "degisiklik": deg, "cikarimlar": cikarimlar, "foto": foto}


def _cikarim_yeni(kid, ogeler, yol, mevcut):
    """ogeler: [{alan, deger}] (alan: hakkinda | kurum | rol). Aynı kişi/alan/değer herhangi bir durumda kuyrukta varsa (onaylanmış olsa da) tekrar eklenmez."""
    var = {(r["kisi"], r["alan"], c.sade(r["deger"])) for r in mevcut}
    return [{"kisi": kid, "alan": o["alan"], "deger": o["deger"], "kaynak": yol, "gerekce": "Kasa notu: Çıkarım (onay bekliyor) bölümü; kullanıcı onaylayana kadar olgu değil"}
            for o in ogeler if (kid, o["alan"], c.sade(o["deger"])) not in var]


def plan(a=None):
    """Önizleme: yazmadan her not için yapılacağı hesaplar."""
    t = tara(a)
    kisiler = c.kisileri_oku()
    ben = c.sade(c.ben().get("ad"))
    mevcut_cikarim = c.cikarimlari_oku()
    satirlar, alinan = [], []   # alinan: bu turda "yeni" olarak sayılan notların ad kümeleri (yinelenen not engeli)
    for n in t["notlar"]:
        kayit = {"yol": n["yol"], "ad": n["ad"], "durum": "", "neden": "", "degisiklik": [], "cikarim": 0, "foto": False}
        adlar = _adlar(n)
        if c.sade(n["ad"]) == ben:
            kayit.update(durum="atla", neden="Bu sensin (Ben); kasadaki kendi notun içe alınmaz.")
        elif any(adlar & x for x in alinan):
            kayit.update(durum="atla", neden="Aynı kişi için kasada başka bir not var.")
        else:
            k, belirsiz = _esle(n, kisiler)
            if belirsiz:
                kayit.update(durum="atla", neden="Ağda birden çok kişiyle eşleşiyor; karışmasın diye atlandı.")
            else:
                s = birlestir(n, k)
                kid = k["id"] if k else None
                yeni_c = _cikarim_yeni(kid or "x", s["cikarimlar"], n["yol"], mevcut_cikarim) if k else _cikarim_yeni("x", s["cikarimlar"], n["yol"], [])
                kayit["cikarim"] = len(yeni_c)
                kayit["foto"] = bool(s["foto"])
                kayit["degisiklik"] = s["degisiklik"] + ([f"{len(yeni_c)} çıkarım (Doğrula kuyruğu)"] if yeni_c else [])
                kayit["durum"] = "yeni" if not k else ("guncelleme" if kayit["degisiklik"] else "guncel")
                kayit["kid"] = kid
                alinan.append(adlar)
        satirlar.append(kayit)
    say = lambda d: sum(1 for x in satirlar if x["durum"] == d)
    return {"etkin": True, "bulunan": len(satirlar), "yeni": say("yeni"), "guncelleme": say("guncelleme"), "guncel": say("guncel"),
            "atlanan": say("atla"), "hassas_klasor": t["hassas_klasor"], "ozel": t["ozel"], "okunamayan": t["okunamayan"],
            "kesildi": t["kesildi"], "kisiler": [{a: x for a, x in r.items() if a != "kid"} for r in satirlar], "_notlar": t["notlar"]}


def onizle(a=None):
    """`plan`ın arayüze gidecek hâli (iç not nesneleri olmadan)."""
    p = plan(a)
    p.pop("_notlar")
    return p


def al(yollar, a=None):
    """Onaylanan notları Kut'a yazar. `yollar`: önizlemedeki kasa yolları; taramada bulunmayan her yol (kasa dışı, `..`, hassas) reddedilir.
    Yazım öncesi mevcut kişi `arsiv/surum/`'a kopyalanır. Kasaya yazılmaz."""
    if not isinstance(yollar, list) or not yollar:
        raise ValueError("Önce önizlemeden en az bir kişi seç.")
    p = plan(a)
    notlar = {n["yol"]: n for n in p.pop("_notlar")}
    durum = {r["yol"]: r for r in p["kisiler"]}
    sonuc = {"yeni": 0, "guncellenen": 0, "cikarim": 0, "foto": 0, "reddedilen": []}
    for yol in dict.fromkeys(x for x in yollar if isinstance(x, str)):
        n, r = notlar.get(yol), durum.get(yol)
        if not n or not r or r["durum"] in ("atla", "guncel"):
            sonuc["reddedilen"].append(yol)
            continue
        kisiler = c.kisileri_oku()   # önceki not aynı turda kişi eklemiş olabilir
        k, belirsiz = _esle(n, kisiler)
        if belirsiz:
            sonuc["reddedilen"].append(yol)
            continue
        s = birlestir(n, k)
        if k:
            c.surum_al(k["id"])
            kid = k["id"]
        else:
            kid = c.bos_slug(n["ad"])
        if s["foto"]:
            s["alanlar"]["foto"] = c.foto_kaydet(kid, s["foto"])
            sonuc["foto"] += 1
        c.kisi_yaz(kid, s["alanlar"], s["govde"])
        yeni_c = _cikarim_yeni(kid, s["cikarimlar"], n["yol"], c.cikarimlari_oku())
        if yeni_c:
            sonuc["cikarim"] += c.cikarim_ekle(yeni_c)
        sonuc["guncellenen" if k else "yeni"] += 1
    return sonuc
