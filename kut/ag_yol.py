"""Tanıştırma yolu: "X'e ulaşmak istiyorum" → ağdaki en sıcak bağ zinciri, ilk adım ve gönderilebilir bir taslak mesaj.

Yerel ve deterministiktir: model ve ağ yok, dosya okumaz/yazmaz. Saf işlevler `c.veri_hazirla(foto_gom=False)` çıktısı biçimindeki `veri`
sözlüğünü alır (demo ve testler aynı işlevleri çağırır).

Graf: düğümler merkez + hariç olmayan kişiler. Merkez–kişi kenarı kişinin yakınlığından ve sıcaklığından, kişi–kişi kenarı `iliskiler`
tipinden gelir (ağırlıklar aşağıda). `rakip` ve `gerginlik` kenar değildir; o çift yolda yan yana da gelemez (kenarları çıkarılır).
Yönlü tipler (mentor, yonetici, asistan, hocasi: A → B) kenar olarak yönsüzdür ama gerekçe cümlesinde yönü korunur.
Skor = kenar ağırlıklarının çarpımı × atlama cezası; 0–100. En çok 4 kenar (3 ara kişi). Arama: −log ağırlık maliyetiyle Dijkstra/A*
(katmanlı: kenarın sırası cezayı belirler) + Yen k-en-kısa yol; ilk adımı farklı yollar öne alınır.

Merkez–kişi kenarı yalnız yakınlığı ≥ 1 kişide vardır: yakınlık 0 "tanımıyorum" demektir (hedef olur, doğrudan bağ sayılmaz); merkezi
içeren bir `iliskiler` satırı (ör. hocasi hoca → ben) yakınlık ≥ 1 kişide, yakınlık kenarından güçlüyse onun yerine geçer."""
import heapq
import math
import re
from datetime import date

import ag_cekirdek as c

# merkez–kişi: yakınlık → ağırlık (× sıcaklık çarpanı); sıcaklık yoksa 0,7
AGIRLIK_YAKINLIK = {3: 0.92, 2: 0.75, 1: 0.45}
SICAKLIK_YOK = 0.7
# kişi–kişi: ilişki tipi → ağırlık (rakip ve gerginlik kenar değil, engel)
AGIRLIK_TIP = {"partner": 0.9, "akraba": 0.85, "arkadas": 0.8, "birlikte-calisiyor": 0.7, "is-ortagi": 0.7, "mentor": 0.7,
               "yonetici": 0.65, "hocasi": 0.65, "asistan": 0.65, "tanisiyor": 0.4}
ENGEL_TIPLERI = ("rakip", "gerginlik")
ATLAMA = 0.9                 # 2. ve sonraki ara kişi için çarpan
AZAMI_KENAR = 4              # en çok 4 kenar = 3 ara kişi
VARSAYILAN_K = 3
EN_COK_K = 5
ADAY_AZAMI = 12              # çeşitlendirme için Yen'in üretebileceği en çok yol
CESIT_ESIK = 0.5             # farklı ilk adımlı yol, en iyi skorun bu oranından zayıfsa öne alınmaz
ARAMA_AZAMI = 80
HEDEF_AZAMI = 8
TANIDIK_AZAMI = 20
SOGUK_GUN = 90
UYARI_AZAMI = 6
AMAC_AZAMI = 120
YOK_NEDENI = "Ağında bu kişiye giden bir bağ yok. Bir bağ ekle ya da doğrudan yaz."

_LOG_ATLAMA = -math.log(ATLAMA)
_UNVAN = {"hoca", "dr", "prof", "doc", "ogr", "av", "muh", "uzm", "yrd", "op", "bey", "hanim", "abi", "abla"}
_YONLU_ISIM = {"mentor": "mentoru", "yonetici": "yöneticisi", "asistan": "asistanı", "hocasi": "hocası"}
_YONLU_SEN = {"mentor": "mentorun", "yonetici": "yöneticin", "asistan": "asistanın", "hocasi": "hocan"}
_YONLU_BEN = {"mentor": "mentorusun", "yonetici": "yöneticisisin", "asistan": "asistanısın", "hocasi": "hocasısın"}
_SIMETRIK = {"tanisiyor": "{a} ile {b} tanışıyor.", "arkadas": "{a} ve {b} arkadaş.", "birlikte-calisiyor": "{a} ve {b} birlikte çalışıyor.",
             "is-ortagi": "{a} ve {b} iş ortağı.", "akraba": "{a} ve {b} akraba.", "partner": "{a} ve {b} partner."}
