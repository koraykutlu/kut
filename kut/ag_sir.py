"""Sır kapısı: API anahtarı, parola, token gibi değerleri uzak modele gitmeden ve Kut'un kendi notlarına yazılmadan önce [gizlendi] yapar.
Yalnız SAYI tutulur/yazılır, değer asla. URL-kodlu (%74oken=...) biçimler çözülerek aranır; yalnız kodlu halde geçen sırrın bulunduğu parça
(boşluksuz öbek) orijinalde komple gizlenir. Kullanıcının ham dosyalarına dokunulmaz; bu yalnız kopya/istem/yazma yolunda çalışır."""
import math
import re
import sys
from urllib.parse import unquote

GIZLI = "[gizlendi]"
TOPLAM = 0   # süreç boyunca gizlenen sır sayısı (yalnız sayı)

_S, _I = "[sş]", "[iıİI]"   # Türkçe i/İ/ı, s/ş
_ANAHTAR_GUCLU = rf"api[_\-.]?key|apikey|secret|passw(?:or)?d|passwd|pwd|parola|{_S}{_I}fre|token|(?<![A-Za-z])sig(?:nature)?|credential|private[_\-.]?key|access[_\-.]?key"
_ANAHTAR_ZAYIF = r"auth|key|authorization"

_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|\Z)", re.S)
_URL_PAROLA = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s:/@\[\]]+:)([^\s@/]+)(@)", re.I)
_BEARER = re.compile(r"(\bbearer\s+)(?!\[gizlendi\])[A-Za-z0-9._~+/=\-]{8,}", re.I)
_ATAMA = re.compile(
    rf"(?<![\w])((?:[\w.\-]*?)(?P<k>{_ANAHTAR_GUCLU}|{_ANAHTAR_ZAYIF}))(?P<q1>[\"']?)(?P<ayr>[ \t]*[=:][ \t]*)(?P<q2>[\"']?)"
    rf"(?:(?:bearer|basic|token)[ \t]+)?(?P<v>[^\s\"'<>&;,]{{3,}})", re.I)
_ONEK = re.compile(
    r"\b(?:sk-ant-[A-Za-z0-9_\-]{10,}|sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[bpasr]-[A-Za-z0-9\-]{10,}"
    r"|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|glpat-[A-Za-z0-9_\-]{16,}|npm_[A-Za-z0-9]{30,}|SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}"
    r"|(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,})")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}")
_UZUN = re.compile(r"(?<![A-Za-z0-9_+/=\-])[A-Za-z0-9_+/=\-]{32,}(?![A-Za-z0-9_+/=\-])")


def _entropi(s):
    return -sum(s.count(ch) / len(s) * math.log2(s.count(ch) / len(s)) for ch in set(s))


