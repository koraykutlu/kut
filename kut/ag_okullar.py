"""Okul bağdaştırıcıları: ortak arayüz ve kayıt defteri.

Her bağdaştırıcı bir okulun HERKESE AÇIK ders programından ders kodu → şube → hocalar eşlemesini çıkarır. Giriş isteyen (OBS/öğrenci girişi),
robots.txt'in yasakladığı ya da bot korumalı kaynaklar kullanılmaz. Ağ yalnız ag_kaynak._istek üzerinden gider (SSRF koruması,
zaman aşımı, boyut sınırı, User-Agent, istek hızı sınırı); yanıtlar önbelleğe alınır. Okul, kullanıcı Ayarlar → Kaynaklar'dan seçmedikçe
hiçbir okul sitesine istek atılmaz.

Arayüz (Baglastirici):
- anahtar, ad, kisa, alan_adi, ders_kaynak, donem_adi
- dersler(kodlar) → (kayitlar, bulunamayan); kayit = {kod, sube, ad, hocalar: [ad], saat, bolum}
- hoca_profili(ad_veya_url) → {unvan, eposta, foto, ozgecmis, orcid} (kaynak profil sayfası sunmuyorsa boş sözlük)

Kayıt defteri: KAYIT[anahtar]. okul_kayitlari() → ag_kaynak.OKULLAR'a eklenen kayıtlar (Ayarlar açılır listesi buradan dolar).
Yeditepe'nin kaydı ag_kaynak.OKULLAR'da kalır (eski davranış birebir); buradaki YeditepeBaglastirici yalnız ortak arayüzü sağlar.

Yeni okul: Baglastirici'dan türet (ya da BannerBaglastirici'ya adres ver), kaydet() ile kayıt defterine ekle, tests/fixtures/ altına
küçük bir HTML/JSON örneği koyup ayrıştırıcıyı test et. Kaynağın robots.txt ve kullanım koşullarını önce kontrol et.
"""
import html as htmlmod
import json
import os
import re
import time

KAYIT = {}


def _kn():
    import ag_kaynak
    return ag_kaynak


def kaydet(b):
    KAYIT[b.anahtar] = b
    return b


def okul_kayitlari():
    """ag_kaynak.OKULLAR'a eklenecek kayıtlar (Yeditepe hariç: o zaten orada)."""
    return {a: b.kayit() for a, b in KAYIT.items() if a != "yeditepe"}


def hocalar(ay, dersler):
    """ag_kaynak.ders_hocalari yolunun çıktısı: ({ad: {satirlar, kodlar, bolum}}, bulunamayan)."""
    b = KAYIT[ay["anahtar"]]
    kayitlar, bulunamayan = b.dersler(dersler)
    return kayitlardan_hocalar(kayitlar, b.donem_adi_al()), bulunamayan


GUN_KISA = {"pazartesi": "Pzt", "sali": "Sal", "carsamba": "Çar", "persembe": "Per", "cuma": "Cum", "cumartesi": "Cmt", "pazar": "Paz"}


def _duz(x):
    """Etiketleri atar (<br> → satır sonu), HTML karakterlerini çözer, boşlukları sadeleştirir; satırları '\\n' ile döndürür."""
    x = re.sub(r"<br\s*/?>", "\n", x or "", flags=re.I)
    x = htmlmod.unescape(re.sub(r"<[^>]+>", " ", x))
    return "\n".join(s for s in (" ".join(l.split()) for l in x.split("\n")) if s)


def kayitlardan_hocalar(kayitlar, donem_adi):
    """Ders kayıtlarını doldur()'un beklediği hoca yapısına çevirir (Yeditepe yolundaki satır biçimiyle aynı)."""
    kn = _kn()
    sonuc = {}
    for k in kayitlar:
        satir = f"{donem_adi} · {k['kod']}-{k['sube']} {k.get('ad') or ''} · {k.get('saat') or ''}".replace(" ·  ", " · ").strip().replace(" · · ", " · ")
        satir = satir.rstrip(" ·")
        for h in k.get("hocalar") or []:
            ad = kn.tr_ad(" ".join(h.split()))
            if not ad:
                continue
            sonuc.setdefault(ad, {"satirlar": [], "kodlar": set(), "bolum": k.get("bolum") or ""})
            if satir not in sonuc[ad]["satirlar"]:
                sonuc[ad]["satirlar"].append(satir)
            sonuc[ad]["kodlar"].add(k["kod"].split()[0])
    return sonuc