_SIMETRIK_SEN = {"tanisiyor": "{p} ile tanışıyorsun", "arkadas": "{p} senin arkadaşın", "birlikte-calisiyor": "{p} ile birlikte çalışıyorsun",
                 "is-ortagi": "{p} senin iş ortağın", "akraba": "{p} senin akraban", "partner": "{p} senin partnerin"}


# ---------- Türkçe yardımcılar ----------
def _kucuk(s):
    return str(s).replace("İ", "i").replace("I", "ı").lower()


def _tek_satir(s, azami):
    return " ".join(str(s or "").split())[:azami].strip()


def _kisa(ad, kid=""):
    """İlk ad; Hoca/Dr./Prof. gibi unvanlı adlar olduğu gibi kalır."""
    parca = _tek_satir(ad, 120).split()
    if not parca:
        return kid or "Bu kişi"
    return " ".join(parca) if any(c.sade(p) in _UNVAN for p in parca) else parca[0]


def _ek(ad, tur):
    """Özel ada kesme işaretiyle ek getirir (ünlü uyumu): ilgi (-ın/-nın), yönelme (-a/-ya), belirtme (-ı/-yı), ayrılma (-dan/-tan)."""
    ad = _tek_satir(ad, 120)
    harfler = "".join(ch for ch in (ad.split() or [""])[-1] if ch.isalpha())
    if not harfler:
        return ad
    kucuk = _kucuk(harfler).replace("â", "a").replace("î", "i").replace("û", "u")
    unlu = "aeıioöuü"
    son_unlu = next((ch for ch in reversed(kucuk) if ch in unlu), "e")
    unlu_sonu = kucuk[-1] in unlu
    dar = {"a": "ı", "ı": "ı", "e": "i", "i": "i", "o": "u", "u": "u", "ö": "ü", "ü": "ü"}[son_unlu]
    genis = "a" if son_unlu in "aıou" else "e"
    if tur == "ilgi":
        ek = ("n" if unlu_sonu else "") + dar + "n"
    elif tur == "yonelme":
        ek = ("y" if unlu_sonu else "") + genis
    elif tur == "belirtme":
        ek = ("y" if unlu_sonu else "") + dar
    else:   # ayrilma
        ek = ("t" if kucuk[-1] in "çfhkpsşt" else "d") + genis + "n"
    return f"{ad}'{ek}"


def _tarih(s):
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def _gun_once(son, bugun):
    """'bugün', 'dün', '3 gün önce', 'yaklaşık 4 ay önce', '2 yıl önce'."""
    g = max((bugun - son).days, 0)
    if g == 0:
        return "bugün"
    if g == 1:
        return "dün"
    if g < 60:
        return f"{g} gün önce"
    if g < 730:
        return f"yaklaşık {round(g / 30)} ay önce"
    return f"{g // 365} yıl önce"


def _suredir(gun):
    """'90 gündür', '5 aydır', '2 yıldır' (konuşmadın)."""
    if gun < 120:
        return f"{gun} gündür"
    if gun < 730:
        return f"{round(gun / 30)} aydır"
    return f"{gun // 365} yıldır"


def _son_temas(k):
    return _tarih(k.get("etkin_son_temas") or k.get("son_temas"))


def _yakinlik(k):
    try:
        return max(0, min(3, int(k.get("yakinlik") or 0)))
    except (TypeError, ValueError):
        return 0


