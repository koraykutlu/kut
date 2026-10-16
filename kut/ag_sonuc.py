"""Sonuç döngüsü: Kut'un önerdiği somut adımlar ve kullanıcının kararı.

Kaynak `<veri>/sonuclar.md` (okunur Markdown tablo; elle de düzenlenebilir; ilk yazışta `visibility: private` frontmatter'ı eklenir):

    | no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |

`kaynak` ozet | yol | brifing | elle; `sonuc` bekliyor | yaptim | ise_yaradi | ise_yaramadi | ertelendi | atlandi. Strateji hamlelerinin kendi
sonucu (`ag_strateji.sonuc_yaz`) aynen kalır; bu modül onları yalnız `istatistik`e katar. Model ve ağ yok.

Dosya kuralları: başlık ve açıklama korunur, tanınmayan/bozuk satıra dokunulmaz (okunurken atlanır, yazılırken olduğu gibi kalır); yeni satır
tablonun sonuna eklenir, değişen satır yerinde güncellenir. Yazma atomiktir (geçici dosya + `os.replace`); aynı süreçte `threading.Lock`,
süreçler arasında (Kut penceresi + zamanlanmış özet) küçük bir kilit dosyası yazanları sıraya koyar. Hücre metni tek satır, `|` → `/`,
en çok 200 karakter, sır süzgecinden geçmiş.

Öğrenme (`ayar`) kural tabanlı ve açıklanabilir; her kuralın gerekçesi `neden` alanında okunur cümledir.
"""
import contextlib
import os
import re
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

import ag_cekirdek as c
import ag_sir

SONUCLAR = {"bekliyor": "Bekliyor", "yaptim": "Yaptım", "ise_yaradi": "İşe yaradı", "ise_yaramadi": "İşe yaramadı",
            "ertelendi": "Ertelendi", "atlandi": "Atlandı", "reddedildi": "Uymuyor"}
# "Uymuyor": kullanıcı öneriyi gerekçesiyle reddeder. Gerekçe hem veridir (hangi tür öneride yanıldığım sayılır) hem de o kişiyi ne kadar
# süre önermeyeceğimi belirler. Not hücresinde "[kod] serbest metin" olarak durur. kod: (etiket, bekleme günü)
RED_NEDENLERI = {"yakin_degil": ("O kadar yakın değiliz", 365), "gerek_yok": ("Zaten görüşüyoruz, gerek yok", 60),
                 "zamani_degil": ("Şu an zamanı değil", 30), "istemiyorum": ("İletişim kurmak istemiyorum", 365),
                 "yanlis": ("Öneri yanlış ya da yersiz", 90), "diger": ("Başka bir neden", 45)}
_RED_KALIP = re.compile(r"^\[([a-z_]+)\]\s*")
KAYNAKLAR = ("ozet", "yol", "brifing", "elle")
SUTUN = ("no", "tarih", "kaynak", "kisi", "oneri", "sonuc", "not", "kapanis")
HUCRE_AZAMI = 200
TEMAS_SONUCLARI = ("yaptim", "ise_yaradi", "ise_yaramadi")   # kişiyle gerçekten konuşulmuş demektir: temas satırı eklenebilir
ISTATISTIK_GUN = 56                                          # son 8 hafta
BEKLIYOR_SORU_GUN = 3                                        # "bekliyor" kayıt bu kadar gün sonra "yaptın mı?" diye sorulur
YAPTIM_SORU_GUN = 5                                          # "yaptim" kayıt bu kadar gün sonra "nasıl geçti?" diye sorulur
SORU_AZAMI_GUN = 45                                          # bundan eski kayıt artık sorulmaz (sonsuza dek bekleyen kayıt olmasın)
BEKLEYEN_AZAMI = 10
OGRENME_GUN = 120                                            # çarpan (işe yaradı/yaramadı) yalnız son 120 günün sonucundan öğrenir
BEKLE_ATLANDI, BEKLE_KARISIK, BEKLE_ERTELENDI = 28, 21, 7
CARPAN_YARAMADI, CARPAN_YARADI = 0.5, 1.15
KILIT_BEKLE, KILIT_ESKI = 5.0, 30.0                          # kilit dosyası için en çok bekleme / bayatlama (sn)

