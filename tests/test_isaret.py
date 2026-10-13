"""Kişi işaretleri her kurulumda aynı: fotoğrafsız kişi tür renginde dolu kare + baş harf (yuvarlak avatar yok).

Kök neden: demo verisi köşeleri şeffaf yuvarlak PNG avatarlar yazıyordu; haritada tür renkli karenin içinde daire görünüyordu.
Boş ayar/veri klasörüyle sayfa üretilir; tarayıcı açılmadan kod düzeyinde doğrulanır.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import os
import re
import struct
import sys
import tempfile
import unittest
import zlib

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(DEPO, "kut")
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.join(DEPO, "demo"))
import ag_cekirdek as c  # noqa: E402
import demo_veri as dv  # noqa: E402


def sablon():
    return open(os.path.join(KOK, "ag_sablon.html"), encoding="utf-8").read()


def png_alfa(ham):
    """RGBA 8 bit, süzgeçsiz (demo üreticisi) PNG'nin alfa kanalı değerleri."""
    assert ham[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", ham[16:24])
    idat = b""
    i = 8
    while i < len(ham):
        n = struct.unpack(">I", ham[i:i + 4])[0]
        if ham[i + 4:i + 8] == b"IDAT":
            idat += ham[i + 8:i + 8 + n]
        i += 12 + n
    d = zlib.decompress(idat)
    satir = 1 + w * 4
    return {d[y * satir + 1 + x * 4 + 3] for y in range(h) for x in range(w)}


class SablonIsaretTest(unittest.TestCase):
    def test_harita_dugumu_kare_ve_bas_harf_her_kisi_icin_cizilir(self):
        h = sablon()
        i = h.index('class: "govde-c"')
        blok = h[i:i + 1500]
        self.assertIn('el("rect"', h[i - 40:i])                      # gövde kare (rect), daire değil
        self.assertLess(blok.index('class: "bas"'), blok.index("if (k.foto)"))   # baş harf fotoğraftan bağımsız çizilir
        self.assertNotIn('el("circle", { class: "govde', h)
        self.assertNotRegex(h, r'el\("circle",\s*\{\s*r:\s*r\b')

    def test_kisi_avatarlari_kare(self):
        h = sablon()
        # Kut kimlik bloğu temel yuvarlak avatarı kare yapar ve sonra gelir (kaynak sırası)
        temel = h.index(".avatar img,.avatar .harf{position:absolute")
        kare = h.index(".avatar img,.avatar .harf{border-radius:2px")
        self.assertGreater(kare, temel)
        self.assertGreater(h.index(".liste .mav,td .mini,#foto-on,#fb-on{border-radius:2px"), h.index(".liste .mav{width:30px"))
        # yuvarlak yedek yok: JS'te arc/ellipse ile kişi işareti çizilmez
        self.assertNotRegex(h, r"\.arc\(|\"ellipse\"")

    def test_tema_ve_palet_ayara_bagli_degil(self):
        h = sablon()
        self.assertIn('PALET = "kut"', h)
        self.assertNotIn("ayarlar.json", h)
        # tür rengi her türde var ve tanımsız tür sözlük dışına düşmez
        for t in ("ben", "yakin", "cevre", "akademi", "is", "finans", "siyaset", "etkinlik"):
            self.assertRegex(h, rf"\b{t}: \"#[0-9A-Fa-f]{{6}}\"")

    def test_fotografsiz_avatar_tur_renginde(self):
        h = sablon()
        self.assertIn('`<span class="${sinif}" style="background:${T[k.tur][1]}">${esc(harf(k.ad))}</span>`', h)
        self.assertIn('style="background:${T[k.tur][1]}"', h)   # fotoğraflı liste avatarı: şeffaf köşede tür rengi


class DemoVeriTest(unittest.TestCase):
    def test_demo_avatari_opak_kare(self):
        self.assertEqual(png_alfa(dv.avatar("Ali Veli", (200, 100, 50))), {255})

    def test_yeni_kurulum_sayfasi_fotografsiz_kisi_icerir_ve_yuvarlak_foto_yok(self):
        eski = (c.VERI, c.KISILER, c.FOTO)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                c.veri_klasoru(tmp)
                c.kisi_yaz("ali", {"ad": "Ali Veli", "tur": "akademi", "yakinlik": "1"}, "# Ali\n")
                c.kisi_yaz("tursuz", {"ad": "Tür Suz", "tur": "", "yakinlik": "1"}, "# T\n")
                html = c.sayfa(c.veri_hazirla([]))
            finally:
                c.veri_klasoru(eski[0])
        self.assertNotIn("/*VERI*/null", html)
        for k in re.findall(r'"id":\s*"(ali|tursuz)"', html):
            self.assertTrue(k)
        self.assertIn("harf(k.ad)", html)
        self.assertNotIn('"foto": "data:', html)   # yeni kurulumda gömülü fotoğraf yok


if __name__ == "__main__":
    unittest.main()
