"""Bekçi: test koşusu gerçek %LOCALAPPDATA%\agim klasörüne yazmamalı. Yalnız yol karşılaştırır; gerçek klasörün içeriğini okumaz."""
import glob
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401

import os
import re
import sys
import unittest

KOK_DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK_DEPO, "kut"))
import ag_analiz as an  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_sunucu as s  # noqa: E402


def _altinda(yol, kok):
    a, k = os.path.normcase(os.path.abspath(yol)), os.path.normcase(os.path.abspath(kok))
    return a == k or a.startswith(k + os.sep)


class GercekKlasoreYazmaz(unittest.TestCase):
    def test_gecici_dizin_gercekten_ayri(self):
        self.assertTrue(_yalitim.GERCEK_DEPO)
        self.assertFalse(_altinda(_yalitim.KOK, _yalitim.GERCEK_DEPO))
        self.assertFalse(_altinda(_yalitim.GERCEK_DEPO, _yalitim.KOK))
        self.assertEqual(os.environ["LOCALAPPDATA"], _yalitim.LOCALAPPDATA)

    def test_depo_turevli_yollar_gecici_dizinde(self):
        yollar = {"ia.DEPO": ia.DEPO, "ia.AYARLAR": ia.AYARLAR, "ia.ADAYLAR": ia.ADAYLAR, "sunucu.GUNLUK": s.GUNLUK,
                  "sunucu.PROFIL": s.PROFIL, "an.KLASOR": an.KLASOR, "an.SOHBET_KLASOR": an.SOHBET_KLASOR,
                  "kaynak.DURUM": kn.DURUM, "kaynak.ONBELLEK": kn.ONBELLEK, "kesif.KLASOR": ks.KLASOR}
        for ad, yol in yollar.items():
            with self.subTest(ad):
                self.assertTrue(_altinda(yol, _yalitim.KOK), f"{ad} geçici dizin dışında")
                self.assertFalse(_altinda(yol, _yalitim.GERCEK_DEPO), f"{ad} gerçek klasörde")

    def test_ses_ve_guncelleme_yollari(self):
        import ag_ses_kur as sk
        self.assertTrue(_altinda(sk.klasor(), _yalitim.KOK))
        self.assertTrue(_altinda(os.path.join(ia.DEPO, "guncelleme.log"), _yalitim.KOK))

    def test_alt_surec_dosyalari_gecici_localappdata_verir(self):
        """Alt süreç başlatan her test dosyası env'e LOCALAPPDATA (geçici) ve AGIM_VERI vermeli (statik denetim)."""
        denetlenen = 0
        for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_*.py"))):
            kaynak = open(f, encoding="utf-8").read()
            if os.path.basename(f) == "test_yalitim.py":
                continue
            if re.search(r"subprocess\.Popen\(\s*\[\s*sys\.executable", kaynak):
                denetlenen += 1
                with self.subTest(os.path.basename(f)):
                    self.assertRegex(kaynak, r'"LOCALAPPDATA"\s*:\s*\w')
                    self.assertRegex(kaynak, r'"AGIM_VERI"\s*:')
        self.assertGreaterEqual(denetlenen, 6)

    def test_her_test_dosyasi_kutten_once_yalitimi_ice_aktarir(self):
        """Tek başına çalıştırılan (python -m unittest tests/test_x.py) her dosya da gerçek ayar klasörüne dokunmamalı:
        kut modülleri (ag_*, goc, surum) içe aktarılmadan ÖNCE `import _yalitim` satırı bulunmalı (statik denetim)."""
        for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_*.py"))):
            satirlar = open(f, encoding="utf-8").read().split("\n")
            yal = next((i for i, l in enumerate(satirlar) if re.match(r"\s*import _yalitim\b", l)), None)
            kut = next((i for i, l in enumerate(satirlar) if re.match(r"\s*(import|from)\s+(ag_\w+|goc|surum)\b", l)), None)
            with self.subTest(os.path.basename(f)):
                if kut is not None:
                    self.assertIsNotNone(yal, "kut içe aktarılıyor ama _yalitim içe aktarılmıyor")
                    self.assertLess(yal, kut, "_yalitim kut modüllerinden önce içe aktarılmalı")


if __name__ == "__main__":
    unittest.main()
