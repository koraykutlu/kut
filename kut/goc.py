"""Veri göçleri: bir sürüm veri biçimini değiştirirse buraya sıralı bir göç eklenir. Şimdilik hiç göç yok.

Kural: göç yalnız gerekliyse çalışır; önce veri klasörü `<veri>/arsiv/goc/` altına zip'lenir (silinmez). Veri sürümü ayarlarda
(`veri_surumu`, LOCALAPPDATA) tutulur, veri klasörüne yazılmaz. Kaydı olmayan kurulum 1.0.0 sayılır. Göçler tekrar çalışsa zarar vermemeli (idempotent).
MIGRASYONLAR: (hedef_surum, ad, fonksiyon(veri_klasoru)) üçlüleri, hedef sürüme göre artan sırada.
"""
import os
import zipfile
from datetime import datetime

import ag_ice_aktar as ia
import surum as sv

TABAN = "1.0.0"
MIGRASYONLAR = []


def kayitli_surum():
    return str(ia.ayarlar().get("veri_surumu") or TABAN)


def _damga(s):
    a = ia.ayarlar()
    if a.get("veri_surumu") != s:
        a["veri_surumu"] = s
        ia.ayar_yaz(a)


def bekleyenler(kayit=None, hedef=sv.SURUM):
    kayit = kayit or kayitli_surum()
    return [m for m in MIGRASYONLAR if sv.karsilastir(m[0], kayit) > 0 and sv.karsilastir(m[0], hedef) <= 0]


def yedekle(veri):
    """Veri klasörünü zip'ler (arsiv/goc hariç); yolu döndürür."""
    hedef_klasor = os.path.join(veri, "arsiv", "goc")
    os.makedirs(hedef_klasor, exist_ok=True)
    yol = os.path.join(hedef_klasor, f"{datetime.now():%Y%m%d-%H%M%S}-{kayitli_surum()}.zip")
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as z:
        for kok, klasorler, dosyalar in os.walk(veri):
            if os.path.normpath(kok) == os.path.normpath(hedef_klasor):
                klasorler[:] = []
                continue
            for d in dosyalar:
                tam = os.path.join(kok, d)
                z.write(tam, os.path.relpath(tam, veri))
    return yol


def calistir(veri, hedef=sv.SURUM):
    """Bekleyen göç varsa yedekleyip sırayla çalıştırır, her birinden sonra sürümü damgalar. Yoksa hiçbir şeye dokunmaz
    (yalnız sürüm kaydı güncellenir). Döner: çalışan göçlerin adları."""
    bekleyen = bekleyenler(hedef=hedef)
    if not bekleyen:
        if sv.karsilastir(kayitli_surum(), hedef) < 0:
            _damga(hedef)
        return []
    yedekle(veri)
    adlar = []
    for s, ad, f in sorted(bekleyen, key=lambda m: sv.ayristir(m[0])):
        f(veri)
        _damga(s)
        adlar.append(ad)
    _damga(hedef)
    return adlar
