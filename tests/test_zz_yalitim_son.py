"""Son bekçi: dosya adı sıralaması en sona düşer. Tam koşunun sonunda c.VERI geçici kök altında olmalı; kayarsa (bir test veri_klasoru'nu
geri yüklemeyi atlamışsa) sonraki testler ve depo içindeki gerçek veri/ tehlikeye girer. Yalnız yol karşılaştırır."""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402


class VeriKlasoruSonDurum(unittest.TestCase):
    def test_c_veri_gecici_kok_altinda_ve_baslangicta_ayni(self):
        kok = os.path.normcase(os.path.abspath(_yalitim.VERI))
        self.assertEqual(os.path.normcase(os.path.abspath(c.VERI)), kok, "c.VERI kaymış: bir test veri_klasoru'nu geri yüklemedi")
        self.assertTrue(os.path.normcase(os.path.abspath(c.VERI)).startswith(os.path.normcase(_yalitim.KOK) + os.sep))


if __name__ == "__main__":
    unittest.main()
