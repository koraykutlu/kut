"""Uzak modele (claude -p) giden verinin TEK kapısı. Bir kişinin verisi dışarı gidebilir mi?
Hayır: haric.md ile eşleşiyorsa (kurum/parti/rol) YA DA kişi notunda `remote_allowed: false` varsa; kişi dosyası yoksa/okunamıyorsa da hayır.
Alan hiç yoksa varsayılan EVET (Pusula ve sohbet ağın tamamını görsün; yalnız "görme" denenler kapalı).
Sohbet/strateji `--add-dir` ile gerçek veri klasörünü değil, bu kapıdan geçmiş geçici kopyayı görür (kopya()). Kopya dışında kalanlar:
reddedilen kişinin dosyası/fotoğrafı/belgesi/yorumu, ona (ya da sahibi belirsiz) ham WhatsApp sohbeti, haric.md, ag.html, arsiv/,
kilit/PIN/anahtar adlı dosyalar, sembolik bağ ve veri klasörü dışına çözülen her şey. Ortak dosyalarda (iliskiler, cikarimlar, kesif...)
reddedilen kişinin id'sini ya da adını içeren SATIRLAR atılır."""
import contextlib
import json
import os
import re
import shutil
import tempfile

import ag_cekirdek as c
import ag_ice_aktar as ia
import ag_sir

HAYIR = ("false", "hayir", "no", "0", "off")
METIN_UZANTI = {".md", ".txt", ".json", ".csv", ".tsv", ".yaml", ".yml", ".html", ".htm"}
HASSAS_AD = re.compile(r"kilit|(?<![a-z])pin(?![a-z])|(?<![a-z])ayar|settings|token|secret|sifre|parola|password|\.env|\.key|\.pem|credential|anahtar", re.I)
ATLANAN_DOSYA = {"haric.md", "ag.html"}


def _red_mi(alanlar, hl):
    return str(alanlar.get("remote_allowed", "")).strip().lower() in HAYIR or c.haric_mi(alanlar, hl)


class Kapi:
    """Anlık görüntü: veri klasöründeki kişiler ve hangilerinin dışarı gönderilemeyeceği."""

    def __init__(self):
        hl = c.haric_listesi()
        self.red, self.var = {}, set()
        if os.path.isdir(c.KISILER):
            for ad in os.listdir(c.KISILER):
                kid = ad.split(".")[0]
                if not ad.endswith(".md") or ad.startswith("_") or not kid:
                    continue
                self.var.add(kid)
                try:
                    k = c.kisi_oku(os.path.join(c.KISILER, ad))
                except (OSError, ValueError):
                    k = None
                if k is None or _red_mi(k, hl):   # okunamıyor / frontmatter yok → kapalı
                    self.red[kid] = k or {}
        adlar = [c.sade(k.get("ad") or "") for k in self.red.values()]
        for k in self.red.values():
            adlar += [c.sade(a) for a in c.liste_yap(k.get("aliases"))]
        self.adlar = [a for a in adlar if (len(a) >= 3 and " " in a) or len(a) >= 5]
        self._id = re.compile(r"(?<![\w-])(" + "|".join(re.escape(i) for i in self.red) + r")(?![\w-])", re.I) if self.red else None

    def acik_mi(self, kid):
        """Bu kişinin verisi dışarı gidebilir mi? (geçersiz id / dosyası yok → hayır)"""
        return bool(c.gecerli_id(kid)) and kid in self.var and kid not in self.red

    def izinli(self, k):
        return self.acik_mi(k.get("id"))

    def anilir_mi(self, metin):
        if not self.red:
            return False
        if self._id.search(metin or ""):
            return True
        s = " " + c.sade(metin) + " "
        return any(f" {a} " in s for a in self.adlar)

    def temizle(self, metin):
        """Reddedilen kişiyi anan satırları atar, sırları (anahtar/parola/token) gizler (ortak dosya/özet metinleri için)."""
        if metin and self.red:
            metin = "\n".join(l for l in metin.split("\n") if not self.anilir_mi(l))
        return ag_sir.temizle(metin, "kapı")