ONCUL = ["---", "visibility: private", "---"]   # ikinci beyin yalnız bunu tanır: kişi adları, notlar ve öneriler özel kalır
BASLIK = """# Kut önerileri ve sonuçları
Kut'un önerdiği adımlar ve senin kararın. Bu dosyayı elle de düzenleyebilirsin; satır silmek yerine sonucu değiştir.

"""
TABLO_BASLIK = ["| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |", "|---|---|---|---|---|---|---|---|"]

_KILIT = threading.Lock()
_ETIKET_SONUC = {c.sade(v): k for k, v in SONUCLAR.items()}
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


# ---------- küçük yardımcılar ----------
def yol():
    """`<veri>/sonuclar.md`: veri klasörü her çağrıda `c.VERI`'den türer (testler ve --veri klasörü değiştirir)."""
    return os.path.join(c.VERI, "sonuclar.md")


def _tarih(s):
    s = str(s or "").strip()
    if not _ISO.fullmatch(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _bugun(b=None):
    if b is None:
        return date.today()
    if isinstance(b, datetime):
        return b.date()
    if isinstance(b, date):
        return b
    d = _tarih(b)
    if d is None:
        raise ValueError("geçersiz tarih")
    return d


def _hucre(m, azami=HUCRE_AZAMI):
    """Tablo hücresi: tek satır, `|` → `/`, sır süzgeci, en çok `azami` karakter."""
    m = " ".join(str(m if m is not None else "").split())[:2000].replace("|", "/")
    return ag_sir.temizle(m, "sonuç kaydı", entropi=False)[:azami].strip()


def _hafta(d):
    y, h, _ = d.isocalendar()
    return y, h


def _anahtar(kaynak, kisi, oneri, d):
    """Tekrar kaydı önleme: (kaynak, kişi, sadeleştirilmiş öneri, ISO hafta)."""
    return kaynak, kisi, c.sade(oneri), _hafta(d)


# ---------- dosya: okuma ----------
def _satirlari_oku():
    try:
        with open(yol(), encoding="utf-8-sig", errors="replace") as f:
            return f.read().replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except OSError:
        return None


def _hucreler(satir):
    s = satir.strip()
    if not s.startswith("|"):
        return None
    s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [x.strip() for x in s.split("|")]


def _no_oku(satir):
    """Satırın kayıt numarası (ilk hücre tamsayıysa), değilse None. Bozuk satırın numarası da sayılır: yeni no onunla çakışmaz."""
    h = _hucreler(satir)
    if h and h[0].isascii() and h[0].isdigit():
        return int(h[0])
    return None


def _coz(satir):
    """Bir tablo satırı → kayıt; kayıt değilse (başlık, ayırıcı, bozuk satır) None. Elle yazılmış biçimler hoş görülür:
    kaynak bilinmiyorsa 'elle', sonuç 'İşe yaradı' gibi etiketle yazılmışsa tanınır, boş sonuç 'bekliyor'."""
    h = _hucreler(satir)
    no = _no_oku(satir)
    if no is None or len(h) > len(SUTUN):
        return None
    h += [""] * (len(SUTUN) - len(h))
    r = dict(zip(SUTUN, h))
    r["no"] = no
    if _tarih(r["tarih"]) is None or not r["oneri"]:
        return None
    r["kaynak"] = r["kaynak"].lower() if r["kaynak"].lower() in KAYNAKLAR else "elle"
    s = r["sonuc"]
    anahtar = c.sade(s).replace(" ", "_")
    if not s:
        r["sonuc"] = "bekliyor"
    elif anahtar in SONUCLAR:
        r["sonuc"] = anahtar
    elif c.sade(s) in _ETIKET_SONUC:
        r["sonuc"] = _ETIKET_SONUC[c.sade(s)]
    else:
        return None
    if r["kapanis"] and _tarih(r["kapanis"]) is None:
        r["kapanis"] = ""
    return r


def _kayitlar(satirlar):
    """[(satır indeksi, kayıt)]: aynı no ikinci kez geçerse ilki geçerlidir."""
    var, sonuc = set(), []
    for i, s in enumerate(satirlar or []):
        r = _coz(s)
        if r and r["no"] not in var:
            var.add(r["no"])
            sonuc.append((i, r))
    return sonuc


def oku():
    """Tüm kayıtlar (dosya sırasıyla): [{no:int, tarih, kaynak, kisi, oneri, sonuc, not, kapanis}]. Dosya yoksa []; bozuk satır atlanır."""
    return [r for _, r in _kayitlar(_satirlari_oku())]


# ---------- dosya: yazma ----------
def _satir_yaz(r):
    return "| " + " | ".join(str(r.get(a, "")) for a in SUTUN) + " |"


@contextlib.contextmanager
def _yazma():
    """Yazanları sıraya koyar: süreç içi `threading.Lock` + süreçler arası kilit dosyası (bayatlarsa kırılır; beklemeyi aşarsa yine yazılır,
    atomik `os.replace` dosyayı bozmaz)."""
    with _KILIT:
        kilit = yol() + ".kilit"
        fd = None
        try:
            os.makedirs(os.path.dirname(kilit), exist_ok=True)
            son = time.monotonic() + KILIT_BEKLE
            while True:
                try:
                    fd = os.open(kilit, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    break
                except FileExistsError:
                    try:
                        if time.time() - os.path.getmtime(kilit) > KILIT_ESKI:
                            os.remove(kilit)
                            continue
                    except OSError:
                        pass
                    if time.monotonic() > son:
                        break
                    time.sleep(0.02)
        except OSError:
            fd = None
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    os.remove(kilit)
                except OSError:
                    pass


def _ozel_yap(satirlar):
    """Dosyanın başına `visibility: private` frontmatter'ı koyar (yoksa); frontmatter'ı olup `visibility` satırı eksikse satırı ekler.
    Elle yazılmış başlık/açıklama ve diğer frontmatter alanları korunur; mevcut `visibility` değerine dokunulmaz."""
    satirlar = list(satirlar)
    if satirlar and satirlar[0].lstrip("\ufeff").strip() == "---":
        kapanis = next((i for i in range(1, min(len(satirlar), 40)) if satirlar[i].strip() == "---"), None)
        if kapanis is not None:
            if not any(re.match(r"\s*visibility\s*:", l) for l in satirlar[1:kapanis]):
                satirlar.insert(kapanis, ONCUL[1])
            return satirlar
    return ONCUL + satirlar


def _dosya_yaz(satirlar):
    satirlar = _ozel_yap(satirlar)
    hedef = yol()
    klasor = os.path.dirname(hedef)
    os.makedirs(klasor, exist_ok=True)
    fd, gecici = tempfile.mkstemp(prefix="sonuclar.", suffix=".tmp", dir=klasor)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(satirlar))
        for deneme in range(6):   # Windows: virüs tarayıcı/okuyucu anlık tutarsa os.replace PermissionError verebilir
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


def _satir_ekle(satirlar, satir):
    """Yeni kayıt satırı: tablonun son satırından sonra. Tablo ya da dosya yoksa başlıkla kurulur."""
    if satirlar is None:
        return (BASLIK + "\n".join(TABLO_BASLIK + [satir]) + "\n").split("\n")
    son = max((i for i, s in enumerate(satirlar) if s.lstrip().startswith("|")), default=None)
    if son is None:
        while satirlar and not satirlar[-1].strip():
            satirlar.pop()
        return satirlar + ([""] if satirlar else []) + TABLO_BASLIK + [satir, ""]
    return satirlar[:son + 1] + [satir] + satirlar[son + 1:]


# ---------- API ----------
def kaydet(kaynak, kisi, oneri, bugun=None):
    """Önerilen adımı `bekliyor` olarak kaydeder, numarasını döndürür. Aynı ISO haftada aynı (kaynak, kişi, öneri) varsa mevcut no döner."""
    kaynak = str(kaynak or "").strip().lower()
    if kaynak not in KAYNAKLAR:
        raise ValueError("bilinmeyen kaynak")
    kisi = str(kisi or "").strip()
    if kisi and not c.gecerli_id(kisi):
        raise ValueError("geçersiz kişi")
    oneri = _hucre(oneri)
    if not oneri:
        raise ValueError("öneri boş")
    bugun = _bugun(bugun)
    anahtar = _anahtar(kaynak, kisi, oneri, bugun)
    with _yazma():
        satirlar = _satirlari_oku()
        mevcut = _kayitlar(satirlar)
        for _, r in mevcut:
            if _anahtar(r["kaynak"], r["kisi"], r["oneri"], _tarih(r["tarih"])) == anahtar:
                return r["no"]
        no = 1 + max([_no_oku(s) or 0 for s in satirlar or []] + [0])
        satir = _satir_yaz({"no": no, "tarih": bugun.isoformat(), "kaynak": kaynak, "kisi": kisi, "oneri": oneri,
                            "sonuc": "bekliyor", "not": "", "kapanis": ""})
        _dosya_yaz(_satir_ekle(satirlar, satir))
        return no


def _kanal(kanal):
    return " ".join(str(kanal or "").replace("·", "-").split())[:30] or "diğer"


def _temas_ekle(kid, oneri, kanal, bugun):
    """Kişinin `## Temas` bölümüne 'GG.AA.YYYY · kanal · Kut önerisi: ...' ekler; son_temas yalnız ileri gider. Eklendiyse True.
    Kişi yoksa, hariçse ya da aynı gün aynı satır zaten varsa dokunmaz. Yazmadan önce sürüm kopyası (`c.surum_al`)."""
    if not c.gecerli_id(kid) or kid == c.ben_id():
        return False
    dosya = os.path.join(c.KISILER, kid + ".md")
    if not os.path.exists(dosya):
        return False
    k = c.kisi_oku(dosya)
    if not k or c.haric_mi(k):
        return False
    govde = k.pop("govde")
    satir = f"{bugun:%d.%m.%Y} · {_kanal(kanal)} · Kut önerisi: {str(oneri).replace('·', '-')}"
    if any(s.strip() == "- " + satir for s in govde.split("\n")):
        return False
    mevcut = _tarih(k.get("son_temas"))
    if mevcut is None or mevcut < bugun:
        k["son_temas"] = bugun.isoformat()
    c.surum_al(kid)
    c.kisi_yaz(kid, k, c.temas_ekle(govde, satir))
    return True


def red_nedeni(r):
    """'reddedildi' kaydının gerekçe kodu ('' = yok/tanınmıyor)."""
    m = _RED_KALIP.match(str((r or {}).get("not") or ""))
    return m.group(1) if m and m.group(1) in RED_NEDENLERI else ""


def isaretle(no, sonuc, not_="", temas=False, kanal="", bugun=None, neden=""):
    """Kaydın sonucunu işaretler (kapanış = bugün; 'bekliyor'a dönüşte boş). `not_` doluysa notun yerine geçer.
    temas=True ve sonuc yaptim/ise_yaradi/ise_yaramadi ise kişinin temas bölümüne satır eklenir (kişi yok/hariç ya da aynı gün aynı satır varsa eklenmez;
    sonuç yine kaydedilir). Döner: {"no", "sonuc", "temas_eklendi"}. Bilinmeyen sonuç ya da no → ValueError."""
    if sonuc not in SONUCLAR:
        raise ValueError("bilinmeyen sonuç")
    if sonuc == "reddedildi" and neden not in RED_NEDENLERI:
        raise ValueError("Uymuyor için bir neden seç.")
    try:
        no = int(no)
    except (TypeError, ValueError):
        raise ValueError("geçersiz kayıt numarası") from None
    bugun = _bugun(bugun)
    with _yazma():
        satirlar = _satirlari_oku()
        bulunan = next(((i, r) for i, r in _kayitlar(satirlar) if r["no"] == no), None)
        if not bulunan:
            raise ValueError("kayıt bulunamadı")
        i, r = bulunan
        r["sonuc"] = sonuc
        r["kapanis"] = "" if sonuc == "bekliyor" else bugun.isoformat()
        if sonuc == "reddedildi":   # gerekçe kodu notun başında; serbest metin isteğe bağlı
            r["not"] = _hucre(f"[{neden}] " + " ".join(str(not_ or "").split())).strip()
        elif str(not_ or "").strip():
            r["not"] = _hucre(not_)
        elif red_nedeni(r):   # reddedilmiş kayıt başka bir sonuca çevrilince gerekçe kodu kalkar (öğrenme onu artık saymaz)
            r["not"] = _RED_KALIP.sub("", r["not"])
        satirlar[i] = _satir_yaz(r)
        _dosya_yaz(satirlar)
        eklendi = False
        if temas and sonuc in TEMAS_SONUCLARI and r["kisi"]:
            try:
                eklendi = _temas_ekle(r["kisi"], r["oneri"], kanal, bugun)
            except OSError:
                eklendi = False   # sonuç kaydedildi; kişi dosyası yazılamadı
    return {"no": no, "sonuc": sonuc, "temas_eklendi": eklendi}


def _sira(r):
    return r.get("kapanis") or r.get("tarih") or "", int(r.get("no") or 0)


def kisi_gecmisi(kid, kayitlar=None):
    """Kişinin kayıtları, en yeni önce."""
    kayitlar = oku() if kayitlar is None else kayitlar
    return sorted((r for r in kayitlar if r.get("kisi") == kid), key=lambda r: (r.get("tarih") or "", int(r.get("no") or 0)), reverse=True)


def bekleyenler(bugun=None, kayitlar=None):
    """Sonucu sorulacak kayıtlar: 'bekliyor' (≥ 3 gün) ve 'yaptim' (kapanıştan ≥ 5 gün). En eski 10; 45 günden eskiye artık sorulmaz.
    Her kayda `gun` (referans tarihten beri) ve `asama` ('bekliyor' | 'yaptim') eklenir."""
    bugun = _bugun(bugun)
    kayitlar = oku() if kayitlar is None else kayitlar
    sonuc = []
    for r in kayitlar:
        if r.get("sonuc") == "bekliyor":
            ref, esik = _tarih(r.get("tarih")), BEKLIYOR_SORU_GUN
        elif r.get("sonuc") == "yaptim":
            ref, esik = _tarih(r.get("kapanis")) or _tarih(r.get("tarih")), YAPTIM_SORU_GUN
        else:
            continue
        if ref is None:
            continue
        gun = (bugun - ref).days
        if esik <= gun <= SORU_AZAMI_GUN:
            sonuc.append(({**r, "gun": gun, "asama": r["sonuc"]}, ref))
    sonuc.sort(key=lambda x: (x[1], int(x[0].get("no") or 0)))
    return [r for r, _ in sonuc[:BEKLEYEN_AZAMI]]


def ayar(kid, bugun=None, kayitlar=None):
    """Bir kişi için öğrenilmiş davranış: {"bekle_gun", "carpan", "neden", "sure", "bitis"}. Varsayılan {0, 1.0, ""}.

    `bekle_gun` bugünden itibaren KALAN bekleme gündür (0 = bekleme yok ya da doldu); çağıran `bekle_gun > 0` ise kişiyi önermez.
    `sure` kuralın toplam süresi, `bitis` bekleme bitiş tarihi (kural yoksa 0 / ""). Yalnız karara bağlanmış kayıtlar (`bekliyor` değil) sayılır.
    Bekleme (kapanıştan itibaren; birden çok kural uyarsa en uzunu):
      - son 2 karar 'atlandi' → 28 gün;
      - son 3 karar 'atlandi'/'ertelendi' karışık → 21 gün;
      - son karar 'ertelendi' → 7 gün.
    Çarpan (son 120 gün): son 2 sonuçlu kayıt ('ise_yaradi'/'ise_yaramadi') ikisi de 'ise_yaramadi' → 0,5; son karar 'ise_yaradi' → 1,15."""
    bugun = _bugun(bugun)
    kayitlar = oku() if kayitlar is None else kayitlar
    kk = sorted((r for r in kayitlar if r.get("kisi") == kid and r.get("sonuc") in SONUCLAR and r.get("sonuc") != "bekliyor"), key=_sira)
    sonuc = {"bekle_gun": 0, "carpan": 1.0, "neden": "", "sure": 0, "bitis": ""}
    if not kk:
        return sonuc
    son = kk[-1]
    ref = _tarih(son.get("kapanis")) or _tarih(son.get("tarih")) or bugun
    son_sonuclar = [r["sonuc"] for r in kk]
    neden = []

    sure, kural = 0, ""
    if son["sonuc"] == "reddedildi" and red_nedeni(son):   # kullanıcının açık kararı: diğer kurallardan önce gelir
        etiket, sure = RED_NEDENLERI[red_nedeni(son)]
        kural = "«" + etiket + "» dedin; {kalan} gün bu kişiyi önermem."
    elif son_sonuclar[-2:] == ["atlandi", "atlandi"]:
        sure, kural = BEKLE_ATLANDI, "Son iki öneriyi atladın; {kalan} gün daha dinlendiriyorum."
    elif len(son_sonuclar) >= 3 and all(s in ("atlandi", "ertelendi") for s in son_sonuclar[-3:]):
        sure, kural = BEKLE_KARISIK, "Son üç öneriyi atladın ya da erteledin; {kalan} gün daha dinlendiriyorum."
    elif son["sonuc"] == "ertelendi":
        sure, kural = BEKLE_ERTELENDI, "Bu öneriyi erteledin; {kalan} gün sonra tekrar bakarım."
    if sure:
        bitis = ref + timedelta(days=sure)
        kalan = max(0, (bitis - bugun).days)
        sonuc.update(sure=sure, bitis=bitis.isoformat(), bekle_gun=kalan)
        if kalan:
            neden.append(kural.format(kalan=kalan))

    def yeni(r):
        d = _tarih(r.get("kapanis")) or _tarih(r.get("tarih"))
        return d is not None and 0 <= (bugun - d).days <= OGRENME_GUN

    sonuclu = [r for r in kk if r["sonuc"] in ("ise_yaradi", "ise_yaramadi") and yeni(r)]
    if len(sonuclu) >= 2 and sonuclu[-1]["sonuc"] == sonuclu[-2]["sonuc"] == "ise_yaramadi":
        sonuc["carpan"] = CARPAN_YARAMADI
        neden.append("Son iki deneme işe yaramadı; farklı bir yol dene (ortak tanıdık, yüz yüze).")
    elif son["sonuc"] == "ise_yaradi" and yeni(son):
        sonuc["carpan"] = CARPAN_YARADI
        neden.append("Son deneme işe yaradı; ritmi koru.")
    sonuc["neden"] = " ".join(neden)
    return sonuc


def _sayim(kayitlar):
    """[(sonuc anahtarı)] → {"toplam", "yapilan", "ise_yarayan", "oran"}; oran = işe yarayan / sonuçlanmış (işe yaradı + yaramadı), yoksa None."""
    yarayan = sum(1 for s in kayitlar if s == "ise_yaradi")
    sonuclanan = yarayan + sum(1 for s in kayitlar if s == "ise_yaramadi")
    return {"toplam": len(kayitlar), "yapilan": sum(1 for s in kayitlar if s in TEMAS_SONUCLARI), "ise_yarayan": yarayan,
            "oran": round(yarayan / sonuclanan, 2) if sonuclanan else None}


STRATEJI_ESLE = {"yaptim": "yaptim", "ise_yaradi": "ise_yaradi", "ise_yaramadi": "ise_yaramadi", "yapmadim": "atlandi"}   # "gecersiz" sayılmaz


def istatistik(bugun=None, kayitlar=None, strateji_sonuclari=None):
    """Son 8 hafta (56 gün): {"son_8_hafta": {"toplam", "yapilan", "ise_yarayan", "oran"}, "kaynaklara_gore": {kaynak: {...}}}.

    `strateji_sonuclari`: strateji hamleleri ([{sonuc, sonuc_tarih, ...}], `ag_strateji.oku(...)["hamleler"]`); sonucu işaretlenmiş olanlar 'strateji'
    kaynağı olarak katılır (yaptim/ise_yaradi/ise_yaramadi aynen, yapmadim → atlandi, gecersiz sayılmaz)."""
    bugun = _bugun(bugun)
    kayitlar = oku() if kayitlar is None else kayitlar

    def pencerede(t):
        d = _tarih(t)
        return d is not None and 0 <= (bugun - d).days < ISTATISTIK_GUN

    gruplar = {}
    for r in kayitlar:
        if pencerede(r.get("tarih")) and r.get("sonuc") in SONUCLAR:
            gruplar.setdefault(r.get("kaynak") or "elle", []).append(r["sonuc"])
    for h in strateji_sonuclari or []:
        s = STRATEJI_ESLE.get((h or {}).get("sonuc"))
        if s and pencerede(h.get("sonuc_tarih") or h.get("tarih")):
            gruplar.setdefault("strateji", []).append(s)
    red = {}   # "Uymuyor" gerekçeleri: Kut'un hangi tür öneride yanıldığı (son 8 hafta, kapanış tarihine göre)
    for r in kayitlar:
        if r.get("sonuc") == "reddedildi" and red_nedeni(r) and pencerede(r.get("kapanis") or r.get("tarih")):
            red[red_nedeni(r)] = red.get(red_nedeni(r), 0) + 1
    return {"son_8_hafta": _sayim([s for g in gruplar.values() for s in g]),
            "kaynaklara_gore": {k: _sayim(g) for k, g in sorted(gruplar.items())},
            "red_nedenleri": dict(sorted(red.items(), key=lambda x: -x[1]))}
