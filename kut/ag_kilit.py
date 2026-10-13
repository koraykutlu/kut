"""Kut kilidi: PIN olmadan sunucu hiçbir kişisel veri göndermez (sayfa yalnız gök, açılış ve kilit ekranıdır).

PIN düz yazılmaz: ayarlar.json → "kilit": {"tuz", "ozet", "n", "sure_dk"} (PBKDF2-SHA256). Oturumlar yalnız bellekte tutulur:
sunucu yeniden başlayınca, `sure_dk` boyunca istek gelmeyince ya da kullanıcı 🔒'a basınca kilitlenir. Yanlış PIN'de bekleme artar.
Sınır: kilit arayüzü korur; diskteki Markdown dosyaları için disk şifrelemesi (BitLocker) gerekir.
PIN unutulursa: %LOCALAPPDATA%\\agim\\ayarlar.json'dan "kilit" anahtarını sil, Kut'u yeniden aç, yeni PIN belirle.
"""
import hashlib
import hmac
import secrets
import threading
import time

import ag_ice_aktar as ia

N = 600_000
VARSAYILAN_SURE = 15
_oturumlar = {}          # belirteç → son etkinlik zamanı
_dogrulama = threading.Lock()   # PIN denemeleri tek tek sayılır (PBKDF2 dahil kilit altında)
CEREZ = "kut_oturum"
kapaninca = []           # oturum kapanınca/süresi dolunca çağrılacaklar (ör. bellekteki sohbet geçmişini silmek)


def _kapandi():
    for f in list(kapaninca):
        try:
            f()
        except Exception:
            pass


def ayar():
    return ia.ayarlar().get("kilit") or {}


def kurulu():
    return bool(ayar().get("ozet"))


def sure_dk():
    return int(ayar().get("sure_dk", VARSAYILAN_SURE))


def _ozet(pin, tuz, n):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(tuz), n).hex()


def _pin_denetle(pin):
    pin = str(pin or "")
    if len(pin) < 4 or len(pin) > 64:
        raise ValueError("PIN en az 4, en çok 64 karakter olmalı")
    return pin


def pin_yaz(pin, sure=None):
    """Yeni PIN yazar; hata sayacı da sıfırlanır (çağıran PIN'i önceden doğrulamış olmalı)."""
    pin = _pin_denetle(pin)
    with _dogrulama:
        a = ia.ayarlar()
        tuz = secrets.token_hex(16)
        eski = a.get("kilit") or {}
        a["kilit"] = {"tuz": tuz, "ozet": _ozet(pin, tuz, N), "n": N,
                      "sure_dk": int(sure if sure is not None else eski.get("sure_dk", VARSAYILAN_SURE))}
        ia.ayar_yaz(a)


def sure_yaz(sure):
    """Otomatik kilit süresini (dk) PIN denemesiyle AYNI kilit altında yazar; okuma-yazma arası başarısız deneme sayacı ezilmez."""
    with _dogrulama:
        a = ia.ayarlar()
        a.setdefault("kilit", {})["sure_dk"] = int(sure)
        ia.ayar_yaz(a)


def pin_dogru(pin):
    """Sayaçsız ham karşılaştırma (yalnız iç/test kullanımı); dışarıdan gelen denemede `dogrula` kullan."""
    k = ayar()
    if not k.get("ozet"):
        return False
    return hmac.compare_digest(_ozet(str(pin or ""), k["tuz"], int(k.get("n", N))), k["ozet"])


