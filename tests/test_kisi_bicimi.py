"""Kişi dosyası Beyin kişi notu biçiminde (beyin entegrasyonu): kind/title/facts türetilir, Kut alanları kaybolmaz."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import os
import sys
import tempfile
import unittest

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_cekirdek as c  # noqa: E402


class KisiBicimiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eski = c.KISILER
        c.KISILER = self.tmp.name

    def tearDown(self):
        c.KISILER = self.eski
        self.tmp.cleanup()

    def yaz_oku(self, alanlar, govde="# X\n\n## Kerem'le temas\n- (henüz yok)\n"):
        c.kisi_yaz("x", alanlar, govde)
        yol = os.path.join(self.tmp.name, "x.md")
        return open(yol, encoding="utf-8").read(), c.kisi_oku(yol)

    def test_turetilen_alanlar_yazilir_okunurken_atlanir(self):
        metin, k = self.yaz_oku({"ad": "Ayşe Yılmaz", "tur": "akademi", "kurum": "Örnek Ünv.", "rol": "Doçent",
                                 "son_temas": "2026-10-01", "aliases": ["Ayşe hoca"]})
        self.assertTrue(metin.startswith("---\nkind: person\ntitle: Ayşe Yılmaz\n"))
        self.assertIn("facts:\n  kurum: Örnek Ünv.\n  rol: Doçent\n  son_temas: 2026-10-01\n", metin)
        for t in c.TURETILEN:
            self.assertNotIn(t, k)
        self.assertEqual(k["aliases"], ["Ayşe hoca"])
        self.assertEqual(k["kurum"], "Örnek Ünv.")

    def test_ikinci_yazim_ayni_dosyayi_uretir(self):
        metin, k = self.yaz_oku({"ad": "Ali", "tur": "cevre", "kurum": "A"})
        govde = k.pop("govde")
        c.kisi_yaz("x", k, govde)
        self.assertEqual(open(os.path.join(self.tmp.name, "x.md"), encoding="utf-8").read(), metin)

    def test_degisen_kurum_factsi_gunceller(self):
        _, k = self.yaz_oku({"ad": "Ali", "tur": "cevre", "kurum": "Eski"})
        govde = k.pop("govde")
        k["kurum"] = "Yeni"
        c.kisi_yaz("x", k, govde)
        metin = open(os.path.join(self.tmp.name, "x.md"), encoding="utf-8").read()
        self.assertIn("  kurum: Yeni\n", metin)
        self.assertNotIn("Eski", metin)

    def test_bos_factsi_yazmaz(self):
        metin, _ = self.yaz_oku({"ad": "Ali", "tur": "cevre"})
        self.assertNotIn("facts:", metin)


if __name__ == "__main__":
    unittest.main()