def _rastgele_mi(t):
    """≥32 karakterlik öbek anahtar gibi mi? Düz kelime/slug/yol değil: harf+rakam karışık ve yüksek entropi."""
    t = t.strip("-=_")
    if len(t) < 32 or not re.search(r"\d", t) or not re.search(r"[A-Za-z]", t):
        return False
    if re.fullmatch(r"[0-9a-fA-F]+", t):
        return _entropi(t) >= 3.3
    parcalar = [p for p in re.split(r"[-/_+=]", t) if p]
    if len(parcalar) >= 3 and sum(bool(re.fullmatch(r"[a-zçğıöşü]{3,}", p)) for p in parcalar) * 2 >= len(parcalar):   # URL yolu / slug
        return False
    sinif = sum(bool(re.search(p, t)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[_+/=\-]"))
    return sinif >= 3 and _entropi(t) >= 4.0 and t.count("-") < len(t) // 6


def _atama_degistir(m):
    k, v, ayr = m.group("k").lower(), m.group("v"), m.group("ayr").strip()
    if v.startswith("[") or v.lower().startswith(("http://", "https://")) and "@" not in v:
        return m.group(0)
    zayif = re.fullmatch(_ANAHTAR_ZAYIF, k) is not None
    if zayif and not (len(v) >= 8 and re.search(r"\d", v) and re.search(r"[A-Za-z]", v)):   # "key: değer", "auth: evet" gibi düz kelime
        return m.group(0)
    if ayr == ":" and not zayif and len(v) < 4:
        return m.group(0)
    return m.group(0)[:m.start("v") - m.start(0)] + GIZLI


def _yol_mu(metin, m):
    """Eşleşme bir URL / dosya yolu / alan adı öbeğinin içinde mi? (entropi kuralı oralarda tetiklenmez)"""
    bas = max(metin.rfind(" ", 0, m.start()), metin.rfind("\n", 0, m.start())) + 1
    e = re.search(r"\s", metin[m.end():])
    kelime = metin[bas:len(metin) if e is None else m.end() + e.start()]
    return bool(re.search(r"[/\\]|://|\.[A-Za-z]{2,5}\b", kelime))


def _bul(metin, entropi=True):
    """(yeni_metin, sayı) — yalnız düz (çözülmemiş) metin üzerinde. entropi=False: yalnız yüksek kesinlikli kurallar."""
    n = 0

    def say(sonuc):
        nonlocal n
        n += 1
        return sonuc
    metin = _PEM.sub(lambda m: say(GIZLI), metin)
    metin = _URL_PAROLA.sub(lambda m: say(m.group(1) + GIZLI + m.group(3)) if m.group(2) != GIZLI else m.group(0), metin)
    metin = _BEARER.sub(lambda m: say(m.group(1) + GIZLI), metin)

    def atama(m):
        r = _atama_degistir(m)
        return say(r) if r != m.group(0) else r
    metin = _ATAMA.sub(atama, metin)
    metin = _ONEK.sub(lambda m: say(GIZLI), metin)
    metin = _JWT.sub(lambda m: say(GIZLI), metin)
    if entropi:
        metin = _UZUN.sub(lambda m: say(GIZLI) if _rastgele_mi(m.group(0)) and not _yol_mu(metin, m) else m.group(0), metin)
    return metin, n


def _coz(s):
    for _ in range(2):
        y = unquote(s)
        if y == s:
            break
        s = y
    return s


def sir_temizle(metin, entropi=True):
    """(temiz_metin, sayı): sırları [gizlendi] yapar. Önce düz metinde, sonra URL-kodlu öbeklerde (çözülmüş halinde sır varsa öbek komple) arar."""
    global TOPLAM
    if not metin or not isinstance(metin, str):
        return metin, 0
    metin, n = _bul(metin, entropi)
    if "%" in metin:
        def parca(m):
            nonlocal n
            tok = m.group(0)
            if "%" not in tok or GIZLI in tok and "%" not in tok.replace(GIZLI, ""):
                return tok
            cozuk = _coz(tok)
            if cozuk != tok and _bul(cozuk, entropi)[1]:
                n += 1
                return GIZLI
            return tok
        metin = re.sub(r"\S+", parca, metin)
        # sır boşlukla bölünmüş kodlu parçalara yayıldıysa (ör. "%74oken=abc%20x") satır düzeyinde son kontrol
        satirlar = []
        for l in metin.split("\n"):
            if "%" in l and _coz(l) != l and _bul(_coz(l), entropi)[1]:
                n += 1
                l = GIZLI
            satirlar.append(l)
        metin = "\n".join(satirlar)
    TOPLAM += n
    return metin, n


def temizle(metin, yer="", entropi=True):
    """Yalnız temiz metni verir; bir şey gizlenmişse sayıyı (değeri değil) stderr'e yazar."""
    temiz, n = sir_temizle(metin, entropi)
    if n:
        print(f"Kut: {n} sır gizlendi" + (f" ({yer})" if yer else ""), file=sys.stderr)
    return temiz
