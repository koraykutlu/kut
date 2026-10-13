"""Veri entegrasyonlarının (takvim .ics, LinkedIn CSV, ders listesi) ortak parçaları. Ağ yok, model yok.

İlkeler (YOL-HARITASI "Veri entegrasyonları"): kişi + temas olayına normalize et, içerik değil üst veri; önizleme hiçbir şey yazmaz,
yazım yalnız kullanıcı onayıyla; ham dosya saklanmaz (önizleme sonucu yalnız bellekte, kısa süre durur).
"""
import os
import re
import contextlib
import secrets
import threading
import time
from datetime import date, datetime

import ag_cekirdek as c
import ag_kaynak as kn

BEKLEME_SURESI = 30 * 60
BEKLEME_AZAMI = 6
_bekleyen = {}   # token → (tur, zaman, veri): yalnız bellekte; diske yazılmaz
_bekleyen_kilidi = threading.Lock()   # önizlemeler genel veri kilidi dışında çalışır: bekleyen sözlüğü kendi küçük kilidini kullanır
_okuma_kilidi = None


def okuma_kilidi_ayarla(kilit):
    """Sunucu, kişi dosyalarını yazanların tuttuğu genel veri kilidini verir. Önizleme (yazmaz) ağır ayrıştırmayı kilitsiz yapar,
    yalnız kişi dosyalarını okuduğu kısa bölümü bu kilit altında çalıştırır (yarım yazılmış dosya okumasın)."""
    global _okuma_kilidi
    _okuma_kilidi = kilit


def okuma_kilidi():
    return _okuma_kilidi if _okuma_kilidi is not None else contextlib.nullcontext()


def sakla(tur, veri):
    """Önizleme sonucunu bellekte tutar, onay için belirteç verir. Eskiler ve fazlası atılır."""
    simdi = time.time()
    with _bekleyen_kilidi:
        for t in [t for t, (_, z, _) in _bekleyen.items() if simdi - z > BEKLEME_SURESI]:
            _bekleyen.pop(t, None)
        while len(_bekleyen) >= BEKLEME_AZAMI:
            _bekleyen.pop(min(_bekleyen, key=lambda t: _bekleyen[t][1]), None)
        t = secrets.token_urlsafe(12)
        _bekleyen[t] = (tur, simdi, veri)
    return t


def al(token, tur):
    with _bekleyen_kilidi:
        kayit = _bekleyen.get(str(token or ""))
    if not kayit or kayit[0] != tur or time.time() - kayit[1] > BEKLEME_SURESI:
        raise ValueError("Önizleme süresi doldu ya da bulunamadı; dosyayı yeniden yükle.")
    return kayit[2]


def birak(token):
    with _bekleyen_kilidi:
        _bekleyen.pop(str(token or ""), None)


# ---------- kimlik: e-posta, LinkedIn adresi, ad ----------
EPOSTA = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def eposta_norm(s):
    m = EPOSTA.search(str(s or ""))
    return m.group(0).lower() if m else ""


LINKEDIN_ADRES = re.compile(r"^https?://(?:[\w-]+\.)?linkedin\.com/in/([^/?#\s]+)", re.I)


def formul_temizle(s):
    """Boşlukları sadeleştirir; baştaki `=`, `+`, `-`, `@` (ve sekme/satır başı) karakterlerini atar: CSV/tablo programlarında formül olarak
    çalışabilecek hücre başlangıcı (savunma derinliği; Kut CSV dışa aktarmaz)."""
    s = " ".join(str(s or "").split())
    return s.lstrip("=+-@\t\r ").strip()


def linkedin_slug(url):
    """'https://tr.linkedin.com/in/Ada-Deneme-123/?x=1' → 'ada-deneme-123' (yalnız LinkedIn'in kendi /in/ profilleri; adres baştan çıpalı,
    'https://kotu.example/?u=linkedin.com/in/x' ya da 'linkedin.com.kotu.example/in/x' kabul edilmez)."""
    m = LINKEDIN_ADRES.match(str(url or "").strip())
    if not m:
        return ""
    try:
        from urllib.parse import unquote
        return unquote(m.group(1)).strip().lower()
    except ValueError:
        return m.group(1).strip().lower()


SERTIFIKA = {"mba", "pmp", "phd", "cpa", "cfa", "msc", "bsc", "md", "mph", "cissp", "csm", "pmi", "mcse", "frm", "dds"}