def _wa_sahipleri(kok):
    """Ham WhatsApp dosyası → ilişkili kişi id'leri: kişi notlarındaki dosya anmaları + analiz kuyruğu + aday havuzu."""
    wa = os.path.join(kok, "gelen", "whatsapp")
    sahip = {}
    if not os.path.isdir(wa):
        return sahip
    adlar = os.listdir(wa)
    for f in os.listdir(c.KISILER) if os.path.isdir(c.KISILER) else []:
        try:
            metin = open(os.path.join(c.KISILER, f), encoding="utf-8").read()
        except (OSError, ValueError):
            continue
        for a in adlar:
            if a in metin:
                sahip.setdefault(a, set()).add(f.split(".")[0])
    try:
        for j in json.load(open(os.path.join(ia.DEPO, "analiz", "durum.json"), encoding="utf-8")).get("isler", []):
            sahip.setdefault(os.path.basename(str(j.get("ham"))), set()).update(str(x) for x in j.get("kisiler") or [])
    except (OSError, ValueError, AttributeError):
        pass
    try:
        for a in ia.adaylar().values():
            for k in a.get("kaynaklar") or []:
                if a.get("kisi") and k.get("ham"):
                    sahip.setdefault(os.path.basename(str(k["ham"])), set()).add(a["kisi"])
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return sahip


def _gercek(yol, kok_gercek):
    """Sembolik bağ/junction değil ve gerçekten veri klasörünün içinde mi?"""
    if os.path.islink(yol):
        return False
    r = os.path.normcase(os.path.realpath(yol))
    beklenen = os.path.normcase(os.path.join(os.path.realpath(os.path.dirname(yol)), os.path.basename(yol)))
    return r == beklenen and r.startswith(kok_gercek + os.sep)


def _kopyala(kok, hedef, kapi):
    kok_g = os.path.normcase(os.path.realpath(kok))
    sahip = _wa_sahipleri(kok)
    for yol, dizinler, dosyalar in os.walk(kok, followlinks=False):
        goreli = os.path.relpath(yol, kok)
        parca = [] if goreli == "." else goreli.replace("\\", "/").split("/")
        dizinler[:] = [d for d in dizinler if _gercek(os.path.join(yol, d), kok_g) and not HASSAS_AD.search(d)
                       and not (not parca and d == "arsiv") and not (parca == ["belgeler"] and d in kapi.red)]
        for ad in dosyalar:
            tam, kid, ust = os.path.join(yol, ad), ad.split(".")[0], (parca[0] if parca else "")
            if (not parca and ad in ATLANAN_DOSYA) or ad.endswith(".eski") or HASSAS_AD.search(ad) or not _gercek(tam, kok_g):
                continue
            if len(parca) == 1 and kid in kapi.red and (ust == "foto" or ust == "yorumlar" or (ust == "kisiler" and not ad.startswith("_"))):
                continue
            wa = parca[:2] == ["gelen", "whatsapp"]
            if wa:
                k = sahip.get(ad)
                if not k or any(not kapi.acik_mi(x) for x in k):   # sahibi bilinmeyen sohbet de kapalı
                    continue
            h = os.path.join(hedef, *parca, ad)
            if os.path.splitext(ad)[1].lower() in METIN_UZANTI:
                try:
                    metin = open(tam, encoding="utf-8").read()
                except (OSError, ValueError):
                    continue
                if wa:
                    if kapi.anilir_mi(metin):   # sohbette reddedilen biri geçiyorsa (grup üyesi) tümü kapalı
                        continue
                    metin = ag_sir.temizle(metin, "kopya")   # ham dosya değişmez; modele giden kopyada sır yok
                else:
                    metin = kapi.temizle(metin)
                os.makedirs(os.path.dirname(h), exist_ok=True)
                with open(h, "w", encoding="utf-8", newline="\n") as f:
                    f.write(metin)
            else:
                os.makedirs(os.path.dirname(h), exist_ok=True)
                shutil.copyfile(tam, h)


@contextlib.contextmanager
def kopya(kok=None):
    """Süzülmüş geçici veri kopyasının yolunu verir (VERI dışında); çıkışta siler."""
    kok = kok or c.VERI
    ust = os.path.join(ia.DEPO, "gecici")
    try:
        os.makedirs(ust, exist_ok=True)
    except OSError:
        ust = None
    hedef = tempfile.mkdtemp(prefix="kut-", dir=ust)

    def sil(f, p, _):
        with contextlib.suppress(OSError):
            os.chmod(p, 0o700)
            f(p)
    try:
        _kopyala(kok, hedef, Kapi())
        yield hedef
    finally:
        shutil.rmtree(hedef, onerror=sil)
