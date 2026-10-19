"""Arayüz dili: Türkçe varsayılan ve kaynaktır; İngilizce isteğe bağlıdır.

Sözlük (`dil_en.json`) Türkçe metni anahtar alır: {"Kaydet": "Save", "{0} kişi": "{0} people"}. `{n}` taşıyan anahtar kalıptır
(yer tutucu herhangi bir metni yakalar). Türkçede hiçbir şey çevrilmez: kod yolları Türkçe metni olduğu gibi üretir, İngilizce
seçiliyse sayfa sözlüğü taşır ve arayüz metnini ekrana gelirken çevirir (ag_sablon.html "Dil" bölümü). Python tarafı aynı sözlüğü
MCP çıktısı ve model cevap dili için kullanır.

Veri biçimi hiç değişmez: Markdown alan adları (ad, tur, yakinlik, ## Temas, ## Sözler …) ve dosyaya yazılan her şey Türkçe kalır;
yalnız arayüz etiketi çevrilir. Seçim `ayarlar.json` → "dil" ("tr" | "en"); tarayıcıda `kut_dil` çerezi aynı seçimi kilit ekranına
taşır (kilitliyken diske yazılmaz).
"""
import json
import os
import re
import sys
from functools import lru_cache

DILLER = ("tr", "en")
VARSAYILAN = "tr"
CEREZ = "kut_dil"
_KOK = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
SOZLUK_YOLU = os.path.join(_KOK, "dil_en.json")
_YER = re.compile(r"\{(\d+)\}")


def gecerli(dil):
    return dil if dil in DILLER else None


def ayar_dili():
    """ayarlar.json → "dil"; yoksa ya da okunamazsa None (çağıran varsayılana düşer)."""
    try:
        import ag_ice_aktar   # geç içe aktarma: ayar yolu veri klasörüne bağlı
        return gecerli(ag_ice_aktar.ayarlar().get("dil"))
    except Exception:
        return None


def dil_ayarla(dil):
    import ag_ice_aktar
    if not gecerli(dil):
        raise ValueError("dil: tr ya da en olmalı")
    a = ag_ice_aktar.ayarlar()
    a["dil"] = dil
    ag_ice_aktar.ayar_yaz(a)
    return dil


def etkin():
    return ayar_dili() or VARSAYILAN


def cerezden(baslik):
    """Cookie başlığından kut_dil değeri (geçersizse None)."""
    for parca in (baslik or "").split(";"):
        ad, _, deger = parca.strip().partition("=")
        if ad == CEREZ:
            return gecerli(deger.strip())
    return None


def _surum():
    try:
        return os.path.getmtime(SOZLUK_YOLU)
    except OSError:
        return 0


def sozluk():
    """Sözlük; dosya değişince yeniden okunur (geliştirirken sunucuyu yeniden başlatmak gerekmez)."""
    return _sozluk(_surum())


@lru_cache(maxsize=2)
def _sozluk(_surum):
    with open(SOZLUK_YOLU, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if isinstance(k, str) and isinstance(v, str) and not k.startswith("_")}


def _kaliplar():
    return _kalip_listesi(_surum())


@lru_cache(maxsize=2)
def _kalip_listesi(_surum):
    liste = []
    for k, v in sozluk().items():
        if not _YER.search(k):
            continue
        sira, desen = [], []
        parcalar = re.split(r"(\{\d+\})", k)
        for i, p in enumerate(parcalar):
            m = _YER.fullmatch(p)
            if m:
                sira.append(int(m.group(1)))
                # en az bir karakter; anahtarın sonundaki (ya da yalnız noktalamadan önceki) yer tutucu boş kalabilir
                desen.append("(.*?)" if re.fullmatch(r"[.)]?", "".join(parcalar[i + 1:])) else "(.+?)")
            else:
                desen.append(re.escape(p))
        sabit = re.split(r"\{\d+\}", k)
        capa = max(sabit, key=len)
        sayisal = len("".join(sabit).strip()) < 6   # "{0} gün" gibi kısa kalıp yalnız sayı yakalar (arayüzdeki kuralın aynısı)
        liste.append((re.compile("^" + "".join(desen) + "$", re.S), sira, v, capa, sayisal, bool(CUMLE_SINIRI.search(k))))
    liste.sort(key=lambda x: -len(x[3]))
    return liste


_SAYI = re.compile(r"^[\d.,:%+\-–\s/]*$")
CUMLE_SINIRI = re.compile(r"[.!?] (?=[A-ZÇĞİÖŞÜ«\"“])|; (?=\S)")
CUMLE_BOL = re.compile(r"(?<=[.!?]) (?=[A-ZÇĞİÖŞÜ«\"“])|(?<=;) (?=\S)")


