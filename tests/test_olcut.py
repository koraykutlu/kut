"""Puan ölçütleri: ölçüt tablosu tam, asistan puan denetimi kuralları uyguluyor, köprü puanı kanal adlarını saymıyor."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_analiz as an  # noqa: E402
import ag_cekirdek as c  # noqa: E402


class OlcutTest(unittest.TestCase):
    def test_her_ozelligin_bantlari_0_10_araligini_bosluksuz_kapsar(self):
        for a, _, _ in c.OZELLIKLER:
            bantlar = c.OLCUTLER[a]["bantlar"]
            kapsanan = sorted(v for alt, ust, _ in bantlar for v in range(alt, ust + 1))
            self.assertEqual(kapsanan, list(range(11)), a)
            self.assertTrue(c.OLCUTLER[a]["kanit"] and c.OLCUTLER[a]["sayilmaz"], a)

    def test_bant_metni(self):
        self.assertIn("karar verici", c.olcut_bandi("etki", 7).lower())
        self.assertEqual(c.olcut_bandi("etki", 11), "")

    def test_istem_tum_ozellikleri_ve_kurallari_icerir(self):
        m = c.olcut_metni()
        for a, _, _ in c.OZELLIKLER:
            self.assertIn(a, m)
        self.assertIn("en çok 8", m)

    def test_kanitsiz_puan_duser(self):
        self.assertEqual(an.ozellik_denetle({"etki": 7, "destek": 5}, ["destek: ilanı paylaştı"]), {"destek": 5})

    def test_yedi_ustu_iki_kanit_ister(self):
        self.assertEqual(an.ozellik_denetle({"destek": 8}, ["destek: ilanı paylaştı"]), {"destek": 6})
        self.assertEqual(an.ozellik_denetle({"destek": 8}, ["destek: ilanı paylaştı", "Destek: tanıştırdı"]), {"destek": 8})

    def test_tek_kaynak_en_cok_sekiz(self):
        g = ["güvenilirlik: sözünü tuttu", "Güvenilirlik: zamanında döndü"]
        self.assertEqual(an.ozellik_denetle({"guvenilirlik": 10}, g), {"guvenilirlik": 8})
        self.assertEqual(an.ozellik_denetle({"guvenilirlik": 10}, g, tek_kaynak=False), {"guvenilirlik": 10})

    def test_bilinmeyen_anahtar_ve_sinir_disi(self):
        self.assertEqual(an.ozellik_denetle({"zeka": 9, "uyum": 15}, ["zeka: x", "uyum: a", "uyum: b"]), {"uyum": 8})

    def test_kopru_kanal_adlarini_saymaz(self):
        kanal = {"nereden": ["whatsapp", "rehber", "linkedin"], "yakinlik": 1}
        cevre = {"nereden": ["ytu-meta", "water-ai"], "yakinlik": 1}
        self.assertIsNone(c.iliski_puanlari(kanal, set(), [], date(2026, 10, 11))["kopru"])
        self.assertEqual(c.iliski_puanlari(cevre, set(), [], date(2026, 10, 11))["kopru"], 20)


if __name__ == "__main__":
    unittest.main()