def onbellekli(ad, uretici, saat=24):
    """JSON olarak önbellekten (ag_kaynak.ONBELLEK) ver; yoksa ya da eskiyse uretici()'yi çağır (bozuk sonucu yazma)."""
    kn = _kn()
    os.makedirs(kn.ONBELLEK, exist_ok=True)
    yol = os.path.join(kn.ONBELLEK, re.sub(r"[^A-Za-z0-9._-]", "_", ad) + ".json")
    if os.path.exists(yol) and time.time() - os.path.getmtime(yol) < saat * 3600:
        try:
            with open(yol, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    veri = uretici()
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(veri, f, ensure_ascii=False)
    return veri


def _tip(veri, tip, ne):
    """Uzak (ya da önbellekteki) JSON beklenen tipte değilse ValueError; liste ise öğeleri sözlük olmalı."""
    if not isinstance(veri, tip) or (tip is list and not all(isinstance(x, dict) for x in veri)):
        raise ValueError(f"beklenmeyen {ne} biçimi")
    return veri


def robots_ok(url):
    """robots.txt izin vermiyorsa False (ag_kesif.robots_izin: SSRF korumalı, süreç içinde önbellekli)."""
    import ag_kesif
    return ag_kesif.robots_izin(url)


def al(url, **kw):
    """Robots denetimli, SSRF korumalı GET/POST; metin döndürür."""
    if not robots_ok(url):
        raise OSError("robots.txt bu adrese izin vermiyor: " + url)
    ham, _ = _kn()._istek(url, **kw)
    return ham.decode("utf-8", "replace")


class Baglastirici:
    anahtar = ""
    ad = ""
    kisa = ""
    alan_adi = ""
    ders_kaynak = ""
    eposta_alani = ""
    etkinlik_url = ""
    kurum_en = ()      # OpenAlex kurum adı parçaları (küçük harf, İngilizce) → ag_akademik isim eşleşmesi
    harfli_sube = False

    def donem_adi_al(self):
        return getattr(self, "donem_adi", "")

    def kayit(self):
        """ag_kaynak.OKULLAR kaydı: açılır liste ve doldur() bu alanları kullanır."""
        return {"ad": self.ad, "kisa": self.kisa or self.ad, "ders_kaynak": self.ders_kaynak or self.alan_adi, "donem_adi": getattr(self, "donem_adi", "güncel dönem"),
                "tur": self.anahtar, "anahtar": self.anahtar, "alan_adi": self.alan_adi, "kadro": {}, "kadro_adi": {},
                "eposta_alani": self.eposta_alani, "etkinlik_url": self.etkinlik_url, "kurum_en": list(self.kurum_en)}

    def dersler(self, kodlar):
        raise NotImplementedError

    def hoca_profili(self, ad_veya_url):
        return {}

    def _coz(self, kodlar):
        kn = _kn()
        istenen, bulunamayan = [], []
        for d in kodlar:
            kod, sube = kn._ders_coz(d, self.harfli_sube)
            (istenen if kod else bulunamayan).append((kod, sube, d) if kod else d)
        return istenen, bulunamayan


# ---------- Yeditepe (ortak arayüz sarmalayıcısı; doldur() eski yolu kullanır) ----------
class YeditepeBaglastirici(Baglastirici):
    anahtar = "yeditepe"

    def kayit(self):
        return _kn().OKULLAR["yeditepe"]

    def donem_adi_al(self):
        return _kn().OKULLAR["yeditepe"]["donem_adi"]

    def dersler(self, kodlar):
        kn = _kn()
        veri = kn._ders_verisi()
        sonuc, bulunamayan = [], []
        for d in kodlar:
            kod, sube = kn._ders_coz(d)
            es = [x for x in veri if kod and x.get("code") == kod and (sube is None or str(x.get("section")) == sube)] if kod else []
            if not es:
                bulunamayan.append(d)
            for x in es:
                saat = ", ".join(f"{kn.GUN.get(m.get('day'), m.get('day'))} {m.get('startTime')}–{m.get('endTime')}" for m in x.get("meetings") or [])
                sonuc.append({"kod": kod, "sube": str(x.get("section")), "ad": x.get("name") or x.get("nameEn") or "",
                              "hocalar": [h for h in x.get("instructors") or []], "saat": saat, "bolum": x.get("departmentName") or ""})
        return sonuc, bulunamayan

    def hoca_profili(self, ad_veya_url):
        kn = _kn()
        if not str(ad_veya_url).startswith("http"):
            return {}
        p = kn.profil_oku(ad_veya_url)
        return {"orcid": p.get("orcid", ""), "alanlar": p.get("alanlar", []), "ozgecmis": p.get("ozgecmis", [])}


# ---------- İTÜ: herkese açık ders programı (obs.itu.edu.tr/public/DersProgram, JSON + HTML tablo) ----------
class ItuBaglastirici(Baglastirici):
    anahtar = "itu"
    ad = "İstanbul Teknik Üniversitesi"
    kisa = "İTÜ"
    alan_adi = "itu.edu.tr"
    ders_kaynak = "obs.itu.edu.tr"
    eposta_alani = "itu.edu.tr"
    etkinlik_url = ""
    kurum_en = ("istanbul technical university",)
    TABAN = "https://obs.itu.edu.tr/public/DersProgram"
    SEVIYELER = ("LS", "LU", "OL")   # lisans, lisansüstü, önlisans

    def donem_adi_al(self):
        try:
            donem = onbellekli("itu-donem", lambda: _tip(json.loads(al(self.TABAN + "/GetAktifDonemByProgramSeviye?programSeviyeTipiAnahtari=LS")), dict, "dönem yanıtı")
                               .get("aktifDonem") or "", 24)   # önbellek de uzak JSON gibi güvenilmez: tip denetlenir
            return donem if isinstance(donem, str) and donem else "İTÜ aktif dönem"
        except (OSError, ValueError):
            return "İTÜ aktif dönem"

    @staticmethod
    def satirlari_ayristir(sayfa):
        """DersProgramSearch HTML tablosu → [{crn, kod, ad, hocalar, saat, bolum?}]. Tablo biçimi: CRN, ders kodu, ad, yöntem, öğretim üyesi, bina, gün, saat, ..."""
        sonuc = []
        for tr in re.findall(r"<tr>(.*?)</tr>", sayfa.split("<tbody>", 1)[-1], re.S):
            td = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(td) < 9:
                continue
            crn, kod, ad, _, hoca, _, gun, saat = (_duz(x) for x in td[:8])
            kod = " ".join(kod.split())
            if not crn.isdigit() or not re.match(r"^[A-Z]{2,5} \d{3}[A-Z]?$", kod):
                continue
            gunler, saatler = gun.split("\n"), saat.split("\n")
            zaman = ", ".join(f"{GUN_KISA.get(_gun_anahtar(g), g)} {s.replace('/', '–')}" for g, s in zip(gunler, saatler) if g and g != "-")
            sonuc.append({"sube": crn, "kod": kod, "ad": ad, "hocalar": [h.strip() for h in hoca.split("\n") if h.strip() and h.strip() != "-"],
                          "saat": zaman, "bolum": ""})
        return sonuc

    def _branslar(self, seviye):
        return _tip(onbellekli(f"itu-brans-{seviye}", lambda: _tip(json.loads(al(f"{self.TABAN}/SearchBransKoduByProgramSeviye?programSeviyeTipiAnahtari={seviye}")), list, "branş listesi"),
                               24 * 7), list, "branş listesi")

    def _brans_dersleri(self, seviye, brans_id):
        donem = re.sub(r"\W+", "", self.donem_adi_al())
        return _tip(onbellekli(f"itu-{seviye}-{brans_id}-{donem}",
                               lambda: self.satirlari_ayristir(al(f"{self.TABAN}/DersProgramSearch?programSeviyeTipiAnahtari={seviye}&dersBransKoduId={int(brans_id)}")), 24),
                    list, "ders listesi")

    def dersler(self, kodlar):
        istenen, bulunamayan = self._coz(kodlar)
        sonuc = []
        for kod, sube, ham in istenen:
            onek = kod.split()[0]
            bulundu = False
            for seviye in self.SEVIYELER:
                brans = next((b.get("bransKoduId") for b in self._branslar(seviye) if b.get("dersBransKodu") == onek), None)
                if brans is None:
                    continue
                es = [x for x in self._brans_dersleri(seviye, brans) if x["kod"] == kod and (sube is None or x["sube"] == sube)]
                sonuc += es
                if es:
                    bulundu = True
                    break
            if not bulundu:
                bulunamayan.append(ham)
        return sonuc, bulunamayan


def _gun_anahtar(g):
    return g.lower().replace("ç", "c").replace("ş", "s").replace("ğ", "g").replace("ı", "i").replace("ö", "o").replace("ü", "u")


kaydet(YeditepeBaglastirici())
kaydet(ItuBaglastirici())
