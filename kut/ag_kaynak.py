"""Açık kaynaklardan otomatik doldurma: herkese açık sayfalardan kişi ekler ve eksik alanları tamamlar.

Bilgisayardan dışarı yalnız herkese açık sayfa İSTEĞİ çıkar; ağındaki hiçbir veri gönderilmez.
Kaynaktan gelen olgular (ders, unvan, e-posta, fotoğraf) kaynağıyla birlikte doğrudan yazılır; yalnız boş alanlar doldurulur,
senin girdiğin değer ezilmez. Yorum gerektiren şeyler (tanışıklık vb.) soru olarak Doğrula'ya düşer.

Okul bağdaştırıcıları (OKULLAR sözlüğü; profildeki `okul` alanı anahtarı seçer, boş/bilinmiyorsa okul özellikleri kapalıdır):
- yeditepe (ÖRNEK bağdaştırıcı): ders programı (yeditepeders.com, herkese açık kopya) → derslerinin hocaları + "## Dersler";
  fakülte akademik kadro sayfası → unvan, e-posta, fotoğraf. Site çalışmıyorsa sonra yeniden denenir.
  Yeni okul eklemek için OKULLAR'a aynı alanlarla bir kayıt eklemek yeter (ders_json/kadro sayfası biçimi uyumluysa).
- ag_okullar.py kayıt defteri: ortak arayüzlü bağdaştırıcılar (İTÜ vb.); kayıtları dosya sonunda OKULLAR'a eklenir ve ders_hocalari
  `tur` alanı olan okulları oraya yönlendirir. Okuldan bağımsız OpenAlex/ORCID zenginleştirmesi ag_akademik.py (kapalı gelir; Doğrula'ya düşer).
"""
import html
import http.cookiejar
import json
import ipaddress
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

import ag_cekirdek as c
import ag_ice_aktar as ia
import ag_akademik

DURUM = os.path.join(ia.DEPO, "kaynak.json")
ONBELLEK = os.path.join(ia.DEPO, "kaynak")
TARAYICI = "Mozilla/5.0 (compatible; Kut/1; yerel kisisel ag araci)"
YENIDEN_DENE_SAAT = 6

# Okul bağdaştırıcıları: anahtar = profildeki `okul` alanının sade() hâli. Aşağıdaki "yeditepe" kaydı bir ÖRNEKTİR.
OKULLAR = {
    "yeditepe": {
        "ad": "Yeditepe Üniversitesi",
        "kisa": "Yeditepe",
        "ders_json": "https://yeditepeders.com/data/courses-{donem}.json",
        "ders_kaynak": "yeditepeders.com",
        "donem": "141",  # 141 = 2026 Güz (yeditepeders.com seasonId)
        "donem_adi": "Güz 2026",
        # ders kodu öneki → akademik kadro bloğu (site, bölüm numarası). Bölüm numarası sayfadaki data-block-ek-id'den.
        "kadro": {"ISE": ("https://mdbf.yeditepe.edu.tr", "141"), "ACM": ("https://bbbf.yeditepe.edu.tr", "91")},
        "kadro_adi": {"ISE": "Yeditepe Endüstri Müh.", "ACM": "Yeditepe Bilişim Sistemleri ve Teknolojileri"},
        "kadro_plugin": "yeditepe_akademik_kadro_block",
        "eposta_alani": "yeditepe.edu.tr",
        "profil_ornek": "yeditepe.edu.tr/tr/akademik-kadro/<n>",
        "etkinlik_url": "https://yeditepe.edu.tr/tr/etkinlikler",
        "kurum_en": ["yeditepe university"],   # OpenAlex'teki kurum adı (küçük harf); ag_akademik "kesin" eşleşmesi için
    },
}


def okul_ayar(okul=None):
    """Profildeki okula karşılık gelen bağdaştırıcı kaydı; okul boş ya da bilinmiyorsa None (okul özellikleri kapalı)."""
    if okul is None:
        okul = (c.ben().get("okul") or "")
    return OKULLAR.get(c.sade(okul))


def okul_adi():
    a = okul_ayar()
    return a["ad"] if a else ""


def _ay(okul=None):
    a = okul_ayar(okul)
    if not a:
        raise ValueError("okul tanımlı değil")
    return a


GUN = {"MON": "Pzt", "TUE": "Sal", "WED": "Çar", "THU": "Per", "FRI": "Cum", "SAT": "Cmt", "SUN": "Paz"}
UNVAN = re.compile(r"(Prof\.\s*Dr\.|Doç\.\s*Dr\.|Dr\.\s*Öğr\.\s*Üyesi|Öğr\.\s*Gör\.(?:\s*Dr\.)?|Arş\.\s*Gör\.(?:\s*Dr\.)?|"
                   r"Araştırma\s+Görevlisi(?:\s*Dr\.)?|Öğretim\s+Görevlisi(?:\s*Dr\.)?|Assoc\.\s*Prof\.(?:\s*Dr\.)?|Asst\.\s*Prof\.(?:\s*Dr\.)?|Prof\.(?:\s*Dr\.)?|Lecturer|Res\.\s*Asst\.)")