def dogrula(pin):
    """Sayaçlı doğrulama: bekleme varsa PermissionError(sn); önce sayaç artar, sonra doğrulanır, doğruysa sıfırlanır.
    Sayaç ve bekleme ayarlar.json'da durur (yeniden başlatma sıfırlamaz). Bekleme: 5 hatadan sonra 30 sn, 60 sn, ... (en çok 32 dk).
    Doğru girişte eski (düşük yinelemeli) özet yeni yineleme sayısıyla yeniden yazılır."""
    pin = str(pin or "")
    with _dogrulama:
        a = ia.ayarlar()
        k = a.get("kilit") or {}
        if not k.get("ozet"):
            return False
        kalan = float(k.get("bekle", 0)) - time.time()
        if kalan > 0:
            raise PermissionError(int(kalan) + 1)
        sayi = int(k.get("hata", 0)) + 1
        k["hata"] = sayi
        if sayi >= 5:
            k["bekle"] = time.time() + 30 * 2 ** min(sayi - 5, 6)
        ia.ayar_yaz(a)      # yazılamazsa deneme yapılmaz (hata yükselir): sayaç doğrulamadan önce kalıcı olmalı
        n = int(k.get("n", N))
        if not hmac.compare_digest(_ozet(pin, k["tuz"], n), k["ozet"]):
            return False
        k.pop("hata", None)
        k.pop("bekle", None)
        if n < N:
            k["ozet"], k["n"] = _ozet(pin, k["tuz"], N), N
        ia.ayar_yaz(a)
        return True


def ac(pin):
    """Doğruysa yeni oturum belirteci döner. Yanlışta ValueError, beklemedeyse PermissionError(sn)."""
    if not dogrula(pin):
        raise ValueError("PIN yanlış")
    return yeni_oturum()


def yeni_oturum():
    t = secrets.token_urlsafe(32)
    _oturumlar[t] = time.time()
    return t


def gecerli(belirtec, dokun=True):
    son = _oturumlar.get(belirtec) if belirtec else None   # tek okuma: başka istek aynı anda kapatabilir
    if son is None:
        return False
    sure = sure_dk()
    if sure > 0 and time.time() - son > sure * 60:
        _oturumlar.pop(belirtec, None)
        _kapandi()
        return False
    if dokun:
        _oturumlar[belirtec] = time.time()
    return True


def kilitli_mi():
    """PIN kuruluysa ve süresi dolmamış açık oturum yoksa True. Kilitliyken model çağrısı (ag_model.cagir) yapılmaz.
    Süresi dolmuş oturumlar burada da düşer (ve kapanış işleri çalışır). PIN kurulu değilse kilit yoktur: False."""
    if not kurulu():
        return False
    sure = sure_dk()
    simdi = time.time()
    for t, son in list(_oturumlar.items()):
        if sure > 0 and simdi - son > sure * 60:
            _oturumlar.pop(t, None)
            _kapandi()
    return not _oturumlar


def kapat(belirtec=None):
    if belirtec:
        _oturumlar.pop(belirtec, None)
    else:
        _oturumlar.clear()
    _kapandi()


def cerez_oku(baslik):
    for parca in (baslik or "").split(";"):
        ad, _, deger = parca.strip().partition("=")
        if ad == CEREZ:
            return deger
    return ""


def cerez_yaz(belirtec):
    return f"{CEREZ}={belirtec}; Path=/; HttpOnly; SameSite=Strict"


def bos_veri():
    """Kilitliyken sayfaya giden veri: yalnız tür/bağ sözlükleri ve isimsiz bir merkez. Kişi, bağ, fotoğraf yok."""
    import ag_cekirdek as c
    merkez = {k: "" for k in c.BEN_ALANLARI}
    merkez.update({"id": "ben", "ad": "Kut", "tur": "ben", "foto": "", "govde": ""})
    return {
        "turler": c.TURLER, "tipler": c.TIPLER, "kisiler": [merkez], "iliskiler": [],
        "ozellik_tanim": c.OZELLIKLER, "puan_tanim": c.ILISKI_PUANLARI, "ozellik_olcut": c.OLCUTLER,
        "olcut_kurallari": c.OLCUT_KURALLARI, "yakinlik_olcut": c.YAKINLIK_OLCUT,
        "ben": {k: merkez.get(k, "") for k in c.BEN_ALANLARI}, "dikkatler": [], "bu_hafta": [],
        "cikarimlar": [], "cikarim_turleri": c.CIKARIM_TURLERI, "siklik": {a: v[1] for a, v in c.SIKLIK.items()},
        "uretildi": "", "uyarilar": [],
    }