def _sertifika_mi(parca):
    p = c.sade(parca).replace(" ", "")
    return p in SERTIFIKA


def temiz_ad(ad):
    """Takvim/LinkedIn adındaki sertifika, emoji ve fazla boşluğu atar; 'Soyad, Ad' (Outlook) → 'Ad Soyad'.
    'Ada Deneme, MBA 🚀' → 'Ada Deneme'; 'Deneme, Ada' → 'Ada Deneme'; 'Ada Deneme MBA' → 'Ada Deneme'."""
    ad = re.sub(r"\(.*?\)|\[.*?\]", " ", str(ad or ""))
    parcalar = [p.strip() for p in ad.split(",") if p.strip()]
    if len(parcalar) >= 2 and not _sertifika_mi(parcalar[1]) and len(parcalar[0].split()) <= 2 and len(parcalar[1].split()) <= 3:
        ad = f"{parcalar[1]} {parcalar[0]}"
    else:
        ad = parcalar[0] if parcalar else ""
    ad = "".join(ch for ch in ad if ch.isalpha() or ch in " '’.-")
    ad = " ".join(ad.split()).strip(" .-'’")
    while len(ad.split()) > 2 and _sertifika_mi(ad.split()[-1]):
        ad = ad.rsplit(" ", 1)[0]
    return kn.tr_ad(ad) if ad and ad == ad.upper() else ad


class Dizin:
    """Mevcut kişilerde e-posta / LinkedIn / ad / takma ad (aliases) araması. Belirsiz (birden çok kişi) eşleşme eşleşme sayılmaz."""

    def __init__(self, kisiler):
        self.kisiler = kisiler
        self.eposta, self.slug, self.ad, self.ilk = {}, {}, {}, {}   # ilk: ilk ad → [(id, sade parçalar)] (alt küme araması hızlı kalsın)
        for k in kisiler:
            e = eposta_norm(k.get("eposta"))
            if e:
                self.eposta.setdefault(e, set()).add(k["id"])
            s = linkedin_slug(k.get("linkedin"))
            if s:
                self.slug.setdefault(s, set()).add(k["id"])
            for ad in [k.get("ad")] + c.liste_yap(k.get("aliases")):
                if c.sade(ad or ""):
                    self.ad.setdefault(c.sade(ad), set()).add(k["id"])
            parcalar = c.sade(k.get("ad") or "").split()
            if parcalar:
                self.ilk.setdefault(parcalar[0], []).append((k["id"], parcalar))

    def ekle(self, kid, ad="", eposta="", linkedin=""):
        """Yeni açılan kişiyi dizine işler (binlerce kişi eklerken dizini baştan kurmamak için)."""
        self.kisiler.append({"id": kid, "ad": ad})
        if eposta_norm(eposta):
            self.eposta.setdefault(eposta_norm(eposta), set()).add(kid)
        if linkedin_slug(linkedin):
            self.slug.setdefault(linkedin_slug(linkedin), set()).add(kid)
        if c.sade(ad):
            self.ad.setdefault(c.sade(ad), set()).add(kid)
            self.ilk.setdefault(c.sade(ad).split()[0], []).append((kid, c.sade(ad).split()))

    @staticmethod
    def _tek(kume):
        return next(iter(kume)) if kume and len(kume) == 1 else None

    def bul(self, ad="", eposta="", linkedin=""):
        """(kisi_id | None, neden). neden: 'eposta' | 'linkedin' | 'ad' | 'belirsiz' | ''."""
        e, s = eposta_norm(eposta), linkedin_slug(linkedin)
        if e and e in self.eposta:
            t = self._tek(self.eposta[e])
            return (t, "eposta") if t else (None, "belirsiz")
        if s and s in self.slug:
            t = self._tek(self.slug[s])
            return (t, "linkedin") if t else (None, "belirsiz")
        ad = temiz_ad(ad)
        sade = c.sade(ad)
        if not sade:
            return None, ""
        if sade in self.ad:
            t = self._tek(self.ad[sade])
            return (t, "ad") if t else (None, "belirsiz")
        # "Ada Deneme" ↔ "Ada Deneme Örnek" (ilk ad aynı, en az iki parça, sıralı alt küme); yalnız tek aday
        p = sade.split()
        adaylar = {i for i, q in self.ilk.get(p[0], []) if kn._ad_alt_kume(p, q)}
        if len(adaylar) == 1:
            return next(iter(adaylar)), "ad"
        return (None, "belirsiz") if adaylar else (None, "")