def _cevir_ic(ic, derinlik):
    """Boşluğu sadeleşmiş tek metin → çeviri ya da None (ag_sablon.html cevirIc ile aynı kurallar)."""
    s = sozluk()
    if ic in s:
        return s[ic]
    cok = bool(CUMLE_SINIRI.search(ic))
    for desen, sira, hedef, capa, sayisal, cumle in _kaliplar():
        if (capa and capa not in ic) or (cok and not cumle):   # tek cümlelik kalıp çok cümleli metni yutmaz
            continue
        e = desen.match(ic)
        if not e or (sayisal and not all(_SAYI.match(x) for x in e.groups())):
            continue

        def yer(x):
            n = int(x.group(1))
            if n not in sira:
                return ""
            parca = e.group(sira.index(n) + 1)
            return cevir(parca, "en", derinlik - 1) if derinlik > 0 else parca
        return _YER.sub(yer, hedef)
    if derinlik <= 0:
        return None
    if cok:   # cümle cümle; her parça daha kısa olduğu için özyineleme biter
        p = CUMLE_BOL.split(ic)
        if len(p) > 1:
            y = [_cevir_ic(x, derinlik) or x for x in p]
            if y != p:
                return " ".join(y)
    if ic[-1] in ".;":   # sondaki nokta
        y = _cevir_ic(ic[:-1], derinlik)
        if y is not None:
            return y + ic[-1]
    on = re.match(r"^([\d–\-.,·\s]+:?\s)(\S.*)$", ic, re.S)   # "0–2: bant metni" gibi sayı önekli satır
    if on:
        y = _cevir_ic(on.group(2), derinlik - 1)
        if y is not None:
            return on.group(1) + y
    if " · " in ic:   # birleşik satır: parça parça
        p = ic.split(" · ")
        y = [_cevir_ic(x, derinlik - 1) or x for x in p]
        if y != p:
            return " · ".join(y)
    return None


def cevir(metin, dil=None, derinlik=2):
    """Tek bir arayüz metnini çevirir (baş/son boşluk korunur). Türkçede ya da sözlükte yoksa metni aynen döner."""
    if (dil or etkin()) != "en" or not isinstance(metin, str):
        return metin
    m = re.match(r"^(\s*)(.*?)(\s*)$", metin, re.S)
    ic = re.sub(r"\s+", " ", m.group(2))
    if not ic:
        return metin
    if "\n" in m.group(2) and ic not in sozluk():   # çok satırlı metin: satır satır (arayüzdeki kuralın aynısı)
        satir = "\n".join(cevir(x, "en", derinlik) for x in m.group(2).split("\n"))
        if satir != m.group(2):
            return m.group(1) + satir + m.group(3)
    y = _cevir_ic(ic, derinlik)
    return metin if y is None else m.group(1) + _tekil(y) + m.group(3)


TEKIL = {"people": "person", "days": "day", "months": "month", "years": "year", "items": "item", "links": "link", "lines": "line",
         "inferences": "inference", "questions": "question", "suggestions": "suggestion", "promises": "promise", "candidates": "candidate",
         "goals": "goal", "events": "event", "courses": "course", "chats": "chat", "matches": "match", "connections": "connection",
         "interactions": "interaction", "meetings": "meeting", "instructors": "instructor", "msgs": "msg"}


def _tekil(s):
    """"1 days" → "1 day" (arayüzdeki kuralın aynısı)."""
    return re.sub(r"\b1 ([a-z]+)\b", lambda x: "1 " + TEKIL[x.group(1)] if x.group(1) in TEKIL else x.group(0), s)


def t(metin, *args, dil=None):
    """Kod içinden: t("Son {0} günde kayıtlı temas yok.", gun). Türkçede metin.format ile aynı sonucu verir."""
    return _YER.sub(lambda x: str(args[int(x.group(1))]) if int(x.group(1)) < len(args) else x.group(0), cevir(metin, dil))


def satirlar(metin, dil=None):
    """Çok satırlı metni (Markdown dahil) satır satır çevirir; başlık/madde işareti korunur."""
    if (dil or etkin()) != "en" or not metin:
        return metin
    cikti = []
    for satir in metin.split("\n"):
        m = re.match(r"^(\s*(?:#{1,6} |[-*] |\d+\. )?)(.*)$", satir)
        bas, govde = m.group(1), m.group(2)
        cevrilen = cevir(govde, "en")
        if cevrilen == govde and ": " in govde:   # "Etiket: değer" satırında yalnız etiket
            etiket, _, deger = govde.partition(": ")
            cevrilen = cevir(etiket, "en") + ": " + deger
        cikti.append(bas + cevrilen)
    return "\n".join(cikti)


def sayfa_dili(veri):
    """Sayfaya gömülecek nesne: Türkçede None (şablon değişmeden kalır), İngilizcede {dil, sozluk}."""
    return {"dil": "en", "sozluk": sozluk()} if veri == "en" else None