def durum():
    try:
        return json.load(open(DURUM, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _durum_yaz(d):
    os.makedirs(ia.DEPO, exist_ok=True)
    json.dump(d, open(DURUM, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


AZAMI_OKUMA = 30_000_000


def _kayit_alani(host):
    """'mdbf.okul.edu.tr' → 'okul.edu.tr' (basit kayıtlı alan adı: edu.tr/com.tr gibi ikili son ekleri bilir)."""
    p = (host or "").lower().strip(".").split(".")
    if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in ("edu", "com", "org", "gov", "net", "k12", "gen", "bel"):
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def _guvenli_url(url, kaynak=None):
    """SSRF koruması: yalnız http/https; ana makine adı İSTEKTEN HEMEN ÖNCE çözülür ve her adres küresel olmalı
    (localhost, 127.x, 10.x, 169.254.x, ::1 vb. reddedilir). kaynak verilirse (fotoğraf/profil bağlantıları) ana makine
    kaynak sayfanın kayıtlı alan adında olmalı. Geçersizse ValueError; geçerliyse url'yi döndürür."""
    u = urllib.parse.urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("yalnız http/https adresi")
    if kaynak and _kayit_alani(u.hostname) != _kayit_alani(urllib.parse.urlparse(kaynak).hostname):
        raise ValueError("adres kaynak sitenin dışında")
    try:
        adresler = {a[4][0] for a in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except (OSError, UnicodeError):
        raise ValueError("ana makine çözülemedi")
    if not adresler:
        raise ValueError("ana makine çözülemedi")
    for a in adresler:
        try:
            genel = ipaddress.ip_address(a.split("%")[0]).is_global
        except ValueError:
            genel = False
        if not genel:
            raise ValueError("özel/yerel ağ adresi")
    return url


class GuvenliYonlendirme(urllib.request.HTTPRedirectHandler):
    """Her yönlendirme adımını _guvenli_url'den geçirir (herkese açık adresten içeri sızdırma engeli)."""
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _guvenli_url(urllib.parse.urljoin(req.full_url, newurl))
        except ValueError as e:
            raise urllib.error.URLError("yönlendirme reddedildi: " + str(e))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def guvenli_acici(*islemciler):
    return urllib.request.build_opener(GuvenliYonlendirme, *islemciler)


def sinirli_oku(y, azami):
    ham = y.read(azami + 1)
    if len(ham) > azami:
        raise OSError("yanıt çok büyük")
    return ham


ISTEK_ARALIGI = 0.5   # aynı ana makineye iki istek arası en az bu kadar saniye (nazik tarama; sınır test için 0 yapılabilir)
_son_istek = {}


def _hiz_sinirla(host):
    bekle = ISTEK_ARALIGI - (time.monotonic() - _son_istek.get(host, -1e9))
    if bekle > 0:
        time.sleep(bekle)
    _son_istek[host] = time.monotonic()


def _istek(url, veri=None, basliklar=None, acici=None, zaman=25, azami=AZAMI_OKUMA, kaynak=None):
    try:
        _guvenli_url(url, kaynak)
    except ValueError as e:
        raise OSError("adres reddedildi: " + str(e))
    _hiz_sinirla(urllib.parse.urlparse(url).hostname)
    r = urllib.request.Request(url, data=veri, headers={"User-Agent": TARAYICI, **(basliklar or {})})
    with (acici or guvenli_acici()).open(r, timeout=zaman) as y:
        return sinirli_oku(y, azami), y.headers.get("Content-Type", "")


def tr_ad(ad):
    """'ADA DENEME ÖRNEK' → 'Ada Deneme Örnek' (Türkçe büyük/küçük harf kuralıyla)."""
    def kelime(w):
        if len(w) > 1 and w.upper() == w:
            ilk, kalan = w[0], w[1:]
            return ilk + kalan.replace("I", "ı").replace("İ", "i").lower()
        return w
    return " ".join(kelime(w) for w in ad.split())


# ---------- okul: ders programı → hocalar ----------
def _ders_verisi(yenile=False):
    os.makedirs(ONBELLEK, exist_ok=True)
    ay = _ay()
    yol = os.path.join(ONBELLEK, f"{c.sade(c.ben().get('okul') or '')}-dersler-{ay['donem']}.json")
    if yenile or not os.path.exists(yol) or time.time() - os.path.getmtime(yol) > 24 * 3600:
        ham, _ = _istek(ay["ders_json"].format(donem=ay["donem"]), zaman=60)
        json.loads(ham)  # bozuk veriyi önbelleğe yazma
        open(yol, "wb").write(ham)
    return json.load(open(yol, encoding="utf-8"))


def _ders_coz(s, harfli=False):
    """'ISE 426-1' → ('ISE 426', '1'); 'ISE 426' → ('ISE 426', None). harfli=True: şube harf de olabilir ('CS 201-A')."""
    sube = r"([0-9A-Za-z]{1,3})" if harfli else r"(\d+)"
    m = re.match(r"^\s*([A-Za-z]{2,5})\s*(\d{3}[A-Za-z]?)\s*(?:[-/.ş]\s*" + sube + r")?\s*$", s or "")
    return (f"{m.group(1).upper()} {m.group(2).upper()}", m.group(3)) if m else (None, None)


def ders_hocalari(dersler):
    """Profildeki derslerin hocaları: {ad: {satirlar, kodlar, bolum}}. Kayıt defterindeki (ag_okullar) okulda bağdaştırıcı çalışır;
    Yeditepe (OKULLAR'daki tür alanı olmayan kayıt) eski yolu izler."""
    ay = okul_ayar()
    if ay and ay.get("tur"):
        import ag_okullar as ok
        return ok.hocalar(ay, dersler)
    veri = _ders_verisi()
    sonuc, bulunamayan = {}, []
    for d in dersler:
        kod, sube = _ders_coz(d)
        if not kod:
            bulunamayan.append(d)
            continue
        eslesen = [x for x in veri if x.get("code") == kod and (sube is None or str(x.get("section")) == sube)]
        if not eslesen:
            bulunamayan.append(d)
        for x in eslesen:
            saat = ", ".join(f"{GUN.get(m.get('day'), m.get('day'))} {m.get('startTime')}–{m.get('endTime')}"
                             f"{(' ' + m['room']) if m.get('room') else ''}{(' (' + m['typeShort'] + ')') if m.get('typeShort') not in (None, 'LEC') else ''}"
                             for m in x.get("meetings") or [])
            for h in x.get("instructors") or []:
                ad = tr_ad(" ".join(h.split()))
                satir = f"{_ay()['donem_adi']} · {kod}-{x.get('section')} {x.get('name') or x.get('nameEn') or ''} · {saat}".strip()
                sonuc.setdefault(ad, {"satirlar": [], "kodlar": set(), "bolum": x.get("departmentName") or ""})
                if satir not in sonuc[ad]["satirlar"]:
                    sonuc[ad]["satirlar"].append(satir)
                sonuc[ad]["kodlar"].add(kod.split()[0])
    return sonuc, bulunamayan


def _sirali_alt_kume(kisa, uzun):
    """Kısa adın tüm parçaları uzun adda aynı sırayla var mı ('Ahmet Yıldırım' ⊂ 'Ahmet Can Yıldırım')."""
    it = iter(uzun)
    return all(p in it for p in kisa)


def _ad_alt_kume(a, b):
    """İki ad (sade parça listesi) aynı kişi olabilir mi: ilk ad aynı, en az iki parça, kısa ad uzunun sıralı alt kümesi.
    'Ahmet Yıldırım' ≈ 'Ahmet Can Yıldırım' ama 'Ahmet Yıldırım' ≠ 'Ahmet Kaya Yılmaz'."""
    kisa, uzun = (a, b) if len(a) <= len(b) else (b, a)
    return len(kisa) >= 2 and kisa[0] == uzun[0] and _sirali_alt_kume(kisa, uzun)


def _kisi_esle(ad, kisiler):
    hedef = c.sade(ad)
    for k in kisiler:
        if c.sade(k.get("ad") or "") == hedef:
            return k
    # "Ada Deneme" ↔ "Ada Deneme Örnek" gibi: yalnız ad alt küme uyumunda
    p = hedef.split()
    for k in kisiler:
        if _ad_alt_kume(p, c.sade(k.get("ad") or "").split()):
            return k
    return None


# ---------- okul: fakülte akademik kadro (unvan, e-posta, fotoğraf) ----------
def _kadro_html(site, bolum):
    """Drupal 'akademik kadro' bloğunu sayfanın kendi yaptığı gibi ister: önce oturum anahtarı, sonra ajax POST."""
    acici = guvenli_acici(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    _istek(site + "/tr", acici=acici)
    token = _istek(site + "/session/token", acici=acici)[0].decode().strip()
    blok = f"akademik_kadro_config_key_{bolum}"
    ayar = {"plugin_id": _ay()["kadro_plugin"], "block_id": blok, "settings": {"department": bolum}}
    form = urllib.parse.urlencode({"plugin_id": ayar["plugin_id"], "block_id": blok, "settings[department]": bolum,
                                   "_drupal_ajax": "1"}).encode()
    parcalar = []
    for govde, tip in ((form, "application/x-www-form-urlencoded; charset=UTF-8"), (json.dumps(ayar).encode(), "application/json")):
        try:
            ham, _ = _istek(site + "/tr/ajax/akademik-kadro?_wrapper_format=drupal_ajax", veri=govde, acici=acici,
                            basliklar={"Content-Type": tip, "X-CSRF-Token": token, "X-Requested-With": "XMLHttpRequest",
                                       "Accept": "application/json, text/javascript, */*; q=0.01", "Referer": site + "/tr"})
        except OSError:
            continue
        metin = ham.decode("utf-8", "replace")
        try:
            komutlar = json.loads(metin)
            parcalar = [k.get("data") for k in komutlar if isinstance(k, dict) and isinstance(k.get("data"), str)]
        except ValueError:
            parcalar = [metin]
        if any("<img" in p for p in parcalar):
            break
    return "\n".join(parcalar), acici


def _ayni_site(site, bag):
    """Sayfadan gelen göreli/mutlak bağlantıyı site köküne bağlar; http(s) değilse ya da başka bir alan adındaysa boş döner."""
    t = urllib.parse.urljoin(site + "/", bag)
    u = urllib.parse.urlparse(t)
    ok = u.scheme in ("http", "https") and u.hostname and _kayit_alani(u.hostname) == _kayit_alani(urllib.parse.urlparse(site).hostname)
    return t if ok else ""


def _eposta_deseni():
    """Okulun e-posta alan adı biliniyorsa yalnız o alan adı; bilinmiyorsa her e-posta."""
    alan = (okul_ayar() or {}).get("eposta_alani")
    return r"([\w.+-]+@" + re.escape(alan) + ")" if alan else r"([\w.+-]+@[\w-]+(?:\.[\w-]+)+)"


def _kadro_kartlari(sayfa, site):
    """Kadro HTML'inden kişi kartları: ad, unvan, e-posta, fotoğraf, profil bağlantısı. Biçim bilinmediği için toleranslı."""
    kartlar = []
    # Her kişi bir 'akademik-kadro-item' kutusu (profil bağlantısı resimden ÖNCE gelir); bu sınıf yoksa resimlerden böl.
    parcalar = re.split(r'(?=<div[^>]*class="[^"]*akademik-kadro-item)', sayfa)[1:] or re.split(r"(?=<img\b)", sayfa)[1:]
    for parca in parcalar:
        img = re.search(r'<img\b[^>]*?(?:data-src|src)="([^"]+)"', parca)
        metin = html.unescape(re.sub(r"<[^>]+>", "\n", parca[:4000]))
        satirlar = [" ".join(x.split()) for x in metin.split("\n") if x.strip()]
        alt = re.search(r'<img\b[^>]*?alt="([^"]+)"', parca)
        eposta = re.search(_eposta_deseni(), parca)
        profil = re.search(r'<a\b[^>]*href="([^"#]*akademik-kadro/\d+)"', parca)
        unvan = next((UNVAN.search(s).group(1) for s in satirlar if UNVAN.search(s)), "")
        ad = " ".join(html.unescape(alt.group(1)).split()) if alt else ""
        if not ad:  # alt yoksa ilk satırdan unvanı at
            ad = " ".join(UNVAN.sub("", next((s for s in satirlar if UNVAN.search(s)), satirlar[0] if satirlar else "")).split())
        kartlar.append({"ad": ad, "foto": _ayni_site(site, html.unescape(img.group(1))) if img else "",
                        "metin": satirlar[:12], "alt": html.unescape(alt.group(1)) if alt else "",
                        "eposta": eposta.group(1) if eposta else "", "unvan": " ".join(unvan.split()),
                        "profil": _ayni_site(site, html.unescape(profil.group(1))) if profil else ""})
    return kartlar


def kadro_onbellek_yolu(site, bolum):
    host = urllib.parse.urlparse(site).netloc.split(".")[0] or "site"
    return os.path.join(ONBELLEK, f"kadro-{host}-{bolum}.json")


def kadro_onbellek_yaz(site, bolum, onek, kartlar):
    """Kadro kartlarını (ad, unvan, e-posta, profil, foto, bölüm anahtarı) sonradan ağsız kullanılmak üzere saklar."""
    os.makedirs(ONBELLEK, exist_ok=True)
    kayit = {"site": site, "bolum": bolum, "onek": onek, "bolum_adi": (okul_ayar() or {}).get("kadro_adi", {}).get(onek, ""), "tarih": date.today().isoformat(),
             "kartlar": [{k: x.get(k, "") for k in ("ad", "unvan", "eposta", "profil", "foto")} for x in kartlar]}
    yol = kadro_onbellek_yolu(site, bolum)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=1)
    return yol


def kadro_onbellek_oku():
    """Önbellekteki tüm kadro kayıtları (ağ isteği yok)."""
    sonuc = []
    if os.path.isdir(ONBELLEK):
        for ad in sorted(os.listdir(ONBELLEK)):
            if ad.startswith("kadro-") and ad.endswith(".json"):
                try:
                    with open(os.path.join(ONBELLEK, ad), encoding="utf-8") as f:
                        kayit = json.load(f)
                except (OSError, ValueError):
                    continue
                if isinstance(kayit, dict) and isinstance(kayit.get("kartlar"), list):
                    kayit["kartlar"] = [x for x in kayit["kartlar"] if isinstance(x, dict)]  # bozuk kartları ele
                    sonuc.append(kayit)
    return sonuc


def _kart_unvan_uyumlu(kart, k):
    """Kişinin rolünde bir akademik unvan varsa kartın unvanıyla çelişmemeli (boşsa çelişki sayılmaz)."""
    kullanici_unvan = UNVAN.search(k.get("rol") or "")
    kart_unvan = (kart.get("unvan") or "").strip()
    return not (kullanici_unvan and kart_unvan and c.sade(kart_unvan) not in c.sade(k.get("rol") or ""))


def _kart_bolum_uyumlu(bolum_adi, k):
    """Kartın bölümü ('Örnek Okul Endüstri Müh.') kişinin kurumundaki bölümle ('Örnek Okul · Endüstri Mühendisliği') çelişmemeli."""
    parcalar = [x.strip() for x in (k.get("kurum") or "").split("·")]
    if not bolum_adi or len(parcalar) < 2 or not parcalar[1]:
        return True
    onek = lambda s: {w[:3] for w in c.sade(s).split() if len(w) > 2 and w not in (c.sade((okul_ayar() or {}).get("kisa") or ""), "universitesi", "fakultesi")}
    return bool(onek(bolum_adi) & onek(parcalar[1]))


def kart_esle(kart, kisiler, bolum_adi=""):
    """Kadro kartını ağdaki kişiyle eşler: önce e-posta, sonra tam ad, en son ad alt küme uyumu (kısa ad uzunun sıralı alt kümesi).
    Ad tam değilken unvan ya da bölüm çelişiyorsa eşlemez."""
    if not isinstance(kart, dict):
        return None
    ep = (kart.get("eposta") or "").lower()
    if ep:
        for k in kisiler:
            if (k.get("eposta") or "").lower() == ep:
                return k
    hedef = c.sade(kart.get("ad") or "")
    if not hedef:
        return None
    for k in kisiler:
        if c.sade(k.get("ad") or "") == hedef:
            return k
    p = hedef.split()
    for k in kisiler:
        if (_ad_alt_kume(p, c.sade(k.get("ad") or "").split())
                and _kart_unvan_uyumlu(kart, k) and _kart_bolum_uyumlu(bolum_adi, k)):
            return k
    return None


# ---------- fotoğraf ----------
VARSAYILAN_FOTO = re.compile(r"default|avatar|placeholder|no[-_]?image|no[-_]?photo|silhouette|anonymous|dummy|user[-_]icon|blank[-_.]", re.I)


def varsayilan_foto_mu(url):
    """Sitenin yer tutucu/varsayılan avatarı mı (URL'e bakar; kişiye ait gerçek fotoğraf sayılmaz).
    Drupal'ın '/sites/default/files/' klasörü 'default' sayılmaz; '/themes/' altındaki görseller site görselidir, kişi fotoğrafı değil."""
    if not (url or "").strip():
        return True
    yol = urllib.parse.unquote(urllib.parse.urlparse(url).path).replace("/sites/default/", "/sites/_/")
    return bool(VARSAYILAN_FOTO.search(yol)) or "/themes/" in yol


def _foto_indir(url, acici=None):
    """Kişi fotoğrafını indirir (JPEG/PNG, < 3 MB); varsayılan avatar, bozuk ya da büyük dosyada None. Kilit DIŞINDA çağır."""
    if varsayilan_foto_mu(url):
        return None
    try:
        ham, _ = _istek(url, acici=acici, azami=3_100_000)
    except OSError:
        return None
    return ham if (ham[:3] == b"\xff\xd8\xff" or ham[1:4] == b"PNG") and len(ham) < 3_000_000 else None


def _duz(x):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", x)).split())


def _bas_harf(x):
    """'YEDİTEPE ÜNİVERSİTESİ' gibi tamamı büyük metni okunur yap; karışık yazılmışa dokunma."""
    return (" " + tr_ad(x) + " ").replace(" Ve ", " ve ").replace(" İle ", " ile ").strip() if x.upper() == x else x


def profil_oku(url, acici=None):
    """Akademik kadro profil sayfası (okul sitesindeki akademik-kadro/<n> sayfası): çalışma alanları, ORCID, yayın sayısı,
    akademik görevler, öğrenim, üniversite dışı deneyim. Ayrıştırma kurala dayalı; model kullanılmaz."""
    sayfa = _istek(url, acici=acici)[0].decode("utf-8", "replace")
    p = {"alanlar": [], "orcid": "", "makale": 0, "ozgecmis": []}
    m = re.search(r"Çalışma Alanları</span>\s*:(.*?)</p>", sayfa, re.S)
    if m:
        p["alanlar"] = [x for x in (_duz(y) for y in m.group(1).split(",")) if x and x != "Mühendislik Temel Alanı"]
    m = re.search(r"ORCID:\s*([\d-]{15,19}X?)", sayfa)
    p["orcid"] = m.group(1) if m else ""
    m = re.search(r'id="makaleler".*?(?=<div class="tab-pane)', sayfa, re.S)
    p["makale"] = len(re.findall(r"<li\b", m.group(0))) if m else 0

    def bolum(baslik):
        m = re.search(rf"<h5[^>]*>\s*{baslik}\s*</h5>\s*<ul[^>]*>(.*?)</ul>", sayfa, re.S)
        for li in re.findall(r"<li\b[^>]*>(.*?)</li>", m.group(1), re.S) if m else []:
            rozet = [_duz(x) for x in re.findall(r'<span class="badge[^"]*"[^>]*>(.*?)</span>', li, re.S)]
            ps = [_duz(x) for x in re.findall(r"<p>(.*?)</p>", li, re.S)]
            donem = next((x for x in rozet if re.fullmatch(r"\d{4}(\s*-\s*\d{4})?", x)), "")
            ad = next((x for x in rozet if x != donem and x != "Diğer"), "")
            yield donem, _bas_harf(ad), [_bas_harf(x) for x in ps if x and not x.startswith("Tez adı")]

    for donem, ad, ps in bolum("Akademik Görevler"):
        p["ozgecmis"].append((donem, ad or (ps[0] if ps else ""), ps[-1] if len(ps) > 1 else (ps[0] if ps else "")))
    for donem, ad, ps in bolum("Öğrenim Bilgisi"):
        p["ozgecmis"].append((donem, ad, ", ".join(ps[:2])))
    for donem, _, ps in bolum("Üniversite Dışı Deneyim"):
        if ps:
            p["ozgecmis"].append((donem, ps[0], ps[1] if len(ps) > 1 else ""))
    p["ozgecmis"].sort(key=lambda x: x[0][-4:] if x[0] else "", reverse=True)
    return p


def _kart_bul(ad, kartlar):
    hedef = c.sade(ad).split()
    for k in kartlar:
        ic = " " + c.sade(" ".join(k["metin"] + [k["alt"]])) + " "
        if all(f" {p} " in ic or f"{p} " in ic for p in hedef):
            return k
    return None


# ---------- çalıştırıcı ----------
def doldur(kilit, yenile_cb, zorla=False):
    """Profildeki okul + derslerden hocaları ekler/günceller, kadro sayfasından eksikleri tamamlar. Dönen: özet."""
    b = c.ben()
    okul = c.sade(b.get("okul") or "")
    dersler = c.liste_yap(b.get("dersler"))
    ozet = {"eklenen": [], "guncellenen": [], "bekleyen": [], "hata": []}
    ay = OKULLAR.get(okul)
    if not ay or not dersler:
        ozet["hata"].append("Profilde tanımlı bir okul (" + ", ".join(sorted(OKULLAR)) + ") ve en az bir ders olmalı (Profilimi düzenle).")
        return ozet
    try:
        hocalar, bulunamayan = ders_hocalari(dersler)
    except (OSError, ValueError) as e:
        ozet["hata"].append(f"ders programı alınamadı: {e}")
        return ozet
    if bulunamayan:
        ozet["hata"].append("programda bulunamayan ders: " + ", ".join(bulunamayan))
    d = durum()
    donem_adi = ag_okullar.KAYIT[ay["anahtar"]].donem_adi_al() if ay.get("tur") else ay["donem_adi"]
    kaynak_ders = f"{ay['ders_kaynak']} ({donem_adi} ders programı, {date.today():%d.%m.%Y})"

    # kadro sayfası (ağ isteği kilit dışında)
    kartlar, hata_kadro, acici = {}, {}, None
    gerekli = {o for h in hocalar.values() for o in h["kodlar"] if o in ay["kadro"]}
    for onek in gerekli:
        site, bolum = ay["kadro"][onek]
        anahtar = f"kadro:{site}:{bolum}"
        son = d.get(anahtar, {})
        if not zorla and son.get("durum") == "hata" and time.time() - son.get("zaman", 0) < YENIDEN_DENE_SAAT * 3600:
            hata_kadro[onek] = son.get("mesaj", "")
            continue
        try:
            sayfa, acici = _kadro_html(site, bolum)
            kartlar[onek] = _kadro_kartlari(sayfa, site)
            if not kartlar[onek]:
                raise ValueError("kadro sayfasında kişi kartı bulunamadı")
            kadro_onbellek_yaz(site, bolum, onek, kartlar[onek])
            d[anahtar] = {"durum": "ok", "zaman": time.time(), "kisi": len(kartlar[onek])}
        except Exception as e:  # site çökük / biçim değişmiş: sonra yeniden dene
            d[anahtar] = {"durum": "hata", "zaman": time.time(), "mesaj": str(e)[:200]}
            hata_kadro[onek] = str(e)[:200]

    fotolar = {}
    for ad, h in hocalar.items():
        kart = next((_kart_bul(ad, kartlar[o]) for o in h["kodlar"] if o in kartlar), None)
        if kart and kart["foto"]:
            ham = _foto_indir(kart["foto"], acici)
            if ham:
                fotolar[ad] = ham
        h["kart"] = kart
        h["profil"] = None
        if kart and kart["profil"]:
            try:
                h["profil"] = profil_oku(kart["profil"], acici)
            except (OSError, ValueError, AttributeError):
                pass

    # dersi olmayan bölüm personelinin fotoğrafları da kilit dışında indirilir (kilit yalnız yazma için)
    personel_fotolar, on_kisiler = {}, c.kisileri_oku()
    for onek, liste in kartlar.items():
        for kart in liste:
            k = kart_esle(kart, on_kisiler, ay["kadro_adi"].get(onek, ""))
            if k is not None and not k.get("foto") and kart.get("foto") and kart["foto"] not in personel_fotolar:
                personel_fotolar[kart["foto"]] = _foto_indir(kart["foto"], acici)

    with kilit:
        kisiler = c.kisileri_oku()
        sorular, islenen = [], set()
        for ad, h in hocalar.items():
            k = _kisi_esle(ad, kisiler)
            if k is None:
                kid = c.bos_slug(ad)
                bolum = h["bolum"].replace(" Lisans Programı", "")
                alanlar = {"ad": ad, "foto": "", "tur": "akademi", "kurum": f"{ay['kisa']} · {bolum}" if bolum else ay["ad"],
                           "rol": "Öğretim elemanı", "alan": ["egitim"], "nereden": [okul], "yakinlik": "0"}   # yakınlık yalnız kullanıcı onayıyla artar
                govde = c.yeni_govde(ad, f"{kaynak_ders}; Kut otomatik ekledi.")
                ozet["eklenen"].append(ad)
                sorular.append({"kisi": kid, "alan": "soru", "deger": f"{ad} ile dersi dışında birebir tanışıklığın var mı?",
                                "kaynak": "Kut · kaynaktan doldurma"})
            else:
                kid = k["id"]
                islenen.add(kid)
                alanlar = c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))  # ham hali (kisileri_oku'nun eklediği boş listeler yazılmasın)
                govde = alanlar.pop("govde")
            onceki = govde
            for satir in h["satirlar"]:
                kod_sube = satir.split(" · ")[1].split(" ")[0] + " " + satir.split(" · ")[1].split(" ")[1]
                if kod_sube not in c.bolum_oku(govde, "Dersler"):
                    govde = c.bolume_ekle(govde, "Dersler", f"{satir} · profildeki dersin · kaynak: {ay['ders_kaynak']}")
            kart = h.get("kart")
            degisen = []
            if kart:
                rol = alanlar.get("rol") or ""
                if kart["unvan"] and c.sade(kart["unvan"]) not in c.sade(rol):
                    alanlar["rol"] = kart["unvan"] if rol in ("", "Öğretim elemanı") else f"{kart['unvan']} · {rol}"; degisen.append("unvan")
                if kart["eposta"] and not alanlar.get("eposta"):
                    alanlar["eposta"] = kart["eposta"]; degisen.append("e-posta")
                if ad in fotolar and not alanlar.get("foto"):
                    alanlar["foto"] = c.foto_kaydet(kid, fotolar[ad]); degisen.append("fotoğraf")
                if kart["profil"] and kart["profil"] not in govde:
                    govde = re.sub(r"\nProfil: \S+\n", "\n", govde)
                    govde = govde.replace("\n## ", f"\nProfil: {kart['profil']}\n\n## ", 1); degisen.append("profil bağlantısı")
                pr = h.get("profil")
                if pr:
                    mevcut = c.sade(c.bolum_oku(govde, c.OZGECMIS_BASLIK))
                    yeni = 0
                    for donem, baslik, ayrinti in pr["ozgecmis"][:15]:
                        if baslik and c.sade(f"{donem or '?'} · {baslik}".replace("·", "-")) not in mevcut.replace("·", "-"):
                            parca = [donem or "?", baslik] + ([ayrinti] if ayrinti else [])
                            govde = c.bolume_ekle(govde, c.OZGECMIS_BASLIK, " · ".join(x.replace("·", "-") for x in parca) + f" · kaynak: {ay['kisa']} profil sayfası")
                            yeni += 1
                    if yeni:
                        degisen.append(f"özgeçmiş ({yeni} madde)")
                    if not c.bolum_oku(govde, c.HAKKINDA_BASLIK) and (pr["alanlar"] or pr["orcid"]):
                        parca = ([f"Çalışma alanları: {', '.join(pr['alanlar'])}."] if pr["alanlar"] else []) + ([f"{pr['makale']} makale."] if pr["makale"] else []) + ([f"ORCID {pr['orcid']}."] if pr["orcid"] else [])
                        govde = c.bolume_ekle(govde, c.HAKKINDA_BASLIK, " ".join(parca) + f" (kaynak: {ay['kisa']} profil sayfası)")
                        degisen.append("hakkında")
                    if pr["alanlar"] and not c.liste_yap(alanlar.get("etiketler")):
                        alanlar["etiketler"] = [re.sub(r"[^a-z0-9]+", "-", c.sade(x)).strip("-") for x in pr["alanlar"][:5]]
                        degisen.append("etiketler")
                if degisen:
                    govde = c.bolume_ekle(govde, "Kaynaklar", f"{date.today():%d.%m.%Y} · {', '.join(degisen)} · {ay['kisa']} akademik kadro ve profil sayfası")
            else:
                for o in h["kodlar"]:
                    if o in hata_kadro:
                        ozet["bekleyen"].append(f"{ad}: fotoğraf/unvan bekliyor (kadro sayfası: {hata_kadro[o][:80]})")
                    elif o in kartlar:
                        ozet["bekleyen"].append(f"{ad}: bölüm kadro sayfasında yok (yarı zamanlı ya da başka bölümden olabilir)")
            if govde != onceki or degisen or k is None:
                if k is not None:
                    c.surum_al(kid)
                    ozet["guncellenen"].append(ad + (f" ({', '.join(degisen)})" if degisen else " (dersler)"))
                c.kisi_yaz(kid, alanlar, govde)
        _personel_doldur(kartlar, kisiler, islenen, personel_fotolar, ozet, sorular)
        if sorular:
            c.cikarim_ekle(sorular)
        if ozet["eklenen"] or ozet["guncellenen"]:
            yenile_cb()
    # okuldan bağımsız akademik zenginleştirme (OpenAlex/ORCID; yalnız Kaynaklar'da açıksa): kişi dosyasına yazılmaz, Doğrula'ya düşer
    ozet["dogrulanacak"] = []
    if ag_akademik.acik() and hocalar:
        on_kisiler = c.kisileri_oku()
        hedefler = [(k["id"], k["ad"]) for k in (_kisi_esle(ad, on_kisiler) for ad in hocalar) if k]
        try:
            yeni = ag_akademik.oneriler(hedefler, ay, d)
            if yeni:
                with kilit:
                    c.cikarim_ekle(yeni)
                ozet["dogrulanacak"] = [y["kisi"] for y in yeni]
        except Exception as e:   # API çöktü: okul doldurma sonucunu bozma
            ozet["hata"].append(f"akademik profil sorgusu yapılamadı: {str(e)[:80]}")
    d["son_doldurma"] = {"zaman": time.time(),"tarih": datetime.now().isoformat(timespec="seconds"),
                         "ozet": {x: len(y) for x, y in ozet.items()}}
    _durum_yaz(d)
    return ozet


def _ad_uyumlu(a, b):
    """Biri diğerinin ad kelimelerinin alt kümesiyse uyumlu ('Ayla Kurgu' ⊂ 'Ayla Nur Deniz Kurgu')."""
    p, q = set(c.sade(a).split()), set(c.sade(b).split())
    return not p or not q or p <= q or q <= p


def _personel_doldur(kartlar, kisiler, islenen, fotolar, ozet, sorular):
    """Dersi olmayan ama ağda bulunan bölüm personelini (ör. asistan) kadro kartıyla eşler, yalnız boş alanları doldurur.
    Ad çelişkisinde adı EZMEZ; soru önerir. fotolar: {foto url: bayt} (kilit dışında önceden indirilmiş; ağ isteği burada yok)."""
    bugun = date.today().strftime("%d.%m.%Y")
    kadro_adi = (okul_ayar() or {}).get("kadro_adi", {})
    for onek, liste in kartlar.items():
        for kart in liste:
            k = kart_esle(kart, kisiler, kadro_adi.get(onek, ""))
            if k is None or k["id"] in islenen:
                continue
            islenen.add(k["id"])
            kid = k["id"]
            alanlar = c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))
            govde = alanlar.pop("govde")
            onceki, degisen = dict(alanlar), []
            rol = alanlar.get("rol") or ""
            if kart["unvan"] and c.sade(kart["unvan"]) not in c.sade(rol):
                alanlar["rol"] = kart["unvan"] if rol in ("", "Öğretim elemanı") else f"{kart['unvan']} · {rol}"; degisen.append("unvan")
            if kart["eposta"] and not alanlar.get("eposta"):
                alanlar["eposta"] = kart["eposta"]; degisen.append("e-posta")
            ham = (fotolar or {}).get(kart["foto"]) if kart["foto"] and not alanlar.get("foto") else None
            if ham and not varsayilan_foto_mu(kart["foto"]):
                alanlar["foto"] = c.foto_kaydet(kid, ham); degisen.append("fotoğraf")
            if kart["profil"] and kart["profil"] not in govde:
                govde = re.sub(r"\nProfil: \S+\n", "\n", govde)
                govde = govde.replace("\n## ", f"\nProfil: {kart['profil']}\n\n## ", 1); degisen.append("profil bağlantısı")
            if kart["ad"] and not _ad_uyumlu(kart["ad"], k.get("ad") or ""):
                sorular.append({"kisi": kid, "alan": "soru", "kaynak": "Kut · kadro sayfası",
                                "deger": f"Resmi kadro sayfasında adı '{kart['ad']}' yazıyor; kayıttaki '{k.get('ad')}' yanlış mı?"})
            if degisen:
                govde = c.bolume_ekle(govde, "Kaynaklar", f"{bugun} · {', '.join(degisen)} · fakülte akademik kadro sayfası")
                c.surum_al(kid)
                c.kisi_yaz(kid, alanlar, govde)
                ozet["guncellenen"].append(f"{k.get('ad')} ({', '.join(degisen)})")


def otomatik_gerekli():
    """Sunucu açılışında: son doldurmadan 24 saat geçtiyse ya da kadro sayfası beklemedeyse ve yeniden deneme zamanı geldiyse."""
    if not okul_ayar() or not c.liste_yap(c.ben().get("dersler")):
        return False   # okul bağdaştırıcısı ya da ders yoksa okul özellikleri kapalı
    d = durum()
    son = d.get("son_doldurma", {}).get("zaman", 0)
    if time.time() - son > 24 * 3600:
        return True
    return any(isinstance(v, dict) and v.get("durum") == "hata" and time.time() - v.get("zaman", 0) > YENIDEN_DENE_SAAT * 3600
               for k, v in d.items() if k.startswith("kadro:"))


# Kayıt defterindeki okullar açılır listeye buradan girer (en sonda: ag_okullar, ag_kaynak'a yalnız çağrı anında ihtiyaç duyar).
import ag_okullar  # noqa: E402
OKULLAR.update(ag_okullar.okul_kayitlari())
