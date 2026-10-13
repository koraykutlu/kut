import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_ice_aktar as ia  # noqa: E402
import ag_kesif as ks  # noqa: E402


class VekilpediaAyarTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.kl = os.path.join(self.d.name, "kesif")
        self.ayar = os.path.join(self.d.name, "ayarlar.json")
        for p in (mock.patch.object(ks, "KLASOR", self.kl), mock.patch.object(ia, "AYARLAR", self.ayar),
                  mock.patch.object(ia, "DEPO", self.d.name)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.d.cleanup()

    def _csv(self):
        v = os.path.join(self.kl, "vekilpedia")
        os.makedirs(v)
        open(os.path.join(v, "milletvekilleri.csv"), "w").close()

    def _ayar(self, deger):
        with open(self.ayar, "w", encoding="utf-8") as f:
            json.dump({"kesif": {"vekilpedia": deger}}, f)

    def _indirme(self, zorla=True):
        with mock.patch.object(ks, "_istek", side_effect=AssertionError("ağ çağrıldı")) as m, \
                mock.patch.object(ks, "robots_izin", return_value=True):
            try:
                ks.vekil_verisi_yenile(zorla)
            except AssertionError:
                return True
            return m.called

    def test_taze_kurulum_kapali_ve_ag_yok(self):
        self.assertFalse(ks.vekilpedia_acik())
        self.assertFalse(self._indirme())

    def test_eski_csv_varsa_acik(self):
        self._csv()
        self.assertTrue(ks.vekilpedia_acik())
        self.assertTrue(self._indirme())

    def test_acik_false_csv_olsa_da_kapali(self):
        self._csv()
        self._ayar(False)
        self.assertFalse(ks.vekilpedia_acik())
        self.assertFalse(self._indirme())

    def test_acik_true_taze_kurulumda_acik(self):
        self._ayar(True)
        self.assertTrue(ks.vekilpedia_acik())
        self.assertTrue(self._indirme())

    def test_ayarla_ve_veri_yok_notu(self):
        ks.vekilpedia_ayarla(True)
        self.assertTrue(ks.vekilpedia_acik())
        ks.vekilpedia_ayarla(False)
        self.assertFalse(ks.vekilpedia_acik())
        with mock.patch.object(ks, "vekil_klasoru", return_value=os.path.join(self.kl, "vekilpedia")):
            s = ks.vekil_adaylari([], bekle=False)
        self.assertTrue(s["veri_yok"] and s["kapali"])


if __name__ == "__main__":
    unittest.main()