def _sicaklik(k):
    s = (k.get("puan") or {}).get("sicaklik")
    return float(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None


# ---------- graf ----------
class _Graf:
    """Veri sözlüğünden kurulan salt-okur graf. kenar[(a,b)] (a<b) → {w, tip, kaynak, a, b}; kom[u] → [(v, w)] sıralı."""

    def __init__(self, veri):
        kisiler = veri.get("kisiler") or []
        if not kisiler or not isinstance(kisiler[0], dict) or not c.gecerli_id(kisiler[0].get("id")):
            raise ValueError("Ağ verisi boş.")
        self.merkez = kisiler[0]
        self.ben = self.merkez["id"]
        self.kisi, self.haric = {}, set()
        for k in kisiler[1:]:
            kid = k.get("id") if isinstance(k, dict) else None
            if not c.gecerli_id(kid) or kid == self.ben or kid in self.kisi:
                continue
            if k.get("haric"):
                self.haric.add(kid)
            else:
                self.kisi[kid] = k
        dugum = set(self.kisi) | {self.ben}
        engel, iliski = set(), {}
        for i in veri.get("iliskiler") or []:
            a, b, tip = i.get("a"), i.get("b"), i.get("tip")
            if tip not in c.TIPLER or a == b or a not in dugum or b not in dugum:
                continue
            cift = tuple(sorted((a, b)))
            if tip in ENGEL_TIPLERI:
                engel.add(cift)
                continue
            w = AGIRLIK_TIP.get(tip)
            if w is None:
                continue
            aday = (-w, tip, a, b)
            if cift not in iliski or aday < iliski[cift]:
                iliski[cift] = aday
        self.kenar, kom = {}, {}
        # merkez–kişi: yakınlık × sıcaklık; merkezi içeren ilişki satırı yalnız yakınlık ≥ 1'de ve daha güçlüyse geçer
        self.merkez_kenar = {}
        for kid, k in self.kisi.items():
            y = _yakinlik(k)
            if y < 1:
                continue
            s = _sicaklik(k)
            w = AGIRLIK_YAKINLIK[y] * (SICAKLIK_YOK if s is None else 0.55 + 0.45 * max(0.0, min(100.0, s)) / 100)
            kayit = {"w": w, "tip": "yakinlik", "kaynak": "yakinlik", "a": self.ben, "b": kid}
            r = iliski.get(tuple(sorted((self.ben, kid))))
            if r and -r[0] > w:
                kayit = {"w": -r[0], "tip": r[1], "kaynak": "iliski", "a": r[2], "b": r[3]}
            self.merkez_kenar[kid] = kayit
        for kid, kayit in self.merkez_kenar.items():
            if tuple(sorted((self.ben, kid))) not in engel:
                self.kenar[tuple(sorted((self.ben, kid)))] = kayit
        for cift, r in iliski.items():
            if self.ben in cift or cift in engel:
                continue
            self.kenar[cift] = {"w": -r[0], "tip": r[1], "kaynak": "iliski", "a": r[2], "b": r[3]}
        for (a, b), kayit in self.kenar.items():
            kom.setdefault(a, []).append((b, kayit["w"]))
            kom.setdefault(b, []).append((a, kayit["w"]))
        self.kom = {u: sorted(v) for u, v in kom.items()}
        self.dikkat = [d for d in (veri.get("dikkatler") or []) if isinstance(d, dict)]

    def kenar_bul(self, u, v):
        if self.ben in (u, v):   # gerginlik yüzünden grafa girmeyen doğrudan bağ da burada bulunur
            return self.merkez_kenar[v if u == self.ben else u]
        return self.kenar[(u, v) if u < v else (v, u)]

    def ad(self, kid):
        if kid == self.ben:
            return _tek_satir(self.merkez.get("ad"), 120) or "Sen"
        return _tek_satir((self.kisi.get(kid) or {}).get("ad"), 120) or kid


def _maliyet(derinlik, w):
    """Derinlik = kenarın yol içindeki sırası (0'dan). 3. kenardan sonra (2. ara kişi ve sonrası) atlama cezası."""
    return -math.log(w) + (_LOG_ATLAMA if derinlik >= 2 else 0.0)


def _yol_maliyeti(g, yol):
    return sum(_maliyet(i, g.kenar_bul(yol[i], yol[i + 1])["w"]) for i in range(len(yol) - 1))


def _yol_skoru(g, yol):
    return max(1, round(100 * math.exp(-_yol_maliyeti(g, yol))))


def _hedefe_uzaklik(g, hedef):
    """h[d][v]: v düğümünde d kenar kullanılmışken hedefe en ucuz kalan maliyet (A* sezgisi; yasaklar yok sayılır → tutarlı)."""
    h = [{hedef: 0.0} for _ in range(AZAMI_KENAR + 1)]
    for d in range(AZAMI_KENAR - 1, -1, -1):
        hd = h[d]
        for u, hu in h[d + 1].items():
            for v, w in g.kom.get(u, ()):
                m = _maliyet(d, w) + hu
                if m < hd.get(v, math.inf):
                    hd[v] = m
    return h


def _a_yildiz(g, h, bas, derinlik, hedef, yasak_dugum, yasak_kenar):
    """bas düğümünden (derinlik kenar kullanılmış) hedefe en ucuz yol; yoksa None. Yasaklı düğüm/kenar atlanır."""
    if h[derinlik].get(bas) is None:
        return None
    en_iyi, ata = {(bas, derinlik): 0.0}, {}
    kuyruk = [(h[derinlik][bas], 0.0, derinlik, bas)]
    while kuyruk:
        _, gc, d, n = heapq.heappop(kuyruk)
        if gc > en_iyi.get((n, d), math.inf):
            continue
        if n == hedef:
            yol, an = [n], (n, d)
            while an in ata:
                an = ata[an]
                yol.append(an[0])
            return yol[::-1]
        if d >= AZAMI_KENAR:
            continue
        for v, w in g.kom.get(n, ()):
            if v in yasak_dugum or (n, v) in yasak_kenar:
                continue
            hv = h[d + 1].get(v)
            if hv is None:
                continue
            ng = gc + _maliyet(d, w)
            if ng < en_iyi.get((v, d + 1), math.inf):
                en_iyi[(v, d + 1)] = ng
                ata[(v, d + 1)] = (n, d)
                heapq.heappush(kuyruk, (ng + hv, ng, d + 1, v))
    return None


def _yen(g, hedef, k):
    """Merkezden hedefe en ucuzdan başlayarak basit yollar (düğüm listesi, maliyet sırası). `k` farklı ilk adım bulunana ya da
    ADAY_AZAMI yola varana dek sürer."""
    h = _hedefe_uzaklik(g, hedef)
    ilk = _a_yildiz(g, h, g.ben, 0, hedef, frozenset(), frozenset())
    if not ilk:
        return []
    kabul, aday, gorulen = [ilk], [], {tuple(ilk)}
    while len(kabul) < ADAY_AZAMI and len({p[1] for p in kabul}) < k:
        onceki = kabul[-1]
        for i in range(len(onceki) - 1):
            kok = onceki[:i + 1]
            yasak_k = {(p[i], p[i + 1]) for p in kabul if len(p) > i + 1 and p[:i + 1] == kok}
            sapma = _a_yildiz(g, h, onceki[i], i, hedef, frozenset(kok[:-1]), yasak_k)
            if not sapma:
                continue
            toplam = tuple(kok[:-1] + sapma)
            if len(set(toplam)) != len(toplam) or toplam in gorulen:
                continue
            gorulen.add(toplam)
            heapq.heappush(aday, (_yol_maliyeti(g, toplam), toplam))
        if not aday:
            break
        kabul.append(list(heapq.heappop(aday)[1]))
    return kabul


def _en_iyi_maliyetler(g):
    """Merkezden her düğüme en ucuz (≤ 4 kenar) maliyet: ara() için tek geçişte sıralama."""
    en_iyi, simdiki = {}, {g.ben: 0.0}
    for d in range(AZAMI_KENAR):
        sonraki = {}
        for v, cv in simdiki.items():
            for u, w in g.kom.get(v, ()):
                if u == g.ben:
                    continue
                m = cv + _maliyet(d, w)
                if m < sonraki.get(u, math.inf):
                    sonraki[u] = m
        for u, m in sonraki.items():
            if m < en_iyi.get(u, math.inf):
                en_iyi[u] = m
        simdiki = sonraki
    return en_iyi


def _cesitlendir(g, yollar, k):
    """İlk adımları farklı yollar öne alınır; aynı ilk adımlı yollar (farklı olan varsa) sona itilir."""
    if not yollar:
        return []
    skorlar = [_yol_skoru(g, y) for y in yollar]
    ilkler, secilen, kalan = set(), [], []
    for y, s in zip(yollar, skorlar):
        if y[1] not in ilkler and (not secilen or s >= CESIT_ESIK * skorlar[0]):
            ilkler.add(y[1])
            secilen.append(y)
        else:
            kalan.append(y)
    return (secilen + kalan)[:k]


# ---------- gerekçe, uyarı, taslak ----------
def _etiket(tip):
    return c.TIPLER[tip][0].split(" (")[0] if tip in c.TIPLER else "Yakınlık"


def _merkez_cumlesi(g, kayit, kid, y):
    p = _kisa(g.ad(kid), kid)
    if kayit["kaynak"] == "yakinlik":
        return f"{p} ile " + {3: "çok yakınsın", 2: "yakınsın", 1: "ara sıra yazışıyorsun"}.get(y, "tanışıyorsun")
    tip = kayit["tip"]
    if tip in _YONLU_SEN:
        return f"{p} senin {_YONLU_SEN[tip]}" if kayit["b"] == g.ben else f"{_ek(p, 'ilgi')} {_YONLU_BEN[tip]}"
    return _SIMETRIK_SEN[tip].format(p=p)


def _cift_cumlesi(g, kayit):
    a, b, tip = _kisa(g.ad(kayit["a"]), kayit["a"]), _kisa(g.ad(kayit["b"]), kayit["b"]), kayit["tip"]
    if tip in _YONLU_ISIM:
        return f"{a}, {_ek(b, 'ilgi')} {_YONLU_ISIM[tip]}."
    return _SIMETRIK[tip].format(a=a, b=b)


def _gerekce(g, yol, bugun):
    sonuc = []
    for i in range(len(yol) - 1):
        kayit = g.kenar_bul(yol[i], yol[i + 1])
        if i == 0:
            kid = yol[1]
            k = g.kisi[kid]
            son = _son_temas(k)
            cumle = _merkez_cumlesi(g, kayit, kid, _yakinlik(k))
            cumle += f"; son temas {_gun_once(son, bugun)}." if son else "; temas kaydı yok."
        else:
            cumle = _cift_cumlesi(g, kayit)
        sonuc.append(cumle)
    return sonuc


def _uyarilar(g, yol, bugun, dogrudan):
    sonuc = []
    ilk = g.kisi[yol[1]]
    son = _son_temas(ilk)
    if son and (bugun - son).days >= SOGUK_GUN:
        ad = _kisa(g.ad(yol[1]), yol[1])
        gun = (bugun - son).days
        sonuc.append(f"{ad} ile {_suredir(gun)} konuşmadın; yeniden bir temas kur." if dogrudan else
                     f"{ad} ile {_suredir(gun)} konuşmadın; tanıştırma istemeden önce bağı ısıt.")
    for i in range(1, len(yol) - 1):
        kayit = g.kenar_bul(yol[i], yol[i + 1])
        if kayit["tip"] == "tanisiyor":
            sonuc.append(f"{_kisa(g.ad(yol[i]), yol[i])} ile {_kisa(g.ad(yol[i + 1]), yol[i + 1])} yalnız tanışıyor; tanıştırma zayıf kalabilir.")
    if len(yol) - 1 >= AZAMI_KENAR:
        sonuc.append("Zincir uzun; her halka isteği biraz seyreltir. Yolu kısaltacak ortak bir tanıdık varsa onu dene.")
    uzerinde = set(yol) - {g.ben}
    for d in g.dikkat:
        kisiler = d.get("kisiler") or []
        if kisiler and set(kisiler) <= uzerinde and d.get("seviye") in ("yuksek", "orta") and d.get("metin"):
            sonuc.append(_tek_satir(d["metin"], 400))
    gorulen, temiz = set(), []
    for u in sonuc:
        if u not in gorulen:
            gorulen.add(u)
            temiz.append(u)
    return temiz[:UYARI_AZAMI]


def _amac_temizle(amac):
    return _tek_satir(amac, AMAC_AZAMI).rstrip(" .;,")


_RESMI_UNVAN = {"hoca", "dr", "prof", "doc"}
_RESMI_TUR = ("siyaset", "is")


def _hitap(kisi, ad=""):
    """"siz" ya da "sen": akademi türü kişiler, adında Hoca/Dr./Prof./Doç. olanlar ve merkeze yakınlığı ≤ 1 olan siyaset/iş kişileri
    "siz" ile karşılanır (kuralı ag_ozet.hitap ile aynı tut; ag_yol ona bağımlı değildir)."""
    kisi = kisi or {}
    ad = ad or kisi.get("ad") or ""
    if kisi.get("tur") == "akademi" or any(c.sade(p) in _RESMI_UNVAN for p in str(ad).split()):
        return "siz"
    return "siz" if kisi.get("tur") in _RESMI_TUR and _yakinlik(kisi) <= 1 else "sen"


def _selam_adi(ad, siz):
    """Hitap adı: ilk ad / unvanlı ad; "siz" kipinde unvandaki "Hoca" → "Hocam"."""
    kisa = _kisa(ad)
    return " ".join("Hocam" if siz and c.sade(p) == "hoca" else p for p in kisa.split()) if siz else kisa


def _taslak(isimler, son, amac, bugun, kisi=None):
    """isimler: yol üzerindeki kişilerin (merkez hariç) tam adları, hedef sonda; son: ilk adımın son temas tarihi;
    kisi: mesajın gideceği kişinin kaydı (ilk adım; doğrudan durumda hedef) → hitap kipi."""
    siz = _hitap(kisi, isimler[0]) == "siz"
    konu = f" Konu: {amac}." if amac else ""
    hedef = _kisa(isimler[-1])
    ilk = _selam_adi(isimler[0], siz)
    selam = f"Merhaba {ilk}, nasılsınız?" if siz else f"Selam {ilk}, nasılsın?"
    if len(isimler) == 1:
        uzun = son is None or (bugun - son).days >= 60
        if siz:
            giris = "Uzun zamandır konuşmadık; " if uzun else "Size bir şey danışmak istiyordum; "
            if amac:
                return f"{selam} {giris}sizinle şu konuda konuşmak isterim: {amac}. Müsait olduğunuzda kısa bir görüşme yapabilir miyiz?"
            return f"{selam} {giris}müsait olduğunuzda kısa bir görüşme yapabilir miyiz?"
        giris = "Uzun zamandır konuşmadık; " if uzun else "Sana bir şey danışmak istiyordum; "
        if amac:
            return f"{selam} {giris}seninle şu konuda konuşmak isterim: {amac}. Müsait olduğunda kısa bir sohbet edebilir miyiz?"
        return f"{selam} {giris}müsait olduğunda kısa bir sohbet edebilir miyiz?"
    if len(isimler) == 2:
        if siz:
            return (f"{selam} Bir ricam olacak: {hedef} ile tanışmak istiyorum.{konu} Siz onu tanıyorsunuz diye düşündüm; "
                    "uygun görürseniz bizi tanıştırabilir misiniz? İsterseniz kısa bir tanıtım metni de hazırlayayım.")
        return (f"{selam} Bir ricam olacak: {hedef} ile tanışmak istiyorum.{konu} Sen onu tanıyorsun diye düşündüm; "
                "uygun görürsen bizi tanıştırabilir misin? İstersen kısa bir tanıtım metni de hazırlayayım.")
    sonraki = _kisa(isimler[1])
    if siz:
        return (f"{selam} Bir ricam olacak: {hedef} ile tanışmak istiyorum.{konu} {sonraki} üzerinden ulaşmaya çalışıyorum; "
                f"siz {sonraki} ile tanışıyorsunuz diye düşündüm, uygun görürseniz beni tanıştırabilir misiniz? İsterseniz kısa bir tanıtım metni de hazırlayayım.")
    return (f"{selam} Bir ricam olacak: {hedef} ile tanışmak istiyorum.{konu} {sonraki} üzerinden ulaşmaya çalışıyorum; "
            f"sen {sonraki} ile tanışıyorsun diye düşündüm, uygun görürsen beni tanıştırabilir misin? İstersen kısa bir tanıtım metni de hazırlayayım.")


def _yol_kaydi(g, yol, bugun, amac):
    """Düğüm id listesinden sözleşmedeki 'yol' sözlüğü."""
    dugumler = [{"id": g.ben, "ad": g.ad(g.ben), "tur": "ben", "yakinlik": 3}]
    for kid in yol[1:]:
        k = g.kisi[kid]
        dugumler.append({"id": kid, "ad": g.ad(kid), "tur": k.get("tur") or "", "yakinlik": _yakinlik(k)})
    kenarlar = []
    for i in range(len(yol) - 1):
        kayit = g.kenar_bul(yol[i], yol[i + 1])
        kenarlar.append({"a": yol[i], "b": yol[i + 1], "tip": kayit["tip"],
                         "etiket": f"Yakınlık {_yakinlik(g.kisi[yol[i + 1]])}" if kayit["tip"] == "yakinlik" else _etiket(kayit["tip"]),
                         "guc": round(100 * kayit["w"]), "yonlu": kayit["tip"] in _YONLU_ISIM, "ters": kayit["tip"] in _YONLU_ISIM and kayit["a"] != yol[i]})
    dogrudan = len(yol) == 2
    ilk = g.kisi[yol[1]]
    return {"skor": _yol_skoru(g, yol),
            "dugumler": dugumler, "kenarlar": kenarlar, "ilk_adim": {"id": yol[1], "ad": g.ad(yol[1])},
            "gerekce": _gerekce(g, yol, bugun), "uyarilar": _uyarilar(g, yol, bugun, dogrudan),
            "taslak": _taslak([g.ad(x) for x in yol[1:]], _son_temas(ilk), _amac_temizle(amac), bugun, ilk)}


def _bugun(veri, bugun):
    return bugun or _tarih(veri.get("uretildi")) or date.today()


def _hedef_ozeti(g, kid):
    k = g.kisi[kid]
    return {"id": kid, "ad": g.ad(kid), "tur": k.get("tur") or "", "kurum": k.get("kurum") or "", "rol": k.get("rol") or ""}


def _yollar(g, hedef_id, k, amac, bugun):
    if not c.gecerli_id(hedef_id) or (hedef_id not in g.kisi and hedef_id not in g.haric and hedef_id != g.ben):
        raise ValueError("kişi bulunamadı")
    if hedef_id == g.ben:
        raise ValueError("Bu sensin; kendine yol çizmeye gerek yok.")
    if hedef_id in g.haric:
        raise ValueError("Bu kişi hariç listende; öneri üretilmez.")
    try:
        k = max(1, min(EN_COK_K, int(k)))
    except (TypeError, ValueError):
        k = VARSAYILAN_K
    hedef = _hedef_ozeti(g, hedef_id)
    if hedef_id in g.merkez_kenar:   # zaten tanıyorsun: tek "yol" merkez → hedef (gerginlik olsa da doğrudan bağ gerçektir)
        return {"hedef": hedef, "dogrudan": True, "yollar": [_yol_kaydi(g, [g.ben, hedef_id], bugun, amac)], "yok_nedeni": ""}
    secilen = _cesitlendir(g, _yen(g, hedef_id, k), k)
    return {"hedef": hedef, "dogrudan": False, "yollar": [_yol_kaydi(g, y, bugun, amac) for y in secilen],
            "yok_nedeni": "" if secilen else YOK_NEDENI}


# ---------- genel API ----------
def yollar(veri, hedef_id, k=3, amac="", bugun=None):
    """Merkezden `hedef_id`'ye en iyi `k` tanıştırma yolu. Saf işlev; ayrıntı için modül başındaki sözleşme.
    Hariç/bilinmeyen hedef ve merkezin kendisi için ValueError. `bugun` yalnız testler içindir (yoksa veri['uretildi'])."""
    return _yollar(_Graf(veri), hedef_id, k, amac, _bugun(veri, bugun))


def taslak(yol, veri, amac="", bugun=None):
    """`yollar` çıktısındaki bir yol için ilk adıma yazılacak mesaj (yol['taslak'] ile aynı kurallar; amac değiştirilebilir)."""
    dugumler = (yol or {}).get("dugumler") or []
    if len(dugumler) < 2:
        raise ValueError("Yolda en az iki kişi olmalı.")
    kmap = {k.get("id"): k for k in (veri.get("kisiler") or []) if isinstance(k, dict)}
    ilk = kmap.get(dugumler[1].get("id")) or {}
    return _taslak([d.get("ad") or d.get("id") or "" for d in dugumler[1:]], _son_temas(ilk), _amac_temizle(amac), _bugun(veri, bugun), ilk)


def _sorgu(metin):
    if not isinstance(metin, str):
        raise ValueError("Aranacak bir ifade yaz.")
    sorgu = _tek_satir(metin, 10_000)
    if len(sorgu) > ARAMA_AZAMI:
        raise ValueError(f"Arama en çok {ARAMA_AZAMI} karakter olabilir.")
    if not c.sade(sorgu):
        raise ValueError("Aranacak bir ifade yaz (ör. kurum, rol ya da alan).")
    return sorgu


def _eslesir(k, jetonlar):
    """Her sorgu jetonu ad/kurum/rol/alan/etiketlerdeki bir jetonla eşleşmeli (3+ harfte önek, kısa jetonda tam eşleşme)."""
    parcalar = [k.get("ad"), k.get("kurum"), k.get("rol")] + list(c.liste_yap(k.get("alan"))) + list(c.liste_yap(k.get("etiketler")))
    hay = c.sade(" ".join(str(p) for p in parcalar if p)).split()
    return all(any(h == j or (len(j) >= 3 and h.startswith(j)) for h in hay) for j in jetonlar)


def ara(veri, metin, amac="", bugun=None):
    """Serbest metinle hedef ara. Eşleşenler iki grup: `tanidiklarin` (yakınlık ≥ 1, zaten tanıyorsun) ve `hedefler` (yakınlık 0,
    her biri için en iyi yol; en çok 8, skora göre). Yolu olmayan eşleşme sonda `en_iyi: None` ile gelir."""
    sorgu = _sorgu(metin)
    jetonlar = c.sade(sorgu).split()
    g = _Graf(veri)
    bugun = _bugun(veri, bugun)
    eslesen = [kid for kid in sorted(g.kisi) if _eslesir(g.kisi[kid], jetonlar)]
    tanidik = []
    for kid in eslesen:
        k = g.kisi[kid]
        if _yakinlik(k) >= 1:
            tanidik.append({"id": kid, "ad": g.ad(kid), "kurum": k.get("kurum") or "", "rol": k.get("rol") or "", "yakinlik": _yakinlik(k), "sicaklik": _sicaklik(k)})
    tanidik.sort(key=lambda t: (-t["yakinlik"], -(t["sicaklik"] if t["sicaklik"] is not None else -1), t["ad"], t["id"]))
    uzak = [kid for kid in eslesen if _yakinlik(g.kisi[kid]) == 0]
    maliyet = _en_iyi_maliyetler(g)
    ulasilan = sorted((kid for kid in uzak if kid in maliyet), key=lambda kid: (maliyet[kid], g.ad(kid), kid))[:HEDEF_AZAMI]
    hedefler = []
    for kid in ulasilan:
        sonuc = _yollar(g, kid, 1, amac, bugun)
        if sonuc["yollar"]:
            hedefler.append({"hedef": sonuc["hedef"], "en_iyi": sonuc["yollar"][0], "skor": sonuc["yollar"][0]["skor"]})
    hedefler.sort(key=lambda h: (-h["skor"], h["hedef"]["ad"], h["hedef"]["id"]))
    for kid in sorted((x for x in uzak if x not in maliyet), key=lambda x: (g.ad(x), x)):
        if len(hedefler) >= HEDEF_AZAMI:
            break
        hedefler.append({"hedef": _hedef_ozeti(g, kid), "en_iyi": None, "skor": 0, "yok_nedeni": YOK_NEDENI})
    return {"sorgu": sorgu, "tanidiklarin": tanidik[:TANIDIK_AZAMI], "hedefler": hedefler[:HEDEF_AZAMI]}