def ben_kimligi(ek_adlar=(), ek_epostalar=()):
    """(sade adlar, e-postalar): kendini takvimden/mesajlardan çıkarmak için. Kaynaklar: ayarlar.json (ben_adlari, ben_epostalari),
    ben.md (ad, eposta)."""
    import ag_ice_aktar as ia
    a = ia.ayarlar()
    b = c.ben()
    adlar = {c.sade(x) for x in list(ia.ben_adlari_al()) + list(ek_adlar) if c.sade(x)}
    epostalar = {eposta_norm(x) for x in list(a.get("ben_epostalari") or []) + [b.get("eposta")] + list(ek_epostalar) if eposta_norm(x)}
    return adlar, epostalar


def ben_epostasi_kaydet(epostalar):
    import ag_ice_aktar as ia
    yeni = sorted({eposta_norm(x) for x in epostalar if eposta_norm(x)})
    if not yeni:
        return
    a = ia.ayarlar()
    a["ben_epostalari"] = sorted(set(a.get("ben_epostalari") or []) | set(yeni))
    ia.ayar_yaz(a)


# ---------- yazım ----------
def tarih_tr(d):
    return d.strftime("%d.%m.%Y")


def _tarihli_say(govde, tarih_metni, kanal):
    """Temas bölümünde 'GG.AA.YYYY · kanal' ile başlayan satır sayısı (başlık ne olursa olsun: aynı gün-kanal tek olay sayılır)."""
    onek = f"- {tarih_metni} · {kanal}"
    return sum(1 for l in govde.split("\n") if l.startswith(onek))


def temas_satirlari_yaz(kid, olaylar, kanal, bugun=None, yaz=True, kaynak_notu=None, ayirt=None, nereden=()):
    """olaylar: [(date, metin)]. Aynı kişide aynı gün ve kanalda zaten yazılı olay sayısı kadarı atlanır (idempotent: dosyayı iki kez
    yüklemek ikinci kez yazmaz). son_temas yalnız ileri gider ve bugünü aşmaz. kaynak_notu: '## Kaynaklar'a (içinde `ayirt` yoksa)
    eklenecek satır; nereden: kişinin 'nereden' listesine eklenecekler. Tek yazımda, yazım öncesi sürüm kopyasıyla.
    Dönen: yazılan temas satırı sayısı (yaz=False: yazılacak sayı, dosya değişmez)."""
    bugun = bugun or date.today()
    yol = os.path.join(c.KISILER, kid + ".md")
    k = c.kisi_oku(yol)
    govde = k.pop("govde")
    yazilan, say = 0, {}
    for d, metin in sorted(olaylar, key=lambda x: x[0]):
        if d > bugun:
            continue
        tm = tarih_tr(d)
        say[tm] = say.get(tm, 0) + 1
        if say[tm] <= _tarihli_say(govde, tm, kanal):
            continue
        govde = c.temas_ekle(govde, f"{tm} · {kanal} · {metin}")
        yazilan += 1
    degisti = bool(yazilan)
    if kaynak_notu and (ayirt or kaynak_notu) not in c.bolum_oku(govde, "Kaynaklar"):
        govde = c.bolume_ekle(govde, "Kaynaklar", kaynak_notu)
        degisti = True
    yeni_nereden = sorted(set(c.liste_yap(k.get("nereden"))) | set(nereden))
    if nereden and yeni_nereden != sorted(set(c.liste_yap(k.get("nereden")))):
        k["nereden"] = yeni_nereden
        degisti = True
    if not degisti or not yaz:
        return yazilan   # yaz=False: yalnız ne kadar yazılacağını söyler, dosya değişmez
    sonlar = [d for d, _ in olaylar if d <= bugun]
    if sonlar and yazilan and (not k.get("son_temas") or max(sonlar).isoformat() > k["son_temas"]):
        k["son_temas"] = max(sonlar).isoformat()
    c.surum_al(kid)
    c.kisi_yaz(kid, k, govde)
    return yazilan


def haric_mi(kurum="", rol="", liste=None):
    return c.haric_mi({"kurum": kurum, "rol": rol}, liste)


def bugun_tr():
    return datetime.now().strftime("%d.%m.%Y")
